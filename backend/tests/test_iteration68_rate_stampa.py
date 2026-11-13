# Iteration 68: multiple installments (rate) shown in invoice print + courtesy PDF ("Scadenze di pagamento"), single scadenza fallback,
# layout campi.scadenza off hides them, XML DettaglioPagamento one per rata (TP01 if >1).
# Run: pytest tests/test_iteration68_rate_stampa.py -v -n 0   (T68_KEEP=1 keeps data for UI test; then `python tests/test_iteration68_rate_stampa.py clean`)
import io
import os
import re
import subprocess
import sys
from datetime import date, timedelta

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
T = date.today()
UID, TOK = "test-user-t68-admin", "test_session_t68_admin"
S = {}
COLLS = ["invoices", "parties", "payments", "coa_entries", "coa_accounts", "coa_causali", "coa_iva", "sdi_events", "audit", "com_log", "export_log"]


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


def piva(b):
    s = 0
    for i, ch in enumerate(b):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            d = d - 9 if d > 9 else d
        s += d
    return b + str((10 - s % 10) % 10)


def sess():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    if S.get("cid"):
        s.headers["X-Company-Id"] = S["cid"]
    return s


def clean():
    colls = "[" + ",".join(f'"{c}"' for c in COLLS) + "]"
    mongo(f'db.companies.find({{denominazione:/^TEST_T68/}}).forEach(c=>{{{colls}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def pdf_text(b):
    from pypdf import PdfReader
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(b)).pages)


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t68@example.com", name:"TEST_t68", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    co = piva("0987123468")
    r = sess().post(f"{API}/companies", json={"denominazione": "TEST_T68 Rate Srl", "partita_iva": co, "codice_fiscale": co, "regime_fiscale": "RF01",
                                              "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT",
                                              "iban": "IT60X0542811101000000123456"})
    assert r.status_code == 200, r.text
    S["cid"] = r.json()["id"]
    pv = piva("0123456768")
    r = sess().post(f"{API}/parties", json={"tipo": "cliente", "denominazione": "TEST_T68 Cliente Srl", "partita_iva": pv, "codice_fiscale": pv,
                                            "codice_destinatario": "ABC1234", "email": "cli68@example.com", "indirizzo": "Via X 1", "cap": "20100",
                                            "comune": "Milano", "provincia": "MI", "nazione": "IT"})
    assert r.status_code == 200, r.text
    S["party"] = r.json()["id"]
    yield
    if not os.environ.get("T68_KEEP"):
        clean()
    else:
        print("\nKEEP", S)


def base(**kw):
    b = {"tipo_documento": "TD01", "data": T.isoformat(), "party_id": S["party"], "modalita_pagamento": "MP05",
         "lines": [{"descrizione": "TEST_T68 riga", "quantita": 1, "prezzo_unitario": 300, "aliquota": 22}]}
    b.update(kw)
    return b


D = lambda n: (T + timedelta(days=n)).isoformat()  # noqa: E731
RATE3 = [{"scadenza": D(90), "importo": 122}, {"scadenza": D(30), "importo": 122}, {"scadenza": D(60), "importo": 122}]  # unsorted on purpose


def test_create_invoices():
    s = sess()
    r = s.post(f"{API}/invoices", json=base(rate=RATE3))
    assert r.status_code == 200, r.text
    d = r.json()
    S["i3"] = d["id"]
    assert [x["scadenza"] for x in d["rate"]] == [D(30), D(60), D(90)] and d["scadenza"] == D(90)
    r = s.post(f"{API}/invoices", json=base(rate=[{"scadenza": D(20), "importo": 200}, {"scadenza": D(50), "importo": 166}]))
    assert r.status_code == 200, r.text
    S["i2"] = r.json()["id"]
    r = s.post(f"{API}/invoices", json=base(scadenza=D(45)))
    assert r.status_code == 200, r.text
    S["i1"] = r.json()["id"]
    assert r.json()["scadenza"] == D(45)
    r = s.post(f"{API}/invoices", json=base(rate=[{"scadenza": D(40), "importo": 366}]))
    assert r.status_code == 200, r.text
    S["i1r"] = r.json()["id"]
    # persisted
    g = s.get(f"{API}/invoices/{S['i3']}").json()
    assert len(g["rate"]) == 3 and round(sum(x["importo"] for x in g["rate"]), 2) == g["netto"] == 366


def test_rate_sum_mismatch_422():
    r = sess().post(f"{API}/invoices", json=base(rate=[{"scadenza": D(20), "importo": 100}, {"scadenza": D(50), "importo": 100}]))
    assert r.status_code == 422, r.text


def test_xml_dettaglio_per_rata():
    s = sess()
    x = s.get(f"{API}/invoices/{S['i3']}/xml").text
    assert x.count("<DettaglioPagamento>") == 3 and "<CondizioniPagamento>TP01" in x
    for dt in (D(30), D(60), D(90)):
        assert f"<DataScadenzaPagamento>{dt}</DataScadenzaPagamento>" in x
    x = s.get(f"{API}/invoices/{S['i1']}/xml").text
    assert x.count("<DettaglioPagamento>") == 1 and "<CondizioniPagamento>TP02" in x and D(45) in x
    x = s.get(f"{API}/invoices/{S['i1r']}/xml").text
    assert x.count("<DettaglioPagamento>") == 1 and "TP02" in x


def _comp():
    c = sess().get(f"{API}/company").json()
    c["layout"] = sess().get(f"{API}/company/layout").json()
    return c


def _itd(s):
    y, m, d = s.split("-")
    return f"{d}/{m}/{y}"


def test_courtesy_pdf_multi_rate():
    from export_comm import courtesy_pdf
    inv = sess().get(f"{API}/invoices/{S['i3']}").json()
    b = courtesy_pdf(_comp(), inv["cliente"], inv)
    open("/tmp/t68_rate3.pdf", "wb").write(b)
    txt = pdf_text(b)
    print(txt)
    assert "Scadenze di pagamento" in txt and "<b>" not in txt
    assert "Scadenza pagamento:" not in txt
    for i, dt in enumerate((D(30), D(60), D(90)), 1):
        assert f"{i}/3" in txt and _itd(dt) in txt
    assert txt.count("122,00") >= 3


def test_courtesy_pdf_single():
    from export_comm import courtesy_pdf
    for k in ("i1", "i1r"):
        inv = sess().get(f"{API}/invoices/{S[k]}").json()
        txt = pdf_text(courtesy_pdf(_comp(), inv["cliente"], inv))
        assert "Scadenze di pagamento" not in txt
        assert f"Scadenza pagamento: {_itd(inv['scadenza'])}" in txt, k


def test_layout_scadenza_off_hides():
    from export_comm import courtesy_pdf
    s = sess()
    lay = s.get(f"{API}/company/layout").json()
    lay["campi"]["scadenza"] = False
    assert s.put(f"{API}/company/layout", json=lay).status_code == 200
    try:
        for k in ("i3", "i1"):
            inv = s.get(f"{API}/invoices/{S[k]}").json()
            txt = pdf_text(courtesy_pdf(_comp(), inv["cliente"], inv))
            assert "Scadenze di pagamento" not in txt and "Scadenza pagamento" not in txt, k
    finally:
        lay["campi"]["scadenza"] = True
        assert s.put(f"{API}/company/layout", json=lay).status_code == 200


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "clean":
    clean()
    print("cleaned")

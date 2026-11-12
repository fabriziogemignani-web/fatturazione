# Iteration 61: F24 bolli trimestrale GET /api/bolli/f24 (PDF, codice 2521-2524, anno, importo = report trimestre, CF/denominazione,
# banca predefinita, scadenza lavorativa, nota bolli), 400 trimestre vuoto, 422, isolamento, 403 modulo/menu off,
# regressione F24 IVA (liquidazione-iva) and ritenute nota default. Run: pytest tests/test_iteration61_bolli_f24.py -v -n 0
# UI fixtures: T61_RUN=123456 python tests/test_iteration61_bolli_f24.py setup|clean
import io
import json
import os
import random
import sys
from datetime import date

import pytest
import requests
from pypdf import PdfReader

from test_iteration7_pa_scartate_registro import API, mongo

RUN = os.environ.get("T61_RUN") or str(random.randint(100000, 999999))
TOK, UID = f"test_session_t61_admin_{RUN}", f"test-user-t61-admin-{RUN}"
TOK_OP, UID_OP = f"test_session_t61_op_{RUN}", f"test-user-t61-op-{RUN}"
PIVA, PIVA2, CF = "87" + RUN + "611", "87" + RUN + "612", "97" + RUN + "619"
T = date.today()
Y = T.year
Q = (T.month - 1) // 3 + 1
COLLS = ["invoices", "passive_invoices", "parties", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "partite_aperte", "comunicazioni", "f24_versamenti"]
ST = {}
ON = {"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True, "corrispettivi": True, "contabilita": True}
IBAN = "IT60X0542811101000000123456"


def sess(tok=TOK, cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    if cid or ST.get("cid"):
        s.headers["X-Company-Id"] = cid or ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{partita_iva:{{$in:["{PIVA}","{PIVA2}"]}}}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:["{UID}","{UID_OP}"]}}}}); db.user_sessions.deleteMany({{user_id:{{$in:["{UID}","{UID_OP}"]}}}});')


def company(name, piva, cf, banche):
    r = sess(cid="").post(f"{API}/companies", json={"denominazione": name, "partita_iva": piva, "codice_fiscale": cf, "regime_fiscale": "RF01",
                                                   "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT",
                                                   "banche": banche})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    assert sess(cid=cid).put(f"{API}/companies/{cid}/moduli", json=ON).status_code == 200
    return cid


def party(name, piva, cid=None):
    r = sess(cid=cid).post(f"{API}/parties", json={"tipo": "cliente", "denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "codice_destinatario": "ABC1234",
                                                   "indirizzo": "Via Milano 2", "cap": "20100", "comune": "Milano", "provincia": "MI"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def ln(desc, prezzo, natura="N2.1"):
    return {"descrizione": desc, "quantita": 1, "prezzo_unitario": prezzo, "aliquota": 0, "natura": natura}


def inv(party_id, lines, cid=None):
    r = sess(cid=cid).post(f"{API}/invoices", json={"tipo_documento": "TD01", "data": T.isoformat(), "party_id": party_id, "lines": lines})
    assert r.status_code == 200, r.text
    return r.json()


def ins(i, anno, data, status="consegnata", cid=None):
    mongo(f'db.invoices.insertOne({{id:"t61-{RUN}-{i}", company_id:"{cid or ST["cid"]}", anno:{anno}, data:"{data}", numero:{900 + i}, numero_display:"TEST_T61 X-{i}", sezionale:"X",'
          f'tipo_documento:"TD01", status:"{status}", bollo_virtuale:true, bollo_importo:2, bollo_addebitato:false, bollo_esenti:100, totale:100, cliente:{{denominazione:"TEST_T61 cli"}}}})')


def setup_data():
    clean()
    for uid, tok, role in ((UID, TOK, "admin"), (UID_OP, TOK_OP, "operatore")):
        mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.t61.{uid}@example.com", name:"TEST_T61 {role}", picture:"", role:"{role}", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
              f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    ST["cid"] = company(f"TEST_T61 Bolli {RUN} Srl", PIVA, CF, [{"nome": "Banca Secondaria", "iban": "IT52X0306909606100000063529", "predefinita": False},
                                                              {"nome": "Banca Predefinita T61", "iban": IBAN, "abi": "05428", "cab": "11101", "predefinita": True}])
    ST["cid2"] = company(f"TEST_T61 Altra {RUN} Srl", PIVA2, PIVA2, [])
    mongo(f'db.users.updateOne({{user_id:"{UID_OP}"}}, {{$set:{{company_ids:["{ST["cid"]}"]}}}})')
    ST["c"] = party("TEST_T61 Cliente", "0" + RUN + "6111")
    ST["c2"] = party("TEST_T61 Cliente2", "0" + RUN + "6112", ST["cid2"])
    # current quarter: 2 sent invoices + 1 draft (API)
    for k in range(2):
        j = inv(ST["c"], [ln(f"TEST_T61 esente {k}", 100 + k)])
        assert j["bollo_virtuale"] is True
        assert sess().post(f"{API}/invoices/{j['id']}/send").status_code == 200
    ST["draft"] = inv(ST["c"], [ln("TEST_T61 bozza", 150)])["id"]
    # other company: same quarter, 1 sent
    j = inv(ST["c2"], [ln("TEST_T61 altra", 200)], cid=ST["cid2"])
    sess(cid=ST["cid2"]).post(f"{API}/invoices/{j['id']}/send")
    # previous year Q4 (scadenza Y-02-28) and previous year Q2 (Y-1-09-30) + a scartata in Q2
    ins(1, Y - 1, f"{Y - 1}-11-10")
    ins(2, Y - 1, f"{Y - 1}-12-10")
    ins(3, Y - 1, f"{Y - 1}-12-11", status="scartata")
    ins(4, Y - 1, f"{Y - 1}-05-10")
    ins(5, Y - 1, f"{Y - 1}-03-10", status="bozza")  # Q1 Y-1 only draft -> empty
    return ST


@pytest.fixture(scope="module", autouse=True)
def setup():
    setup_data()
    yield
    clean()


def pdf_text(r):
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)


def lav(d):
    from datetime import timedelta
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def itd(d):
    return d.strftime("%d/%m/%Y")


# F24 bolli PDF
class TestBolliF24:
    def test_01_current_quarter_pdf(self):
        rep = sess().get(f"{API}/bolli", params={"anno": Y}).json()
        q = rep["trimestri"][Q - 1]
        assert q["importo"] == 4 and q["n"] == 2, q
        r = sess().get(f"{API}/bolli/f24", params={"anno": Y, "trimestre": Q})
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/pdf")
        assert f'F24_bolli_{Y}_T{Q}.pdf' in r.headers["content-disposition"] and "attachment" in r.headers["content-disposition"]
        assert r.content[:4] == b"%PDF"
        tx = pdf_text(r)
        ST["tx"] = tx
        assert f"252{Q}" in tx and str(Y) in tx and "4,00" in tx
        assert CF in tx and f"TEST_T61 Bolli {RUN} Srl" in tx
        assert "Banca Predefinita T61" in tx and "Banca Secondaria" not in tx and IBAN in tx and "05428" in tx
        scad = lav(date.fromisoformat(q["scadenza"]))
        assert itd(scad) in tx
        assert "Imposta di bollo" in tx and "liquidazione IVA" not in tx
        assert "2 documenti" in tx

    def test_02_prev_year_q4_scadenza_working_day(self):
        rep = sess().get(f"{API}/bolli", params={"anno": Y - 1}).json()
        q4 = rep["trimestri"][3]
        assert q4["importo"] == 4 and q4["n"] == 2, q4  # scartata excluded
        r = sess().get(f"{API}/bolli/f24", params={"anno": Y - 1, "trimestre": 4})
        assert r.status_code == 200, r.text
        tx = pdf_text(r)
        assert "2524" in tx and str(Y - 1) in tx and "4,00" in tx
        exp = lav(date(Y, 2, 28))
        assert itd(exp) in tx, (exp, tx[-800:])
        q2 = sess().get(f"{API}/bolli/f24", params={"anno": Y - 1, "trimestre": 2})
        assert q2.status_code == 200
        t2 = pdf_text(q2)
        assert "2522" in t2 and "2,00" in t2 and itd(lav(date(Y - 1, 9, 30))) in t2

    def test_03_empty_quarter_400(self):
        r = sess().get(f"{API}/bolli/f24", params={"anno": Y - 1, "trimestre": 1})  # only draft
        assert r.status_code == 400
        assert "Nessun bollo" in r.json()["detail"]
        r = sess().get(f"{API}/bolli/f24", params={"anno": Y - 1, "trimestre": 3})
        assert r.status_code == 400

    def test_04_validation(self):
        for p in ({"anno": Y, "trimestre": 0}, {"anno": Y, "trimestre": 5}, {"anno": 1990, "trimestre": 1}, {"anno": Y}, {"trimestre": 1}):
            assert sess().get(f"{API}/bolli/f24", params=p).status_code == 422, p

    def test_05_isolation(self):
        r = sess(cid=ST["cid2"]).get(f"{API}/bolli/f24", params={"anno": Y, "trimestre": Q})
        assert r.status_code == 200
        tx = pdf_text(r)
        assert "2,00" in tx and f"TEST_T61 Altra {RUN} Srl" in tx and "1 documenti" in tx
        # cid2 has no previous-year bolli
        assert sess(cid=ST["cid2"]).get(f"{API}/bolli/f24", params={"anno": Y - 1, "trimestre": 4}).status_code == 400
        # operatore not member of cid2
        assert sess(TOK_OP, cid=ST["cid2"]).get(f"{API}/bolli/f24", params={"anno": Y, "trimestre": Q}).status_code in (403, 404)
        assert sess(TOK_OP).get(f"{API}/bolli/f24", params={"anno": Y, "trimestre": Q}).status_code == 200

    def test_06_module_menu_off(self):
        u = f"{API}/companies/{ST['cid']}/moduli"
        sess().put(u, json={**ON, "fatture_attive": False})
        try:
            assert sess().get(f"{API}/bolli/f24", params={"anno": Y, "trimestre": Q}).status_code == 403
        finally:
            sess().put(u, json=ON)
        m = f"{API}/companies/{ST['cid']}/menu"
        assert sess().put(m, json={"off": ["bolli-virtuali"]}).status_code == 200
        try:
            assert sess().get(f"{API}/bolli/f24", params={"anno": Y, "trimestre": Q}).status_code == 403
        finally:
            sess().put(m, json={"off": []})
        assert sess().get(f"{API}/bolli/f24", params={"anno": Y, "trimestre": Q}).status_code == 200

    def test_07_no_bank_company(self):
        # cid2 has no banks -> still renders
        r = sess(cid=ST["cid2"]).get(f"{API}/bolli/f24", params={"anno": Y, "trimestre": Q})
        assert r.status_code == 200 and r.content[:4] == b"%PDF"


# Regression: other F24 builders keep default note
class TestF24Regression:
    def test_01_build_pdf_default_note(self):
        sys.path.insert(0, "/app/backend")
        import f24
        pdf = f24.build_pdf({"denominazione": "X", "codice_fiscale": "1"}, {}, {"codice": "6011", "descrizione": "IVA", "anno_riferimento": 2026,
                                                                              "importo": 10, "scadenza": "2026-02-16"}, [], "2026-02-16")
        tx = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
        assert "liquidazione IVA" in tx and "16/02/2026" in tx

    def test_02_liquidazione_iva_f24(self):
        r = sess().get(f"{API}/liquidazione-iva/f24", params={"anno": Y, "periodicita": "mensile", "periodo": 1})
        assert r.status_code in (200, 400), r.text  # no IVA in test company -> 400 'nessuna IVA da versare'
        r = sess().post(f"{API}/liquidazione-iva/f24", json={"anno": Y, "periodicita": "mensile", "periodo": 1, "data_versamento": f"{Y}-02-16"})
        assert r.status_code in (200, 400), r.text
        if r.status_code == 200:
            assert r.content[:4] == b"%PDF" and "liquidazione IVA" in "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)


if __name__ == "__main__":
    if sys.argv[1] == "setup":
        print(json.dumps({**setup_data(), "tok": TOK}))
    else:
        clean()

# Iteration 83: Ratei e risconti PDF print (GET /api/contabilita/ratei/pdf?anno=) - content, quota filter by year, riepilogo per tipo,
# contabilizzato in definitiva column, totals attivi/passivi, empty year, tenant isolation, auth/company requirements.
# Run: pytest tests/test_iteration83_ratei_pdf.py -v -n 0   (T83_KEEP=1 keeps data; `python tests/<file> clean`)
import json
import os
import random
import sys

import pymupdf
import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

RUN = os.environ.get("T83_RUN") or str(random.randint(100000, 999999))
TOK, UID = "test_session_t83_admin", "test-user-t83-admin"
TOK_OP, UID_OP = "test_session_t83_op", "test-user-t83-op"
ST = {}
COLLS = ["invoices", "passive_invoices", "parties", "articles", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "partite_aperte", "ratei_risconti", "coa_chiusure", "counters"]


def sess(cid=None, tok=TOK):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    c = cid if cid is not None else ST.get("A")
    if c:
        s.headers["X-Company-Id"] = c
    return s


def clean():
    mongo(f'db.companies.find({{denominazione:/^TEST_T83/}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:["{UID}","{UID_OP}"]}}}}); db.user_sessions.deleteMany({{user_id:{{$in:["{UID}","{UID_OP}"]}}}});')


def mk_company(tag, piva):
    r = sess("").post(f"{API}/companies", json={"denominazione": f"TEST_T83 {tag} {RUN} Srl", "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01",
                                               "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    sess(cid).put(f"{API}/companies/{cid}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                         "corrispettivi": True, "contabilita": True})
    sess(cid).get(f"{API}/contabilita/conti")
    return cid


def party(cid, tipo, name, piva):
    r = sess(cid).post(f"{API}/parties", json={"tipo": tipo, "denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "codice_destinatario": "ABC1234",
                                              "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT", "ratei_risconti": True})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def conto(cid, kind):
    rx = "^40\\\\.01" if kind == "ricavo" else "^(30|50)"
    out = mongo(f'print(JSON.stringify(db.coa_accounts.find({{company_id:"{cid}", livello:3, codice:{{$regex:"{rx}"}}}},{{_id:0,codice:1,descrizione:1}}).limit(1).toArray()))')
    return json.loads(out)[0]


def manual(cid, **kw):
    r = sess(cid).post(f"{API}/contabilita/ratei", json=kw)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def pdf_text(anno, cid=None):
    r = sess(cid).get(f"{API}/contabilita/ratei/pdf", params={"anno": anno})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/pdf")
    assert f'filename="Ratei_risconti_{anno}.pdf"' in r.headers.get("content-disposition", "")
    assert r.content[:4] == b"%PDF"
    doc = pymupdf.open(stream=r.content, filetype="pdf")
    return "\n".join(p.get_text() for p in doc)


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t83.admin@example.com", name:"TEST_T83 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    ST["A"] = mk_company("Alfa", "83" + RUN + "831")
    ST["B"] = mk_company("Beta", "84" + RUN + "841")
    a, b = ST["A"], ST["B"]
    ST["costo"], ST["ricavo"] = conto(a, "costo"), conto(a, "ricavo")
    F = party(a, "fornitore", "TEST_T83 Fornitore Affitti", "01234567890")
    C = party(a, "cliente", "TEST_T83 Cliente Canoni", "02345670481")
    FB = party(b, "fornitore", "TEST_T83 Fornitore BETA SEGRETO", "09876543217")
    ST["R1"] = manual(a, origine="acquisto", party_id=F, documento="T83-RISC-1", data_documento="2026-10-01", data_registrazione="2026-10-01",
                      competenza_dal="2026-10-01", competenza_al="2027-09-30", tipo="risconto", righe=[{"conto": ST["costo"]["codice"], "importo": 1200}])
    ST["R2"] = manual(a, origine="vendita", party_id=C, documento="T83-RAT-2", data_documento="2027-01-15", data_registrazione="2027-01-15",
                      competenza_dal="2026-07-01", competenza_al="2026-12-31", tipo="rateo", righe=[{"conto": ST["ricavo"]["codice"], "importo": 500}])
    ST["R3"] = manual(a, origine="acquisto", party_id=F, documento="T83-OLD-3", data_documento="2024-10-01", data_registrazione="2024-10-01",
                      competenza_dal="2024-10-01", competenza_al="2025-03-31", tipo="risconto", righe=[{"conto": ST["costo"]["codice"], "importo": 365}])
    cb = conto(b, "costo")["codice"]
    ST["RB"] = manual(b, origine="acquisto", party_id=FB, documento="T83-BETA-X", data_documento="2026-10-01", data_registrazione="2026-10-01",
                      competenza_dal="2026-10-01", competenza_al="2027-09-30", tipo="risconto", righe=[{"conto": cb, "importo": 7777}])
    yield
    if os.environ.get("T83_KEEP"):
        print("\nKEEP", RUN, ST["A"], ST["B"])
    else:
        clean()


# PDF content and amounts
class TestPdf:
    def test_01_content_2026(self):
        t = pdf_text(2026)
        ST["t26"] = t
        assert "Prospetto ratei e risconti al 31/12/2026" in t
        assert f"TEST_T83 Alfa {RUN} Srl" in t
        assert "T83-RISC-1" in t and "T83-RAT-2" in t
        assert "T83-OLD-3" not in t  # no quota in 2026
        assert "TEST_T83 Fornitore Affitti" in t and "TEST_T83 Cliente Canoni" in t
        assert "Risconto attivo" in t and "Rateo attivo" in t
        assert "897,53" in t and "1.200,00" in t and "273/365" in t
        assert "500,00" in t and "184/184" in t
        assert "01/10/2026" in t and "30/09/2027" in t
        assert ST["costo"]["codice"] in t and ST["ricavo"]["codice"] in t

    def test_02_riepilogo_and_totals(self):
        t = ST["t26"]
        assert "Riepilogo per tipo" in t and "Conto di stato patrimoniale" in t
        assert "Totale ratei e risconti attivi" in t and "Totale ratei e risconti passivi" in t
        assert "1.397,53" in t  # 897.53 + 500
        assert "Da contabilizzare" in t and "provvisorio" in t

    def test_03_isolation(self):
        t = ST["t26"]
        assert "BETA" not in t and "7.777" not in t and "T83-BETA-X" not in t
        tb = pdf_text(2026, ST["B"])
        assert "T83-BETA-X" in tb and "T83-RISC-1" not in tb and "T83-RAT-2" not in tb

    def test_04_old_year_and_empty(self):
        t24 = pdf_text(2024)
        assert "T83-OLD-3" in t24 and "T83-RISC-1" not in t24
        t30 = pdf_text(2030)
        assert "Nessun rateo o risconto" in t30 and "Riepilogo per tipo" not in t30

    def test_05_definitiva_column(self):
        r = sess().post(f"{API}/contabilita/ratei/contabilizza", json={"anno": 2026, "definitiva": True, "ids": [ST["R1"]]})
        assert r.status_code == 200 and r.json()["contabilizzati"] == 1, r.text
        t = pdf_text(2026)
        assert "Definitiva" in t
        # riepilogo row of Risconto attivo: contabilizzato 897,53 ; Rateo attivo: 0,00
        assert t.count("897,53") >= 3, t
        r = sess().post(f"{API}/contabilita/ratei/annulla", json={"anno": 2026, "ids": [ST["R1"]]})
        assert r.status_code == 200, r.text

    def test_06_requires_company_and_auth(self):
        r = sess("").get(f"{API}/contabilita/ratei/pdf", params={"anno": 2026})
        assert r.status_code == 400
        r = requests.get(f"{API}/contabilita/ratei/pdf", params={"anno": 2026}, headers={"X-Company-Id": ST["A"]})
        assert r.status_code == 401
        r = sess().get(f"{API}/contabilita/ratei/pdf")
        assert r.status_code == 422
        r = sess().get(f"{API}/contabilita/ratei/pdf", params={"anno": "abc"})
        assert r.status_code == 422

    def test_07_operatore_other_company(self):
        mongo(f'db.users.insertOne({{user_id:"{UID_OP}", email:"test.user.t83.op@example.com", name:"TEST_T83 op", picture:"", role:"operatore", status:"approved", company_ids:["{ST["A"]}"], created_at:new Date().toISOString()}});'
              f'db.user_sessions.insertOne({{user_id:"{UID_OP}", session_token:"{TOK_OP}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
        r = sess(ST["B"], TOK_OP).get(f"{API}/contabilita/ratei/pdf", params={"anno": 2026})
        assert r.status_code == 404
        r = sess(ST["A"], TOK_OP).get(f"{API}/contabilita/ratei/pdf", params={"anno": 2026})
        print("operatore own company status:", r.status_code)
        assert r.status_code in (200, 403)


if __name__ == "__main__" and sys.argv[-1] == "clean":
    clean()

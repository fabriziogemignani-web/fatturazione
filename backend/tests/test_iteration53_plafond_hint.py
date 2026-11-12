# Iteration 53: Plafond hint in invoice editor - backend support: GET /api/intenti?party_id=..&escludi=<invoiceId>
# Run: pytest tests/test_iteration53_plafond_hint.py -v -n 0
import json
import random
from datetime import date

import pytest
import requests

from test_iteration7_pa_scartate_registro import API, mongo

RUN = str(random.randint(100000, 999999))
TOK, UID = f"test_session_t53_admin_{RUN}", f"test-user-t53-admin-{RUN}"
PIVA = "87" + RUN + "531"
T = date.today()
Y = T.year
TODAY = T.isoformat()
ST = {}
COLLS = ["invoices", "passive_invoices", "parties", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "intenti", "partite_aperte"]
PROT = f"{RUN}00000000001-000001"


def sess():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{partita_iva:"{PIVA}"}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def body(pid, n35, td="TD01", **kw):
    return {"tipo_documento": td, "data": TODAY, "party_id": pid, "modalita_pagamento": "MP05",
            "lines": [{"descrizione": "TEST_n35", "quantita": 1, "prezzo_unitario": n35, "aliquota": 0, "natura": "N3.5"}], **kw}


def decl(**params):
    r = sess().get(f"{API}/intenti", params={"party_id": ST["A"], **params})
    assert r.status_code == 200, r.text
    return next(x for x in r.json() if x["id"] == ST["D"])


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    try:
        mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t53.{UID}@example.com", name:"TEST_T53 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
              f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
        r = sess().post(f"{API}/companies", json={"denominazione": f"TEST_T53 Plafond {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                                 "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
        assert r.status_code == 200, r.text
        ST["cid"] = r.json()["id"]
        r = sess().post(f"{API}/parties", json={"tipo": "cliente", "denominazione": "TEST_T53 Esportatore Srl", "partita_iva": "01234567890",
                                                "codice_fiscale": "RSSMRA80A01H501U", "codice_destinatario": "ABC1234", "indirizzo": "Via X 1",
                                                "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT", "natura_default": "N3.5"})
        assert r.status_code == 200, r.text
        ST["A"] = r.json()["id"]
        r = sess().post(f"{API}/intenti", json={"party_id": ST["A"], "protocollo": PROT, "data": f"{Y}-01-01", "anno": Y, "importo": 10000})
        assert r.status_code == 200, r.text
        ST["D"] = r.json()["id"]
        yield
    finally:
        clean()


class TestEscludi:
    def test_01_fresh_declaration(self):
        d = decl()
        assert d["residuo"] == 10000 and d["utilizzato"] == 0

    def test_02_draft_counts_and_escludi_removes_it(self):
        r = sess().post(f"{API}/invoices", json=body(ST["A"], 3000))
        assert r.status_code == 200, r.text
        ST["I1"] = r.json()["id"]
        assert r.json().get("intento", {}).get("id") == ST["D"]
        assert decl()["residuo"] == 7000
        d = decl(escludi=ST["I1"])
        assert d["residuo"] == 10000 and d["utilizzato"] == 0

    def test_03_escludi_unknown_id_no_effect(self):
        assert decl(escludi="nonexistent-id")["residuo"] == 7000

    def test_04_list_without_party_unchanged(self):
        r = sess().get(f"{API}/intenti")
        assert r.status_code == 200
        x = next(x for x in r.json() if x["id"] == ST["D"])
        assert x["residuo"] == 7000 and x["percentuale_residua"] == 70 and "_id" not in x

    def test_05_edit_draft_up_to_full_plafond(self):
        r = sess().put(f"{API}/invoices/{ST['I1']}", json=body(ST["A"], 10000))
        assert r.status_code == 200, r.text
        assert decl()["residuo"] == 0
        assert decl(escludi=ST["I1"])["residuo"] == 10000

    def test_06_edit_draft_exceeding_422(self):
        r = sess().put(f"{API}/invoices/{ST['I1']}", json=body(ST["A"], 10000.01))
        assert r.status_code == 422, r.text
        assert "Plafond superato" in r.text
        r = sess().put(f"{API}/invoices/{ST['I1']}", json=body(ST["A"], 9500))
        assert r.status_code == 200, r.text
        assert decl()["residuo"] == 500

    def test_07_new_invoice_exceeding_422(self):
        r = sess().post(f"{API}/invoices", json=body(ST["A"], 600))
        assert r.status_code == 422 and "Plafond superato" in r.text

    def test_08_credit_note_increases_residuo(self):
        r = sess().post(f"{API}/invoices/{ST['I1']}/send")
        assert r.status_code == 200, r.text
        sess().post(f"{API}/invoices/{ST['I1']}/refresh")
        r = sess().post(f"{API}/invoices", json=body(ST["A"], 1000, td="TD04", fattura_collegata_id=ST["I1"]))
        assert r.status_code == 200, r.text
        ST["NC"] = r.json()["id"]
        assert decl()["residuo"] == 1500
        assert decl(escludi=ST["NC"])["residuo"] == 500

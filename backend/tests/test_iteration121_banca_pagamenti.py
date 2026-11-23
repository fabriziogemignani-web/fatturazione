# Iteration 121: payment bank choice (banca_iban) on POST /invoices/{iid}/pagamenti and /passive/{pid}/pagamenti.
# >1 banks + bank method without banca_iban -> 400 field banca_iban; 1 bank auto; unknown IBAN 400; contanti -> null; normalization.
# Run: pytest tests/test_iteration121_banca_pagamenti.py -v -n 0   (T121_KEEP=1 keeps data for UI testing)
import json
import os
import random
import sys
from datetime import date, timedelta

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo, party, inv  # noqa: E402
import test_iteration89_rigenera_passive as t89  # noqa: E402

RUN = str(random.randint(100000, 999999))
TOK, UID = "test_session_t121_admin", "test-user-t121-admin"
PIVA = "12" + RUN + "121"
PIVA2 = "13" + RUN + "131"
ST = {}
COLLS = ["invoices", "passive_invoices", "parties", "articles", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "partite_aperte", "counters", "bank_tx", "bank_accounts"]
T = date.today()
D = lambda n: (T - timedelta(days=n)).isoformat()  # noqa: E731
IBAN1 = "IT60X0542811101000000123456"
IBAN2 = "IT42L1234512345123456789012"


def sess(cid=None):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {TOK}", "X-Requested-With": "invoix"})
    c = cid or ST.get("cid")
    if c:
        s.headers["X-Company-Id"] = c
    return s


def clean():
    mongo(f'db.companies.find({{denominazione:/^TEST_T121/}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def mk_company(name, piva, contab):
    r = sess("").post(f"{API}/companies", json={"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01",
                                               "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    s = sess(cid)
    s.put(f"{API}/companies/{cid}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                 "corrispettivi": True, "contabilita": contab})
    c = s.get(f"{API}/company").json()
    c["banche"] = [{"nome": "TEST_Banca Uno", "iban": IBAN1, "predefinita": True},
                   {"nome": "TEST_Banca Due", "iban": IBAN2, "predefinita": False, "conto_coge": "06.01.002" if contab else ""}]
    r = s.put(f"{API}/company", json=c)
    assert r.status_code == 200, r.text
    assert len(r.json()["banche"]) == 2
    return cid


def sales_invoice(cid, price=1000):
    s = sess(cid)
    pid = s.post(f"{API}/parties", json=party("TEST_T121 Cliente", piva="01234567892", cf="01234567892")).json()["id"]
    r = s.post(f"{API}/invoices", json=inv(pid, data=D(20), price=price))
    assert r.status_code == 200, r.text
    iid = r.json()["id"]
    assert s.post(f"{API}/invoices/{iid}/send").status_code == 200
    s.post(f"{API}/invoices/{iid}/refresh")
    return iid


def pxml(num, data, ced, piva, imp=1000.0):
    return t89.xml(num, data, ced, imp).replace(t89.PIVA.encode(), piva.encode()).replace(b"TEST_T89", b"TEST_T121")


def upload(cid, x):
    r = sess(cid).post(f"{API}/passive/upload", files=[("files", (f"t121_{RUN}_{random.randint(1, 10**6)}.xml", x, "application/octet-stream"))])
    assert r.status_code == 200, r.text
    j = r.json()[0]
    assert j["ok"], j
    return j["documenti"][0]["id"]


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t121.admin@example.com", name:"TEST_T121 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    ST["cid"] = mk_company("TEST_T121 Contab Srl", PIVA, True)
    ST["cid2"] = mk_company("TEST_T121 NoContab Srl", PIVA2, False)
    sess().get(f"{API}/contabilita/conti")
    yield
    if os.environ.get("T121_KEEP"):
        print("\nKEEP", RUN, ST, TOK)
        json.dump({**ST, "tok": TOK}, open("/tmp/t121.json", "w"))
    else:
        clean()


class TestBancaPagamenti:
    def test_01_conti_pagamento_bank2(self):
        j = sess().get(f"{API}/contabilita/conti-pagamento").json()
        print("conti", [(c["conto"], c["label"]) for c in j["conti"]])
        ST["has0602"] = any(c["conto"] == "06.01.002" for c in j["conti"])

    def test_02_sales_missing_banca_400(self):
        ST["I"] = sales_invoice(ST["cid"])
        r = sess().post(f"{API}/invoices/{ST['I']}/pagamenti", json={"data": D(3), "importo": 100, "metodo": "bonifico"})
        assert r.status_code == 400, r.text
        assert "banca_iban" in r.text and "Seleziona la banca" in r.text, r.text

    def test_03_sales_unknown_iban_400(self):
        r = sess().post(f"{API}/invoices/{ST['I']}/pagamenti", json={"data": D(3), "importo": 100, "metodo": "bonifico", "banca_iban": "IT00X0000000000000000000000"})
        assert r.status_code == 400 and "banca_iban" in r.text, r.text

    def test_04_sales_bank2_normalized(self):
        spaced = "it42 l123 4512 3451 2345 6789 012"
        r = sess().post(f"{API}/invoices/{ST['I']}/pagamenti", json={"data": D(3), "importo": 100, "metodo": "bonifico", "banca_iban": spaced})
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["banca_iban"] == IBAN2 and p["banca_nome"] == "TEST_Banca Due", p
        ST["P1"] = p["id"]
        g = sess().get(f"{API}/invoices/{ST['I']}/pagamenti").json()
        pp = next(x for x in g["pagamenti"] if x["id"] == p["id"])
        assert pp["banca_iban"] == IBAN2 and pp["banca_nome"] == "TEST_Banca Due"

    def test_05_sales_methods_bank_required(self):
        for m in ("assegno", "carta", "riba", "rid"):
            r = sess().post(f"{API}/invoices/{ST['I']}/pagamenti", json={"data": D(3), "importo": 1, "metodo": m})
            assert r.status_code == 400 and "banca_iban" in r.text, (m, r.text)
        r = sess().post(f"{API}/invoices/{ST['I']}/pagamenti", json={"data": D(3), "importo": 10, "metodo": "riba", "banca_iban": IBAN1})
        assert r.status_code == 200 and r.json()["banca_nome"] == "TEST_Banca Uno", r.text

    def test_06_sales_contanti_null(self):
        r = sess().post(f"{API}/invoices/{ST['I']}/pagamenti", json={"data": D(3), "importo": 10, "metodo": "contanti", "banca_iban": IBAN1})
        assert r.status_code == 200, r.text
        assert r.json()["banca_iban"] is None and r.json()["banca_nome"] is None
        r = sess().post(f"{API}/invoices/{ST['I']}/pagamenti", json={"data": D(3), "importo": 10, "metodo": "altro"})
        assert r.status_code == 200 and r.json()["banca_iban"] is None, r.text

    def test_07_passive_missing_and_ok(self):
        pid = upload(ST["cid"], pxml("T121-1", D(30), "01111111111", PIVA))
        r = sess().patch(f"{API}/passive/{pid}", json={"stato_reg": "registrata", "data_registrazione": D(25)})
        assert r.status_code == 200, r.text
        ST["PA"] = pid
        r = sess().post(f"{API}/passive/{pid}/pagamenti", json={"data": D(5), "importo": 100, "metodo": "bonifico"})
        assert r.status_code == 400 and "banca_iban" in r.text, r.text
        r = sess().post(f"{API}/passive/{pid}/pagamenti", json={"data": D(5), "importo": 100, "metodo": "bonifico", "banca_iban": "IT99Z9999999999999999999999"})
        assert r.status_code == 400 and "banca_iban" in r.text, r.text
        r = sess().post(f"{API}/passive/{pid}/pagamenti", json={"data": D(5), "importo": 100, "metodo": "bonifico", "banca_iban": IBAN1})
        assert r.status_code == 200, r.text
        assert r.json()["banca_iban"] == IBAN1 and r.json()["banca_nome"] == "TEST_Banca Uno"
        r = sess().post(f"{API}/passive/{pid}/pagamenti", json={"data": D(5), "importo": 5, "metodo": "contanti", "banca_iban": IBAN1})
        assert r.status_code == 200 and r.json()["banca_iban"] is None, r.text

    def test_08_no_contab_company(self):
        iid = sales_invoice(ST["cid2"])
        s = sess(ST["cid2"])
        r = s.post(f"{API}/invoices/{iid}/pagamenti", json={"data": D(3), "importo": 50, "metodo": "bonifico"})
        assert r.status_code == 400 and "banca_iban" in r.text, r.text
        r = s.post(f"{API}/invoices/{iid}/pagamenti", json={"data": D(3), "importo": 50, "metodo": "bonifico", "banca_iban": IBAN2})
        assert r.status_code == 200 and r.json()["banca_nome"] == "TEST_Banca Due", r.text
        ST["I2"] = iid

    def test_09_single_bank_auto(self):
        s = sess(ST["cid2"])
        c = s.get(f"{API}/company").json()
        c["banche"] = [b for b in c["banche"] if b["iban"] == IBAN2]
        c["banche"][0]["predefinita"] = True
        assert s.put(f"{API}/company", json=c).status_code == 200
        r = s.post(f"{API}/invoices/{ST['I2']}/pagamenti", json={"data": D(3), "importo": 5, "metodo": "bonifico"})
        assert r.status_code == 200, r.text
        assert r.json()["banca_iban"] == IBAN2 and r.json()["banca_nome"] == "TEST_Banca Due"
        # restore 2 banks for UI
        c["banche"] = [{"nome": "TEST_Banca Uno", "iban": IBAN1, "predefinita": True}, {"nome": "TEST_Banca Due", "iban": IBAN2, "predefinita": False}]
        assert s.put(f"{API}/company", json=c).status_code == 200

    def test_10_no_banks_null(self):
        s = sess(ST["cid2"])
        c = s.get(f"{API}/company").json()
        saved = c["banche"]
        c["banche"], c["iban"] = [], ""  # legacy single iban is migrated into banche ("Banca") if left
        assert s.put(f"{API}/company", json=c).status_code == 200
        r = s.post(f"{API}/invoices/{ST['I2']}/pagamenti", json={"data": D(3), "importo": 5, "metodo": "bonifico"})
        assert r.status_code == 200 and r.json()["banca_iban"] is None, r.text
        c["banche"] = saved
        assert s.put(f"{API}/company", json=c).status_code == 200

    def test_11_iban_too_long_422(self):
        r = sess().post(f"{API}/invoices/{ST['I']}/pagamenti", json={"data": D(3), "importo": 1, "metodo": "bonifico", "banca_iban": "X" * 40})
        assert r.status_code in (400, 422), r.text

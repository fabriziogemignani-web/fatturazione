# Iteration 94: POST /contabilita/pagamenti-mancanti (old payments -> prima nota) and card statements
# GET /contabilita/carte/estratto + POST /contabilita/carte/addebito.
# Run: pytest tests/test_iteration94_pagamenti_mancanti_carte.py -v -n 0
import json
import os
import random
import sys
import uuid
from datetime import date, timedelta

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo, party, inv  # noqa: E402
import test_iteration89_rigenera_passive as t89  # noqa: E402

RUN = str(random.randint(100000, 999999))
TOK, UID = "test_session_t94_admin", "test-user-t94-admin"
PIVA = "94" + RUN + "941"
ST = {}
COLLS = ["invoices", "passive_invoices", "parties", "articles", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "partite_aperte", "f24_versamenti", "pag_distinte", "ratei_risconti", "counters", "bank_tx", "bank_accounts"]
IBAN = "IT60X0542811101000000123456"
_prev = date.today().replace(day=1) - timedelta(days=1)
MESE = _prev.strftime("%Y-%m")
M = lambda d: f"{MESE}-{d:02d}"  # noqa: E731


def sess():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{denominazione:/^TEST_T94/}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def upload(x):
    r = sess().post(f"{API}/passive/upload", files=[("files", (f"t94_{RUN}_{random.randint(1, 10**6)}.xml", x, "application/octet-stream"))])
    assert r.status_code == 200, r.text
    j = r.json()[0]
    assert j["ok"], j
    return j["documenti"][0]["id"]


def pxml(num, data, ced, imp=1000.0):
    return t89.xml(num, data, ced, imp).replace(t89.PIVA.encode(), PIVA.encode()).replace(b"TEST_T89", b"TEST_T94")


def entry(eid):
    return json.loads(mongo(f'print(JSON.stringify(db.coa_entries.findOne({{id:"{eid}", company_id:"{ST["cid"]}"}},{{_id:0}})))') or "null")


def getpay(coll, pid):
    return json.loads(mongo(f'print(JSON.stringify(db.{coll}.findOne({{id:"{pid}"}},{{_id:0}})))') or "null")


def side(e, conto):
    rows = [r for r in e["righe"] if r["conto"] == conto]
    return round(sum(r.get("dare") or 0 for r in rows), 2), round(sum(r.get("avere") or 0 for r in rows), 2)


def ins(coll, invoice_id, party_id, data, importo, metodo, **extra):
    pid = "t94-" + uuid.uuid4().hex[:10]
    doc = {"id": pid, "company_id": ST["cid"], "invoice_id": invoice_id, "party_id": party_id, "numero_display": extra.pop("num", "X"),
           "data": data, "importo": importo, "metodo": metodo, "note": "TEST_T94 old", "nc_id": None, "created_at": "2026-01-01T00:00:00Z", **extra}
    mongo(f"db.{coll}.insertOne({json.dumps(doc)})")
    return pid


def estratto(conto="06.03.001"):
    r = sess().get(f"{API}/contabilita/carte/estratto", params={"mese": MESE})
    assert r.status_code == 200, r.text
    return next(c for c in r.json()["carte"] if c["conto"] == conto)


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t94.admin@example.com", name:"TEST_T94 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": "TEST_T94 Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    sess().put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                            "corrispettivi": True, "contabilita": True})
    mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}}, {{$set:{{banche:[{{nome:"TEST_T94 Banca", iban:"{IBAN}", predefinita:true}}]}}}})')
    sess().get(f"{API}/contabilita/conti")
    yield
    if os.environ.get("T94_KEEP"):
        print("\nKEEP", RUN, ST["cid"], TOK)
    else:
        clean()


class TestPagamentiMancanti:
    def test_01_setup_docs(self):
        s = sess()
        ST["A"] = upload(pxml("A-1", M(1), "01111111111"))
        r = s.patch(f"{API}/passive/{ST['A']}", json={"stato_reg": "registrata", "data_registrazione": M(2)})
        assert r.status_code == 200, r.text
        ST["A_party"] = s.get(f"{API}/passive/{ST['A']}").json()["party_id"]
        ST["B"] = upload(pxml("B-1", M(1), "02222222222"))
        ST["B_party"] = s.get(f"{API}/passive/{ST['B']}").json()["party_id"]
        pid = s.post(f"{API}/parties", json=party("TEST_T94 Cliente", piva="01234567892", cf="01234567892")).json()["id"]
        r = s.post(f"{API}/invoices", json=inv(pid, data=M(3)))
        assert r.status_code == 200, r.text
        ST["I"], ST["I_party"] = r.json()["id"], pid
        assert s.post(f"{API}/invoices/{ST['I']}/send").status_code == 200
        s.post(f"{API}/invoices/{ST['I']}/refresh")

    def test_02_insert_old(self):
        A, pa = ST["A"], ST["A_party"]
        ST["p_bon"] = ins("passive_payments", A, pa, M(10), 100, "bonifico", num="A-1")
        ST["p_carta"] = ins("passive_payments", A, pa, M(12), 50, "carta", num="A-1")
        ST["p_cont"] = ins("passive_payments", A, pa, M(13), 20, "contanti", num="A-1")
        ST["p_conto"] = ins("passive_payments", A, pa, M(14), 30, "bonifico", num="A-1", conto="06.03.001")
        ST["p_badconto"] = ins("passive_payments", A, pa, M(14), 5, "bonifico", num="A-1", conto="30.06.001")
        ST["p_comp"] = ins("passive_payments", A, pa, M(14), 7, "compensazione", num="A-1")
        ST["p_riba"] = ins("passive_payments", A, pa, M(14), 8, "riba", num="A-1", riba_effetto_id="x")
        ST["p_dist"] = ins("passive_payments", A, pa, M(14), 9, "bonifico", num="A-1", distinta_pag_id="y")
        ST["p_bank"] = ins("passive_payments", A, pa, M(14), 11, "bonifico", num="A-1")
        mongo(f'db.bank_tx.insertOne({{id:"t94-tx-{RUN}", company_id:"{ST["cid"]}", data:"{M(14)}", importo:-11, descrizione:"TEST_T94", match:{{tipo:"pagamento", payment_ids:["{ST["p_bank"]}"]}}}})')
        ST["p_unreg"] = ins("passive_payments", ST["B"], ST["B_party"], M(14), 40, "bonifico", num="B-1")
        ST["p_done"] = ins("passive_payments", A, pa, M(14), 3, "bonifico", num="A-1", coge_entry_id="already")
        I, ip = ST["I"], ST["I_party"]
        ST["i_bon"] = ins("payments", I, ip, M(15), 200, "bonifico", num="1/2026")
        ST["i_cont"] = ins("payments", I, ip, M(16), 96, "contanti", num="1/2026", ritenuta_subita=4)
        ST["i_rit"] = ins("payments", I, ip, M(16), 4, "ritenuta", num="1/2026", ritenuta_subita=0, parent_payment_id=ST["i_cont"])

    def test_03_register(self):
        r = sess().post(f"{API}/contabilita/pagamenti-mancanti")
        assert r.status_code == 200, r.text
        j = r.json()
        print(j)
        assert j["pagamenti"] == 5 and j["incassi"] == 2 and j["saltati"] == 1, j
        assert any("B-1" in x and "non è ancora registrata" in x for x in j["errori"]), j

    def test_04_passive_entries(self):
        exp = {"p_bon": ("06.01.001", 100), "p_carta": ("06.03.001", 50), "p_cont": ("06.02.001", 20), "p_conto": ("06.03.001", 30), "p_badconto": ("06.01.001", 5)}
        for k, (conto, v) in exp.items():
            p = getpay("passive_payments", ST[k])
            assert p["conto"] == conto and p["coge_entry_id"] and p["coge_rif"].startswith("prima nota n."), (k, p)
            e = entry(p["coge_entry_id"])
            assert e["origine"] == "pagamento" and e["causale"] == "PG" and e["ref_id"] == p["id"], e
            assert side(e, conto) == (0, v) and side(e, "13.02.001") == (v, 0), (k, e)
        for k in ("p_comp", "p_riba", "p_dist", "p_bank", "p_unreg"):
            p = getpay("passive_payments", ST[k])
            assert not p.get("coge_entry_id"), (k, p)
        assert getpay("passive_payments", ST["p_done"])["coge_entry_id"] == "already"

    def test_05_incassi_entries(self):
        p = getpay("payments", ST["i_bon"])
        e = entry(p["coge_entry_id"])
        assert e["causale"] == "IN" and side(e, "06.01.001") == (200, 0) and side(e, "05.01.001") == (0, 200), e
        p2 = getpay("payments", ST["i_cont"])
        e2 = entry(p2["coge_entry_id"])
        assert side(e2, "06.02.001") == (96, 0) and side(e2, "05.02.003") == (4, 0) and side(e2, "05.01.001") == (0, 100), e2
        rit = getpay("payments", ST["i_rit"])
        assert rit["coge_entry_id"] == p2["coge_entry_id"] and rit["coge_rif"] == p2["coge_rif"], rit

    def test_06_idempotent(self):
        r = sess().post(f"{API}/contabilita/pagamenti-mancanti")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["pagamenti"] == 0 and j["incassi"] == 0 and j["saltati"] == 1, j
        n = mongo(f'print(db.coa_entries.countDocuments({{company_id:"{ST["cid"]}", origine:"pagamento"}}))')
        assert n == "7", n

    # Old payment dated before the passive invoice registration date (manual entry would be blocked)
    def test_07_before_registration(self):
        pid = ins("passive_payments", ST["A"], ST["A_party"], M(1), 6, "bonifico", num="A-1")
        j = sess().post(f"{API}/contabilita/pagamenti-mancanti").json()
        print("BEFORE-REG", j)
        p = getpay("passive_payments", pid)
        mongo(f'db.passive_payments.deleteOne({{id:"{pid}"}})')
        if p.get("coge_entry_id"):
            mongo(f'db.coa_entries.deleteOne({{id:"{p["coge_entry_id"]}"}})')
        assert not p.get("coge_entry_id"), f"payment dated {M(1)} before registrazione {M(2)} was registered: {j}"


class TestCarte:
    def test_10_invalid_mese(self):
        for m in ("2026-13", "abc", "2026-1"):
            r = sess().get(f"{API}/contabilita/carte/estratto", params={"mese": m})
            assert r.status_code == 400, (m, r.text)

    def test_11_estratto(self):
        c = estratto()
        assert c["tipo"] == "carta"
        assert len(c["movimenti"]) == 2, c["movimenti"]
        assert c["totale_spese"] == 80 and c["totale_accrediti"] == 0 and c["totale"] == 80, c
        assert c["addebitato"] == 0 and c["da_addebitare"] == 80 and c["addebiti"] == [], c
        assert all(m["party_nome"] for m in c["movimenti"]), c["movimenti"]

    def test_12_addebito_invalid(self):
        s = sess()
        base = {"conto": "06.03.001", "mese": MESE, "data": M(28), "banca": "06.01.001"}
        r = s.post(f"{API}/contabilita/carte/addebito", json={**base, "conto": "06.01.001"})
        assert r.status_code == 400 and "Carta" in r.text, r.text
        r = s.post(f"{API}/contabilita/carte/addebito", json={**base, "banca": "06.02.001"})
        assert r.status_code == 400 and "banca" in r.text, r.text
        prev = (date.fromisoformat(M(1)) - timedelta(days=1)).isoformat()
        r = s.post(f"{API}/contabilita/carte/addebito", json={**base, "data": prev})
        assert r.status_code == 400 and "precedere" in r.text, r.text
        r = s.post(f"{API}/contabilita/carte/addebito", json={**base, "data": f"{MESE}-40"})
        assert r.status_code in (400, 422), r.text

    def test_13_addebito_ok(self):
        s = sess()
        r = s.post(f"{API}/contabilita/carte/addebito", json={"conto": "06.03.001", "mese": MESE, "data": M(28), "banca": "06.01.001"})
        assert r.status_code == 200, r.text
        e = entry(r.json()["id"])
        assert e["origine"] == "carta" and e["causale"] == "GC", e
        assert side(e, "06.03.001") == (80, 0) and side(e, "06.01.001") == (0, 80), e
        c = estratto()
        assert c["addebitato"] == 80 and c["da_addebitare"] == 0 and len(c["addebiti"]) == 1 and c["addebiti"][0]["banca"] == "06.01.001", c
        assert len(c["movimenti"]) == 2
        r = s.post(f"{API}/contabilita/carte/addebito", json={"conto": "06.03.001", "mese": MESE, "data": M(28), "banca": "06.01.001"})
        assert r.status_code == 400 and "Nessun importo" in r.text, r.text

    def test_14_new_payment_then_second_addebito(self):
        s = sess()
        r = s.post(f"{API}/passive/{ST['A']}/pagamenti", json={"data": M(20), "importo": 25, "metodo": "carta"})
        assert r.status_code == 200, r.text
        c = estratto()
        assert c["da_addebitare"] == 25 and c["totale"] == 105, c
        r = s.post(f"{API}/contabilita/carte/addebito", json={"conto": "06.03.001", "mese": MESE, "data": M(29), "banca": "06.01.001"})
        assert r.status_code == 200, r.text
        c = estratto()
        assert c["addebitato"] == 105 and c["da_addebitare"] == 0 and len(c["addebiti"]) == 2, c

    def test_15_other_month_empty(self):
        nxt = (date.fromisoformat(M(28)) + timedelta(days=10)).strftime("%Y-%m")
        r = sess().get(f"{API}/contabilita/carte/estratto", params={"mese": nxt})
        assert r.status_code == 200
        c = next(x for x in r.json()["carte"] if x["conto"] == "06.03.001")
        assert c["movimenti"] == [] and c["da_addebitare"] == 0, c

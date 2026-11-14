# Iteration 78: Dashboard ordini - GET /api/dashboard/riquadri ordini_* counters (status/data_consegna filtering, company isolation)
# and GET /api/ordini/{tipo} data used by OrdiniPanel. Run: pytest tests/test_iteration78_dashboard_ordini.py -v -n 0  (T78_KEEP=1 keeps data for UI)
import json
import os
import random
import sys
from datetime import date, timedelta

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

RUN = os.environ.get("T78_RUN") or str(random.randint(100000, 999999))
TOK, UID = "test_session_t78_admin", "test-user-t78-admin"
D = lambda n: (date.today() + timedelta(days=n)).isoformat()  # noqa: E731
ST = {}


def sess(cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    c = cid or ST.get("cid")
    if c:
        s.headers["X-Company-Id"] = c
    return s


def clean():
    mongo('db.companies.find({denominazione:/^TEST_T78/}).forEach(c=>{db.getCollectionNames().forEach(k=>{if(k!=="companies") db[k].deleteMany({company_id:c.id})});'
          'db.users.updateMany({}, {$pull:{company_ids:c.id}}); db.companies.deleteOne({id:c.id});});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def company(name, piva):
    r = sess("x").post(f"{API}/companies", json={"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01",
                                                 "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    sess(cid).put(f"{API}/companies/{cid}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                         "corrispettivi": True, "contabilita": True})
    return cid


def party(tipo, name, piva, cid=None):
    r = sess(cid).post(f"{API}/parties", json={"tipo": tipo, "denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "codice_destinatario": "ABC1234",
                                               "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"})
    assert r.status_code == 200, r.text
    return r.json()


def ordine(tipo, pid, consegna, q=10, p=5, cid=None, data=None):
    r = sess(cid).post(f"{API}/ordini/{tipo}", json={"data": data or D(-30), "party_id": pid, "data_consegna": consegna,
                                                     "lines": [{"descrizione": f"TEST_T78 riga {tipo}", "quantita": q, "prezzo_unitario": p, "aliquota": 22, "unita_misura": "PZ"}]})
    assert r.status_code == 200, r.text
    return r.json()


def evadi(tipo, o, q):
    r = sess().post(f"{API}/ordini/{tipo}/{o['id']}/evadi", json={"data": D(0), "righe": [{"line_id": o["lines"][0]["id"], "quantita": q}]})
    assert r.status_code == 200, r.text
    return r.json()


def riq(cid=None):
    r = sess(cid).get(f"{API}/dashboard/riquadri")
    assert r.status_code == 200, r.text
    return r.json()


KEYS = ("ordini_clienti_da_evadere", "ordini_clienti_in_ritardo", "ordini_fornitori_in_ritardo", "ordini_fornitori_aperti")


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t78.admin@example.com", name:"TEST_T78 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    ST["cid"] = company(f"TEST_T78 Ordini {RUN} Srl", "78" + RUN + "781")
    ST["cid2"] = company(f"TEST_T78 Altra {RUN} Srl", "79" + RUN + "791")
    ST["C"] = party("cliente", "TEST_T78 Cliente Uno", "09876543217")
    ST["F"] = party("fornitore", "TEST_T78 Fornitore Uno", "12345678903")
    yield
    if os.environ.get("T78_KEEP"):
        print("\nKEEP", RUN, json.dumps({k: v for k, v in ST.items() if isinstance(v, str)}))
    else:
        clean()


class TestRiquadriOrdini:
    def test_01_empty_counters(self):
        r = riq()
        for k in KEYS:
            assert r[k] == 0, (k, r)

    def test_02_create_orders(self):
        c, f = ST["C"]["id"], ST["F"]["id"]
        ST["oc_late"] = ordine("cliente", c, D(-5))
        ST["oc_fut"] = ordine("cliente", c, D(7))
        ST["oc_nodate"] = ordine("cliente", c, "")
        ST["oc_today"] = ordine("cliente", c, D(0))
        ST["oc_part"] = ordine("cliente", c, D(-2))
        ST["oc_evaso"] = ordine("cliente", c, D(-10))
        ST["of_late"] = ordine("fornitore", f, D(-3))
        ST["of_fut"] = ordine("fornitore", f, D(5))
        ST["of_nodate"] = ordine("fornitore", f, "")
        ST["of_evaso"] = ordine("fornitore", f, D(-8))
        ST["of_chiuso"] = ordine("fornitore", f, D(-9))

    def test_03_evadi_and_close(self):
        assert evadi("cliente", ST["oc_part"], 4)["status"] == "parziale"
        assert evadi("cliente", ST["oc_evaso"], 10)["status"] == "evaso"
        assert evadi("fornitore", ST["of_evaso"], 10)["status"] == "evaso"
        r = sess().post(f"{API}/ordini/fornitore/{ST['of_chiuso']['id']}/chiudi")
        assert r.status_code == 200 and r.json()["status"] == "chiuso", r.text

    def test_04_counters(self):
        r = riq()
        # da evadere: late, fut, nodate, today, part = 5 ; ritardo: late, part = 2 (today not late, nodate not late)
        assert r["ordini_clienti_da_evadere"] == 5, r
        assert r["ordini_clienti_in_ritardo"] == 2, r
        # fornitori aperti: late, fut, nodate = 3 ; in ritardo: late = 1
        assert r["ordini_fornitori_aperti"] == 3, r
        assert r["ordini_fornitori_in_ritardo"] == 1, r

    def test_05_company_isolation(self):
        r = riq(ST["cid2"])
        for k in KEYS:
            assert r[k] == 0, (k, r)

    def test_06_other_company_orders_not_counted(self):
        f2 = party("fornitore", "TEST_T78 Forn Altra", "12345678903", cid=ST["cid2"])
        ordine("fornitore", f2["id"], D(-4), cid=ST["cid2"])
        assert riq(ST["cid2"])["ordini_fornitori_in_ritardo"] == 1
        assert riq()["ordini_fornitori_in_ritardo"] == 1

    def test_07_list_data_for_panel(self):
        rows = sess().get(f"{API}/ordini/cliente").json()
        byid = {o["id"]: o for o in rows}
        p = byid[ST["oc_part"]["id"]]
        assert p["status"] == "parziale" and p["lines"][0]["evasa"] == 4 and p["imponibile"] == 50
        assert byid[ST["oc_evaso"]["id"]]["status"] == "evaso"
        assert all("_id" not in o for o in rows)

    def test_08_riopen_counts_again(self):
        r = sess().post(f"{API}/ordini/fornitore/{ST['of_chiuso']['id']}/riapri")
        assert r.status_code == 200 and r.json()["status"] == "aperto", r.text
        r = riq()
        assert r["ordini_fornitori_in_ritardo"] == 2 and r["ordini_fornitori_aperti"] == 4, r
        sess().post(f"{API}/ordini/fornitore/{ST['of_chiuso']['id']}/chiudi")

    def test_09_requires_auth(self):
        r = requests.get(f"{API}/dashboard/riquadri", headers={"X-Company-Id": ST["cid"]})
        assert r.status_code == 401, r.text

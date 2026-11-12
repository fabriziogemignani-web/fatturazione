# Iteration 56: Riquadri personalizzabili - GET/PUT /api/me/riquadri per-user preference (ordine, nascosti), dedup, isolation, validation.
# Run: pytest tests/test_iteration56_riquadri_pref.py -v -n 0   (UI helper: python tests/test_iteration56_riquadri_pref.py setup|clean)
import json
import os
import subprocess
import sys

import pytest
import requests

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
U1, T1 = "test-user-t56a", "test_session_t56a"
U2, T2 = "test-user-t56b", "test_session_t56b"
PIVA = "86000056501"
ST = {}


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


def clean():
    mongo(f'db.companies.find({{partita_iva:"{PIVA}"}}).forEach(c=>{{["invoices","parties","audit","coa_accounts","coa_causali","coa_iva"].forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          'db.counters.deleteMany({key:{$regex:c.id}}); db.users.updateMany({}, {$pull:{company_ids:c.id}}); db.companies.deleteOne({id:c.id});});'
          f'db.users.deleteMany({{user_id:{{$in:["{U1}","{U2}"]}}}}); db.user_sessions.deleteMany({{user_id:{{$in:["{U1}","{U2}"]}}}});')


def sess(tok, cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    if cid:
        s.headers["X-Company-Id"] = cid
    return s


def setup():
    clean()
    mongo(f'db.users.insertMany([{{user_id:"{U1}", email:"test.user.t56a@example.com", name:"TEST_T56 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}},'
          f'{{user_id:"{U2}", email:"test.user.t56b@example.com", name:"TEST_T56 oper", picture:"", role:"operatore", status:"approved", company_ids:[], created_at:new Date().toISOString()}}]);'
          f'db.user_sessions.insertMany([{{user_id:"{U1}", session_token:"{T1}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}},'
          f'{{user_id:"{U2}", session_token:"{T2}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}}]);')
    r = sess(T1).post(f"{API}/companies", json={"denominazione": "TEST_T56 Riquadri Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                                "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    r.raise_for_status()
    cid = r.json()["id"]
    mongo(f'db.users.updateMany({{user_id:{{$in:["{U1}","{U2}"]}}}}, {{$addToSet:{{company_ids:"{cid}"}}}})')
    return {"cid": cid}


@pytest.fixture(scope="module", autouse=True)
def fx():
    try:
        ST.update(setup())
        yield
    finally:
        clean()


class TestRiquadriPref:
    def test_01_requires_auth(self):
        assert requests.get(f"{API}/me/riquadri").status_code == 401
        assert requests.put(f"{API}/me/riquadri", json={"ordine": [], "nascosti": []}).status_code == 401

    def test_02_default_empty(self):
        r = sess(T1).get(f"{API}/me/riquadri")
        assert r.status_code == 200, r.text
        assert r.json() == {"ordine": [], "nascosti": []}

    def test_03_put_dedup_and_persist(self):
        r = sess(T1).put(f"{API}/me/riquadri", json={"ordine": ["ddt", "fatture", "ddt", "passive"], "nascosti": ["riba", "riba"]})
        assert r.status_code == 200, r.text
        assert r.json() == {"ordine": ["ddt", "fatture", "passive"], "nascosti": ["riba"]}
        assert sess(T1).get(f"{API}/me/riquadri").json() == {"ordine": ["ddt", "fatture", "passive"], "nascosti": ["riba"]}

    def test_04_other_user_unaffected(self):
        assert sess(T2).get(f"{API}/me/riquadri").json() == {"ordine": [], "nascosti": []}
        r = sess(T2).put(f"{API}/me/riquadri", json={"ordine": ["magazzino"], "nascosti": []})
        assert r.status_code == 200
        assert sess(T1).get(f"{API}/me/riquadri").json()["ordine"] == ["ddt", "fatture", "passive"]

    def test_05_partial_body_defaults(self):
        r = sess(T2).put(f"{API}/me/riquadri", json={"nascosti": ["fatture"]})
        assert r.status_code == 200, r.text
        assert r.json() == {"ordine": [], "nascosti": ["fatture"]}

    def test_06_validation(self):
        assert sess(T1).put(f"{API}/me/riquadri", json={"ordine": "x"}).status_code == 422
        assert sess(T1).put(f"{API}/me/riquadri", json={"ordine": [str(i) for i in range(31)]}).status_code == 422
        r = sess(T1).put(f"{API}/me/riquadri", json={"ordine": ["a" * 100]})
        assert r.status_code == 200 and len(r.json()["ordine"][0]) == 40

    def test_07_reset(self):
        r = sess(T1).put(f"{API}/me/riquadri", json={"ordine": [], "nascosti": []})
        assert r.status_code == 200
        assert sess(T1).get(f"{API}/me/riquadri").json() == {"ordine": [], "nascosti": []}

    def test_08_auth_me_unaffected(self):
        r = sess(T1).get(f"{API}/auth/me")
        assert r.status_code == 200 and r.json()["user_id"] == U1


if __name__ == "__main__":
    print(json.dumps(setup()) if sys.argv[1] == "setup" else clean())

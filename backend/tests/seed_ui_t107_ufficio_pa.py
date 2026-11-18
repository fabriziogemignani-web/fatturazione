# Iteration 107 UI seed: TEST_T107 company + test admin session for PartyDialog ufficio_pa / IndicePA test.
# Usage: python seed_ui_t107_ufficio_pa.py setup | clean
import json
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402
import test_iteration101_ai_registrazione_consulente as t101  # noqa: E402

TOK, UID = "test_session_t107_admin", "test-user-t107-admin"
PIVA = "10107107101"
COLLS = t101.COLLS


def sess(cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    s.headers["X-Requested-With"] = "invoix"
    if cid:
        s.headers["X-Company-Id"] = cid
    return s


def clean():
    mongo(f'db.companies.find({{denominazione:/^TEST_T107/}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t107.admin@example.com", name:"TEST_T107 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": "TEST_T107 PA Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                              "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    print("moduli", sess(cid).put(f"{API}/companies/{cid}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True}).status_code)
    print("CID", cid)


if __name__ == "__main__":
    setup() if sys.argv[1] == "setup" else clean()

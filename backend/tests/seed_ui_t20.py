# Seed/cleanup for iteration 20 UI test (banche aziendali). Usage: python3 seed_ui_t20.py seed|clean
import sys
import json
import requests
from test_iteration7_pa_scartate_registro import API, mongo, party, inv

TOK, UID, PIVA = "test_session_t20ui_admin", "test-user-t20ui-admin", "87999999001"


def clean():
    mongo(f'var c=db.companies.findOne({{partita_iva:"{PIVA}"}}); if(c){{db.invoices.deleteMany({{company_id:c.id}}); db.parties.deleteMany({{company_id:c.id}});'
          f'db.counters.deleteMany({{key:"progressivo_"+c.id}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}}'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def seed():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t20ui@example.com", name:"TEST_T20UI", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    c = {"denominazione": "TEST_T20UI Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
         "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"}
    cid = s.post(f"{API}/companies", json=c).json()["id"]
    s.headers["X-Company-Id"] = cid
    # legacy: only iban, no banche
    mongo(f'db.companies.updateOne({{id:"{cid}"}}, {{$set:{{iban:"IT60X0542811101000000123456", banche:[]}}}})')
    pid = s.post(f"{API}/parties", json=party("TEST_T20UI Cliente")).json()["id"]
    print(json.dumps({"cid": cid, "pid": pid}))


if __name__ == "__main__":
    seed() if sys.argv[1] == "seed" else clean()

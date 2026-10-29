# Seeds TEST_T6 admin + company + client + 1 sent invoice + 1 scartata for UI testing (cleanup with --clean)
import sys
import subprocess
import requests
from test_iteration6_numbering_lock import API, TOK, UID, mongo, doc, D

if "--clean" in sys.argv:
    c = mongo('const c=db.companies.findOne({partita_iva:"66666666662"}); print(c?c.id:"")')
    if c:
        mongo(f'db.invoices.deleteMany({{company_id:"{c}"}}); db.parties.deleteMany({{company_id:"{c}"}}); db.counters.deleteMany({{key:"progressivo_{c}"}}); db.companies.deleteMany({{id:"{c}"}});')
    mongo(f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')
    print("cleaned")
    sys.exit()

mongo(f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});'
      f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t6.admin@example.com", name:"TEST_T6 Admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
      f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+7*864e5), created_at:new Date().toISOString()}});')
s = requests.Session()
s.headers["Authorization"] = f"Bearer {TOK}"
mongo('db.companies.deleteMany({partita_iva:"66666666662"})')
cid = s.post(f"{API}/companies", json={"denominazione": "TEST_T6 UI Srl", "partita_iva": "66666666662", "codice_fiscale": "66666666662",
                                       "regime_fiscale": "RF01", "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"}).json()["id"]
h = {"X-Company-Id": cid}
pid = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": "TEST_T6 Cliente UI", "partita_iva": "01234567890", "codice_destinatario": "ABC1234",
                                     "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"}, headers=h).json()["id"]
i1 = s.post(f"{API}/invoices", json=doc(pid, D(20)), headers=h).json()["id"]
s.post(f"{API}/invoices/{i1}/send", headers=h)
i2 = s.post(f"{API}/invoices", json=doc(pid, D(15)), headers=h).json()["id"]
s.post(f"{API}/invoices/{i2}/send", headers=h)
mongo(f'db.invoices.updateOne({{id:"{i2}"}}, {{$set:{{status:"scartata"}}}})')
print(f"CID={cid} PID={pid} SENT={i1} SCARTATA={i2}")

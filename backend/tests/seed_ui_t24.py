# Seed for iteration 24 UI test: TEST_ admin session + company with simulato SDI. Prints cid.
import requests
from test_iteration7_pa_scartate_registro import API, mongo
UID, TOK, PA = "test-user-t24ui-admin", "test_session_t24ui_admin", "86999999243"
mongo(f'db.companies.find({{partita_iva:"{PA}"}}).forEach(c=>{{db.passive_invoices.deleteMany({{company_id:c.id}}); db.parties.deleteMany({{company_id:c.id}}); db.companies.deleteOne({{id:c.id}});}});'
      f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});'
      f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t24ui@example.com", name:"TEST_t24ui", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
      f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
r = requests.post(f"{API}/companies", headers={"Authorization": f"Bearer {TOK}"}, json={"denominazione": "TEST_T24UI Srl", "partita_iva": PA, "codice_fiscale": PA, "regime_fiscale": "RF01",
                  "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
print(r.json()["id"])

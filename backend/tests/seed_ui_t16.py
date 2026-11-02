# Seed for iteration 16 UI test: TEST_T16UI company + users (with password / invite pending). Usage: python seed_ui_t16.py [clean]
import sys
import requests
from test_iteration7_pa_scartate_registro import API, mongo

if len(sys.argv) > 1 and sys.argv[1] == "clean":
    mongo('db.companies.deleteMany({denominazione:/^TEST_T16UI/}); var ids=db.users.find({email:/^test\\.user\\.t16ui/}).toArray().map(u=>u.user_id);'
          'db.user_sessions.deleteMany({user_id:{$in:ids}}); db.password_reset_tokens.deleteMany({user_id:{$in:ids}}); db.users.deleteMany({email:/^test\\.user\\.t16ui/});')
    print("cleaned")
    sys.exit()
s = requests.Session()
assert s.post(f"{API}/auth/login", json={"email": "fabrizio.gemignani@gmail.com", "password": "Fe-Admin-2aOBey8irzL8"}).status_code == 200
r = s.post(f"{API}/companies", json={"denominazione": "TEST_T16UI Srl", "partita_iva": "86123456789", "codice_fiscale": "86123456789", "regime_fiscale": "RF01",
                                     "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
print(r.status_code, r.json().get("id"))
print(requests.post(f"{API}/auth/register", json={"name": "TEST_T16UI Pwd", "email": "test.user.t16ui.pwd@example.com", "password": "Password123"}).status_code)
print(s.post(f"{API}/users", json={"name": "TEST_T16UI Inv", "email": "test.user.t16ui.inv@example.com", "role": "operatore", "send_invite": False}).status_code)
s.post(f"{API}/auth/logout")

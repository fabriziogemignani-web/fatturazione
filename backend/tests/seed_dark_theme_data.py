# Creates/deletes TEST_ data (client + invoice draft) for dark theme visual review. Usage: python seed_dark_theme_data.py create|delete
import sys, json, requests
BASE = [l.split("=", 1)[1].strip() for l in open("/app/frontend/.env") if l.startswith("REACT_APP_BACKEND_URL=")][0].rstrip("/")
API = f"{BASE}/api"
s = requests.Session()
r = s.post(f"{API}/auth/login", json={"email": "fabrizio.gemignani@gmail.com", "password": "Fe-Admin-2aOBey8irzL8"})
print("login", r.status_code)
cs = s.get(f"{API}/companies").json()
cid = [c for c in cs if c.get("denominazione") == "TEST_SCREEN Srl"][0]["id"]
s.headers["X-Company-Id"] = cid
if sys.argv[1] == "create":
    p = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": "TEST_DARK_Cliente", "partita_iva": "12345678901", "codice_fiscale": "12345678901",
           "codice_destinatario": "ABC1234", "pec": "", "indirizzo": "Via Test 2", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"})
    print("party", p.status_code, p.text[:200])
    pid = p.json()["id"]
    i = s.post(f"{API}/invoices", json={"tipo_documento": "TD01", "data": "2026-01-15", "party_id": pid, "modalita_pagamento": "MP05",
           "lines": [{"descrizione": "TEST riga dark", "quantita": 2, "prezzo_unitario": 100, "aliquota": 22}]})
    print("invoice", i.status_code, i.text[:200])
    json.dump({"pid": pid, "iid": i.json().get("id")}, open("/tmp/dark_ids.json", "w"))
else:
    ids = json.load(open("/tmp/dark_ids.json"))
    print("del inv", s.delete(f"{API}/invoices/{ids['iid']}").status_code)
    print("del party", s.delete(f"{API}/parties/{ids['pid']}").status_code)

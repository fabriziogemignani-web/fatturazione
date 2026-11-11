# UI fixture helper for iteration 48 Layout documenti (setup|clean). TEST_T48UI company, admin+operatore sessions, TD01 + TD04 with causale/notes/scadenza.
import json
import os
import subprocess
import sys
from datetime import date, timedelta

import requests

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
USERS = {"admin": ("test-user-t48ui", "test_session_t48ui"), "operatore": ("test-user-t48ui-op", "test_session_t48ui_op")}
COLLS = '["invoices","parties","payments","coa_entries","coa_accounts","coa_causali","coa_iva","audit","sdi_events","com_log"]'
T = date.today()


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


def clean():
    ids = "[" + ",".join(f'"{u}"' for u, _ in USERS.values()) + "]"
    mongo(f'db.companies.find({{denominazione:/^TEST_T48UI/}}).forEach(c=>{{{COLLS}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          'db.counters.deleteMany({key:{$regex:c.id}}); db.users.updateMany({}, {$pull:{company_ids:c.id}}); db.companies.deleteOne({id:c.id});});'
          f'db.users.deleteMany({{user_id:{{$in:{ids}}}}}); db.user_sessions.deleteMany({{user_id:{{$in:{ids}}}}});')


def setup():
    clean()
    for role, (uid, tok) in USERS.items():
        mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.{uid}@example.com", name:"TEST_ui48_{role}", picture:"", role:"{role}", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
              f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {USERS['admin'][1]}"
    c = s.post(f"{API}/companies", json={"denominazione": "TEST_T48UI Alfa Srl", "partita_iva": "01234567897", "codice_fiscale": "01234567897", "regime_fiscale": "RF01",
                                         "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT",
                                         "iban": "IT60X0542811101000000123456"}).json()
    s.headers["X-Company-Id"] = c["id"]
    mongo(f'db.users.updateMany({{user_id:"{USERS["operatore"][0]}"}}, {{$set:{{company_ids:["{c["id"]}"]}}}});')
    p = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": "TEST_T48UI Cliente", "partita_iva": "02345670481", "codice_fiscale": "02345670481",
                                       "codice_destinatario": "ABC1234", "pec": "cli@pec.example.com", "email": "cli@example.com", "indirizzo": "Via X 1",
                                       "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"}).json()
    base = {"data": T.isoformat(), "party_id": p["id"], "modalita_pagamento": "MP05", "causale": "CAUSALE_UI48", "scadenza": (T + timedelta(days=30)).isoformat(),
            "lines": [{"descrizione": "TEST riga", "note": "NOTA_UI48", "quantita": 1, "prezzo_unitario": 100, "aliquota": 22}]}
    inv = s.post(f"{API}/invoices", json={**base, "tipo_documento": "TD01"}).json()
    s.post(f"{API}/invoices/{inv['id']}/send").raise_for_status()
    s.post(f"{API}/invoices/{inv['id']}/refresh")
    nc = s.post(f"{API}/invoices", json={**base, "tipo_documento": "TD04", "fattura_collegata_id": inv["id"]})
    print(json.dumps({"cid": c["id"], "inv": inv["id"], "nc": nc.json().get("id"), "nc_status": nc.status_code}))


if __name__ == "__main__":
    setup() if sys.argv[1] == "setup" else clean()

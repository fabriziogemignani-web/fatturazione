# UI fixture helper for iteration 53 plafond hint (setup|clean). TEST_T53UI company, client A (N3.5 + declaration 10000), client B (N3.5, no declaration),
# client C (normal), draft D for A (3000 N3.5), sent invoice S for A (2000 N3.5) for credit note.
import json
import os
import subprocess
import sys
from datetime import date

import requests

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
UID, TOK = "test-user-t53ui", "test_session_t53ui"
PIVA = "86000053501"
COLLS = '["invoices","passive_invoices","parties","payments","passive_payments","coa_entries","coa_accounts","coa_causali","coa_iva","audit","sdi_events","intenti","partite_aperte"]'
T = date.today()


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


def clean():
    mongo(f'db.companies.find({{partita_iva:"{PIVA}"}}).forEach(c=>{{{COLLS}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          'db.counters.deleteMany({key:{$regex:c.id}}); db.users.updateMany({}, {$pull:{company_ids:c.id}}); db.companies.deleteOne({id:c.id});});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def party(s, name, piva, cf, **kw):
    r = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": name, "partita_iva": piva, "codice_fiscale": cf, "codice_destinatario": "ABC1234",
                                       "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT", **kw})
    r.raise_for_status()
    return r.json()["id"]


def inv(s, pid, amount):
    r = s.post(f"{API}/invoices", json={"tipo_documento": "TD01", "data": T.isoformat(), "party_id": pid, "modalita_pagamento": "MP05",
                                        "lines": [{"descrizione": "TEST riga N3.5", "quantita": 1, "prezzo_unitario": amount, "aliquota": 0, "natura": "N3.5"}]})
    r.raise_for_status()
    return r.json()["id"]


def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.{UID}@example.com", name:"TEST_ui53", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    c = s.post(f"{API}/companies", json={"denominazione": "TEST_T53UI Plafond Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                         "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"}).json()
    s.headers["X-Company-Id"] = c["id"]
    ids = {"cid": c["id"]}
    ids["A"] = party(s, "TEST_T53UI Esportatore Srl", "01234567890", "RSSMRA80A01H501U", natura_default="N3.5")
    ids["B"] = party(s, "TEST_T53UI Senza Dich Srl", "09876543210", "VRDLGU80A01H501X", natura_default="N3.5")
    ids["C"] = party(s, "TEST_T53UI Normale Srl", "11122233344", "BNCGNN80A01H501Y")
    r = s.post(f"{API}/intenti", json={"party_id": ids["A"], "protocollo": "12345678901234567-000053", "data": f"{T.year}-01-01", "anno": T.year, "importo": 10000})
    r.raise_for_status()
    ids["DECL"] = r.json()["id"]
    ids["S"] = inv(s, ids["A"], 2000)
    s.post(f"{API}/invoices/{ids['S']}/send").raise_for_status()
    s.post(f"{API}/invoices/{ids['S']}/refresh")
    ids["D"] = inv(s, ids["A"], 3000)
    print(json.dumps(ids))


if __name__ == "__main__":
    setup() if sys.argv[1] == "setup" else clean()

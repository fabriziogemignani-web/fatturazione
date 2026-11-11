# UI fixture helper for iteration 50 Ri.Ba./scadenze/fornitore da verificare (setup|clean). TEST_T50UI company with bank+SIA, client with appoggio, MP12 invoices.
import json
import os
import subprocess
import sys
from datetime import date, timedelta

import requests

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
UID, TOK = "test-user-t50ui", "test_session_t50ui"
PIVA = "86000050501"
COLLS = '["invoices","passive_invoices","parties","payments","passive_payments","coa_entries","coa_accounts","coa_causali","coa_iva","audit","sdi_events","riba_distinte","riba_effetti","partite_aperte"]'
T = date.today()
d = lambda n: (T + timedelta(days=n)).isoformat()  # noqa: E731


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


def clean():
    mongo(f'db.companies.find({{partita_iva:"{PIVA}"}}).forEach(c=>{{{COLLS}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          'db.counters.deleteMany({key:{$regex:c.id}}); db.users.updateMany({}, {$pull:{company_ids:c.id}}); db.companies.deleteOne({id:c.id});});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def inv(s, pid, data, rate, mp="MP12"):
    r = s.post(f"{API}/invoices", json={"tipo_documento": "TD01", "data": data, "party_id": pid, "modalita_pagamento": mp, "scadenza": rate[-1][0],
                                        "rate": [{"scadenza": a, "importo": b} for a, b in rate],
                                        "lines": [{"descrizione": "TEST riga", "quantita": 1, "prezzo_unitario": 100, "aliquota": 22}]})
    r.raise_for_status()
    iid = r.json()["id"]
    s.post(f"{API}/invoices/{iid}/send").raise_for_status()
    s.post(f"{API}/invoices/{iid}/refresh")
    return iid


def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.{UID}@example.com", name:"TEST_ui50", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    c = s.post(f"{API}/companies", json={"denominazione": "TEST_T50UI Riba Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                         "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT",
                                         "iban": "IT60X0542811101000000123456"}).json()
    s.headers["X-Company-Id"] = c["id"]
    s.put(f"{API}/companies/{c['id']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True, "corrispettivi": True, "contabilita": True})
    p = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": "TEST_T50UI Cliente Srl", "partita_iva": "01234567890", "codice_fiscale": "01234567890",
                                       "codice_destinatario": "ABC1234", "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"}).json()
    ids = {"cid": c["id"], "cli": p["id"]}
    ids["P"] = inv(s, p["id"], d(-40), [(d(-10), 122)])
    ids["F"] = inv(s, p["id"], d(-5), [(d(30), 60), (d(60), 62)])
    ids["S"] = inv(s, p["id"], d(-5), [(d(30), 122)], mp="MP05")
    print(json.dumps(ids))


if __name__ == "__main__":
    setup() if sys.argv[1] == "setup" else clean()

# UI fixture helper for iteration 45 (setup|clean). Creates TEST_T45UI company, session, client (with listino), articles, stock.
import json
import os
import subprocess
import sys
from datetime import date

import requests

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
UID, TOK = "test-user-t45ui", "test_session_t45ui"


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


def clean():
    mongo('db.companies.find({partita_iva:"01234567897", denominazione:/^TEST_T45UI/}).forEach(c=>{["invoices","parties","articles","stock_moves","ddts","payments","coa_entries","coa_accounts","coa_causali","coa_iva","audit","sdi_events"].forEach(k=>db[k].deleteMany({company_id:c.id}));'
          'db.counters.deleteMany({key:{$regex:c.id}}); db.users.updateMany({}, {$pull:{company_ids:c.id}}); db.companies.deleteOne({id:c.id});});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t45ui@example.com", name:"TEST_ui45", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    c = s.post(f"{API}/companies", json={"denominazione": "TEST_T45UI Alfa Srl", "partita_iva": "01234567897", "codice_fiscale": "01234567897", "regime_fiscale": "RF01",
                                         "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"}).json()
    s.headers["X-Company-Id"] = c["id"]
    out = {"cid": c["id"]}
    for k, mag, pr in (("MAG", True, 10), ("NOMAG", False, 7)):
        out[k] = s.post(f"{API}/articles", json={"codice": f"T45{k}", "descrizione": f"TEST art {k}", "unita_misura": "PZ", "prezzo": pr, "aliquota": 22, "gestione_magazzino": mag}).json()["id"]
    s.post(f"{API}/magazzino/movimenti", json={"article_id": out["MAG"], "tipo": "carico", "data": f"{date.today().year}-01-01", "quantita": 5, "costo_unitario": 5, "causale": "Acquisto"})
    for k, name, piva in (("cli", "TEST_T45UI Cliente Spa", "02345670481"), ("cli2", "TEST_T45UI Altro Srl", "00743110157")):
        out[k] = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "codice_destinatario": "ABC1234",
                                                "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"}).json()["id"]
    print(json.dumps(out))


if __name__ == "__main__":
    setup() if sys.argv[1] == "setup" else clean()

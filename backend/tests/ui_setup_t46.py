# UI fixture helper for iteration 46 DDT signatures (setup|clean). Creates TEST_T46UI company, admin+operatore sessions, client, confirmed + bozza DDT.
import json
import os
import subprocess
import sys
from datetime import date

import requests

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
USERS = {"admin": ("test-user-t46ui", "test_session_t46ui"), "operatore": ("test-user-t46ui-op", "test_session_t46ui_op")}


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


def clean():
    ids = "[" + ",".join(f'"{u}"' for u, _ in USERS.values()) + "]"
    mongo('db.companies.find({partita_iva:"01234567897", denominazione:/^TEST_T46UI/}).forEach(c=>{["invoices","parties","articles","stock_moves","ddts","payments","coa_entries","coa_accounts","coa_causali","coa_iva","audit","sdi_events"].forEach(k=>db[k].deleteMany({company_id:c.id}));'
          'db.counters.deleteMany({key:{$regex:c.id}}); db.users.updateMany({}, {$pull:{company_ids:c.id}}); db.companies.deleteOne({id:c.id});});'
          f'db.users.deleteMany({{user_id:{{$in:{ids}}}}}); db.user_sessions.deleteMany({{user_id:{{$in:{ids}}}}});')


def setup():
    clean()
    for role, (uid, tok) in USERS.items():
        mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.{uid}@example.com", name:"TEST_ui46_{role}", picture:"", role:"{role}", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
              f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {USERS['admin'][1]}"
    c = s.post(f"{API}/companies", json={"denominazione": "TEST_T46UI Alfa Srl", "partita_iva": "01234567897", "codice_fiscale": "01234567897", "regime_fiscale": "RF01",
                                         "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"}).json()
    s.headers["X-Company-Id"] = c["id"]
    mongo(f'db.users.updateMany({{user_id:"{USERS["operatore"][0]}"}}, {{$set:{{company_ids:["{c["id"]}"]}}}});')
    out = {"cid": c["id"]}
    out["cli"] = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": "TEST_T46UI Cliente Spa", "partita_iva": "02345670481", "codice_fiscale": "02345670481",
                                               "codice_destinatario": "ABC1234", "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"}).json()["id"]
    body = {"data": date.today().isoformat(), "party_id": out["cli"], "causale": "Vendita", "porto": "assegnato", "trasporto_a_cura": "vettore",
            "vettore": {"denominazione": "TEST Vettore Express", "partita_iva": "11111111111", "indirizzo": "Via Corriere 9"}, "colli": 2,
            "lines": [{"descrizione": "TEST riga UI firma", "quantita": 3, "unita_misura": "PZ", "prezzo_unitario": 12.34, "aliquota": 22}]}
    for k in ("conf", "bozza"):
        out[k] = s.post(f"{API}/ddt", json=body).json()["id"]
    s.post(f"{API}/ddt/{out['conf']}/conferma", json={"forza": True}).raise_for_status()
    print(json.dumps(out))


if __name__ == "__main__":
    setup() if sys.argv[1] == "setup" else clean()

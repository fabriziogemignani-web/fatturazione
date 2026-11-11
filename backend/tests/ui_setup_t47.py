# UI fixture helper for iteration 47 Importazione di massa (setup|clean). Creates TEST_T47UI company, admin+operatore sessions, and two xlsx files in /tmp.
import io
import json
import os
import subprocess
import sys

import requests
from openpyxl import load_workbook

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
USERS = {"admin": ("test-user-t47ui", "test_session_t47ui"), "operatore": ("test-user-t47ui-op", "test_session_t47ui_op")}
COLLS = '["invoices","parties","articles","stock_moves","payments","passive_payments","coa_entries","coa_accounts","coa_causali","coa_iva","audit","partite_aperte","import_batches"]'


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


def clean():
    ids = "[" + ",".join(f'"{u}"' for u, _ in USERS.values()) + "]"
    mongo(f'db.companies.find({{partita_iva:"01234567897", denominazione:/^TEST_T47UI/}}).forEach(c=>{{{COLLS}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          'db.counters.deleteMany({key:{$regex:c.id}}); db.users.updateMany({}, {$pull:{company_ids:c.id}}); db.companies.deleteOne({id:c.id});});'
          f'db.users.deleteMany({{user_id:{{$in:{ids}}}}}); db.user_sessions.deleteMany({{user_id:{{$in:{ids}}}}});')


def setup():
    clean()
    for role, (uid, tok) in USERS.items():
        mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.{uid}@example.com", name:"TEST_ui47_{role}", picture:"", role:"{role}", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
              f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {USERS['admin'][1]}"
    c = s.post(f"{API}/companies", json={"denominazione": "TEST_T47UI Alfa Srl", "partita_iva": "01234567897", "codice_fiscale": "01234567897", "regime_fiscale": "RF01",
                                         "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"}).json()
    s.headers["X-Company-Id"] = c["id"]
    mongo(f'db.users.updateMany({{user_id:"{USERS["operatore"][0]}"}}, {{$set:{{company_ids:["{c["id"]}"]}}}});')
    s.get(f"{API}/contabilita/conti").raise_for_status()
    wb = load_workbook(io.BytesIO(s.get(f"{API}/importazione/modello").content))
    wb["Clienti"].append(["TEST_T47UI Cliente", "02345670481", "02345670481", "", "", "", "", "Via X 1", "20100", "Milano", "MI", "IT"])
    wb["Clienti"].append(["TEST_T47UI Errato", "", "", "", "", "", "", "Via X 1", "20100", "Milano", "MI", "IT"])
    wb["Articoli"].append(["T47UI-1", "TEST articolo UI", "PZ", 10, 22, "", "SI", "", "", ""])
    wb["Giacenze"].append(["T47UI-1", "01/01/2025", 5, 3])
    wb["SaldiContabili"].append(["01/01/2025", "02.01.002", "", 100, ""])
    wb["SaldiContabili"].append(["01/01/2025", "01.01.001", "", "", 100])
    wb["PartiteAperte"].append(["cliente", "02345670481", "UI-OLD-1", "01/12/2024", "31/01/2025", 50])
    wb.save("/tmp/t47_ok.xlsx")
    wb["SaldiContabili"].append(["01/01/2025", "01.01.001", "", "", 5])
    wb.save("/tmp/t47_bad.xlsx")
    print(json.dumps({"cid": c["id"]}))


if __name__ == "__main__":
    setup() if sys.argv[1] == "setup" else clean()

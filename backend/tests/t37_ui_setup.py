# Helper for iteration 37 UI test (Comunicazioni): `python t37_ui_setup.py setup` | `python t37_ui_setup.py clean <cid>`
import json
import os
import subprocess
import sys
from datetime import date, timedelta

import requests

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


def piva(b):
    s = 0
    for i, ch in enumerate(b):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            d = d - 9 if d > 9 else d
        s += d
    return b + str((10 - s % 10) % 10)


if sys.argv[1] == "setup":
    s = requests.Session()
    assert s.post(f"{API}/auth/login", json={"email": "fabrizio.gemignani@gmail.com", "password": "Fe-Admin-2aOBey8irzL8"}).status_code == 200
    co = piva("0987123452")
    r = s.post(f"{API}/companies", json={"denominazione": "TEST_T37 UI Srl", "partita_iva": co, "codice_fiscale": co, "regime_fiscale": "RF01",
                                         "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    cid = r.json()["id"]
    s.headers["X-Company-Id"] = cid
    out = {"cid": cid}
    today = date.today()
    pids = []
    for name, pv, em in [("TEST_Alfa UI Srl", piva("0123456781"), "alfa@example.com"), ("TEST_Beta UI Spa", piva("0555666771"), "beta@example.com")]:
        pids.append(s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": name, "partita_iva": pv, "codice_fiscale": pv, "codice_destinatario": "ABC1234",
                                                   "email": em, "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"}).json()["id"])
    for pid, ago, scad in [(pids[0], 30, -25), (pids[1], 2, 3)]:
        iid = s.post(f"{API}/invoices", json={"tipo_documento": "TD01", "data": (today - timedelta(days=ago)).isoformat(), "party_id": pid, "modalita_pagamento": "MP05",
                                              "scadenza": (today + timedelta(days=scad)).isoformat(),
                                              "lines": [{"descrizione": "TEST riga", "quantita": 1, "prezzo_unitario": 100, "aliquota": 22}]}).json()["id"]
        s.post(f"{API}/invoices/{iid}/send")
        s.post(f"{API}/invoices/{iid}/refresh")
    out["esegui_no_smtp"] = s.post(f"{API}/comunicazioni/esegui").json()
    print(json.dumps(out))
else:
    cid = sys.argv[2]
    print(mongo(f'["invoices","parties","payments","coa_entries","coa_accounts","coa_causali","coa_iva","sdi_events","audit","com_log"].forEach(k=>db[k].deleteMany({{company_id:"{cid}"}})); '
                f'db.counters.deleteMany({{key:{{$regex:"{cid}"}}}}); db.users.updateMany({{}},{{$pull:{{company_ids:"{cid}"}}}}); db.companies.deleteOne({{id:"{cid}"}}); print("cleaned")'))

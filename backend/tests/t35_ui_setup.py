# Helper for iteration 35 UI test (search picker in Mastrini/Scadenzario): `python t35_ui_setup.py setup` | `python t35_ui_setup.py clean <cid>`
import json
import os
import subprocess
import sys
from datetime import date, timedelta

import requests

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
PIVA_CO = "09876543217"


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


def piva(base10):
    s = 0
    for i, ch in enumerate(base10):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            d = d - 9 if d > 9 else d
        s += d
    return base10 + str((10 - s % 10) % 10)


def login():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "fabrizio.gemignani@gmail.com", "password": "Fe-Admin-2aOBey8irzL8"})
    assert r.status_code == 200, r.text
    return s


if sys.argv[1] == "setup":
    s = login()
    co = piva("0987654321")
    r = s.post(f"{API}/companies", json={"denominazione": "TEST_T35 Search Srl", "partita_iva": co, "codice_fiscale": co, "regime_fiscale": "RF01",
                                         "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    s.headers["X-Company-Id"] = cid
    out = {"cid": cid}
    for key, tipo, name, pv in [("c1", "cliente", "TEST_Alfa Ricambi Srl", piva("0123456789")), ("c2", "cliente", "TEST_Beta Servizi Spa", piva("0555666777")),
                                ("f1", "fornitore", "TEST_Gamma Forniture Srl", piva("0888999111")), ("f2", "fornitore", "TEST_Delta Energia Srl", piva("0222333444"))]:
        r = s.post(f"{API}/parties", json={"tipo": tipo, "denominazione": name, "partita_iva": pv, "codice_fiscale": pv, "codice_destinatario": "ABC1234",
                                           "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"})
        assert r.status_code == 200, (key, r.text)
        out[key] = r.json()["id"]
        out[key + "_piva"] = pv
    today = date.today()
    for key, pid, price, days_ago, scad in [("i1", out["c1"], 100, 40, -10), ("i2", out["c2"], 300, 5, 25)]:
        r = s.post(f"{API}/invoices", json={"tipo_documento": "TD01", "data": (today - timedelta(days=days_ago)).isoformat(), "party_id": pid, "modalita_pagamento": "MP05",
                                            "scadenza": (today + timedelta(days=scad)).isoformat(),
                                            "lines": [{"descrizione": "TEST riga", "quantita": 1, "prezzo_unitario": price, "aliquota": 22}]})
        assert r.status_code == 200, r.text
        iid = r.json()["id"]
        assert s.post(f"{API}/invoices/{iid}/send").status_code == 200
        rr = s.post(f"{API}/invoices/{iid}/refresh")
        assert rr.status_code == 200, rr.text
        out[key] = iid
        out[key + "_status"] = rr.json().get("status")
    r = s.post(f"{API}/contabilita/registrazioni", json={"data": today.isoformat(), "causale": "GE", "descrizione": "TEST_man forn",
                                                         "righe": [{"conto": "30.07.011", "dare": 50}, {"conto": "13.02.001", "avere": 50, "party_id": out["f1"]}]})
    out["man"] = (r.status_code, r.text[:200])
    print(json.dumps(out))
else:
    cid = sys.argv[2]
    print(mongo(f'["invoices","passive_invoices","parties","articles","payments","passive_payments","bank_tx","bank_accounts","corrispettivi","coa_accounts","coa_causali","coa_iva","coa_entries","sdi_events","audit"].forEach(k=>db[k].deleteMany({{company_id:"{cid}"}})); '
                f'db.counters.deleteMany({{key:{{$regex:"{cid}"}}}}); db.users.updateMany({{}},{{$pull:{{company_ids:"{cid}"}}}}); db.companies.deleteOne({{id:"{cid}"}}); print("cleaned")'))

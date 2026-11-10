# Helper for iteration 41 UI test: adds a no-email client with a delivered invoice + a draft to an existing company. `python t41_ui_setup.py <cid> <client_id>`
import json
import os
import sys
from datetime import date, timedelta

import requests

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
cid, cli = sys.argv[1], sys.argv[2]
s = requests.Session()
assert s.post(f"{API}/auth/login", json={"email": "fabrizio.gemignani@gmail.com", "password": "Fe-Admin-2aOBey8irzL8"}).status_code == 200
s.headers["X-Company-Id"] = cid
r = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": "TEST_T41 NoMail UI", "partita_iva": "08889991115", "codice_fiscale": "",
                                   "codice_destinatario": "ABC1234", "email": "", "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"})
assert r.status_code == 200, r.text
nm = r.json()["id"]


def mk(pid, send=True):
    r = s.post(f"{API}/invoices", json={"tipo_documento": "TD01", "data": (date.today() - timedelta(days=1)).isoformat(), "party_id": pid, "modalita_pagamento": "MP05",
                                        "scadenza": (date.today() + timedelta(days=30)).isoformat(),
                                        "lines": [{"descrizione": "TEST_riga", "quantita": 1, "prezzo_unitario": 50, "aliquota": 22}]})
    assert r.status_code == 200, r.text
    iid = r.json()["id"]
    if send:
        s.post(f"{API}/invoices/{iid}/send")
        s.post(f"{API}/invoices/{iid}/refresh")
    return iid


print(json.dumps({"nomail_party": nm, "nomail_inv": mk(nm), "draft": mk(cli, send=False)}))

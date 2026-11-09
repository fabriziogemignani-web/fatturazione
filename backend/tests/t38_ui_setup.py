# Helper for iteration 38 UI test (IVA indetraibile): `python t38_ui_setup.py setup` | `python t38_ui_setup.py clean <cid>`
import json
import os
import subprocess
import sys
from datetime import date, timedelta

import requests

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
FIX = open(os.path.join(os.path.dirname(__file__), "fixtures", "sample_fattura.xml")).read()


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


if sys.argv[1] == "setup":
    s = requests.Session()
    assert s.post(f"{API}/auth/login", json={"email": "fabrizio.gemignani@gmail.com", "password": "Fe-Admin-2aOBey8irzL8"}).status_code == 200
    co = "88123456380"
    r = s.post(f"{API}/companies", json={"denominazione": "TEST_T38 UI Srl", "partita_iva": co, "codice_fiscale": co, "regime_fiscale": "RF01",
                                         "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    s.headers["X-Company-Id"] = cid
    f = s.post(f"{API}/parties", json={"tipo": "fornitore", "denominazione": "TEST_T38 Carburanti UI", "partita_iva": "02345670481", "codice_fiscale": "",
                                       "indirizzo": "Via Y 1", "cap": "50100", "comune": "Firenze", "provincia": "FI", "nazione": "IT", "detraibilita_iva": 40})
    assert f.status_code == 200, f.text
    d1 = (date.today() - timedelta(days=5)).isoformat()
    xml = FIX.replace("<IdCodice>01234567890</IdCodice>", f"<IdCodice>{co}</IdCodice>").replace("<Numero>5674/2026</Numero>", "<Numero>TEST38UI-1</Numero>") \
        .replace("<Data>2026-10-30</Data>", f"<Data>{d1}</Data>")
    up = s.post(f"{API}/passive/upload", files=[("files", ("p.xml", xml, "text/xml"))])
    assert up.status_code == 200, up.text
    pid = mongo(f'print(db.passive_invoices.findOne({{company_id:"{cid}"}}).id)')
    print(json.dumps({"cid": cid, "forn": f.json()["id"], "pas": pid}))
else:
    cid = sys.argv[2]
    print(mongo(f'["invoices","passive_invoices","parties","payments","passive_payments","coa_entries","coa_accounts","coa_causali","coa_iva","sdi_events","audit","com_log"].forEach(k=>db[k].deleteMany({{company_id:"{cid}"}})); '
                f'db.counters.deleteMany({{key:{{$regex:"{cid}"}}}}); db.users.updateMany({{}},{{$pull:{{company_ids:"{cid}"}}}}); db.companies.deleteOne({{id:"{cid}"}}); print("cleaned")'))

# UI fixture helper for iteration 54 (setup|clean): TEST_T54UI company (codice destinatario set), passive A (IT supplier 22% + N6.3 1000),
# B (22% only), C (DE supplier N2.1 500), foreign supplier party FR for registrazione veloce.
import json
import os
import subprocess
import sys
from datetime import date, timedelta

import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration13_reverse_charge import rc_xml  # noqa: E402

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
UID, TOK = "test-user-t54ui", "test_session_t54ui"
PIVA = "86000054501"
COLLS = '["invoices","passive_invoices","parties","payments","passive_payments","coa_entries","coa_accounts","coa_causali","coa_iva","audit","sdi_events","intenti","partite_aperte"]'
T = date.today()
D1 = max(T - timedelta(days=5), date(T.year, 1, 1)).isoformat()


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


def clean():
    mongo(f'db.companies.find({{partita_iva:"{PIVA}"}}).forEach(c=>{{{COLLS}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          'db.counters.deleteMany({key:{$regex:c.id}}); db.users.updateMany({}, {$pull:{company_ids:c.id}}); db.companies.deleteOne({id:c.id});});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def mk(numero, rc=(("N6.3", 1000.0),), keep22=True, foreign=False):
    x = rc_xml(numero, data=D1, rc=rc, keep22=keep22).decode().replace("<IdCodice>01234567890</IdCodice>", f"<IdCodice>{PIVA}</IdCodice>")
    if foreign:
        x = x.replace("<IdPaese>IT</IdPaese>\n          <IdCodice>02345670481</IdCodice>", "<IdPaese>DE</IdPaese>\n          <IdCodice>811569869</IdCodice>", 1)
        x = x.replace("<CodiceFiscale>02345670481</CodiceFiscale>", "").replace("DEMO Energia Toscana SpA", "TEST_T54UI Berlin GmbH")
        x = x.replace("<CAP>50126</CAP>", "<CAP>10115</CAP>").replace("<Comune>Firenze</Comune>", "<Comune>Berlin</Comune>").replace("<Provincia>FI</Provincia>", "")
        x = x.replace("<Nazione>IT</Nazione>", "<Nazione>DE</Nazione>", 1)
    return x.encode()


def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.{UID}@example.com", name:"TEST_ui54", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    c = s.post(f"{API}/companies", json={"denominazione": "TEST_T54UI Passive Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                         "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"}).json()
    mongo(f'db.companies.updateOne({{id:"{c["id"]}"}}, {{$set:{{codice_destinatario:"M5UXCR1"}}}})')
    s.headers["X-Company-Id"] = c["id"]
    ids = {"cid": c["id"]}
    for k, xml in (("A", mk("T54UI-A")), ("B", mk("T54UI-B", rc=())), ("C", mk("T54UI-C", rc=(("N2.1", 500.0),), keep22=False, foreign=True))):
        r = s.post(f"{API}/passive/upload", files=[("files", (f"{k}.xml", xml, "application/octet-stream"))])
        r.raise_for_status()
        ids[k] = r.json()[0]["documenti"][0]["id"]
    r = s.post(f"{API}/parties", json={"tipo": "fornitore", "denominazione": "TEST_T54UI Paris SARL", "partita_iva": "12345678901", "codice_fiscale": "",
                                       "indirizzo": "Rue X 1", "cap": "75001", "comune": "Paris", "provincia": "", "nazione": "FR"})
    r.raise_for_status()
    ids["FR"] = r.json()["id"]
    print(json.dumps(ids))


if __name__ == "__main__":
    setup() if sys.argv[1] == "setup" else clean()

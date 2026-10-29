# Seeds TEST_T7 UI data: admin session, company, PA split client, B2B 0000000 client, scartata invoice,
# PA invoice with CIG/CUP, registro gap (n.2 free) in previous year. Cleanup with --clean
import sys
import json
import requests
from test_iteration7_pa_scartate_registro import API, mongo, party, inv, PREV

TOK, UID, PIVA = "test_session_t7_ui", "test-user-t7-ui", "77777777772"


def clean():
    c = mongo(f'const c=db.companies.findOne({{partita_iva:"{PIVA}"}}); print(c?c.id:"")')
    if c:
        mongo(f'db.invoices.deleteMany({{company_id:"{c}"}}); db.parties.deleteMany({{company_id:"{c}"}}); db.counters.deleteMany({{key:"progressivo_{c}"}}); db.companies.deleteMany({{id:"{c}"}});')
    mongo(f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


clean()
if "--clean" in sys.argv:
    print("cleaned")
    sys.exit()
mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t7.ui@example.com", name:"TEST_T7 UI", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
      f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+7*864e5), created_at:new Date().toISOString()}});')
s = requests.Session()
s.headers["Authorization"] = f"Bearer {TOK}"
cid = s.post(f"{API}/companies", json={"denominazione": "TEST_T7 UI Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                       "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"}).json()["id"]
h = {"X-Company-Id": cid}
pa = s.post(f"{API}/parties", json=party("TEST_T7 Comune di Prova", codice="UFAB12", pa=True, split=True, piva="80012345678"), headers=h).json()["id"]
bad = s.post(f"{API}/parties", json=party("TEST_T7 B2B NoPEC", codice="", piva="01234567891"), headers=h).json()["id"]
b2b = s.post(f"{API}/parties", json=party("TEST_T7 B2B OK", codice="ABC1234", piva="01234567892"), headers=h).json()["id"]
ipa = s.post(f"{API}/invoices", json=inv(pa, rif_documento="ORD-15", rif_data="2026-01-10", cig="ABCDE12345", cup="J12F34000560007"), headers=h).json()["id"]
sc = s.post(f"{API}/invoices", json=inv(bad, price=500), headers=h).json()["id"]
s.post(f"{API}/invoices/{sc}/send", headers=h)
st = s.post(f"{API}/invoices/{sc}/refresh", headers=h).json()["status"]
ids = [s.post(f"{API}/invoices", json=inv(b2b, data=f"{PREV}-03-{d}"), headers=h).json()["id"] for d in ("01", "05", "10")]
r = s.put(f"{API}/invoices/{ids[1]}", json=inv(b2b, data=f"{PREV}-03-12", numero=4), headers=h)
print(json.dumps({"TOK": TOK, "CID": cid, "PA": pa, "BAD": bad, "B2B": b2b, "INV_PA": ipa, "SCART": sc, "SCART_STATUS": st, "gap_put": r.status_code}))

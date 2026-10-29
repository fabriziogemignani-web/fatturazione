# Seeds TEST_T8 UI data: admin session (cookie session_token=test_session_t8_ui), company, B2B + PA clients, 1 invoice, 1 article. --clean to remove
import sys
import json
import requests
from test_iteration7_pa_scartate_registro import API, mongo, party, inv

TOK, UID, PIVA = "test_session_t8_ui", "test-user-t8-ui", "77777777783"


def clean():
    c = mongo(f'const c=db.companies.findOne({{partita_iva:"{PIVA}"}}); print(c?c.id:"")')
    if c:
        mongo(f'db.invoices.deleteMany({{company_id:"{c}"}}); db.parties.deleteMany({{company_id:"{c}"}}); db.articles.deleteMany({{company_id:"{c}"}});'
              f'db.counters.deleteMany({{key:"progressivo_{c}"}}); db.companies.deleteMany({{id:"{c}"}});')
    mongo(f'db.users.deleteMany({{$or:[{{user_id:"{UID}"}},{{email:/^test\\.user\\.t8ui/}}]}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


clean()
if "--clean" in sys.argv:
    print("cleaned")
    sys.exit()
mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t8.ui@example.com", name:"TEST_T8 UI", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
      f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+7*864e5), created_at:new Date().toISOString()}});')
s = requests.Session()
s.headers["Authorization"] = f"Bearer {TOK}"
cid = s.post(f"{API}/companies", json={"denominazione": "TEST_T8 UI Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                       "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"}).json()["id"]
s.headers["X-Company-Id"] = cid
b2b = s.post(f"{API}/parties", json=party("TEST_T8 B2B", codice="ABC1234")).json()["id"]
pa = s.post(f"{API}/parties", json=party("TEST_T8 Comune PA", codice="UFAB12", pa=True, piva="80012345678")).json()["id"]
i1 = s.post(f"{API}/invoices", json=inv(b2b)).json()
s.post(f"{API}/articles", json={"codice": "TEST_T8ART", "descrizione": "Articolo test", "prezzo": 10, "aliquota": 22})
print(json.dumps({"TOK": TOK, "CID": cid, "B2B": b2b, "PA": pa, "INV1": i1["id"], "NUM1": i1["numero"]}))

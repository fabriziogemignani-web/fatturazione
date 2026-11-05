# Seed/cleanup for iteration 21 UI test (archivio). Usage: python3 seed_ui_t21.py seed|clean
import sys
import json
from test_iteration21_archivio import API, PA, CLI1, SUP1, SUP2, fe, p7m, zipof, sess, mongo, TOK, UID

PIVA_UI = "86999999009"


def clean():
    mongo(f'var c=db.companies.findOne({{partita_iva:"{PIVA_UI}"}}); if(c){{db.arch_invoices.deleteMany({{company_id:c.id}}); db.arch_anagrafiche.deleteMany({{company_id:c.id}});'
          f'db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}}'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def seed():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t21ui@example.com", name:"TEST_T21UI", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    s = sess(TOK)
    cid = s.post(f"{API}/companies", json={"denominazione": "TEST_T21UI Srl", "partita_iva": PIVA_UI, "codice_fiscale": PIVA_UI, "regime_fiscale": "RF01",
                                           "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"}).json()["id"]
    s.headers["X-Company-Id"] = cid
    files = [(f"att{n}.xml", fe(PIVA_UI, CLI1, [{"numero": str(n), "data": f"2024-0{(n % 9) + 1}-10"}], ced_name="TEST_T21UI Srl", ces_name="TEST_Cliente Uno")) for n in (1, 2, 10, 3)]
    files += [("pas1.xml.p7m", p7m(fe(SUP1, PIVA_UI, [{"numero": "FV/10", "data": "2024-02-05", "desc": "Carta igienica"}], ced_name="TEST_Fornitore Uno"))),
              ("pas.zip", zipof([("a.xml", fe(SUP2, PIVA_UI, [{"numero": "A-7", "data": "2023-11-20", "td": "TD04"}], ced_name="TEST_Fornitore Due"))]))]
    r = s.post(f"{API}/archivio/upload", files=[("files", f) for f in files]).json()
    print(json.dumps({"cid": cid, "res": [x["status"] for x in r["results"]]}))


if __name__ == "__main__":
    seed() if sys.argv[1] == "seed" else clean()

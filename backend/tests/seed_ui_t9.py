# Seeds TEST_T9 UI data for scadenzario: admin (cookie test_session_t9_admin) + operatore (test_session_t9_oper),
# company with client A (3 rates, 500 paid), client B (invoice with auto NC + NC credit 61), empty 2nd company. --clean to remove
import sys
import json
import requests
from datetime import timedelta
from test_iteration7_pa_scartate_registro import API, mongo, party, inv
from test_iteration9_scadenzario import _clean, comp, sent, TOK, UID, OTOK, OUID, PIVA, PIVA2, D0, R1, R2, R3, TODAY

_clean()
if "--clean" in sys.argv:
    print("cleaned")
    sys.exit()
mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t9.admin@example.com", name:"TEST_T9 Admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
      f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+7*864e5), created_at:new Date().toISOString()}});')
s = requests.Session()
s.headers["Authorization"] = f"Bearer {TOK}"
cid = s.post(f"{API}/companies", json=comp("TEST_T9 Srl", PIVA)).json()["id"]
cid2 = s.post(f"{API}/companies", json=comp("TEST_T9 Altra Srl", PIVA2)).json()["id"]
mongo(f'db.users.insertOne({{user_id:"{OUID}", email:"test.user.t9.oper@example.com", name:"TEST_T9 Oper", picture:"", role:"operatore", status:"approved", company_ids:["{cid}"], created_at:new Date().toISOString()}});'
      f'db.user_sessions.insertOne({{user_id:"{OUID}", session_token:"{OTOK}", expires_at:new Date(Date.now()+7*864e5), created_at:new Date().toISOString()}});')
h = {"X-Company-Id": cid}
A = s.post(f"{API}/parties", json=party("TEST_T9 Cliente A", piva="01234567801"), headers=h).json()["id"]
B = s.post(f"{API}/parties", json=party("TEST_T9 Cliente B", piva="01234567802"), headers=h).json()["id"]
i3 = sent(s, h, inv(A, data=D0, rate=[{"scadenza": R1, "importo": 400}, {"scadenza": R2, "importo": 400}, {"scadenza": R3, "importo": 420}]))["id"]
s.post(f"{API}/invoices/{i3}/pagamenti", json={"data": TODAY.isoformat(), "importo": 500, "note": "TEST"}, headers=h)
iB = sent(s, h, inv(B, data=D0, scadenza=R2))["id"]
ncB = sent(s, h, inv(B, tipo_documento="TD04", price=200, fattura_collegata_id=iB))["id"]
iC = sent(s, h, inv(B, price=100))["id"]
s.post(f"{API}/invoices/{iC}/pagamenti", json={"data": TODAY.isoformat(), "importo": 122}, headers=h)
ncC = sent(s, h, inv(B, tipo_documento="TD04", price=50, fattura_collegata_id=iC))["id"]
draft = s.post(f"{API}/invoices", json=inv(A, price=1000), headers=h).json()["id"]
print(json.dumps({"CID": cid, "CID2": cid2, "A": A, "B": B, "I3": i3, "IB": iB, "NCB": ncB, "IC": iC, "NCC": ncC, "DRAFT": draft}))

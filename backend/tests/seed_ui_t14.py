# Seeds TEST_T14 UI data for scadenzario period filter/sort/grouping (active + passive). --clean removes
import sys
import json
import random
from datetime import date, timedelta
from test_iteration7_pa_scartate_registro import API, mongo, party, inv
from test_iteration9_scadenzario import sent
from test_iteration12_iva import sess, comp
from test_iteration11_passive import variant, up

TOK, UID = "test_session_t14_admin", "test-user-t14-admin"
PIVA = "01234567890"
T = date.today()
D = lambda n: (T + timedelta(days=n)).isoformat()


def clean():
    mongo('db.companies.find({denominazione:/^TEST_T14/}).forEach(c=>{["invoices","parties","payments","passive_invoices","passive_payments"].forEach(k=>db[k].deleteMany({company_id:c.id}));'
          'db.counters.deleteMany({key:{$regex:c.id}}); db.companies.deleteOne({id:c.id});});'
          'db.users.deleteMany({user_id:/^test-user-t14-/}); db.user_sessions.deleteMany({session_token:/^test_session_t14_/});')


clean()
if "--clean" in sys.argv:
    print("cleaned")
    sys.exit()
mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t14.admin@example.com", name:"TEST_T14 Admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
      f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+7*864e5), created_at:new Date().toISOString()}});')
s = sess(TOK)
cid = s.post(f"{API}/companies", json=comp("TEST_T14 Scad Srl", PIVA)).json()["id"]
h = {"X-Company-Id": cid}
A = s.post(f"{API}/parties", json=party("TEST_T14 Cliente A", piva="01234567841"), headers=h).json()["id"]
B = s.post(f"{API}/parties", json=party("TEST_T14 Cliente B", piva="01234567842"), headers=h).json()["id"]
# A: 1220 split into 7 rate
offs = [-41, -16, 0, 5, 25, 60, 100]
amts = [100, 110, 120, 130, 140, 150, 470]
ia = sent(s, h, inv(A, data=D(-60), rate=[{"scadenza": D(o), "importo": a} for o, a in zip(offs, amts)]))["id"]
# B: single scadenza +15, plus a paid invoice with linked NC -> credit 61
ic = sent(s, h, inv(B, data=D(-20), price=100, scadenza=D(-5)))["id"]
s.post(f"{API}/invoices/{ic}/pagamenti", json={"data": T.isoformat(), "importo": 122}, headers=h)
ib = sent(s, h, inv(B, data=D(-10), scadenza=D(15)))["id"]
nc = sent(s, h, inv(B, tipo_documento="TD04", price=50, fattura_collegata_id=ic))["id"]
# passive: 2 docs with rate
R = str(random.randint(1000, 9999))
p1 = up(s, h, ("p1.xml", variant(f"T14-{R}-1", data=D(-50), rate=[(D(-10), 100.0), (D(20), 200.0), (D(45), 274.93)])))[0]["documenti"][0]["id"]
p2 = up(s, h, ("p2.xml", variant(f"T14-{R}-2", data=D(-30), rate=[(D(3), 574.93)])))[0]["documenti"][0]["id"]
print(json.dumps({"TOK": TOK, "CID": cid, "A": A, "B": B, "IA": ia, "IB": ib, "IC": ic, "NC": nc, "P1": p1, "P2": p2}))

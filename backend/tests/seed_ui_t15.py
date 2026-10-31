# Seeds TEST_T15 UI data: admin + operatore sessions and a company with NO corrispettivi (sync done via UI). --clean removes
import sys
import json
from test_iteration7_pa_scartate_registro import API, mongo
from test_iteration12_iva import sess, comp


def clean():
    mongo('db.companies.find({denominazione:/^TEST_T15UI/}).forEach(c=>{["invoices","parties","payments","passive_invoices","passive_payments","corrispettivi"].forEach(k=>db[k].deleteMany({company_id:c.id}));'
          'db.counters.deleteMany({key:{$regex:c.id}}); db.companies.deleteOne({id:c.id});});'
          'db.users.deleteMany({user_id:/^test-user-t15ui-/}); db.user_sessions.deleteMany({session_token:/^test_session_t15ui_/});')


clean()
if "--clean" in sys.argv:
    print("cleaned")
    sys.exit()
for uid, tok, role in (("test-user-t15ui-admin", "test_session_t15ui_admin", "admin"),):
    mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.{uid}@example.com", name:"TEST_T15UI {role}", picture:"", role:"{role}", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+7*864e5), created_at:new Date().toISOString()}});')
s = sess("test_session_t15ui_admin")
cid = s.post(f"{API}/companies", json=comp("TEST_T15UI Negozio Srl", "01234567890")).json()["id"]
mongo(f'db.users.insertOne({{user_id:"test-user-t15ui-oper", email:"test.user.t15ui.oper@example.com", name:"TEST_T15UI oper", picture:"", role:"operatore", status:"approved", company_ids:["{cid}"], created_at:new Date().toISOString()}});'
      'db.user_sessions.insertOne({user_id:"test-user-t15ui-oper", session_token:"test_session_t15ui_oper", expires_at:new Date(Date.now()+7*864e5), created_at:new Date().toISOString()});')
print(json.dumps({"CID": cid}))

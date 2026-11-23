# UI setup for iteration 120: create 2 TEST companies + 1 other, an operator assigned to the first two. `python ui_setup_t120.py cleanup` removes them.
import json
import sys
import uuid

import bcrypt
import requests
from test_iteration120_operatore_dati_azienda import BASE_URL, ADMIN_EMAIL, ADMIN_PW, OP_PW, mdb, _company_payload

S = "/tmp/t120.json"
admin = requests.Session()
admin.headers["X-Requested-With"] = "invoix"
assert admin.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW}).status_code == 200
if len(sys.argv) > 1 and sys.argv[1] == "cleanup":
    d = json.load(open(S))
    print(admin.delete(f"{BASE_URL}/api/users/{d['uid']}").status_code)
    for c in d["cids"]:
        print(admin.delete(f"{BASE_URL}/api/companies/{c}").status_code)
    sys.exit()
cids = [admin.post(f"{BASE_URL}/api/companies", json=_company_payload(n)).json()["id"] for n in ("TEST_UI_Alfa", "TEST_UI_Beta", "TEST_UI_Other")]
email = f"test.oper.ui{uuid.uuid4().hex[:6]}@example.com"
uid = admin.post(f"{BASE_URL}/api/users", json={"name": "TEST_OpUI", "email": email, "role": "operatore", "send_invite": False, "company_ids": cids[:2]}).json()["user_id"]
mdb.users.update_one({"user_id": uid}, {"$set": {"password_hash": bcrypt.hashpw(OP_PW.encode(), bcrypt.gensalt()).decode(), "email_verified": True}})
json.dump({"cids": cids, "uid": uid, "email": email}, open(S, "w"))
print(json.dumps({"cids": cids, "uid": uid, "email": email, "url": BASE_URL}))

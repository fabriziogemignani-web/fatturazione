# Seed/cleanup for iteration 22 UI test (moduli). Usage: python3 seed_ui_t22.py seed|clean
import sys
import json
from test_iteration22_moduli import API, TOK, UID, PA, PB, sess, mongo, comp, clean


def seed():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t22ui@example.com", name:"TEST_T22UI", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    s = sess(TOK)
    a = s.post(f"{API}/companies", json=comp("TEST_T22 A Srl", PA)).json()["id"]
    b = s.post(f"{API}/companies", json=comp("TEST_T22 B Srl", PB)).json()["id"]
    print(json.dumps({"a": a, "b": b}))


if __name__ == "__main__":
    seed() if sys.argv[1] == "seed" else clean()

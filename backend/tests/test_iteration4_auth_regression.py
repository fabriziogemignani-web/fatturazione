# Iteration 4: auth regression (register/login/me/logout/lockout) + pending user blocked from companies
import subprocess
import requests
from test_iteration4_multicompany import API, mongo

EMAIL = "test.user.t4.auth@example.com"


def setup_module():
    mongo(f'db.users.deleteMany({{email:"{EMAIL}"}}); db.login_attempts.deleteMany({{identifier:"{EMAIL}"}})')


def teardown_module():
    mongo(f'const u=db.users.findOne({{email:"{EMAIL}"}}); if(u) db.user_sessions.deleteMany({{user_id:u.user_id}});'
          f'db.users.deleteMany({{email:"{EMAIL}"}}); db.login_attempts.deleteMany({{identifier:"{EMAIL}"}})')


def test_register_login_me_logout_lockout():
    s = requests.Session()
    r = s.post(f"{API}/auth/register", json={"name": "TEST_T4 Auth", "email": EMAIL, "password": "Password123"})
    assert r.status_code == 200 and r.json()["status"] == "pending"
    assert "httponly" in r.headers.get("set-cookie", "").lower()
    h = mongo(f'print(db.users.findOne({{email:"{EMAIL}"}}).password_hash)')
    assert h.startswith("$2b$")
    assert s.get(f"{API}/auth/me").status_code == 200
    assert s.get(f"{API}/companies").status_code == 403
    assert s.post(f"{API}/auth/logout").status_code == 200
    s2 = requests.Session()
    assert s2.post(f"{API}/auth/login", json={"email": EMAIL, "password": "Password123"}).status_code == 200
    assert s2.get(f"{API}/auth/me").json()["email"] == EMAIL
    codes = [requests.post(f"{API}/auth/login", json={"email": EMAIL, "password": "bad"}).status_code for _ in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429

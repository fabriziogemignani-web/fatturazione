# Iteration 90: PATCH /api/users/{id} - admin edits email/name/role/company_ids; self/owner name-only; non-admin 403
import os
import subprocess
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
API = f"{BASE_URL.rstrip('/')}/api"
OWNER_EMAIL = "fabrizio.gemignani@gmail.com"
OWNER_PW = "Fe-Admin-2aOBey8irzL8"
PW = "TestPass123!"
CREATED = {"users": [], "companies": []}


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PW})
    if r.status_code != 200:
        pytest.skip(f"owner login failed {r.status_code}")
    s.owner_id = r.json()["user_id"]
    yield s
    for uid in CREATED["users"]:
        s.delete(f"{API}/users/{uid}")
    for cid in CREATED["companies"]:
        mongo(f'db.companies.deleteOne({{id:"{cid}"}})')


def register(name="TEST_U"):
    em = f"test.user.{uuid.uuid4().hex[:8]}@example.com"
    s = requests.Session()
    r = s.post(f"{API}/auth/register", json={"name": name, "email": em, "password": PW})
    assert r.status_code == 200, r.text
    uid = r.json()["user_id"]
    CREATED["users"].append(uid)
    return uid, em


@pytest.fixture(scope="module")
def company():
    cid = f"test-co-{uuid.uuid4().hex[:8]}"
    mongo(f'db.companies.insertOne({{id:"{cid}", denominazione:"TEST_T90 Srl", partita_iva:"90909090901"}})')
    CREATED["companies"].append(cid)
    return cid


def get_user(admin, uid):
    return next((u for u in admin.get(f"{API}/users").json() if u["user_id"] == uid), None)


class TestUserEdit:
    def test_edit_email_name_role_and_login_with_new_email(self, admin, company):
        uid, em = register()
        assert admin.patch(f"{API}/users/{uid}", json={"status": "approved"}).status_code == 200
        mongo(f'db.users.updateOne({{user_id:"{uid}"}},{{$set:{{email_verified:true}}}})')
        new = f"TEST.New.{uuid.uuid4().hex[:6]}@Example.com"
        r = admin.patch(f"{API}/users/{uid}", json={"name": "TEST_Renamed", "email": new, "role": "contabile", "company_ids": [company]})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["email"] == new.lower()
        assert d["name"] == "TEST_Renamed" and d["role"] == "contabile" and d["company_ids"] == [company]
        u = get_user(admin, uid)
        assert u["email"] == new.lower() and u["email_verified"] is False
        assert requests.post(f"{API}/auth/login", json={"email": em, "password": PW}).status_code == 401
        r2 = requests.post(f"{API}/auth/login", json={"email": new, "password": PW})
        assert r2.status_code == 200 and r2.json()["user_id"] == uid

    def test_same_email_noop_keeps_verified(self, admin):
        uid, em = register()
        mongo(f'db.users.updateOne({{user_id:"{uid}"}},{{$set:{{email_verified:true}}}})')
        r = admin.patch(f"{API}/users/{uid}", json={"email": em.upper(), "name": "TEST_X"})
        assert r.status_code == 200
        assert get_user(admin, uid)["email_verified"] is True

    def test_duplicate_email_400_field(self, admin):
        uid1, em1 = register()
        uid2, _ = register()
        r = admin.patch(f"{API}/users/{uid2}", json={"email": em1})
        assert r.status_code == 400
        assert "email" in r.text and "Esiste già" in r.text
        r = admin.patch(f"{API}/users/{uid2}", json={"email": OWNER_EMAIL})
        assert r.status_code == 400

    def test_invalid_email_rejected(self, admin):
        uid, _ = register()
        r = admin.patch(f"{API}/users/{uid}", json={"email": "not-an-email"})
        print("invalid email ->", r.status_code, r.text[:300])
        assert r.status_code in (400, 422)

    def test_invalid_company_400(self, admin):
        uid, _ = register()
        r = admin.patch(f"{API}/users/{uid}", json={"company_ids": ["nope-xyz"]})
        assert r.status_code == 400

    def test_owner_self_name_only(self, admin):
        oid = admin.owner_id
        orig = get_user(admin, oid)["name"]
        for body in ({"email": "x.y@example.com"}, {"role": "operatore"}, {"company_ids": []}, {"name": "X", "role": "admin"}):
            r = admin.patch(f"{API}/users/{oid}", json=body)
            assert r.status_code == 400, body
            assert "solo il nome" in r.json()["detail"]
        r = admin.patch(f"{API}/users/{oid}", json={"name": orig + " T"})
        assert r.status_code == 200 and r.json()["name"] == orig + " T"
        r = admin.patch(f"{API}/users/{oid}", json={"name": orig})
        assert r.status_code == 200 and get_user(admin, oid)["name"] == orig
        u = get_user(admin, oid)
        assert u["email"] == OWNER_EMAIL and u["role"] == "admin"

    def test_other_admin_self_and_owner(self, admin):
        uid, em = register()
        admin.patch(f"{API}/users/{uid}", json={"status": "approved", "role": "admin"})
        s = requests.Session()
        assert s.post(f"{API}/auth/login", json={"email": em, "password": PW}).status_code == 200
        r = s.patch(f"{API}/users/{admin.owner_id}", json={"email": "evil@example.com"})
        assert r.status_code == 400 and "solo il nome" in r.json()["detail"]
        r = s.patch(f"{API}/users/{uid}", json={"role": "operatore"})
        assert r.status_code == 400
        r = s.patch(f"{API}/users/{uid}", json={"name": "TEST_SelfRenamed"})
        assert r.status_code == 200 and r.json()["name"] == "TEST_SelfRenamed"

    def test_non_admin_403(self, admin):
        uid, em = register()
        admin.patch(f"{API}/users/{uid}", json={"status": "approved", "role": "operatore"})
        uid2, _ = register()
        s = requests.Session()
        assert s.post(f"{API}/auth/login", json={"email": em, "password": PW}).status_code == 200
        r = s.patch(f"{API}/users/{uid2}", json={"name": "hack"})
        assert r.status_code == 403
        r = s.patch(f"{API}/users/{uid}", json={"name": "hack"})
        assert r.status_code == 403

    def test_404(self, admin):
        assert admin.patch(f"{API}/users/user_nonexist", json={"name": "a"}).status_code == 404

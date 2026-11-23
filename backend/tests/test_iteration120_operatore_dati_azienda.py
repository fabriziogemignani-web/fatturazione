# Iteration 120: operator default diritti dati_azienda/banche=True; company switcher scoped to assigned companies;
# PUT /api/company by operator; isolation from non-assigned companies; admin revoke banche keeps banche untouched.
import os
import random
import uuid

import bcrypt
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    for line in open("/app/frontend/.env"):
        if line.startswith("REACT_APP_BACKEND_URL"):
            BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
ADMIN_EMAIL = "fabrizio.gemignani@gmail.com"
ADMIN_PW = "Fe-Admin-2aOBey8irzL8"
OP_PW = "TestOper123!"
IBAN1 = "IT60X0542811101000000123456"
IBAN2 = "IT02L1234512345123456789012"  # check digits computed below if invalid

mdb = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[os.environ.get("DB_NAME", "test_database")]


def _fix_iban(country_bban):
    # compute valid IT iban check digits for bban
    bban = country_bban
    s = bban + "IT00"
    n = int("".join(str(int(c, 36)) for c in s))
    return f"IT{98 - n % 97:02d}{bban}"


IBAN2 = _fix_iban("L1234512345123456789012")


def _piva():
    return "".join(str(random.randint(0, 9)) for _ in range(11))


def _company_payload(name, banche=None):
    return {"denominazione": name, "partita_iva": _piva(), "indirizzo": "Via Test 1", "cap": "20100", "comune": "Milano",
            "provincia": "MI", "banche": banche or []}


@pytest.fixture(scope="module")
def ctx():
    admin = requests.Session()
    r = admin.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW})
    assert r.status_code == 200, r.text
    cids = []
    for n in ("TEST_OpA", "TEST_OpB", "TEST_OpC_Other"):
        r = admin.post(f"{BASE_URL}/api/companies", json=_company_payload(n))
        assert r.status_code == 200, r.text
        cids.append(r.json()["id"])
    email = f"test.oper.{uuid.uuid4().hex[:8]}@example.com"
    r = admin.post(f"{BASE_URL}/api/users", json={"name": "TEST_Operatore", "email": email, "role": "operatore",
                                                   "send_invite": False, "company_ids": cids[:2]})
    assert r.status_code == 200, r.text
    uid = r.json()["user_id"]
    mdb.users.update_one({"user_id": uid}, {"$set": {"password_hash": bcrypt.hashpw(OP_PW.encode(), bcrypt.gensalt()).decode(), "email_verified": True}})
    op = requests.Session()
    r = op.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": OP_PW})
    assert r.status_code == 200, r.text
    data = {"admin": admin, "op": op, "cids": cids, "uid": uid, "email": email}
    yield data
    admin.delete(f"{BASE_URL}/api/users/{uid}")
    for c in cids:
        admin.delete(f"{BASE_URL}/api/companies/{c}")


def test_me_default_diritti(ctx):
    r = ctx["op"].get(f"{BASE_URL}/api/auth/me")
    assert r.status_code == 200
    d = r.json()["diritti"]
    assert d["dati_azienda"] is True and d["banche"] is True
    assert d["tabelle_contabili"] is False and d["testi_comunicazioni"] is False


def test_list_companies_only_assigned(ctx):
    r = ctx["op"].get(f"{BASE_URL}/api/companies")
    assert r.status_code == 200
    ids = {c["id"] for c in r.json()}
    assert ids == set(ctx["cids"][:2])


def test_admin_users_list_shows_diritti(ctx):
    r = ctx["admin"].get(f"{BASE_URL}/api/users")
    u = next(x for x in r.json() if x["user_id"] == ctx["uid"])
    assert u["diritti"]["dati_azienda"] and u["diritti"]["banche"]


def test_operator_put_company_with_banks(ctx):
    op, cid = ctx["op"], ctx["cids"][0]
    h = {"X-Company-Id": cid}
    cur = op.get(f"{BASE_URL}/api/company", headers=h).json()
    body = {k: cur.get(k) for k in ("denominazione", "partita_iva", "indirizzo", "cap", "comune", "provincia")}
    body.update({"denominazione": "TEST_OpA_Edited", "telefono": "0212345678", "pec": "test@pec.example.com",
                 "banche": [{"nome": "TEST Banca 1", "iban": IBAN1, "predefinita": True}, {"nome": "TEST Banca 2", "iban": IBAN2}]})
    r = op.put(f"{BASE_URL}/api/company", json=body, headers=h)
    assert r.status_code == 200, r.text
    g = op.get(f"{BASE_URL}/api/company", headers=h).json()
    assert g["denominazione"] == "TEST_OpA_Edited" and g["telefono"] == "0212345678"
    assert [b["iban"] for b in g["banche"]] == [IBAN1, IBAN2]
    assert g["iban"] == IBAN1
    assert g["banche"][0]["abi"] == "05428"


def test_operator_put_company_switch_second(ctx):
    op, cid = ctx["op"], ctx["cids"][1]
    h = {"X-Company-Id": cid}
    cur = op.get(f"{BASE_URL}/api/company", headers=h)
    assert cur.status_code == 200 and cur.json()["denominazione"] == "TEST_OpB"


def test_operator_other_company_denied(ctx):
    op, cid = ctx["op"], ctx["cids"][2]
    h = {"X-Company-Id": cid}
    g = op.get(f"{BASE_URL}/api/company", headers=h)
    assert g.status_code in (403, 404), g.text
    body = _company_payload("TEST_Hack")
    p = op.put(f"{BASE_URL}/api/company", json=body, headers=h)
    assert p.status_code in (403, 404), p.text
    assert mdb.companies.find_one({"id": cid})["denominazione"] == "TEST_OpC_Other"


def test_operator_admin_endpoints_denied(ctx):
    op = ctx["op"]
    assert op.get(f"{BASE_URL}/api/users").status_code == 403
    assert op.post(f"{BASE_URL}/api/companies", json=_company_payload("TEST_X")).status_code == 403
    assert op.put(f"{BASE_URL}/api/users/{ctx['uid']}/diritti", json={"dati_azienda": True, "banche": True}).status_code == 403


def test_revoke_banche_keeps_banks(ctx):
    admin, op, cid = ctx["admin"], ctx["op"], ctx["cids"][0]
    r = admin.put(f"{BASE_URL}/api/users/{ctx['uid']}/diritti", json={"dati_azienda": True, "banche": False, "articoli_magazzino": True})
    assert r.status_code == 200
    assert op.get(f"{BASE_URL}/api/auth/me").json()["diritti"]["banche"] is False
    h = {"X-Company-Id": cid}
    cur = op.get(f"{BASE_URL}/api/company", headers=h).json()
    body = {k: cur.get(k) for k in ("denominazione", "partita_iva", "indirizzo", "cap", "comune", "provincia")}
    body.update({"denominazione": "TEST_OpA_NoBank", "banche": [{"nome": "TEST Hack", "iban": IBAN2, "predefinita": True}]})
    r = op.put(f"{BASE_URL}/api/company", json=body, headers=h)
    assert r.status_code == 200, r.text
    g = op.get(f"{BASE_URL}/api/company", headers=h).json()
    assert g["denominazione"] == "TEST_OpA_NoBank"
    assert [b["iban"] for b in g["banche"]] == [IBAN1, IBAN2] and g["iban"] == IBAN1


def test_revoke_dati_keeps_anagrafica(ctx):
    admin, op, cid = ctx["admin"], ctx["op"], ctx["cids"][0]
    admin.put(f"{BASE_URL}/api/users/{ctx['uid']}/diritti", json={"dati_azienda": False, "banche": True})
    h = {"X-Company-Id": cid}
    cur = op.get(f"{BASE_URL}/api/company", headers=h).json()
    body = {k: cur.get(k) for k in ("denominazione", "partita_iva", "indirizzo", "cap", "comune", "provincia")}
    body.update({"denominazione": "TEST_ShouldNotChange", "banche": [{"nome": "TEST Only", "iban": IBAN2, "predefinita": True}]})
    r = op.put(f"{BASE_URL}/api/company", json=body, headers=h)
    assert r.status_code == 200, r.text
    g = op.get(f"{BASE_URL}/api/company", headers=h).json()
    assert g["denominazione"] == "TEST_OpA_NoBank"
    assert [b["iban"] for b in g["banche"]] == [IBAN2]


def test_revoke_both_403(ctx):
    admin, op, cid = ctx["admin"], ctx["op"], ctx["cids"][0]
    admin.put(f"{BASE_URL}/api/users/{ctx['uid']}/diritti", json={"dati_azienda": False, "banche": False})
    h = {"X-Company-Id": cid}
    cur = op.get(f"{BASE_URL}/api/company", headers=h).json()
    body = {k: cur.get(k) for k in ("denominazione", "partita_iva", "indirizzo", "cap", "comune", "provincia")}
    assert op.put(f"{BASE_URL}/api/company", json=body, headers=h).status_code == 403
    # restore defaults for UI test
    admin.put(f"{BASE_URL}/api/users/{ctx['uid']}/diritti", json={"dati_azienda": True, "banche": True, "articoli_magazzino": True})


def test_login_response_includes_diritti(ctx):
    # frontend stores the login response as user: without diritti the "Dati azienda" menu is hidden until reload
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ctx["email"], "password": OP_PW})
    assert r.status_code == 200
    assert r.json()["diritti"]["dati_azienda"] is True and r.json()["diritti"]["banche"] is True

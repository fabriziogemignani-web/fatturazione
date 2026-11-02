# Iteration 16: email/password-only auth (google removed, seeded admin) + per-company SMTP config/test/forgot/invite.
# Needs local debug SMTP: python3 -m smtpd -n -c DebuggingServer 127.0.0.1:1025 > /tmp/smtp.log
# Run with: pytest test_iteration16_smtp_auth.py -n 0
import random
import time
import pytest
import requests
from test_iteration7_pa_scartate_registro import API, mongo

RUN = str(random.randint(100000, 999999))
TOK, UID = f"test_session_t16_admin_{RUN}", f"test-user-t16-admin-{RUN}"
CTOK, CUID = f"test_session_t16_cont_{RUN}", f"test-user-t16-cont-{RUN}"
OTOK, OUID = f"test_session_t16_oper_{RUN}", f"test-user-t16-oper-{RUN}"
PIVA, PIVA2 = "86" + RUN + "001", "86" + RUN + "002"
SMTP_LOG = "/tmp/smtp.log"
ADMIN_EMAIL, ADMIN_PWD = "fabrizio.gemignani@gmail.com", "Fe-Admin-2aOBey8irzL8"
SMTP_OK = {"host": "127.0.0.1", "port": 1025, "security": "none", "username": "", "password": "TEST_secret1",
           "from_email": "noreply@test-t16.it", "from_name": "TEST T16", "reply_to": "amm@test-t16.it"}


def smtp_log():
    time.sleep(1)
    with open(SMTP_LOG) as f:
        return f.read()


def clean_all():
    mongo('db.companies.deleteMany({denominazione:/^TEST_T16/});'
          'var ids=db.users.find({email:/^test\\.user\\.t16/},{user_id:1}).toArray().map(u=>u.user_id);'
          'db.password_reset_tokens.deleteMany({user_id:{$in:ids}}); db.user_sessions.deleteMany({user_id:{$in:ids}});'
          'db.users.deleteMany({email:/^test\\.user\\.t16/}); db.users.deleteMany({user_id:/^test-user-t16-/});'
          'db.user_sessions.deleteMany({session_token:/^test_session_t16_/}); db.login_attempts.deleteMany({identifier:/^test\\.user\\.t16/});')


def user(uid, tok, role, cids):
    mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.t16.{uid}@example.com", name:"TEST_T16 {role}", picture:"", role:"{role}", status:"approved", company_ids:{cids}, created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+7*864e5), created_at:new Date().toISOString()}});')


def sess(tok):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    return s


def comp(name, piva):
    return {"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01",
            "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"}


@pytest.fixture(scope="module")
def ctx():
    clean_all()
    assert mongo('print(db.companies.countDocuments({"smtp.host":{$nin:[null,""]}}))') == "0", "real SMTP config present - abort"
    user(UID, TOK, "admin", "[]")
    s = sess(TOK)
    cid = s.post(f"{API}/companies", json=comp("TEST_T16 Srl", PIVA)).json()["id"]
    cid2 = s.post(f"{API}/companies", json=comp("TEST_T16 Altra Srl", PIVA2)).json()["id"]
    user(CUID, CTOK, "contabile", f'["{cid}"]')
    user(OUID, OTOK, "operatore", f'["{cid}"]')
    yield {"s": s, "c": sess(CTOK), "o": sess(OTOK), "cid": cid, "cid2": cid2, "h": {"X-Company-Id": cid}, "h2": {"X-Company-Id": cid2}}
    clean_all()


# ---- Auth (email/password only) ----
class TestAuth:
    def test_01_google_session_removed(self):
        r = requests.post(f"{API}/auth/session", json={"session_id": "x"})
        assert r.status_code == 404, r.text

    def test_02_admin_login_cookie_me_logout(self):
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PWD})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["email"] == ADMIN_EMAIL and d["role"] == "admin" and "password_hash" not in d
        sc = r.headers.get("set-cookie", "").lower()
        assert "session_token=" in sc and "httponly" in sc and "secure" in sc
        assert s.get(f"{API}/auth/me").json()["role"] == "admin"
        assert s.post(f"{API}/auth/logout").status_code == 200
        assert s.get(f"{API}/auth/me").status_code == 401
        assert mongo(f'print(db.users.findOne({{email:"{ADMIN_EMAIL}"}}).password_hash.slice(0,4))') == "$2b$"

    def test_03_register_pending_and_bruteforce(self):
        em = f"test.user.t16.reg{RUN}@example.com"
        s = requests.Session()
        r = s.post(f"{API}/auth/register", json={"name": "TEST_T16 Reg", "email": em, "password": "Password123"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "pending" and r.json()["role"] == "operatore"
        assert s.get(f"{API}/auth/me").json()["email"] == em
        assert requests.post(f"{API}/auth/login", json={"email": em, "password": "Password123"}).status_code == 200
        codes = [requests.post(f"{API}/auth/login", json={"email": em, "password": "wrong-pass"}).status_code for _ in range(5)]
        assert codes == [401] * 5
        assert requests.post(f"{API}/auth/login", json={"email": em, "password": "Password123"}).status_code == 429


# ---- No SMTP anywhere: forgot ok silently, invite 400 + user not created, test 400 ----
class TestNoSmtp:
    def test_04_forgot_no_smtp_ok(self, ctx):
        r = requests.post(f"{API}/auth/forgot-password", json={"email": f"test.user.t16.{CUID}@example.com"})
        assert r.status_code == 200 and r.json()["ok"] is True

    def test_05_invite_no_smtp_400(self, ctx):
        em = f"test.user.t16.inv0{RUN}@example.com"
        r = ctx["s"].post(f"{API}/users", json={"name": "TEST_T16 Inv", "email": em, "role": "operatore", "send_invite": True})
        assert r.status_code == 400 and "SMTP" in r.json()["detail"], r.text
        assert mongo(f'print(db.users.countDocuments({{email:"{em}"}}))') == "0"

    def test_06_test_send_no_smtp_400(self, ctx):
        r = ctx["s"].post(f"{API}/company/smtp/test", json={"to": "dest@example.com"}, headers=ctx["h"])
        assert r.status_code == 400 and "Configura il server email (SMTP)" in r.json()["detail"], r.text

    def test_07_get_unconfigured(self, ctx):
        d = ctx["s"].get(f"{API}/company/smtp", headers=ctx["h"]).json()
        assert d["configured"] is False and d["has_password"] is False


# ---- SMTP CRUD ----
class TestSmtpCrud:
    def test_08_roles_403(self, ctx):
        for k in ("c", "o"):
            assert ctx[k].get(f"{API}/company/smtp", headers=ctx["h"]).status_code == 403
            assert ctx[k].put(f"{API}/company/smtp", json=SMTP_OK, headers=ctx["h"]).status_code == 403
            assert ctx[k].delete(f"{API}/company/smtp", headers=ctx["h"]).status_code == 403
            assert ctx[k].post(f"{API}/company/smtp/test", json={"to": "a@example.com"}, headers=ctx["h"]).status_code == 403

    def test_09_validation_422(self, ctx):
        r = ctx["s"].put(f"{API}/company/smtp", json={**SMTP_OK, "host": "smtp bad/host"}, headers=ctx["h"])
        assert r.status_code == 422, r.text
        assert "host" in r.text and "Server SMTP non valido" in r.text
        r = ctx["s"].put(f"{API}/company/smtp", json={**SMTP_OK, "from_email": "not-an-email"}, headers=ctx["h"])
        assert r.status_code == 422 and "from_email" in r.text, r.text
        r = ctx["s"].put(f"{API}/company/smtp", json={**SMTP_OK, "port": 70000}, headers=ctx["h"])
        assert r.status_code == 422

    def test_10_put_encrypts(self, ctx):
        r = ctx["s"].put(f"{API}/company/smtp", json=SMTP_OK, headers=ctx["h"])
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["configured"] and d["has_password"] and d["host"] == "127.0.0.1" and d["port"] == 1025
        assert "password" not in d and "password_enc" not in d
        enc = mongo(f'print(db.companies.findOne({{id:"{ctx["cid"]}"}}).smtp.password_enc)')
        assert enc and enc != "TEST_secret1" and "TEST_secret1" not in enc
        g = ctx["s"].get(f"{API}/company/smtp", headers=ctx["h"]).json()
        assert g["has_password"] and g["from_email"] == "noreply@test-t16.it" and g["reply_to"] == "amm@test-t16.it" and "password_enc" not in g

    def test_11_company_endpoints_hide_smtp(self, ctx):
        c = ctx["s"].get(f"{API}/company", headers=ctx["h"])
        assert c.status_code == 200 and "smtp" not in c.json() and "password_enc" not in c.text
        cs = ctx["s"].get(f"{API}/companies")
        assert "password_enc" not in cs.text and "smtp" not in cs.text
        assert "password_enc" not in ctx["c"].get(f"{API}/company", headers=ctx["h"]).text

    def test_12_password_null_keeps_empty_clears(self, ctx):
        r = ctx["s"].put(f"{API}/company/smtp", json={**SMTP_OK, "password": None, "from_name": "TEST T16 b"}, headers=ctx["h"])
        assert r.json()["has_password"] is True and r.json()["from_name"] == "TEST T16 b"
        r = ctx["s"].put(f"{API}/company/smtp", json={**SMTP_OK, "password": ""}, headers=ctx["h"])
        assert r.json()["has_password"] is False
        assert ctx["s"].get(f"{API}/company/smtp", headers=ctx["h"]).json()["has_password"] is False

    def test_13_smtp_isolated_per_company(self, ctx):
        assert ctx["s"].get(f"{API}/company/smtp", headers=ctx["h2"]).json()["configured"] is False


# ---- Sending through company SMTP ----
class TestSmtpSend:
    def test_14_test_send_arrives(self, ctx):
        to = f"dest{RUN}@example.com"
        r = ctx["s"].post(f"{API}/company/smtp/test", json={"to": to}, headers=ctx["h"])
        assert r.status_code == 200, r.text
        log = smtp_log()
        assert to in log and "Email di prova - TEST_T16 Srl" in log and "noreply@test-t16.it" in log

    def test_15_test_send_bad_port_400(self, ctx):
        ctx["s"].put(f"{API}/company/smtp", json={**SMTP_OK, "host": "127.0.0.1", "port": 1026}, headers=ctx["h2"])
        r = ctx["s"].post(f"{API}/company/smtp/test", json={"to": "a@example.com"}, headers=ctx["h2"])
        assert r.status_code == 400 and "Invio email non riuscito" in r.json()["detail"], r.text
        assert ctx["s"].delete(f"{API}/company/smtp", headers=ctx["h2"]).json()["ok"] is True
        assert ctx["s"].get(f"{API}/company/smtp", headers=ctx["h2"]).json()["configured"] is False

    def test_16_test_send_bad_to_422(self, ctx):
        assert ctx["s"].post(f"{API}/company/smtp/test", json={"to": "nope"}, headers=ctx["h"]).status_code == 422

    def test_17_forgot_sends(self, ctx):
        em = f"test.user.t16.{CUID}@example.com"
        r = requests.post(f"{API}/auth/forgot-password", json={"email": em})
        assert r.status_code == 200
        log = smtp_log()
        assert em in log and "reset-password?token=" in log.replace("=\n", "")

    def test_18_invite_sends_and_creates(self, ctx):
        em = f"test.user.t16.inv1{RUN}@example.com"
        r = ctx["s"].post(f"{API}/users", json={"name": "TEST_T16 Inv", "email": em, "role": "operatore", "send_invite": True, "company_ids": [ctx["cid"]]})
        assert r.status_code == 200, r.text
        assert em in smtp_log()
        users = ctx["s"].get(f"{API}/users").json()
        u = next(x for x in users if x["email"] == em)
        assert u["has_password"] is False

    def test_19_delete_smtp(self, ctx):
        assert ctx["s"].delete(f"{API}/company/smtp", headers=ctx["h"]).status_code == 200
        assert ctx["s"].get(f"{API}/company/smtp", headers=ctx["h"]).json()["configured"] is False
        assert mongo(f'print(db.companies.findOne({{id:"{ctx["cid"]}"}}).smtp === undefined)') == "true"

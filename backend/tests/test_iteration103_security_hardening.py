# Iteration 103: security hardening regression - CSRF header guard (X-Requested-With: invoix), CORS foreign origin, docs disabled,
# security headers, /system/update admin-only, stripe webhook signature, AI credits smoke.
# Run: pytest tests/test_iteration103_security_hardening.py -v -n 0
import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

H = {"X-Requested-With": "invoix"}
UID, TOK = "test-user-t103-admin", "test_session_t103_admin"
UID_OP, TOK_OP = "test-user-t103-oper", "test_session_t103_oper"
ST = {}


def raw(tok=TOK, csrf=True, cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    if csrf:
        s.headers.update(H)
    else:
        s.headers.pop("X-Requested-With", None)  # conftest injects it by default
    if cid:
        s.headers["X-Company-Id"] = cid
    return s


def clean():
    mongo('db.companies.find({denominazione:/^TEST_T103/}).forEach(c=>{["parties","invoices","ai_consumi","payment_transactions"].forEach(k=>db[k].deleteMany({company_id:c.id}));'
          'db.counters.deleteMany({key:{$regex:c.id}}); db.users.updateMany({}, {$pull:{company_ids:c.id}}); db.companies.deleteOne({id:c.id});});'
          f'db.users.deleteMany({{user_id:{{$in:["{UID}","{UID_OP}"]}}}}); db.user_sessions.deleteMany({{user_id:{{$in:["{UID}","{UID_OP}"]}}}});')


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    for uid, tok, role in ((UID, TOK, "admin"), (UID_OP, TOK_OP, "operatore")):
        mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.{uid}@example.com", name:"TEST_T103 {role}", picture:"", role:"{role}", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
              f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    yield
    clean()


# CSRF guard
class TestCsrfGuard:
    def test_post_without_header_403(self):
        r = raw(csrf=False).post(f"{API}/companies", json={"denominazione": "TEST_T103 NoHdr"})
        assert r.status_code == 403 and r.json()["detail"] == "Richiesta non consentita"

    def test_login_without_header_403(self):
        r = requests.post(f"{API}/auth/login", json={"email": "x@example.com", "password": "whatever123"}, headers={"X-Requested-With": None})
        assert r.status_code == 403

    def test_wrong_header_value_403(self):
        r = requests.post(f"{API}/auth/logout", headers={"X-Requested-With": "XMLHttpRequest"})
        assert r.status_code == 403

    @pytest.mark.parametrize("m", ["put", "patch", "delete"])
    def test_other_methods_without_header_403(self, m):
        r = getattr(raw(csrf=False), m)(f"{API}/companies/nonexistent")
        assert r.status_code == 403

    def test_get_without_header_ok(self):
        assert raw(csrf=False).get(f"{API}/auth/me").status_code == 200

    def test_create_company_with_header(self):
        r = raw().post(f"{API}/companies", json={"denominazione": "TEST_T103 Srl", "partita_iva": "10310310310", "codice_fiscale": "10310310310",
                                                 "regime_fiscale": "RF01", "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
        assert r.status_code == 200, r.text
        ST["cid"] = r.json()["id"]

    def test_admin_login_with_header(self):
        r = requests.post(f"{API}/auth/login", headers=H, json={"email": os.environ["ADMIN_EMAIL"], "password": os.environ["ADMIN_PASSWORD"]})
        assert r.status_code == 200, r.text
        assert "session_token" in r.cookies or "set-cookie" in {k.lower() for k in r.headers}


# CORS
class TestCors:
    def test_foreign_origin_preflight(self):
        r = requests.options(f"{API}/companies", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST",
                                                          "Access-Control-Request-Headers": "x-requested-with,content-type"})
        assert r.headers.get("access-control-allow-origin") in (None, "")
        assert r.headers.get("access-control-allow-origin") != "*"

    def test_foreign_origin_get(self):
        r = requests.get(f"{API}/auth/me", headers={"Origin": "https://evil.example"})
        assert r.headers.get("access-control-allow-origin") in (None, "")

    def test_same_origin_preflight(self):
        o = API.rsplit("/api", 1)[0]
        r = requests.options(f"{API}/companies", headers={"Origin": o, "Access-Control-Request-Method": "POST"})
        print("same-origin ACAO:", r.status_code, r.headers.get("access-control-allow-origin"))
        assert r.status_code == 200 and r.headers.get("access-control-allow-origin") == o


# Docs / headers
class TestHeadersDocs:
    @pytest.mark.parametrize("p", ["/docs", "/openapi.json", "/redoc", "/api/docs", "/api/openapi.json"])
    def test_docs_disabled_local(self, p):
        assert requests.get(f"http://localhost:8001{p}").status_code == 404

    def test_security_headers(self):
        r = raw().get(f"{API}/auth/me")
        h = {k.lower(): v for k, v in r.headers.items()}
        assert h.get("x-content-type-options") == "nosniff"
        assert h.get("x-frame-options") == "SAMEORIGIN"
        assert "max-age" in h.get("strict-transport-security", "")
        assert "no-store" in h.get("cache-control", "")


# Updater / Stripe / AI credits
class TestAdminEndpoints:
    def test_update_operatore_403(self):
        assert raw(TOK_OP).post(f"{API}/system/update").status_code == 403

    def test_update_status_operatore_ok(self):
        r = raw(TOK_OP).get(f"{API}/system/update-status")
        assert r.status_code == 200 and "enabled" in r.json()

    def test_update_admin_not_403(self):
        r = raw().post(f"{API}/system/update")
        assert r.status_code in (400, 409, 200), r.text

    def test_webhook_no_signature_400(self):
        r = requests.post(f"{API}/stripe/webhook", data=b"{}", headers={"Content-Type": "application/json", "X-Requested-With": None})
        assert r.status_code == 400

    def test_ai_crediti_smoke(self):
        r = raw(cid=ST["cid"]).get(f"{API}/ai/crediti")
        assert r.status_code == 200, r.text
        assert raw(cid=ST["cid"]).put(f"{API}/ai/attiva", json={"attiva": False}).json()["attiva"] is False
        assert raw(cid=ST["cid"], csrf=False).put(f"{API}/ai/attiva", json={"attiva": True}).status_code == 403
        assert raw().get(f"{API}/ai/padre").status_code == 200
        r = raw(cid=ST["cid"]).post(f"{API}/ai/crediti/checkout", json={"pacchetto_id": "base", "origin_url": "https://x.example"})
        assert r.status_code in (400, 404, 200, 502), r.text

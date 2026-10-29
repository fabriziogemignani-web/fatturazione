# Iteration 3: user management, SIMULATED SDI notifications (RC/MC/NS), dashboard cruscotto
import os
import hashlib
import secrets
import subprocess
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"Authorization": "Bearer test_session_T1_admin_approved"}
CONT = {"Authorization": "Bearer test_session_T1_contabile_approved"}
OPER = {"Authorization": "Bearer test_session_T1_operatore_approved"}
DATE = "2026-10-29"


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'],
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture(scope="module", autouse=True)
def setup_module_data():
    subprocess.run(["mongosh", "--quiet", "/app/backend/tests/seed_sessions.js"], capture_output=True)
    yield
    mongo('const ids = db.parties.find({denominazione: /^TEST_T3/}).toArray().map(p=>p.id);'
          'db.invoices.deleteMany({party_id: {$in: ids}}); db.parties.deleteMany({denominazione: /^TEST_T3/});'
          'db.users.deleteMany({email: /^test\\.user\\.t3/});')


# ---- Users ----
class TestUsers:
    def test_list_users_admin(self):
        r = requests.get(f"{API}/users", headers=ADMIN)
        assert r.status_code == 200
        u = r.json()
        assert all("password_hash" not in x and "_id" not in x for x in u)
        assert all("has_password" in x and "is_owner" in x for x in u)

    def test_create_duplicate_patch_delete(self):
        email = "test.user.t3.crud@example.com"
        r = requests.post(f"{API}/users", headers=ADMIN, json={"name": "TEST_T3 Crud", "email": email, "role": "contabile", "send_invite": False})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "approved" and d["role"] == "contabile" and d["email"] == email
        uid = d["user_id"]
        r = requests.post(f"{API}/users", headers=ADMIN, json={"name": "X", "email": email.upper(), "send_invite": False})
        assert r.status_code == 400
        r = requests.patch(f"{API}/users/{uid}", headers=ADMIN, json={"name": "TEST_T3 Renamed", "role": "operatore"})
        assert r.status_code == 200 and r.json()["name"] == "TEST_T3 Renamed" and r.json()["role"] == "operatore"
        lst = requests.get(f"{API}/users", headers=ADMIN).json()
        me = [x for x in lst if x["user_id"] == uid][0]
        assert me["role"] == "operatore" and me["has_password"] is False
        r = requests.delete(f"{API}/users/{uid}", headers=ADMIN)
        assert r.status_code == 200
        lst = requests.get(f"{API}/users", headers=ADMIN).json()
        assert not any(x["user_id"] == uid for x in lst)
        assert requests.delete(f"{API}/users/{uid}", headers=ADMIN).status_code == 404

    def test_invalid_email_and_role(self):
        assert requests.post(f"{API}/users", headers=ADMIN, json={"name": "X", "email": "bad", "send_invite": False}).status_code == 422
        assert requests.post(f"{API}/users", headers=ADMIN, json={"name": "X", "email": "test.user.t3.r@example.com", "role": "boss", "send_invite": False}).status_code == 422
        assert requests.post(f"{API}/users", headers=ADMIN, json={"name": "", "email": "test.user.t3.r@example.com", "send_invite": False}).status_code == 422

    def test_self_cannot_modify(self):
        uid = "test-user-T1-admin-approved"
        assert requests.patch(f"{API}/users/{uid}", headers=ADMIN, json={"role": "operatore"}).status_code == 400
        assert requests.delete(f"{API}/users/{uid}", headers=ADMIN).status_code == 400
        assert requests.post(f"{API}/users/{uid}/send-reset", headers=ADMIN).status_code == 400

    def test_owner_cannot_modify(self):
        mongo('db.users.deleteMany({user_id:"test-owner-t3"}); db.users.insertOne({user_id:"test-owner-t3", email:"fabrizio.gemignani@gmail.com", name:"Owner", role:"admin", status:"approved", created_at:new Date().toISOString()})') \
            if mongo('print(db.users.countDocuments({email:"fabrizio.gemignani@gmail.com"}))') == "0" else None
        oid = mongo('print(db.users.findOne({email:"fabrizio.gemignani@gmail.com"}).user_id)')
        try:
            assert requests.patch(f"{API}/users/{oid}", headers=ADMIN, json={"role": "operatore"}).status_code == 400
            assert requests.delete(f"{API}/users/{oid}", headers=ADMIN).status_code == 400
            assert requests.post(f"{API}/users/{oid}/send-reset", headers=ADMIN).status_code == 400
            lst = requests.get(f"{API}/users", headers=ADMIN).json()
            assert [x for x in lst if x["user_id"] == oid][0]["is_owner"] is True
        finally:
            mongo('db.users.deleteMany({user_id:"test-owner-t3"})')

    def test_non_admin_forbidden(self):
        for h in (CONT, OPER):
            assert requests.get(f"{API}/users", headers=h).status_code == 403
            assert requests.post(f"{API}/users", headers=h, json={"name": "X", "email": "test.user.t3.x@example.com", "send_invite": False}).status_code == 403
            assert requests.delete(f"{API}/users/test-user-T1-operatore-pending", headers=h).status_code == 403
            assert requests.patch(f"{API}/users/test-user-T1-operatore-pending", headers=h, json={"status": "approved"}).status_code == 403
            assert requests.post(f"{API}/users/test-user-T1-operatore-pending/send-reset", headers=h).status_code == 403
        assert requests.get(f"{API}/users").status_code == 401

    def test_invited_user_sets_password_and_logs_in(self):
        email = "test.user.t3.invite@example.com"
        r = requests.post(f"{API}/users", headers=ADMIN, json={"name": "TEST_T3 Invite", "email": email, "role": "operatore", "send_invite": False})
        assert r.status_code == 200
        uid = r.json()["user_id"]
        # cannot login before password is set
        assert requests.post(f"{API}/auth/login", json={"email": email, "password": "Whatever123"}).status_code == 401
        mongo(f'db.login_attempts.deleteMany({{identifier: "{email}"}})')
        tok = secrets.token_urlsafe(32)
        th = hashlib.sha256(tok.encode()).hexdigest()
        mongo(f'db.password_reset_tokens.insertOne({{token_hash:"{th}", user_id:"{uid}", expires_at:new Date(Date.now()+3600000), used:false, created_at:new Date().toISOString()}})')
        r = requests.post(f"{API}/auth/reset-password", json={"token": tok, "password": "InvitePass123"})
        assert r.status_code == 200
        assert requests.post(f"{API}/auth/reset-password", json={"token": tok, "password": "InvitePass123"}).status_code == 400
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": "InvitePass123"})
        assert r.status_code == 200 and r.json()["status"] == "approved"
        assert "session_token" in r.cookies or "session_token" in r.headers.get("set-cookie", "")
        lst = requests.get(f"{API}/users", headers=ADMIN).json()
        assert [x for x in lst if x["user_id"] == uid][0]["has_password"] is True


# ---- SDI + Dashboard ----
@pytest.fixture(scope="module")
def sdi_parties():
    company = requests.get(f"{API}/company", headers=ADMIN).json()
    if not company.get("partita_iva"):
        r = requests.put(f"{API}/company", headers=ADMIN, json={"denominazione": "TEST_T3 Azienda Srl", "partita_iva": "01234567890",
                                                                  "codice_fiscale": "01234567890", "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM"})
        assert r.status_code == 200
    base = {"tipo": "cliente", "indirizzo": "Via Test 1", "cap": "20100", "comune": "Milano", "provincia": "MI"}
    defs = {
        "RC": {"denominazione": "TEST_T3 RC Srl", "partita_iva": "11111111111", "codice_destinatario": "ABC1234"},
        "RC_PEC": {"denominazione": "TEST_T3 RCPEC Srl", "partita_iva": "22222222222", "codice_destinatario": "0000000", "pec": "a@pec.it"},
        "MC": {"denominazione": "TEST_T3 MC Privato", "codice_fiscale": "RSSMRA80A01H501U", "codice_destinatario": "0000000"},
        "NS": {"denominazione": "TEST_T3 NS Srl", "partita_iva": "33333333333", "codice_destinatario": "0000000"},
    }
    out = {}
    for k, v in defs.items():
        r = requests.post(f"{API}/parties", headers=ADMIN, json={**base, **v})
        assert r.status_code == 200, r.text
        out[k] = r.json()["id"]
    return out


def _mk(pid, prezzo):
    r = requests.post(f"{API}/invoices", headers=ADMIN, json={"data": DATE, "party_id": pid,
                      "lines": [{"descrizione": "TEST_T3 servizio", "quantita": 1, "prezzo_unitario": prezzo, "aliquota": 22}]})
    assert r.status_code == 200, r.text
    return r.json()


class TestSdi:
    def test_flow_and_dashboard(self, sdi_parties):
        before = requests.get(f"{API}/dashboard", headers=ADMIN).json()
        assert "notifiche" in before and set(before["notifiche"]) == {"attesa", "RC", "MC", "NS"}
        expected = {"RC": "consegnata", "RC_PEC": "consegnata", "MC": "mancata_consegna", "NS": "scartata"}
        notif = {"RC": "RC", "RC_PEC": "RC", "MC": "MC", "NS": "NS"}
        ids = {}
        for k, pid in sdi_parties.items():
            inv = _mk(pid, 100)
            # operatore cannot send
            assert requests.post(f"{API}/invoices/{inv['id']}/send", headers=OPER).status_code == 403
            s = requests.post(f"{API}/invoices/{inv['id']}/send", headers=CONT)
            assert s.status_code == 200 and s.json()["status"] == "inviata" and s.json()["sdi_notifica"] == "IN"
            ids[k] = inv["id"]
        # extra invoice left in attesa
        pend = _mk(sdi_parties["RC"], 50)
        requests.post(f"{API}/invoices/{pend['id']}/send", headers=ADMIN)
        mid = requests.get(f"{API}/dashboard", headers=ADMIN).json()
        assert mid["notifiche"]["attesa"]["count"] == before["notifiche"]["attesa"]["count"] + 5
        for k, iid in ids.items():
            r = requests.post(f"{API}/invoices/{iid}/refresh", headers=OPER)
            assert r.status_code == 200
            d = r.json()
            assert d["status"] == expected[k], (k, d["status"], d["sdi_message"])
            assert d["sdi_notifica"] == notif[k]
            assert d["sdi_history"][-1]["notifica"] == notif[k]
            assert requests.post(f"{API}/invoices/{iid}/refresh", headers=ADMIN).status_code == 400
        after = requests.get(f"{API}/dashboard", headers=ADMIN).json()
        n, b = after["notifiche"], before["notifiche"]
        assert n["RC"]["count"] == b["RC"]["count"] + 2
        assert n["MC"]["count"] == b["MC"]["count"] + 1
        assert n["NS"]["count"] == b["NS"]["count"] + 1
        assert n["attesa"]["count"] == b["attesa"]["count"] + 1
        assert round(n["RC"]["totale"] - b["RC"]["totale"], 2) == 244.0
        assert round(n["MC"]["totale"] - b["MC"]["totale"], 2) == 122.0
        assert round(n["attesa"]["totale"] - b["attesa"]["totale"], 2) == 61.0
        assert after["inviate_totale"] == sum(v["count"] for v in n.values())
        # fatturato = inviata + consegnata + mancata_consegna (not scartata)
        assert round(after["fatturato"] - before["fatturato"], 2) == 122 * 3 + 61
        assert n["MC"]["status"] == "mancata_consegna"
        last_ids = [x["id"] for x in after["ultime_notifiche"]]
        assert ids["NS"] in last_ids and ids["MC"] in last_ids
        assert all(x["status"] != "bozza" for x in after["ultime_notifiche"])
        # filter by status
        mc = requests.get(f"{API}/invoices", headers=ADMIN, params={"status": "mancata_consegna"}).json()
        assert ids["MC"] in [x["id"] for x in mc] and all(x["status"] == "mancata_consegna" for x in mc)
        # mancata_consegna not editable / not resendable; scartata resendable
        assert requests.post(f"{API}/invoices/{ids['MC']}/send", headers=ADMIN).status_code == 400
        assert requests.delete(f"{API}/invoices/{ids['MC']}", headers=ADMIN).status_code == 400

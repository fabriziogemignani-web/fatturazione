# Iteration 2: email auth (register/login/lockout/forgot/reset), articles, party exemptions/N3.5,
# invoice cassa previdenziale + ritenuta d'acconto, XML, company defaults, regression SDI.
import os
import time
import hashlib
import secrets
from datetime import datetime, timezone, timedelta

import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
ADMIN_TOKEN = "test_session_T1_admin_approved"
TS = str(int(time.time()))
INV_DATE = "2026-11-02"  # existing 1/2026 is dated 2026-10-29

mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def H(tok=ADMIN_TOKEN):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    pids = [p["id"] for p in mdb.parties.find({"denominazione": {"$regex": "^TEST_T2_"}})]
    mdb.invoices.delete_many({"party_id": {"$in": pids}})
    mdb.parties.delete_many({"id": {"$in": pids}})
    mdb.articles.delete_many({"codice": {"$regex": "^TEST_T2_"}})
    uids = [u["user_id"] for u in mdb.users.find({"email": {"$regex": r"^test\.user\.t2"}})]
    mdb.user_sessions.delete_many({"user_id": {"$in": uids}})
    mdb.password_reset_tokens.delete_many({"user_id": {"$in": uids}})
    mdb.users.delete_many({"user_id": {"$in": uids}})
    mdb.login_attempts.delete_many({"identifier": {"$regex": "test.user.t2"}})
    mdb.company.update_one({"key": "main"}, {"$set": {"cassa_tipo": "", "ritenuta_tipo": "", "cassa_ritenuta": False}})


# ---------- Email auth ----------
class TestEmailAuth:
    email = f"test.user.t2reg{TS}@example.com"

    def test_register_pending_and_cookie(self):
        r = requests.post(f"{API}/auth/register", json={"name": "TEST_T2 Reg", "email": self.email.upper(), "password": "Password123"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["email"] == self.email and d["status"] == "pending" and d["role"] == "operatore"
        assert "password_hash" not in d
        sc = r.headers.get("set-cookie", "").lower()
        assert "session_token=" in sc and "httponly" in sc and "secure" in sc
        u = mdb.users.find_one({"email": self.email})
        assert u["password_hash"].startswith("$2b$")
        # pending session -> /auth/me ok, data 403
        s = requests.Session()
        s.cookies.set("session_token", r.cookies.get("session_token"))
        assert s.get(f"{API}/auth/me").status_code == 200
        assert s.get(f"{API}/invoices").status_code == 403

    def test_register_duplicate_and_validation(self):
        r = requests.post(f"{API}/auth/register", json={"name": "X", "email": self.email, "password": "Password123"})
        assert r.status_code == 400
        assert requests.post(f"{API}/auth/register", json={"name": "X", "email": f"test.user.t2b{TS}@example.com", "password": "short"}).status_code == 422
        assert requests.post(f"{API}/auth/register", json={"name": "X", "email": "notanemail", "password": "Password123"}).status_code == 422

    def test_login_ok_and_wrong(self):
        r = requests.post(f"{API}/auth/login", json={"email": self.email, "password": "Password123"})
        assert r.status_code == 200 and "password_hash" not in r.json()
        assert r.json()["status"] == "pending"
        r = requests.post(f"{API}/auth/login", json={"email": self.email, "password": "Wrong12345"})
        assert r.status_code == 401
        assert "detail" in r.json()

    def test_bruteforce_lockout(self):
        em = f"test.user.t2lock{TS}@example.com"
        requests.post(f"{API}/auth/register", json={"name": "TEST_T2 Lock", "email": em, "password": "Password123"})
        codes = [requests.post(f"{API}/auth/login", json={"email": em, "password": "bad-pass-x"}).status_code for _ in range(5)]
        assert codes == [401] * 5, codes
        r = requests.post(f"{API}/auth/login", json={"email": em, "password": "Password123"})
        assert r.status_code == 429, r.text

    def test_google_user_cannot_password_login(self):
        r = requests.post(f"{API}/auth/login", json={"email": "test.user.t1.admin.approved@example.com", "password": "whatever123"})
        assert r.status_code == 401

    def test_me_and_users_no_password_hash(self):
        me = requests.get(f"{API}/auth/me", headers=H())
        assert me.status_code == 200 and "password_hash" not in me.json()
        us = requests.get(f"{API}/users", headers=H())
        assert us.status_code == 200
        assert all("password_hash" not in u for u in us.json())
        assert any(u["email"] == self.email for u in us.json())


class TestPasswordReset:
    email = f"test.user.t2reset{TS}@example.com"

    def _token(self, uid, exp_delta=timedelta(hours=1), used=False):
        tok = secrets.token_urlsafe(32)
        mdb.password_reset_tokens.insert_one({"token_hash": hashlib.sha256(tok.encode()).hexdigest(), "user_id": uid,
                                              "expires_at": datetime.now(timezone.utc) + exp_delta, "used": used,
                                              "created_at": datetime.now(timezone.utc).isoformat()})
        return tok

    def test_forgot_unknown_email_generic(self):
        r = requests.post(f"{API}/auth/forgot-password", json={"email": f"test.user.t2nobody{TS}@example.com"})
        assert r.status_code == 200 and r.json()["ok"] is True

    def test_reset_flow(self):
        r = requests.post(f"{API}/auth/register", json={"name": "TEST_T2 Reset", "email": self.email, "password": "OldPassword1"})
        assert r.status_code == 200
        uid = r.json()["user_id"]
        old_cookie = r.cookies.get("session_token")
        tok = self._token(uid)
        assert requests.post(f"{API}/auth/reset-password", json={"token": tok, "password": "short"}).status_code == 422
        r = requests.post(f"{API}/auth/reset-password", json={"token": tok, "password": "NewPassword1"})
        assert r.status_code == 200, r.text
        # sessions removed
        assert mdb.user_sessions.count_documents({"user_id": uid}) == 0
        assert requests.get(f"{API}/auth/me", cookies={"session_token": old_cookie}).status_code == 401
        # reuse rejected
        assert requests.post(f"{API}/auth/reset-password", json={"token": tok, "password": "NewPassword2"}).status_code == 400
        assert requests.post(f"{API}/auth/login", json={"email": self.email, "password": "OldPassword1"}).status_code == 401
        assert requests.post(f"{API}/auth/login", json={"email": self.email, "password": "NewPassword1"}).status_code == 200

    def test_expired_and_invalid_token(self):
        uid = mdb.users.find_one({"email": self.email})["user_id"]
        tok = self._token(uid, exp_delta=timedelta(minutes=-5))
        r = requests.post(f"{API}/auth/reset-password", json={"token": tok, "password": "Another123"})
        assert r.status_code == 400 and "scadut" in r.json()["detail"].lower()
        assert requests.post(f"{API}/auth/reset-password", json={"token": "garbage", "password": "Another123"}).status_code == 400


# ---------- Articles ----------
class TestArticles:
    def test_crud_and_unique(self):
        c = f"TEST_T2_A{TS}"
        r = requests.post(f"{API}/articles", headers=H(), json={"codice": c, "descrizione": "Consulenza oraria", "unita_misura": "ORE", "prezzo": 80, "aliquota": 22, "natura": "N4"})
        assert r.status_code == 200, r.text
        a = r.json()
        assert a["natura"] is None and a["prezzo"] == 80
        assert requests.post(f"{API}/articles", headers=H(), json={"codice": c, "descrizione": "dup", "prezzo": 1, "aliquota": 22}).status_code == 400
        lst = requests.get(f"{API}/articles", headers=H()).json()
        assert any(x["id"] == a["id"] for x in lst)
        r = requests.put(f"{API}/articles/{a['id']}", headers=H(), json={"codice": c, "descrizione": "Consulenza esente", "prezzo": 90, "aliquota": 0, "natura": "N4"})
        assert r.status_code == 200 and r.json()["natura"] == "N4" and r.json()["prezzo"] == 90
        # duplicate codice on update
        r2 = requests.post(f"{API}/articles", headers=H(), json={"codice": c + "B", "descrizione": "B", "prezzo": 1, "aliquota": 10})
        assert requests.put(f"{API}/articles/{r2.json()['id']}", headers=H(), json={"codice": c, "descrizione": "B", "prezzo": 1, "aliquota": 10}).status_code == 400
        assert requests.put(f"{API}/articles/nonexistent", headers=H(), json={"codice": c + "Z", "descrizione": "B", "prezzo": 1, "aliquota": 10}).status_code == 404
        assert requests.delete(f"{API}/articles/{r2.json()['id']}", headers=H()).status_code == 200
        lst = requests.get(f"{API}/articles", headers=H()).json()
        assert not any(x["id"] == r2.json()["id"] for x in lst)

    def test_validation(self):
        assert requests.post(f"{API}/articles", headers=H(), json={"codice": f"TEST_T2_V{TS}", "descrizione": "x", "prezzo": 1, "aliquota": 0}).status_code == 422
        assert requests.post(f"{API}/articles", headers=H(), json={"codice": f"TEST_T2_V{TS}", "descrizione": "x", "prezzo": 1, "aliquota": 7}).status_code == 422
        assert requests.get(f"{API}/articles").status_code == 401


# ---------- Parties exemptions ----------
PARTY = {"tipo": "cliente", "partita_iva": "12345678901", "codice_destinatario": "ABC1234", "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI"}


@pytest.fixture(scope="module")
def parties():
    ord_ = requests.post(f"{API}/parties", headers=H(), json={**PARTY, "denominazione": "TEST_T2_Ordinario"}).json()
    esp = requests.post(f"{API}/parties", headers=H(), json={**PARTY, "denominazione": "TEST_T2_Esportatore", "natura_default": "N3.5",
                                                             "intento_protocollo": "12345678901234567-000001", "intento_data": "2026-01-10"}).json()
    return {"ord": ord_, "esp": esp}


class TestPartyExemption:
    def test_n35_requires_fields(self):
        base = {**PARTY, "denominazione": "TEST_T2_Bad", "natura_default": "N3.5"}
        assert requests.post(f"{API}/parties", headers=H(), json=base).status_code == 422
        assert requests.post(f"{API}/parties", headers=H(), json={**base, "intento_protocollo": "123-1", "intento_data": "2026-01-10"}).status_code == 422
        assert requests.post(f"{API}/parties", headers=H(), json={**base, "intento_protocollo": "12345678901234567-000001"}).status_code == 422
        assert requests.post(f"{API}/parties", headers=H(), json={**PARTY, "denominazione": "TEST_T2_Bad", "natura_default": "N9"}).status_code == 422

    def test_valid_and_clear(self, parties):
        e = parties["esp"]
        assert e["natura_default"] == "N3.5" and e["intento_protocollo"] == "12345678901234567-000001" and e["intento_data"] == "2026-01-10"
        r = requests.put(f"{API}/parties/{e['id']}", headers=H(), json={**PARTY, "denominazione": "TEST_T2_Esportatore", "natura_default": "N4",
                                                                         "intento_protocollo": "12345678901234567-000001", "intento_data": "2026-01-10"})
        assert r.status_code == 200 and r.json()["intento_protocollo"] == "" and r.json()["natura_default"] == "N4"
        # restore
        r = requests.put(f"{API}/parties/{e['id']}", headers=H(), json={**PARTY, "denominazione": "TEST_T2_Esportatore", "natura_default": "N3.5",
                                                                         "intento_protocollo": "12345678901234567-000001", "intento_data": "2026-01-10"})
        assert r.status_code == 200 and r.json()["intento_protocollo"]


# ---------- Invoices: cassa / ritenuta / N3.5 / XML ----------
LINE = {"descrizione": "Progettazione", "quantita": 1, "prezzo_unitario": 1000, "aliquota": 22}
CASSA = {"tipo": "TC04", "aliquota": 4, "aliquota_iva": 22, "ritenuta": False}
RIT = {"tipo": "RT01", "aliquota": 20, "causale": "A"}


class TestInvoiceCassaRitenuta:
    def test_totals_example(self, parties):
        r = requests.post(f"{API}/invoices", headers=H(), json={"data": INV_DATE, "party_id": parties["ord"]["id"], "lines": [LINE], "cassa": CASSA, "ritenuta": RIT})
        assert r.status_code == 200, r.text
        d = r.json()
        assert (d["imponibile"], d["iva"], d["totale"], d["ritenuta_importo"], d["netto"], d["cassa_importo"]) == (1040, 228.8, 1268.8, 200, 1068.8, 40)
        TestInvoiceCassaRitenuta.iid = d["id"]
        # XML
        x = requests.get(f"{API}/invoices/{d['id']}/xml", headers=H()).text
        for s in ["<DatiRitenuta>", "<TipoRitenuta>RT01</TipoRitenuta>", "<ImportoRitenuta>200.00</ImportoRitenuta>", "<AliquotaRitenuta>20.00</AliquotaRitenuta>",
                  "<CausalePagamento>A</CausalePagamento>", "<DatiCassaPrevidenziale>", "<TipoCassa>TC04</TipoCassa>", "<AlCassa>4.00</AlCassa>",
                  "<ImportoContributoCassa>40.00</ImportoContributoCassa>", "<ImponibileCassa>1000.00</ImponibileCassa>",
                  "<Ritenuta>SI</Ritenuta>", "<ImportoPagamento>1068.80</ImportoPagamento>", "<ImportoTotaleDocumento>1268.80</ImportoTotaleDocumento>"]:
            assert s in x, s
        assert x.count("<Ritenuta>SI</Ritenuta>") == 1  # only on line (cassa not subject)

    def test_cassa_soggetta_ritenuta_update(self, parties):
        r = requests.put(f"{API}/invoices/{self.iid}", headers=H(), json={"data": INV_DATE, "party_id": parties["ord"]["id"], "lines": [LINE], "cassa": {**CASSA, "ritenuta": True}, "ritenuta": RIT})
        assert r.status_code == 200, r.text
        g = requests.get(f"{API}/invoices/{self.iid}", headers=H()).json()
        assert g["ritenuta_importo"] == 208 and g["netto"] == 1060.8 and g["ritenuta_imponibile"] == 1040
        x = requests.get(f"{API}/invoices/{self.iid}/xml", headers=H()).text
        assert x.count("<Ritenuta>SI</Ritenuta>") == 2 and "<ImportoPagamento>1060.80</ImportoPagamento>" in x

    def test_invalid_cassa_ritenuta(self, parties):
        b = {"data": INV_DATE, "party_id": parties["ord"]["id"], "lines": [LINE]}
        assert requests.post(f"{API}/invoices", headers=H(), json={**b, "cassa": {**CASSA, "tipo": "TC99"}}).status_code == 422
        assert requests.post(f"{API}/invoices", headers=H(), json={**b, "cassa": {**CASSA, "aliquota_iva": 0}}).status_code == 422
        assert requests.post(f"{API}/invoices", headers=H(), json={**b, "ritenuta": {**RIT, "tipo": "RT09"}}).status_code == 422
        assert requests.post(f"{API}/invoices", headers=H(), json={**b, "ritenuta": {**RIT, "aliquota": 0}}).status_code == 422

    def test_n35_requires_client_dichiarazione(self, parties):
        r = requests.post(f"{API}/invoices", headers=H(), json={"data": INV_DATE, "party_id": parties["ord"]["id"], "lines": [{**LINE, "aliquota": 0, "natura": "N3.5"}]})
        assert r.status_code == 422 and "N3.5" in r.json()["detail"]

    def test_n35_xml_intento(self, parties):
        r = requests.post(f"{API}/invoices", headers=H(), json={"data": INV_DATE, "party_id": parties["esp"]["id"], "lines": [{**LINE, "aliquota": 0, "natura": "N3.5"}, {**LINE, "aliquota": 0, "natura": "N3.5"}]})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["iva"] == 0 and d["totale"] == 2000
        x = requests.get(f"{API}/invoices/{d['id']}/xml", headers=H()).text
        assert "<TipoDato>INTENTO</TipoDato>" in x and "<RiferimentoTesto>12345678901234567-000001</RiferimentoTesto>" in x
        assert "<RiferimentoData>2026-01-10</RiferimentoData>" in x and x.count("<TipoDato>INTENTO</TipoDato>") == 1
        assert "<Natura>N3.5</Natura>" in x and "Dich. intento prot." in x
        TestInvoiceCassaRitenuta.n35_id = d["id"]


# ---------- Company defaults ----------
class TestCompanyDefaults:
    def test_put_defaults(self):
        c = requests.get(f"{API}/company", headers=H()).json()
        c.update({"cassa_tipo": "TC04", "cassa_aliquota": 4, "cassa_aliquota_iva": 22, "cassa_ritenuta": True, "ritenuta_tipo": "RT01", "ritenuta_aliquota": 20, "ritenuta_causale": "A"})
        r = requests.put(f"{API}/company", headers=H(), json=c)
        assert r.status_code == 200
        g = requests.get(f"{API}/company", headers=H()).json()
        assert g["cassa_tipo"] == "TC04" and g["ritenuta_tipo"] == "RT01" and g["cassa_ritenuta"] is True


# ---------- Regression SDI ----------
class TestRegressionSDI:
    def test_send_refresh(self, parties):
        iid = TestInvoiceCassaRitenuta.n35_id
        r = requests.post(f"{API}/invoices/{iid}/send", headers=H())
        assert r.status_code == 200 and r.json()["status"] == "inviata"
        r = requests.post(f"{API}/invoices/{iid}/refresh", headers=H())
        assert r.status_code == 200 and r.json()["status"] == "consegnata"
        assert requests.put(f"{API}/invoices/{iid}", headers=H(), json={"data": INV_DATE, "party_id": parties["esp"]["id"], "lines": [LINE]}).status_code == 400

    def test_numbering_sequential(self):
        lst = [i for i in requests.get(f"{API}/invoices", headers=H()).json() if i["anno"] == 2026]
        nums = sorted(i["numero"] for i in lst)
        assert nums == list(range(1, len(nums) + 1)), nums

# Iteration 4: multi-company (tenant via X-Company-Id), companies CRUD, user company assignment, isolation
import os
import subprocess
from datetime import date
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
ADMIN_TOK = "test_session_a"
CONT_TOK = "test_session_T4_cont"
OPER_TOK = "test_session_T4_oper"
TODAY = date.today().isoformat()


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'],
                          capture_output=True, text=True).stdout.strip()


def H(tok, cid=None):
    h = {"Authorization": f"Bearer {tok}"}
    if cid:
        h["X-Company-Id"] = cid
    return h


def company(piva, name):
    return {"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01",
            "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"}


def party(name, **kw):
    d = {"tipo": "cliente", "denominazione": name, "partita_iva": "01234567890", "codice_destinatario": "ABC1234",
         "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"}
    d.update(kw)
    return d


def inv(pid):
    return {"tipo_documento": "TD01", "data": TODAY, "party_id": pid, "modalita_pagamento": "MP05",
            "lines": [{"descrizione": "Consulenza", "quantita": 1, "prezzo_unitario": 100, "aliquota": 22}]}


@pytest.fixture(scope="module")
def ctx():
    exp = "new Date(Date.now()+7*24*3600*1000)"
    mongo(f'db.users.deleteMany({{user_id: /^test-user-T4/}}); db.user_sessions.deleteMany({{user_id: /^test-user-T4/}});'
          f'db.users.insertOne({{user_id:"test-user-T4-cont", email:"test.user.t4.cont@example.com", name:"TEST_T4 Cont", role:"contabile", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.users.insertOne({{user_id:"test-user-T4-oper", email:"test.user.t4.oper@example.com", name:"TEST_T4 Oper", role:"operatore", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"test-user-T4-cont", session_token:"{CONT_TOK}", expires_at:{exp}}});'
          f'db.user_sessions.insertOne({{user_id:"test-user-T4-oper", session_token:"{OPER_TOK}", expires_at:{exp}}});')
    c = {}
    for k, piva, name in (("A", "44444444441", "TEST_T4 Alfa"), ("B", "44444444442", "TEST_T4 Beta"), ("D", "44444444443", "TEST_T4 Delta")):
        mongo(f'db.companies.deleteMany({{partita_iva:"{piva}"}})')
        r = requests.post(f"{API}/companies", headers=H(ADMIN_TOK), json=company(piva, name))
        assert r.status_code == 200, r.text
        c[k] = r.json()["id"]
    yield c
    ids = list(c.values())
    js_ids = str(ids).replace("'", '"')
    mongo(f'db.invoices.deleteMany({{company_id: {{$in: {js_ids}}}}}); db.parties.deleteMany({{company_id: {{$in: {js_ids}}}}});'
          f'db.articles.deleteMany({{company_id: {{$in: {js_ids}}}}}); db.companies.deleteMany({{id: {{$in: {js_ids}}}}});'
          f'db.users.deleteMany({{user_id: /^test-user-T4/}}); db.user_sessions.deleteMany({{user_id: /^test-user-T4/}});'
          f'db.users.deleteMany({{email: /^test\\.user\\.t4/}}); db.users.updateMany({{}}, {{$pull: {{company_ids: {{$in: {js_ids}}}}}}});')


# ---- Companies CRUD ----
class TestCompanies:
    def test_list_admin_sees_all(self, ctx):
        r = requests.get(f"{API}/companies", headers=H(ADMIN_TOK))
        assert r.status_code == 200
        ids = [x["id"] for x in r.json()]
        assert all(v in ids for v in ctx.values())
        assert all("_id" not in x for x in r.json())

    def test_duplicate_piva_create_and_update(self, ctx):
        r = requests.post(f"{API}/companies", headers=H(ADMIN_TOK), json=company("44444444441", "TEST_T4 Dup"))
        assert r.status_code == 400
        r = requests.put(f"{API}/company", headers=H(ADMIN_TOK, ctx["B"]), json=company("44444444441", "TEST_T4 Beta"))
        assert r.status_code == 400
        r = requests.put(f"{API}/company", headers=H(ADMIN_TOK, ctx["B"]), json={**company("44444444442", "TEST_T4 Beta2"), "iban": "IT60X0542811101000000123456"})
        assert r.status_code == 200 and r.json()["denominazione"] == "TEST_T4 Beta2"
        g = requests.get(f"{API}/company", headers=H(ADMIN_TOK, ctx["B"])).json()
        assert g["denominazione"] == "TEST_T4 Beta2" and g["id"] == ctx["B"]

    def test_create_validation(self):
        assert requests.post(f"{API}/companies", headers=H(ADMIN_TOK), json=company("123", "X")).status_code == 422

    def test_non_admin_cannot_create_or_delete(self, ctx):
        assert requests.post(f"{API}/companies", headers=H(CONT_TOK), json=company("44444444449", "X")).status_code == 403
        assert requests.delete(f"{API}/companies/{ctx['A']}", headers=H(OPER_TOK)).status_code == 403

    def test_missing_header_400(self):
        for p in ("company", "parties", "articles", "invoices", "dashboard"):
            assert requests.get(f"{API}/{p}", headers=H(ADMIN_TOK)).status_code == 400, p

    def test_unknown_company_404(self):
        assert requests.get(f"{API}/parties", headers=H(ADMIN_TOK, "nope")).status_code == 404


# ---- Isolation + numbering ----
class TestIsolation:
    def test_isolation_and_numbering(self, ctx):
        A, B = H(ADMIN_TOK, ctx["A"]), H(ADMIN_TOK, ctx["B"])
        pa = requests.post(f"{API}/parties", headers=A, json=party("TEST_T4 ClienteA")).json()
        pb = requests.post(f"{API}/parties", headers=B, json=party("TEST_T4 ClienteB")).json()
        assert pa["company_id"] == ctx["A"]
        la = [p["id"] for p in requests.get(f"{API}/parties", headers=A).json()]
        assert pa["id"] in la and pb["id"] not in la
        # cross-company party
        assert requests.put(f"{API}/parties/{pa['id']}", headers=B, json=party("hack")).status_code == 404
        # articles: same codice allowed across companies
        aa = requests.post(f"{API}/articles", headers=A, json={"codice": "T4ART", "descrizione": "a", "prezzo": 10, "aliquota": 22})
        ab = requests.post(f"{API}/articles", headers=B, json={"codice": "T4ART", "descrizione": "b", "prezzo": 10, "aliquota": 22})
        assert aa.status_code == 200 and ab.status_code == 200, (aa.text, ab.text)
        assert requests.post(f"{API}/articles", headers=A, json={"codice": "T4ART", "descrizione": "a", "prezzo": 1, "aliquota": 22}).status_code == 400
        assert requests.put(f"{API}/articles/{aa.json()['id']}", headers=B, json={"codice": "T4X", "descrizione": "x", "aliquota": 22}).status_code == 404
        assert [a["id"] for a in requests.get(f"{API}/articles", headers=B).json()] == [ab.json()["id"]]
        # invoices numbering per company
        ia = requests.post(f"{API}/invoices", headers=A, json=inv(pa["id"]))
        ib = requests.post(f"{API}/invoices", headers=B, json=inv(pb["id"]))
        assert ia.status_code == 200 and ib.status_code == 200, (ia.text, ib.text)
        yr = TODAY[:4]
        assert ia.json()["numero_display"] == f"1/{yr}" and ib.json()["numero_display"] == f"1/{yr}"
        assert ia.json()["progressivo_invio"] == "00001" and ib.json()["progressivo_invio"] == "00001"
        # cross-company invoice
        assert requests.post(f"{API}/invoices", headers=B, json=inv(pa["id"])).json().get("detail") == "Cliente non trovato"
        iid = ia.json()["id"]
        for m, p in (("get", ""), ("get", "/xml"), ("post", "/send"), ("post", "/refresh"), ("delete", "")):
            assert getattr(requests, m)(f"{API}/invoices/{iid}{p}", headers=B).status_code == 404, p
        assert requests.put(f"{API}/invoices/{iid}", headers=B, json=inv(pb["id"])).status_code == 404
        assert requests.delete(f"{API}/parties/{pa['id']}", headers=B).json() == {"ok": True}
        assert requests.get(f"{API}/invoices/{iid}", headers=A).status_code == 200  # party A untouched
        assert pa["id"] in [p["id"] for p in requests.get(f"{API}/parties", headers=A).json()]
        lb = [i["id"] for i in requests.get(f"{API}/invoices", headers=B).json()]
        assert lb == [ib.json()["id"]]
        # XML for A uses company A
        x = requests.get(f"{API}/invoices/{iid}/xml", headers=A)
        assert x.status_code == 200 and "44444444441" in x.text and "TEST_T4 Alfa" in x.text
        assert "44444444441" in x.headers.get("X-Filename", "")
        # send/refresh
        s = requests.post(f"{API}/invoices/{iid}/send", headers=A)
        assert s.status_code == 200 and s.json()["status"] == "inviata"
        rf = requests.post(f"{API}/invoices/{iid}/refresh", headers=A)
        assert rf.status_code == 200 and rf.json()["status"] == "consegnata"
        # dashboard scoped
        da = requests.get(f"{API}/dashboard", headers=A).json()
        db_ = requests.get(f"{API}/dashboard", headers=B).json()
        assert da["totale_fatture"] == 1 and da["counts"]["consegnata"] == 1 and da["fatturato"] == 122.0
        assert db_["totale_fatture"] == 1 and db_["counts"]["bozza"] == 1 and db_["fatturato"] == 0
        ctx["inv_A"] = iid
        ctx["party_A"] = pa["id"]

    def test_delete_company_with_invoices_blocked(self, ctx):
        r = requests.delete(f"{API}/companies/{ctx['A']}", headers=H(ADMIN_TOK))
        assert r.status_code == 400

    def test_delete_company_without_invoices(self, ctx):
        D = H(ADMIN_TOK, ctx["D"])
        p = requests.post(f"{API}/parties", headers=D, json=party("TEST_T4 ClienteD")).json()
        requests.post(f"{API}/articles", headers=D, json={"codice": "T4D", "descrizione": "d", "aliquota": 22})
        mongo(f'db.users.updateOne({{user_id:"test-user-T4-oper"}}, {{$addToSet: {{company_ids: "{ctx["D"]}"}}}})')
        r = requests.delete(f"{API}/companies/{ctx['D']}", headers=H(ADMIN_TOK))
        assert r.status_code == 200
        assert mongo(f'print(db.parties.countDocuments({{company_id:"{ctx["D"]}"}}) + db.articles.countDocuments({{company_id:"{ctx["D"]}"}}))') == "0"
        assert p["id"]
        assert ctx["D"] not in mongo('print(JSON.stringify(db.users.findOne({user_id:"test-user-T4-oper"}).company_ids))')
        assert requests.get(f"{API}/company", headers=D).status_code == 404
        assert requests.delete(f"{API}/companies/{ctx['D']}", headers=H(ADMIN_TOK)).status_code == 404


# ---- User assignment + non-admin access ----
class TestUserAssignment:
    def test_patch_company_ids_validation(self, ctx):
        assert requests.patch(f"{API}/users/test-user-T4-cont", headers=H(ADMIN_TOK), json={"company_ids": ["nope"]}).status_code == 400
        r = requests.patch(f"{API}/users/test-user-T4-cont", headers=H(ADMIN_TOK), json={"company_ids": [ctx["A"], ctx["A"]]})
        assert r.status_code == 200 and r.json()["company_ids"] == [ctx["A"]]
        u = [x for x in requests.get(f"{API}/users", headers=H(ADMIN_TOK)).json() if x["user_id"] == "test-user-T4-cont"][0]
        assert u["company_ids"] == [ctx["A"]]

    def test_non_admin_scoped(self, ctx):
        r = requests.get(f"{API}/companies", headers=H(CONT_TOK))
        assert [c["id"] for c in r.json()] == [ctx["A"]]
        assert requests.get(f"{API}/invoices", headers=H(CONT_TOK, ctx["B"])).status_code == 404
        assert requests.get(f"{API}/company", headers=H(CONT_TOK, ctx["B"])).status_code == 404
        li = requests.get(f"{API}/invoices", headers=H(CONT_TOK, ctx["A"]))
        assert li.status_code == 200 and [i["id"] for i in li.json()] == [ctx["inv_A"]]
        # contabile cannot edit company settings
        assert requests.put(f"{API}/company", headers=H(CONT_TOK, ctx["A"]), json=company("44444444441", "x")).status_code == 403

    def test_operatore_no_companies(self):
        assert requests.get(f"{API}/companies", headers=H(OPER_TOK)).json() == []

    def test_create_user_with_companies(self, ctx):
        r = requests.post(f"{API}/users", headers=H(ADMIN_TOK), json={"name": "TEST_T4 New", "email": "test.user.t4.new@example.com", "role": "operatore", "send_invite": False, "company_ids": [ctx["B"]]})
        assert r.status_code == 200 and r.json()["company_ids"] == [ctx["B"]]
        r = requests.post(f"{API}/users", headers=H(ADMIN_TOK), json={"name": "TEST_T4 Bad", "email": "test.user.t4.bad@example.com", "send_invite": False, "company_ids": ["nope"]})
        assert r.status_code == 400

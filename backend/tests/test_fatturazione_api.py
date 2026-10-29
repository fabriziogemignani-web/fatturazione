# Regression tests for FE Fatturazione Elettronica API (auth/roles, company, parties, invoices, XML, simulated SDI, dashboard)
# Sessions seeded by: mongosh --quiet /app/backend/tests/seed_sessions.js
import os
import re
import pytest
import requests
import xml.etree.ElementTree as ET

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

TOK = {
    "admin": "test_session_T1_admin_approved",
    "contabile": "test_session_T1_contabile_approved",
    "operatore": "test_session_T1_operatore_approved",
    "pending": "test_session_T1_operatore_pending",
}


def s(role):
    sess = requests.Session()
    sess.headers.update({"Authorization": f"Bearer {TOK[role]}", "Content-Type": "application/json"})
    return sess


COMPANY = {"denominazione": "TEST_Azienda", "partita_iva": "01234567890", "codice_fiscale": "", "regime_fiscale": "RF01",
           "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT",
           "iban": "IT60X0542811101000000123456", "email": "", "pec": "", "telefono": ""}


def party(**kw):
    base = {"tipo": "cliente", "denominazione": "TEST_T1_Cliente", "partita_iva": "12345678901", "codice_fiscale": "",
            "codice_destinatario": "ABC1234", "pec": "", "indirizzo": "Via Test 2", "cap": "20100", "comune": "Milano",
            "provincia": "MI", "nazione": "IT"}
    base.update(kw)
    return base


def inv_body(pid, lines=None, data="2026-01-15"):
    return {"tipo_documento": "TD01", "data": data, "party_id": pid, "modalita_pagamento": "MP05",
            "lines": lines or [{"descrizione": "TEST riga", "quantita": 2, "prezzo_unitario": 100, "aliquota": 22}]}


@pytest.fixture(scope="module")
def created():
    store = {"parties": [], "invoices": []}
    yield store
    a = s("admin")
    for iid in store["invoices"]:
        a.delete(f"{API}/invoices/{iid}")
    for pid in store["parties"]:
        a.delete(f"{API}/parties/{pid}")


# ---- Auth & roles ----
class TestAuth:
    def test_me_admin(self):
        r = s("admin").get(f"{API}/auth/me")
        assert r.status_code == 200
        assert r.json()["role"] == "admin" and "_id" not in r.json()

    def test_unauth(self):
        assert requests.get(f"{API}/auth/me").status_code == 401
        assert requests.get(f"{API}/invoices").status_code == 401

    def test_pending_me_ok_data_403(self):
        p = s("pending")
        assert p.get(f"{API}/auth/me").json()["status"] == "pending"
        for ep in ["/invoices", "/parties", "/company", "/dashboard"]:
            assert p.get(f"{API}{ep}").status_code == 403, ep

    def test_users_admin_only(self):
        assert s("operatore").get(f"{API}/users").status_code == 403
        assert s("contabile").get(f"{API}/users").status_code == 403
        r = s("admin").get(f"{API}/users")
        assert r.status_code == 200 and any(u["user_id"] == "test-user-T1-operatore-pending" for u in r.json())

    def test_patch_user_role_and_status(self):
        a = s("admin")
        uid = "test-user-T1-contabile-approved"
        r = a.patch(f"{API}/users/{uid}", json={"role": "operatore"})
        assert r.status_code == 200 and r.json()["role"] == "operatore"
        r = a.patch(f"{API}/users/{uid}", json={"role": "contabile"})
        assert r.json()["role"] == "contabile"
        assert a.patch(f"{API}/users/{uid}", json={"role": "boss"}).status_code == 422
        assert a.patch(f"{API}/users/nope", json={"role": "admin"}).status_code == 404


# ---- Company ----
class TestCompany:
    def test_put_company_ok(self):
        r = s("admin").put(f"{API}/company", json=COMPANY)
        assert r.status_code == 200 and r.json()["partita_iva"] == "01234567890"
        assert s("operatore").get(f"{API}/company").json()["denominazione"] == "TEST_Azienda"

    def test_company_validation(self):
        r = s("admin").put(f"{API}/company", json={**COMPANY, "partita_iva": "123"})
        assert r.status_code == 422 and "11 cifre" in str(r.json())
        r = s("admin").put(f"{API}/company", json={**COMPANY, "cap": "1234"})
        assert r.status_code == 422 and "5 cifre" in str(r.json())

    def test_company_non_admin_403(self):
        assert s("contabile").put(f"{API}/company", json=COMPANY).status_code == 403


# ---- Parties ----
class TestParties:
    def test_crud(self, created):
        a = s("operatore")
        r = a.post(f"{API}/parties", json=party(tipo="fornitore", denominazione="TEST_T1_Forn"))
        assert r.status_code == 200
        pid = r.json()["id"]
        assert any(p["id"] == pid for p in a.get(f"{API}/parties", params={"tipo": "fornitore"}).json())
        assert not any(p["id"] == pid for p in a.get(f"{API}/parties", params={"tipo": "cliente"}).json())
        r = a.put(f"{API}/parties/{pid}", json=party(tipo="fornitore", denominazione="TEST_T1_Forn2", codice_destinatario="xyz9876"))
        assert r.status_code == 200 and r.json()["denominazione"] == "TEST_T1_Forn2" and r.json()["codice_destinatario"] == "XYZ9876"
        assert a.delete(f"{API}/parties/{pid}").status_code == 200
        assert not any(p["id"] == pid for p in a.get(f"{API}/parties").json())

    def test_validation(self):
        a = s("admin")
        r = a.post(f"{API}/parties", json=party(codice_destinatario="ABC"))
        assert r.status_code == 422 and "7 caratteri" in str(r.json())
        r = a.post(f"{API}/parties", json=party(partita_iva="999"))
        assert r.status_code == 422 and "11 cifre" in str(r.json())

    def test_update_missing_404(self):
        assert s("admin").put(f"{API}/parties/nope", json=party()).status_code == 404


# ---- Invoices + XML + SDI ----
class TestInvoices:
    def test_create_totals_numbering(self, created):
        a = s("admin")
        pid = a.post(f"{API}/parties", json=party()).json()["id"]
        created["parties"].append(pid)
        lines = [
            {"descrizione": "A", "quantita": 2, "prezzo_unitario": 100, "aliquota": 22},
            {"descrizione": "B", "quantita": 1, "prezzo_unitario": 50, "aliquota": 10},
            {"descrizione": "C", "quantita": 3, "prezzo_unitario": 10.33, "aliquota": 4},
            {"descrizione": "D", "quantita": 1, "prezzo_unitario": 20, "aliquota": 5},
            {"descrizione": "E", "quantita": 1, "prezzo_unitario": 30, "aliquota": 0, "natura": "N2.2"},
        ]
        r1 = a.post(f"{API}/invoices", json=inv_body(pid, lines))
        assert r1.status_code == 200, r1.text
        d = r1.json()
        created["invoices"].append(d["id"])
        # imponibile 200+50+30.99+20+30 = 330.99 ; iva 44+5+1.24+1+0 = 51.24
        assert d["imponibile"] == 330.99 and d["iva"] == 51.24 and d["totale"] == 382.23
        assert d["status"] == "bozza" and re.fullmatch(r"\d+/2026", d["numero_display"])
        r2 = a.post(f"{API}/invoices", json=inv_body(pid))
        created["invoices"].append(r2.json()["id"])
        assert r2.json()["numero"] == d["numero"] + 1
        assert r2.json()["totale"] == 244.0
        g = a.get(f"{API}/invoices/{d['id']}").json()
        assert g["totale"] == 382.23 and g["cliente"]["denominazione"] == "TEST_T1_Cliente"
        created["main"] = d["id"]
        created["pid"] = pid

    def test_zero_vat_requires_natura(self, created):
        r = s("admin").post(f"{API}/invoices", json=inv_body(created["pid"], [{"descrizione": "X", "quantita": 1, "prezzo_unitario": 1, "aliquota": 0}]))
        assert r.status_code == 422 and "Natura" in r.text

    def test_invalid_aliquota_and_client(self, created):
        a = s("admin")
        assert a.post(f"{API}/invoices", json=inv_body(created["pid"], [{"descrizione": "X", "quantita": 1, "prezzo_unitario": 1, "aliquota": 21}])).status_code == 422
        assert a.post(f"{API}/invoices", json=inv_body("nope")).status_code == 400

    def test_invalid_date_handled(self, created):
        r = s("admin").post(f"{API}/invoices", json=inv_body(created["pid"], data="abc"))
        assert r.status_code in (400, 422), f"invalid date returned {r.status_code}"

    def test_xml(self, created):
        r = s("admin").get(f"{API}/invoices/{created['main']}/xml")
        assert r.status_code == 200
        fn = r.headers.get("x-filename")
        assert re.fullmatch(r"IT01234567890_[0-9A-Z]{5}\.xml", fn), fn
        root = ET.fromstring(r.content)
        ns = {"p": "http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2"}
        assert root.get("versione") == "FPR12"
        assert root.find(".//ImportoTotaleDocumento").text == "382.23"
        assert root.find(".//CodiceDestinatario").text == "ABC1234"
        nat = [e.text for e in root.iter("Natura")]
        assert "N2.2" in nat and len(root.findall(".//DatiRiepilogo")) == 5

    def test_delete_party_used_blocked(self, created):
        r = s("admin").delete(f"{API}/parties/{created['pid']}")
        assert r.status_code == 400 and "fatture" in r.json()["detail"]

    def test_operatore_cannot_send(self, created):
        assert s("operatore").post(f"{API}/invoices/{created['main']}/send").status_code == 403

    def test_send_refresh_consegnata(self, created):
        c = s("contabile")
        r = c.post(f"{API}/invoices/{created['main']}/send")
        assert r.status_code == 200 and r.json()["status"] == "inviata" and r.json()["sdi_id"]
        assert c.post(f"{API}/invoices/{created['main']}/send").status_code == 400
        assert c.put(f"{API}/invoices/{created['main']}", json=inv_body(created["pid"])).status_code == 400
        assert c.delete(f"{API}/invoices/{created['main']}").status_code == 400
        r = c.post(f"{API}/invoices/{created['main']}/refresh")
        assert r.status_code == 200 and r.json()["status"] == "consegnata"
        assert len(r.json()["sdi_history"]) == 3

    def test_scartata_flow(self, created):
        a = s("admin")
        pid = a.post(f"{API}/parties", json=party(denominazione="TEST_T1_NoPec", codice_destinatario="0000000", pec="")).json()["id"]
        created["parties"].append(pid)
        iid = a.post(f"{API}/invoices", json=inv_body(pid)).json()["id"]
        created["invoices"].append(iid)
        assert a.post(f"{API}/invoices/{iid}/send").json()["status"] == "inviata"
        r = a.post(f"{API}/invoices/{iid}/refresh").json()
        assert r["status"] == "scartata" and "00426" in r["sdi_message"]
        # fix client: add PEC, then edit invoice (re-snapshot) and resend
        a.put(f"{API}/parties/{pid}", json=party(denominazione="TEST_T1_NoPec", codice_destinatario="0000000", pec="t@pec.it"))
        u = a.put(f"{API}/invoices/{iid}", json=inv_body(pid))
        assert u.status_code == 200 and u.json()["cliente"]["pec"] == "t@pec.it"
        x = a.get(f"{API}/invoices/{iid}/xml").text
        assert "<PECDestinatario>t@pec.it</PECDestinatario>" in x
        assert a.post(f"{API}/invoices/{iid}/send").json()["status"] == "inviata"
        assert a.post(f"{API}/invoices/{iid}/refresh").json()["status"] == "consegnata"

    def test_list_filter(self, created):
        a = s("admin")
        lst = a.get(f"{API}/invoices", params={"status": "consegnata"}).json()
        assert all(i["status"] == "consegnata" for i in lst) and any(i["id"] == created["main"] for i in lst)
        assert "sdi_history" not in lst[0]

    def test_dashboard(self):
        r = s("operatore").get(f"{API}/dashboard")
        assert r.status_code == 200
        d = r.json()
        for k in ["counts", "fatturato", "imponibile", "iva", "mesi", "recenti", "totale_fatture"]:
            assert k in d
        assert len(d["mesi"]) == 12 and d["counts"]["consegnata"] >= 2
        assert d["totale_fatture"] == sum(d["counts"].values())

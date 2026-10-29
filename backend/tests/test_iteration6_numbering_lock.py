# Iteration 6: manual invoice numbering (progressivity + date coherence) and lock after SDI send
import os
import subprocess
from datetime import date, timedelta
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
TOK = "test_session_t6_admin"
UID = "test-user-t6-admin"
T = date.today()
YEAR = T.year
D = lambda n: (T - timedelta(days=n)).isoformat()  # noqa: E731  (n days ago)


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


def doc(pid, data, numero=None, tipo="TD01", price=100, link=None):
    d = {"tipo_documento": tipo, "data": data, "party_id": pid, "modalita_pagamento": "MP05",
         "lines": [{"descrizione": "Consulenza", "quantita": 1, "prezzo_unitario": price, "aliquota": 22}]}
    if numero is not None:
        d["numero"] = numero
    if link:
        d["fattura_collegata_id"] = link
    return d


@pytest.fixture(scope="module")
def ctx():
    mongo(f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});'
          f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t6.admin@example.com", name:"TEST_T6 Admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+7*864e5), created_at:new Date().toISOString()}});')
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    mongo('db.companies.deleteMany({partita_iva:"66666666661"})')
    r = s.post(f"{API}/companies", json={"denominazione": "TEST_T6 Numerazione", "partita_iva": "66666666661", "codice_fiscale": "66666666661",
                                         "regime_fiscale": "RF01", "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    h = {"X-Company-Id": cid}
    p = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": "TEST_T6 Cliente", "partita_iva": "01234567890", "codice_destinatario": "ABC1234",
                                       "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"}, headers=h)
    assert p.status_code == 200, p.text
    yield {"s": s, "h": h, "cid": cid, "pid": p.json()["id"], "st": {}}
    mongo(f'db.invoices.deleteMany({{company_id:"{cid}"}}); db.parties.deleteMany({{company_id:"{cid}"}}); db.counters.deleteMany({{key:"progressivo_{cid}"}});'
          f'db.companies.deleteMany({{id:"{cid}"}}); db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


class TestNumbering:
    def test_01_auto_number(self, ctx):
        s, h = ctx["s"], ctx["h"]
        r = s.post(f"{API}/invoices", json=doc(ctx["pid"], D(20)), headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["numero"] == 1 and r.json()["numero_display"] == f"1/{YEAR}"
        ctx["st"]["i1"] = r.json()["id"]

    def test_02_manual_number_gap(self, ctx):
        s, h = ctx["s"], ctx["h"]
        # iteration 7 rule: manual numero > max+1 is rejected when the register is not empty
        r = s.post(f"{API}/invoices", json=doc(ctx["pid"], D(10), numero=5), headers=h)
        assert r.status_code == 400 and "progressiva" in r.json()["detail"], r.text
        # simulate a legacy gap: create n.2 then move it to n.5 directly in DB
        r = s.post(f"{API}/invoices", json=doc(ctx["pid"], D(10)), headers=h)
        assert r.status_code == 200 and r.json()["numero"] == 2, r.text
        iid = r.json()["id"]
        mongo(f'db.invoices.updateOne({{id:"{iid}"}}, {{$set:{{numero:5, numero_display:"5/{YEAR}"}}}})')
        ctx["st"]["i5"] = iid

    def test_03_auto_after_manual_is_max_plus_one(self, ctx):
        s, h = ctx["s"], ctx["h"]
        r = s.post(f"{API}/invoices", json=doc(ctx["pid"], D(5)), headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["numero"] == 6
        ctx["st"]["i6"] = r.json()["id"]

    def test_04_duplicate_number(self, ctx):
        r = ctx["s"].post(f"{API}/invoices", json=doc(ctx["pid"], D(10), numero=5), headers=ctx["h"])
        assert r.status_code == 400 and "già usato" in r.json()["detail"], r.text

    def test_05_date_before_prev(self, ctx):
        # number 3 between 1 (D20) and 5 (D10): date D25 < D20 -> error on previous
        r = ctx["s"].post(f"{API}/invoices", json=doc(ctx["pid"], D(25), numero=3), headers=ctx["h"])
        assert r.status_code == 400 and "Data non coerente" in r.json()["detail"] and "precedente" in r.json()["detail"], r.text

    def test_06_date_after_next(self, ctx):
        r = ctx["s"].post(f"{API}/invoices", json=doc(ctx["pid"], D(7), numero=3), headers=ctx["h"])
        assert r.status_code == 400 and "successivo" in r.json()["detail"], r.text

    def test_07_insert_in_gap_valid(self, ctx):
        r = ctx["s"].post(f"{API}/invoices", json=doc(ctx["pid"], D(15), numero=3), headers=ctx["h"])
        assert r.status_code == 200, r.text
        assert r.json()["numero_display"] == f"3/{YEAR}"
        ctx["st"]["i3"] = r.json()["id"]

    def test_08_boundary_same_date_ok(self, ctx):
        r = ctx["s"].post(f"{API}/invoices", json=doc(ctx["pid"], D(10), numero=4), headers=ctx["h"])
        assert r.status_code == 200, r.text
        ctx["st"]["i4"] = r.json()["id"]

    def test_09_auto_with_earlier_date_rejected(self, ctx):
        r = ctx["s"].post(f"{API}/invoices", json=doc(ctx["pid"], D(30)), headers=ctx["h"])
        assert r.status_code == 400 and "precedente" in r.json()["detail"], r.text

    def test_10_invalid_numero_validation(self, ctx):
        r = ctx["s"].post(f"{API}/invoices", json=doc(ctx["pid"], D(1), numero=0), headers=ctx["h"])
        assert r.status_code == 422

    def test_11_nc_register_separate(self, ctx):
        s, h = ctx["s"], ctx["h"]
        # send i1 so it can be credited
        assert s.post(f"{API}/invoices/{ctx['st']['i1']}/send", headers=h).status_code == 200
        r = s.post(f"{API}/invoices", json=doc(ctx["pid"], D(2), numero=5, tipo="TD04", price=10, link=ctx["st"]["i1"]), headers=h)
        assert r.status_code == 200, r.text  # number 5 is free in NC register
        assert r.json()["numero_display"] == f"5/NC/{YEAR}"
        ctx["st"]["nc5"] = r.json()["id"]


class TestUpdateNumber:
    def test_12_change_number_on_draft(self, ctx):
        s, h = ctx["s"], ctx["h"]
        # iteration 7 rule: renumbering 6 -> 7 would exceed max+1 (5+1) -> rejected
        r = s.put(f"{API}/invoices/{ctx['st']['i6']}", json=doc(ctx["pid"], D(5), numero=7), headers=h)
        assert r.status_code == 400 and "progressiva" in r.json()["detail"], r.text
        g = s.get(f"{API}/invoices/{ctx['st']['i6']}", headers=h).json()
        assert g["numero"] == 6 and g["numero_display"] == f"6/{YEAR}"

    def test_13_update_without_numero_keeps(self, ctx):
        s, h = ctx["s"], ctx["h"]
        r = s.put(f"{API}/invoices/{ctx['st']['i6']}", json=doc(ctx["pid"], D(5), price=200), headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["numero"] == 6 and r.json()["totale"] == 244.0

    def test_14_update_to_used_number(self, ctx):
        r = ctx["s"].put(f"{API}/invoices/{ctx['st']['i6']}", json=doc(ctx["pid"], D(5), numero=5), headers=ctx["h"])
        assert r.status_code == 400 and "già usato" in r.json()["detail"], r.text

    def test_15_update_date_incoherent(self, ctx):
        # i3 (D15) between 1 (D20) and 4 (D10): move date to D8 -> after next
        r = ctx["s"].put(f"{API}/invoices/{ctx['st']['i3']}", json=doc(ctx["pid"], D(8)), headers=ctx["h"])
        assert r.status_code == 400 and "successivo" in r.json()["detail"], r.text

    def test_16_update_same_number_same_date_ok(self, ctx):
        r = ctx["s"].put(f"{API}/invoices/{ctx['st']['i3']}", json=doc(ctx["pid"], D(15), numero=3), headers=ctx["h"])
        assert r.status_code == 200, r.text

    def test_17_change_nc_number(self, ctx):
        s, h = ctx["s"], ctx["h"]
        r = s.put(f"{API}/invoices/{ctx['st']['nc5']}", json=doc(ctx["pid"], D(2), numero=3, tipo="TD04", price=10, link=ctx["st"]["i1"]), headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["numero_display"] == f"3/NC/{YEAR}"


class TestLock:
    def test_18_sent_invoice_not_editable(self, ctx):
        s, h = ctx["s"], ctx["h"]
        r = s.put(f"{API}/invoices/{ctx['st']['i1']}", json=doc(ctx["pid"], D(20)), headers=h)
        assert r.status_code == 400 and "non è più modificabile" in r.json()["detail"], r.text
        r = s.put(f"{API}/invoices/{ctx['st']['i1']}", json=doc(ctx["pid"], D(20), numero=2), headers=h)
        assert r.status_code == 400

    def test_19_sent_not_deletable(self, ctx):
        r = ctx["s"].delete(f"{API}/invoices/{ctx['st']['i1']}", headers=ctx["h"])
        assert r.status_code == 400 and "non può essere eliminato" in r.json()["detail"], r.text

    def test_20_consegnata_and_scartata_locked(self, ctx):
        s, h = ctx["s"], ctx["h"]
        iid = ctx["st"]["i6"]  # number 7, last -> send + refresh -> consegnata
        assert s.post(f"{API}/invoices/{iid}/send", headers=h).status_code == 200
        r = s.post(f"{API}/invoices/{iid}/refresh", headers=h)
        assert r.json()["status"] == "consegnata"
        assert s.put(f"{API}/invoices/{iid}", json=doc(ctx["pid"], D(5)), headers=h).status_code == 400
        assert s.delete(f"{API}/invoices/{iid}", headers=h).status_code == 400
        # force scartata on i5
        iid5 = ctx["st"]["i5"]
        mongo(f'db.invoices.updateOne({{id:"{iid5}"}}, {{$set:{{status:"scartata"}}}})')
        # iteration 7: scartata is now editable (correction), number change still forbidden
        r = s.put(f"{API}/invoices/{iid5}", json=doc(ctx["pid"], D(10)), headers=h)
        assert r.status_code == 200 and r.json()["status"] == "scartata", r.text
        r = s.put(f"{API}/invoices/{iid5}", json=doc(ctx["pid"], D(10), numero=8), headers=h)
        assert r.status_code == 400
        r = s.delete(f"{API}/invoices/{iid5}", headers=h)
        assert r.status_code == 400 and "non può essere eliminato" in r.json()["detail"]
        r = s.post(f"{API}/invoices/{iid5}/send", headers=h)
        assert r.status_code == 200 and r.json()["status"] == "inviata", r.text

    def test_21_draft_delete_still_works_for_last(self, ctx):
        s, h = ctx["s"], ctx["h"]
        r = s.post(f"{API}/invoices", json=doc(ctx["pid"], D(1)), headers=h)
        assert r.status_code == 200 and r.json()["numero"] == 7, r.text
        d = s.delete(f"{API}/invoices/{r.json()['id']}", headers=h)
        assert d.status_code == 200
        assert s.get(f"{API}/invoices/{r.json()['id']}", headers=h).status_code == 404

    def test_22_storno_totale_regression(self, ctx):
        s, h = ctx["s"], ctx["h"]
        r = s.post(f"{API}/invoices/{ctx['st']['i6']}/storno-totale", json={"invia": False}, headers=h)
        assert r.status_code == 200, r.text
        nc = r.json()
        assert nc["tipo_documento"] == "TD04" and nc["numero"] == 4 and nc["numero_display"] == f"4/NC/{YEAR}"
        assert nc["fattura_collegata_id"] == ctx["st"]["i6"] and nc["totale"] == 244.0

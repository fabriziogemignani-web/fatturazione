# Iteration 38: IVA indetraibile su fatture passive - detraibilita_iva fornitore, import passiva -> FA con IVA indetraibile a costo,
# PUT /passive/{id}/detraibilita (rigenera scrittura, blocco anno chiuso), registro IVA acquisti e liquidazione IVA con quota detraibile.
# Run with: pytest test_iteration38_iva_indetraibile.py -n 0
import os
import random
from datetime import date, timedelta

import pytest
import requests

from test_iteration7_pa_scartate_registro import API, mongo

RUN = str(random.randint(100000, 999999))
TOK, UID = f"test_session_t38_admin_{RUN}", f"test-user-t38-admin-{RUN}"
PIVA = "87" + RUN + "381"
FIX = open(os.path.join(os.path.dirname(__file__), "fixtures", "sample_fattura.xml")).read()
TODAY = date.today()
D1 = (TODAY - timedelta(days=5)).isoformat()
ST = {}


def sess():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{partita_iva:"{PIVA}"}}).forEach(c=>{{["invoices","passive_invoices","parties","articles","counters","payments","passive_payments","bank_tx","bank_accounts","corrispettivi","coa_accounts","coa_causali","coa_iva","coa_entries","audit"].forEach(k=>db[k].deleteMany({{company_id:c.id}})); db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def entry_for(ref):
    d = sess().get(f"{API}/contabilita/registrazioni", params={"origine": "acquisto"}).json()
    return next((e for e in d["registrazioni"] if e["ref_id"] == ref), None)


def side(e, conto):
    rows = [r for r in e["righe"] if r["conto"] == conto]
    return round(sum(r["dare"] for r in rows), 2), round(sum(r["avere"] for r in rows), 2)


def balanced(e):
    return round(sum(r["dare"] for r in e["righe"]), 2) == round(sum(r["avere"] for r in e["righe"]), 2)


def xml(num, idc="02345670481"):
    return FIX.replace("<IdCodice>01234567890</IdCodice>", f"<IdCodice>{PIVA}</IdCodice>").replace("<Numero>5674/2026</Numero>", f"<Numero>{num}</Numero>") \
        .replace("<Data>2026-10-30</Data>", f"<Data>{D1}</Data>").replace("<IdCodice>02345670481</IdCodice>", f"<IdCodice>{idc}</IdCodice>")


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t38.{RUN}@example.com", name:"TEST_T38 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": f"TEST_T38 Indet {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                              "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    yield
    clean()


SUP = {"tipo": "fornitore", "denominazione": "TEST_T38 Carburanti", "partita_iva": "02345670481", "codice_fiscale": "",
       "indirizzo": "Via Y 1", "cap": "50100", "comune": "Firenze", "provincia": "FI", "nazione": "IT"}


class TestParty:
    def test_01_validation(self):
        s = sess()
        assert s.post(f"{API}/parties", json={**SUP, "detraibilita_iva": 120}).status_code == 422
        assert s.post(f"{API}/parties", json={**SUP, "detraibilita_iva": -1}).status_code == 422

    def test_02_create_update(self):
        s = sess()
        r = s.post(f"{API}/parties", json={**SUP, "detraibilita_iva": 50})
        assert r.status_code == 200, r.text
        assert r.json()["detraibilita_iva"] == 50
        ST["forn"] = r.json()["id"]
        r = s.put(f"{API}/parties/{ST['forn']}", json={**SUP, "detraibilita_iva": 40})
        assert r.status_code == 200, r.text
        g = s.get(f"{API}/parties", params={"tipo": "fornitore"})
        assert g.status_code == 200
        items = g.json() if isinstance(g.json(), list) else g.json().get("items", [])
        assert next(p for p in items if p["id"] == ST["forn"])["detraibilita_iva"] == 40

    def test_03_default_100(self):
        r = sess().post(f"{API}/parties", json={**SUP, "denominazione": "TEST_T38 Full", "partita_iva": "01234567897"})
        assert r.status_code == 200, r.text
        assert r.json().get("detraibilita_iva") == 100


class TestImport:
    def test_01_import_40(self):
        up = sess().post(f"{API}/passive/upload", files=[("files", ("p.xml", xml("TEST38-1"), "text/xml"))])
        assert up.status_code == 200 and all(x["ok"] for x in up.json()), up.text
        ST["pas"] = up.json()[0]["docs"][0]["id"] if "docs" in up.json()[0] else mongo(f'print(db.passive_invoices.findOne({{company_id:"{ST["cid"]}",numero:"TEST38-1"}}).id)')
        d = sess().get(f"{API}/passive/{ST['pas']}").json()
        assert d["detraibilita_iva"] == 40

    def test_02_entry_40(self):
        e = entry_for(ST["pas"])
        assert e and e["causale"] == "FA" and balanced(e), e
        assert side(e, "05.02.002") == (41.47, 0.0)
        assert side(e, "13.02.001") == (0.0, 574.93)
        costo = [r for r in e["righe"] if r["conto"] not in ("05.02.002", "13.02.001")]
        assert round(sum(r["dare"] for r in costo), 2) == 533.46, e["righe"]
        assert e.get("iva_indetraibile") == 62.21, e

    def test_03_import_100_unaffected(self):
        up = sess().post(f"{API}/passive/upload", files=[("files", ("q.xml", xml("TEST38-2", "01234567897"), "text/xml"))])
        assert up.status_code == 200 and all(x["ok"] for x in up.json()), up.text
        ST["pas100"] = mongo(f'print(db.passive_invoices.findOne({{company_id:"{ST["cid"]}",numero:"TEST38-2"}}).id)')
        e = entry_for(ST["pas100"])
        assert e and balanced(e)
        assert side(e, "05.02.002") == (103.68, 0.0)
        assert e.get("iva_indetraibile") in (0, 0.0, None)


class TestSetDetraibilita:
    def test_01_validation(self):
        assert sess().put(f"{API}/passive/{ST['pas']}/detraibilita", json={"percentuale": 101}).status_code == 422
        assert sess().put(f"{API}/passive/nonexist/detraibilita", json={"percentuale": 50}).status_code == 404

    def test_02_update_to_0_then_40(self):
        s = sess()
        r = s.put(f"{API}/passive/{ST['pas']}/detraibilita", json={"percentuale": 0})
        assert r.status_code == 200, r.text
        assert s.get(f"{API}/passive/{ST['pas']}").json()["detraibilita_iva"] == 0
        e = entry_for(ST["pas"])
        assert balanced(e) and side(e, "05.02.002") == (0.0, 0.0) and e["iva_indetraibile"] == 103.68
        d = s.get(f"{API}/contabilita/registrazioni", params={"origine": "acquisto"}).json()["registrazioni"]
        assert len([x for x in d if x["ref_id"] == ST["pas"]]) == 1
        r = s.put(f"{API}/passive/{ST['pas']}/detraibilita", json={"percentuale": 40})
        assert r.status_code == 200
        assert side(entry_for(ST["pas"]), "05.02.002") == (41.47, 0.0)

    def test_03_closed_year_blocked(self):
        anno = int(entry_for(ST["pas"])["data"][:4])
        mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}},{{$set:{{coge_chiusi:[{anno}]}}}})')
        try:
            r = sess().put(f"{API}/passive/{ST['pas']}/detraibilita", json={"percentuale": 10})
            assert r.status_code == 400, r.text
            assert sess().get(f"{API}/passive/{ST['pas']}").json()["detraibilita_iva"] == 40
        finally:
            mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}},{{$set:{{coge_chiusi:[]}}}})')


class TestIva:
    def test_01_register(self):
        s = sess()
        for pid in (ST["pas"], ST["pas100"]):
            r = s.patch(f"{API}/passive/{pid}", json={"stato_reg": "registrata", "data_registrazione": TODAY.isoformat()})
            assert r.status_code == 200, r.text

    def test_02_registro_acquisti(self):
        d = sess().get(f"{API}/registro-iva-acquisti", params={"anno": TODAY.year}).json()
        rows = {r["id"]: r for r in d["rows"]}
        assert rows[ST["pas"]]["detraibilita_iva"] == 40, rows[ST["pas"]]
        assert rows[ST["pas"]]["iva_indetraibile"] == 62.21
        assert rows[ST["pas100"]]["iva_indetraibile"] == 0
        assert d["imposta_indetraibile"] == 62.21

    def test_03_liquidazione(self):
        d = sess().get(f"{API}/liquidazione-iva", params={"anno": TODAY.year, "periodicita": "mensile"}).json()
        p = d["periodi"][TODAY.month - 1]
        assert p["documenti_acquisti"] == 2
        assert p["iva_credito"] == round(41.47 + 103.68, 2), p["acquisti"]
        q = sess().get(f"{API}/liquidazione-iva", params={"anno": TODAY.year, "periodicita": "trimestrale"}).json()
        assert q["periodi"][(TODAY.month - 1) // 3]["iva_credito"] == 145.15

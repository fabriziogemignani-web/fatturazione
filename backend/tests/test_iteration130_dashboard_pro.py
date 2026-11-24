# Iteration 130: Dashboard pro - GET /api/dashboard/kpi (periodo mese|trimestre|anno|12mesi, NC subtracted, delta), GET/PUT /api/dashboard/layout
# (per user per company, invalid ids filtered, isolation between users), sottoscorta + scadenzario feeding the widgets.
# Run: cd /app/backend && pytest tests/test_iteration130_dashboard_pro.py -v -n 0   (T130_KEEP=1 keeps data and prints ids for UI tests)
import json
import os
import random
import sys
from datetime import date, timedelta

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402
from test_iteration101_ai_registrazione_consulente import COLLS  # noqa: E402

RUN = str(random.randint(100000, 999999))
TOK, UID = "test_session_t130_admin", "test-user-t130-admin"
TOK2, UID2 = "test_session_t130_admin2", "test-user-t130-admin2"
PIVA = "16" + RUN + "130"
ST = {"cids": []}
TODAY = date.today()
ALL_COLLS = COLLS + ["stock_moves", "articles", "orders"]


def sess(tok=TOK, cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    c = cid if cid is not None else ST.get("cid")
    if c:
        s.headers["X-Company-Id"] = c
    return s


def clean():
    ids = json.dumps(ST["cids"])
    mongo(f'{ids}.forEach(id=>{{{json.dumps(ALL_COLLS)}.forEach(k=>db[k].deleteMany({{company_id:id}}));'
          f'db.counters.deleteMany({{key:{{$regex:id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:id}}}}); db.companies.deleteOne({{id:id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:["{UID}","{UID2}"]}}}}); db.user_sessions.deleteMany({{user_id:{{$in:["{UID}","{UID2}"]}}}});')


def invoice(s, pid, d, prezzo, tipo="TD01", send=True, scad=None, coll=None):
    body = {"tipo_documento": tipo, "data": d, "party_id": pid, "modalita_pagamento": "MP05",
            "lines": [{"descrizione": "TEST_servizio", "quantita": 1, "prezzo_unitario": prezzo, "aliquota": 22}]}
    if scad:
        body["scadenza"] = scad
    if coll:
        body["fattura_collegata_id"] = coll
    r = s.post(f"{API}/invoices", json=body)
    assert r.status_code == 200, r.text
    iid = r.json()["id"]
    if send:
        r = s.post(f"{API}/invoices/{iid}/send")
        assert r.status_code == 200, r.text
    return iid


def do_setup():
    for uid, tok, n in ((UID, TOK, "admin"), (UID2, TOK2, "admin2")):
        mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.t130.{n}@example.com", name:"TEST_T130 {n}", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
              f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    r = sess(cid="").post(f"{API}/companies", json={"denominazione": f"TEST_T130 Dashboard {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                                  "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    ST["cids"].append(ST["cid"])
    s = sess()
    r = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": "TEST_T130 Cliente Spa", "partita_iva": "01234567897", "codice_fiscale": "01234567897", "indirizzo": "Via Po 2", "cap": "10100", "comune": "Torino", "provincia": "TO"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    first = TODAY.replace(day=1)
    prev = (first - timedelta(days=1)).replace(day=1)
    ST["inv_prev"] = invoice(s, pid, prev.isoformat(), 800)
    ST["inv_cur"] = invoice(s, pid, first.isoformat(), 1000, scad=(TODAY + timedelta(days=10)).isoformat())
    ST["inv_cur2"] = invoice(s, pid, TODAY.isoformat(), 500, scad=(TODAY - timedelta(days=5)).isoformat())
    ST["nc_cur"] = invoice(s, pid, TODAY.isoformat(), 200, tipo="TD04", coll=ST["inv_cur"])
    ST["bozza"] = invoice(s, pid, TODAY.isoformat(), 9999, send=False)
    ST["pid"] = pid
    arts = []
    for cod, smin in (("TEST_A1", 5), ("TEST_A2", 3), ("TEST_A3", 0)):
        r = s.post(f"{API}/articles", json={"codice": f"{cod}_{RUN}", "descrizione": f"{cod} articolo", "prezzo": 10, "aliquota": 22, "gestione_magazzino": True, "scorta_minima": smin})
        assert r.status_code == 200, r.text
        arts.append(r.json()["id"])
    mongo(f'db.articles.updateOne({{id:"{arts[1]}"}},{{$set:{{giacenza:2}}}}); db.articles.updateOne({{id:"{arts[2]}"}},{{$set:{{giacenza:50}}}});')
    ST["arts"] = arts


@pytest.fixture(scope="module", autouse=True)
def setup():
    try:
        do_setup()
    except Exception:
        clean()
        raise
    yield
    if os.environ.get("T130_KEEP"):
        print(json.dumps(ST))
    else:
        clean()


# --- KPI ---
class TestKpi:
    def test_mese(self):
        r = sess().get(f"{API}/dashboard/kpi", params={"periodo": "mese"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["periodo"] == "mese" and d["dal"] == TODAY.replace(day=1).isoformat() and d["al"] == TODAY.isoformat()
        assert d["fatturato"] == 1300.0  # 1000 + 500 - 200 (NC), bozza excluded
        assert d["fatturato_prec"] == 800.0
        assert d["delta"] == round((1300 - 800) / 800 * 100, 1)

    @pytest.mark.parametrize("p", ["trimestre", "anno", "12mesi"])
    def test_other_periods(self, p):
        r = sess().get(f"{API}/dashboard/kpi", params={"periodo": p})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["periodo"] == p and d["dal"] <= d["al"]
        assert d["fatturato"] >= 1300.0
        assert d["fatturato"] + d["fatturato_prec"] == pytest.approx(2100.0)

    def test_invalid_period(self):
        assert sess().get(f"{API}/dashboard/kpi", params={"periodo": "settimana"}).status_code == 422

    def test_requires_company(self):
        assert sess(cid="").get(f"{API}/dashboard/kpi").status_code == 400


# --- Layout ---
class TestLayout:
    def test_default_none(self):
        r = sess().get(f"{API}/dashboard/layout")
        assert r.status_code == 200, r.text
        assert r.json()["widgets"] is None

    def test_put_get_filtered(self):
        r = sess().put(f"{API}/dashboard/layout", json={"widgets": ["kpi", "sdi", "kpi", "BAD-ID", "x" * 40, "scadenze_fiscali"]})
        assert r.status_code == 200, r.text
        assert r.json()["widgets"] == ["kpi", "sdi", "scadenze_fiscali"]
        assert sess().get(f"{API}/dashboard/layout").json()["widgets"] == ["kpi", "sdi", "scadenze_fiscali"]

    def test_other_user_isolated(self):
        assert sess(TOK2).get(f"{API}/dashboard/layout").json()["widgets"] is None

    def test_stored_per_company(self):
        out = mongo(f'printjson(db.users.findOne({{user_id:"{UID}"}},{{_id:0,dashboard_layout:1}}))')
        assert ST["cid"] in out

    def test_too_many(self):
        assert sess().put(f"{API}/dashboard/layout", json={"widgets": [f"w{i}" for i in range(41)]}).status_code == 422

    def test_empty_list(self):
        r = sess().put(f"{API}/dashboard/layout", json={"widgets": []})
        assert r.status_code == 200 and r.json()["widgets"] == []


# --- Widget data sources ---
class TestWidgetData:
    def test_sottoscorta(self):
        r = sess().get(f"{API}/magazzino/sottoscorta")
        assert r.status_code == 200, r.text
        ids = {a["id"]: a["stato_scorta"] for a in r.json()}
        assert ids.get(ST["arts"][0]) == "esaurito" and ids.get(ST["arts"][1]) == "sottoscorta" and ST["arts"][2] not in ids

    def test_scadenzario(self):
        r = sess().get(f"{API}/scadenzario")
        assert r.status_code == 200, r.text
        inv = {x["invoice_id"] for x in r.json()["rate"] if x["residuo"] > 0.005}
        assert ST["inv_cur"] in inv or ST["inv_cur2"] in inv

    def test_dashboard_counts(self):
        r = sess().get(f"{API}/dashboard")
        assert r.status_code == 200, r.text
        assert r.json()["counts"]["bozza"] == 1

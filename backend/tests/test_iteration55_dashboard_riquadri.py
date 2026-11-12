# Iteration 55: Dashboard riquadri proattivi - GET /api/dashboard/riquadri counts (bozze, scartate, autofatture, passive da registrare,
# fornitori da verificare, scaduti clienti/fornitori, riba insoluti/in scadenza, ddt da fatturare, sottoscorta, movimenti mese) scoped per company,
# plus moduli / menu_off persistence used by frontend tile filtering.
# Run: pytest tests/test_iteration55_dashboard_riquadri.py -v -n 0   (setup|clean helper: python tests/test_iteration55_dashboard_riquadri.py setup|clean)
import json
import os
import subprocess
import sys
from datetime import date, timedelta

import pytest
import requests

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
UID, TOK = "test-user-t55", "test_session_t55"
PIVA_A, PIVA_B = "86000055501", "86000055502"
COLLS = ["invoices", "passive_invoices", "parties", "payments", "passive_payments", "coa_entries", "coa_accounts", "coa_causali", "coa_iva", "audit",
         "sdi_events", "riba_effetti", "ddts", "articles", "partite_aperte", "intenti"]
T = date.today()
TODAY, MESE = T.isoformat(), T.isoformat()[:7]
PAST = (T - timedelta(days=20)).isoformat()
SOON = (T + timedelta(days=5)).isoformat()
FAR = (T + timedelta(days=40)).isoformat()
ST = {}


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


def clean():
    mongo(f'db.companies.find({{partita_iva:{{$in:["{PIVA_A}","{PIVA_B}"]}}}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          'db.counters.deleteMany({key:{$regex:c.id}}); db.users.updateMany({}, {$pull:{company_ids:c.id}}); db.companies.deleteOne({id:c.id});});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def sess(cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    if cid:
        s.headers["X-Company-Id"] = cid
    return s


def mkco(name, piva):
    r = sess().post(f"{API}/companies", json={"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    r.raise_for_status()
    return r.json()["id"]


def seed(cid):
    inv = lambda i, n, st, extra="": (f'{{id:"t55-inv-{i}", company_id:"{cid}", numero:{n}, anno:{T.year}, sezionale:"", numero_display:"{n}/{T.year}", status:"{st}",'
                                      f'data:"{PAST}", tipo_documento:"TD01", totale:122, imponibile:100, iva:22, netto:122, party_id:"t55-cli",'
                                      f'cliente:{{denominazione:"TEST_T55 Cliente"}}, created_at:new Date().toISOString(), updated_at:new Date().toISOString() {extra}}}')
    rp = ', rate:[{scadenza:"' + PAST + '", importo:122}]'
    rf = ', rate:[{scadenza:"' + FAR + '", importo:122}]'
    js = (f'db.invoices.insertMany([{inv(1, 9001, "bozza")}, {inv(2, 9002, "bozza", ", autofattura:true")}, {inv(3, 9003, "scartata")},'
          f'{inv(4, 9004, "consegnata", rp)}, {inv(5, 9005, "consegnata", rf)}]);'
          f'db.passive_invoices.insertMany([{{id:"t55-pas-1", company_id:"{cid}", hash:"t55h1", stato_reg:"da_registrare", numero_display:"P1", data:"{PAST}", party_id:"t55-for",'
          f'fornitore:{{denominazione:"TEST_T55 Forn"}}, totale:50, netto:50, rate:[{{scadenza:"{PAST}", importo:50}}], tipo_documento:"TD01"}},'
          f'{{id:"t55-pas-2", company_id:"{cid}", hash:"t55h2", stato_reg:"registrata", numero_display:"P2", data:"{PAST}", party_id:"t55-for",'
          f'fornitore:{{denominazione:"TEST_T55 Forn"}}, totale:30, netto:30, rate:[{{scadenza:"{PAST}", importo:30}}], tipo_documento:"TD01"}},'
          f'{{id:"t55-pas-3", company_id:"{cid}", hash:"t55h3", stato_reg:"contestata", numero_display:"P3", data:"{PAST}", party_id:"t55-for",'
          f'fornitore:{{denominazione:"TEST_T55 Forn"}}, totale:999, netto:999, rate:[{{scadenza:"{PAST}", importo:999}}], tipo_documento:"TD01"}}]);'
          f'db.parties.insertMany([{{id:"t55-for", company_id:"{cid}", tipo:"fornitore", denominazione:"TEST_T55 Forn", da_verificare:true}},'
          f'{{id:"t55-cli", company_id:"{cid}", tipo:"cliente", denominazione:"TEST_T55 Cliente", da_verificare:true}}]);'
          f'db.riba_effetti.insertMany([{{id:"t55-rb1", company_id:"{cid}", stato:"insoluto", scadenza:"{PAST}", insoluto:{{data:"{TODAY}"}}}},'
          f'{{id:"t55-rb2", company_id:"{cid}", stato:"presentato", scadenza:"{SOON}"}}, {{id:"t55-rb3", company_id:"{cid}", stato:"presentato", scadenza:"{FAR}"}}]);'
          f'db.ddts.insertMany([{{id:"t55-d1", company_id:"{cid}", status:"confermato"}}, {{id:"t55-d2", company_id:"{cid}", status:"confermato"}}, {{id:"t55-d3", company_id:"{cid}", status:"fatturato"}}]);'
          f'db.articles.insertMany([{{id:"t55-a1", company_id:"{cid}", codice:"T55A1", gestione_magazzino:true, scorta_minima:5, giacenza:1}},'
          f'{{id:"t55-a2", company_id:"{cid}", codice:"T55A2", gestione_magazzino:true, scorta_minima:5, giacenza:10}},'
          f'{{id:"t55-a3", company_id:"{cid}", codice:"T55A3", gestione_magazzino:false, scorta_minima:5, giacenza:0}}]);'
          f'db.coa_entries.insertMany([{{id:"t55-e1", company_id:"{cid}", data:"{TODAY}"}}, {{id:"t55-e2", company_id:"{cid}", data:"{TODAY}", modificata:true}},'
          f'{{id:"t55-e3", company_id:"{cid}", data:"{T.year - 1}-01-15", modificata:true}}]);')
    mongo(js)


def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t55@example.com", name:"TEST_T55 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    a, b = mkco("TEST_T55 Riquadri Srl", PIVA_A), mkco("TEST_T55 Vuota Srl", PIVA_B)
    seed(a)
    return {"A": a, "B": b}


@pytest.fixture(scope="module", autouse=True)
def fx():
    try:
        ST.update(setup())
        yield
    finally:
        clean()


class TestRiquadri:
    def test_01_requires_auth(self):
        assert requests.get(f"{API}/dashboard/riquadri").status_code == 401

    def test_02_counts_company_a(self):
        r = sess(ST["A"]).get(f"{API}/dashboard/riquadri")
        assert r.status_code == 200, r.text
        d = r.json()
        print(d)
        exp = {"bozze": 2, "scartate": 1, "autofatture_bozza": 1, "passive_da_registrare": 1, "fornitori_da_verificare": 1,
               "clienti_scaduto_n": 1, "clienti_scaduto": 122.0, "fornitori_scaduto_n": 2, "fornitori_scaduto": 80.0,
               "riba_insoluti_mese": 1, "riba_in_scadenza": 1, "ddt_da_fatturare": 2, "sottoscorta": 1, "movimenti_mese": 2, "movimenti_modificati": 1}
        assert {k: d.get(k) for k in exp} == exp

    def test_03_scoped_company_b_zero(self):
        d = sess(ST["B"]).get(f"{API}/dashboard/riquadri").json()
        assert all(v == 0 for v in d.values()), d

    def test_04_dashboard_still_ok(self):
        r = sess(ST["A"]).get(f"{API}/dashboard")
        assert r.status_code == 200, r.text
        assert r.json()["counts"]["bozza"] == 2

    def test_05_moduli_and_menu_off_exposed(self):
        s = sess()
        r = s.put(f"{API}/companies/{ST['B']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                              "corrispettivi": True, "contabilita": False})
        assert r.status_code == 200, r.text
        r = s.put(f"{API}/companies/{ST['B']}/menu", json={"off": ["magazzino"]})
        assert r.status_code == 200, r.text
        c = next(x for x in s.get(f"{API}/companies").json() if x["id"] == ST["B"])
        assert c["moduli"]["contabilita"] is False and "magazzino" in c["menu_off"]
        # riquadri endpoint still works when contabilita is off
        assert sess(ST["B"]).get(f"{API}/dashboard/riquadri").status_code == 200


if __name__ == "__main__":
    print(json.dumps(setup()) if sys.argv[1] == "setup" else clean())

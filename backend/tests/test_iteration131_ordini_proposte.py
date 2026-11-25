# Iteration 131: Pianificazione ordini a fornitore - GET /api/ordini-proposte (auto-plan from sottoscorta, grouped by fornitore_abituale,
# qty to scorta_minima rounded up to scorta_riordino, idempotent, update, superata), POST conferma (real OF order, ordinato), POST scarta,
# regression GET /api/magazzino/proposta-ordine, tenant isolation, concurrency.
# Run: cd /app/backend && pytest tests/test_iteration131_ordini_proposte.py -v -n 0   (T131_KEEP=1 -s keeps data and prints ids for UI tests)
import json
import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402
from test_iteration101_ai_registrazione_consulente import COLLS  # noqa: E402

RUN = str(random.randint(100000, 999999))
TOK, UID = "test_session_t131_admin", "test-user-t131-admin"
ST = {"cids": []}
TODAY = date.today().isoformat()
ALL_COLLS = COLLS + ["stock_moves", "articles", "orders", "ordini_proposte"]


def sess(cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    c = cid if cid is not None else ST.get("cid")
    if c:
        s.headers["X-Company-Id"] = c
    return s


def clean():
    ids = json.dumps(ST["cids"])
    mongo(f'{ids}.forEach(id=>{{{json.dumps(ALL_COLLS)}.forEach(k=>db[k].deleteMany({{company_id:id}}));'
          f'db.counters.deleteMany({{key:{{$regex:id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:id}}}}); db.companies.deleteOne({{id:id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def company(name, piva):
    r = sess(cid="").post(f"{API}/companies", json={"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01",
                                                   "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cids"].append(r.json()["id"])
    return r.json()["id"]


def setg(aid, **kw):
    mongo(f'db.articles.updateOne({{id:"{aid}"}},{{$set:{json.dumps(kw)}}})')


def do_setup():
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t131.admin@example.com", name:"TEST_T131 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    ST["cid"] = company(f"TEST_T131 Pianifica {RUN} Srl", "17" + RUN + "131")
    ST["cidb"] = company(f"TEST_T131 Altra {RUN} Srl", "18" + RUN + "131")
    s = sess()
    sup = []
    for i, (n, piva) in enumerate((("TEST_T131 Fornitore Uno Srl", "01234567897"), ("TEST_T131 Fornitore Due Spa", "12345678903"))):
        r = s.post(f"{API}/parties", json={"tipo": "fornitore", "denominazione": n, "partita_iva": piva, "codice_fiscale": piva, "indirizzo": "Via Po 2", "cap": "10100", "comune": "Torino", "provincia": "TO"})
        assert r.status_code == 200, r.text
        sup.append(r.json()["id"])
    ST["sup"] = sup
    arts = {}
    spec = {  # key: (smin, lotto, forn, gestione, giacenza)
        "A1": (10, 5, "TEST_T131 Fornitore Uno Srl", True, 3),
        "A2": (10, 0, "TEST_T131 Fornitore Uno Srl", True, 3),
        "A3": (4, 0, "  test_t131 fornitore   DUE spa ", True, 0),
        "A4": (5, 0, "TEST_T131 Sconosciuto Srl", True, 1),
        "A5": (5, 0, "TEST_T131 Fornitore Uno Srl", True, 10),
        "A6": (5, 0, "TEST_T131 Fornitore Uno Srl", False, 0),
    }
    for k, (smin, lotto, forn, gest, g) in spec.items():
        r = s.post(f"{API}/articles", json={"codice": f"TEST_{k}_{RUN}", "descrizione": f"TEST_{k} articolo", "prezzo": 10, "aliquota": 22, "gestione_magazzino": gest,
                                            "scorta_minima": smin, "scorta_riordino": lotto, "fornitore_abituale": forn})
        assert r.status_code == 200, r.text
        arts[k] = r.json()["id"]
        setg(arts[k], giacenza=g, costo_medio=2.5)
    ST["arts"] = arts


@pytest.fixture(scope="module", autouse=True)
def setup():
    try:
        do_setup()
    except Exception:
        clean()
        raise
    yield
    if os.environ.get("T131_KEEP"):
        print(json.dumps(ST))
    else:
        clean()


def proposte():
    r = sess().get(f"{API}/ordini-proposte")
    assert r.status_code == 200, r.text
    return r.json()


def by_party(lst):
    return {p["chiave"]: p for p in lst}


def body_from(p, party_id=None):
    return {"data": TODAY, "party_id": party_id if party_id is not None else p["party_id"], "lines": [
        {"article_id": l["article_id"], "descrizione": l["descrizione"], "quantita": l["quantita"], "prezzo_unitario": l["prezzo_unitario"], "aliquota": l["aliquota"]} for l in p["lines"]]}


class TestPianifica:
    def test_generate(self):
        lst = proposte()
        g = by_party(lst)
        a, s1, s2 = ST["arts"], ST["sup"][0], ST["sup"][1]
        assert set(g) == {s1, s2, "nome:test_t131 sconosciuto srl"}, g.keys()
        assert all(p["status"] == "da_confermare" and "_id" not in p and "firma" not in p for p in lst)
        q1 = {l["article_id"]: l["quantita"] for l in g[s1]["lines"]}
        assert q1 == {a["A1"]: 10, a["A2"]: 7}  # 7 rounded up to lotto 5 -> 10 ; lotto 0 -> 7
        assert g[s1]["fornitore"] == "TEST_T131 Fornitore Uno Srl" and g[s1]["party_id"] == s1
        assert [l["quantita"] for l in g[s2]["lines"]] == [4]  # name matched case/space-insensitively
        unk = g["nome:test_t131 sconosciuto srl"]
        assert unk["party_id"] == "" and unk["fornitore"] == "TEST_T131 Sconosciuto Srl"
        assert g[s1]["lines"][0]["prezzo_unitario"] == 2.5  # costo_medio fallback
        ST["p1"], ST["p2"], ST["pu"] = g[s1]["id"], g[s2]["id"], unk["id"]

    def test_idempotent(self):
        lst = proposte()
        assert len(lst) == 3 and {p["id"] for p in lst} == {ST["p1"], ST["p2"], ST["pu"]}
        n = mongo(f'print(db.ordini_proposte.countDocuments({{company_id:"{ST["cid"]}"}}))').strip().splitlines()[-1]
        assert n == "3"

    def test_update_lines(self):
        setg(ST["arts"]["A2"], giacenza=5)
        g = by_party(proposte())
        p = g[ST["sup"][0]]
        assert p["id"] == ST["p1"]
        assert {l["article_id"]: l["quantita"] for l in p["lines"]}[ST["arts"]["A2"]] == 5

    def test_superata(self):
        setg(ST["arts"]["A3"], giacenza=10)
        g = by_party(proposte())
        assert ST["sup"][1] not in g
        out = mongo(f'print(db.ordini_proposte.findOne({{id:"{ST["p2"]}"}}).status)')
        assert "superata" in out
        setg(ST["arts"]["A3"], giacenza=0)
        g = by_party(proposte())
        assert g[ST["sup"][1]]["id"] != ST["p2"]  # new proposal
        ST["p2b"] = g[ST["sup"][1]]["id"]

    def test_regression_proposta_ordine(self):
        r = sess().get(f"{API}/magazzino/proposta-ordine")
        assert r.status_code == 200, r.text
        gr = r.json()["gruppi"]
        assert len(gr) == 3 and gr[0]["party_id"] and not gr[-1]["party_id"]  # suppliers with party first

    def test_requires_company(self):
        assert sess(cid="").get(f"{API}/ordini-proposte").status_code == 400


class TestConferma:
    def test_cross_tenant(self):
        sb = sess(cid=ST["cidb"])
        assert sb.get(f"{API}/ordini-proposte").json() == []
        assert sb.post(f"{API}/ordini-proposte/{ST['p1']}/scarta").status_code == 404
        p = by_party(proposte())[ST["sup"][0]]
        assert sb.post(f"{API}/ordini-proposte/{ST['p1']}/conferma", json=body_from(p)).status_code == 404

    def test_conferma_bad_party_reverts(self):
        p = by_party(proposte())[ST["sup"][1]]
        r = sess().post(f"{API}/ordini-proposte/{p['id']}/conferma", json=body_from(p, party_id="nonexistent"))
        assert r.status_code == 400, r.text
        assert "da_confermare" in mongo(f'print(db.ordini_proposte.findOne({{id:"{p["id"]}"}}).status)')

    def test_conferma_validation(self):
        p = by_party(proposte())[ST["sup"][1]]
        r = sess().post(f"{API}/ordini-proposte/{p['id']}/conferma", json={"data": TODAY, "party_id": p["party_id"], "lines": []})
        assert r.status_code == 422
        assert "da_confermare" in mongo(f'print(db.ordini_proposte.findOne({{id:"{p["id"]}"}}).status)')

    def test_conferma(self):
        p = by_party(proposte())[ST["sup"][0]]
        r = sess().post(f"{API}/ordini-proposte/{p['id']}/conferma", json=body_from(p))
        assert r.status_code == 200, r.text
        o = r.json()
        assert o["tipo"] == "fornitore" and o["status"] == "aperto" and o["numero_display"] == f"OF 1/{TODAY[:4]}" and o["party_id"] == ST["sup"][0]
        ST["order1"] = o["id"]
        a1 = sess().get(f"{API}/articles/{ST['arts']['A1']}")
        if a1.status_code == 200:
            assert a1.json()["ordinato"] == 10
        else:
            assert 'ordinato: 10' in mongo(f'printjson(db.articles.findOne({{id:"{ST["arts"]["A1"]}"}},{{ordinato:1}}))')
        doc = mongo(f'printjson(db.ordini_proposte.findOne({{id:"{p["id"]}"}},{{_id:0,status:1,order_id:1,numero_ordine:1}}))')
        assert "confermata" in doc and o["id"] in doc
        g = by_party(proposte())
        assert ST["sup"][0] not in g  # ordinato covers A1/A2
        r = sess().get(f"{API}/ordini/fornitore/{o['id']}")
        assert r.status_code == 200 and len(r.json()["lines"]) == 2

    def test_double_conferma(self):
        p = {"party_id": ST["sup"][0], "lines": [{"article_id": ST["arts"]["A1"], "descrizione": "x", "quantita": 1, "prezzo_unitario": 1, "aliquota": 22}]}
        r = sess().post(f"{API}/ordini-proposte/{ST['p1']}/conferma", json=body_from(p))
        assert r.status_code in (404, 409)
        n = sess().get(f"{API}/ordini/fornitore").json()
        assert len(n) == 1

    def test_partial_conferma_reproposes_rest(self):
        # confirm sup2 with lower qty (2 of 4): remaining need should be re-proposed
        p = by_party(proposte())[ST["sup"][1]]
        b = body_from(p)
        b["lines"][0]["quantita"] = 2
        r = sess().post(f"{API}/ordini-proposte/{p['id']}/conferma", json=b)
        assert r.status_code == 200, r.text
        g = by_party(proposte())
        assert [l["quantita"] for l in g[ST["sup"][1]]["lines"]] == [2]
        ST["p2c"] = g[ST["sup"][1]]["id"]


class TestScarta:
    def test_scarta(self):
        r = sess().post(f"{API}/ordini-proposte/{ST['pu']}/scarta")
        assert r.status_code == 200 and r.json()["ok"]
        doc = mongo(f'printjson(db.ordini_proposte.findOne({{id:"{ST["pu"]}"}},{{_id:0,status:1,scartata_il:1}}))')
        assert "scartata" in doc and TODAY in doc
        g = by_party(proposte())
        assert "nome:test_t131 sconosciuto srl" not in g

    def test_scarta_again(self):
        assert sess().post(f"{API}/ordini-proposte/{ST['pu']}/scarta").status_code == 404
        assert sess().post(f"{API}/ordini-proposte/nonexistent/scarta").status_code == 404

    def test_scartata_yesterday_reproposed(self):
        mongo(f'db.ordini_proposte.updateOne({{id:"{ST["pu"]}"}},{{$set:{{scartata_il:"2000-01-01"}}}})')
        g = by_party(proposte())
        assert "nome:test_t131 sconosciuto srl" in g and g["nome:test_t131 sconosciuto srl"]["id"] != ST["pu"]


class TestConcurrency:
    def test_parallel_get_no_duplicates(self):
        setg(ST["arts"]["A5"], giacenza=0, fornitore_abituale="TEST_T131 Nuovo Conc Srl")
        with ThreadPoolExecutor(6) as ex:
            res = list(ex.map(lambda _: sess().get(f"{API}/ordini-proposte").status_code, range(6)))
        assert all(c == 200 for c in res)
        n = mongo(f'print(db.ordini_proposte.countDocuments({{company_id:"{ST["cid"]}", chiave:"nome:test_t131 nuovo conc srl", status:"da_confermare"}}))').strip().splitlines()[-1]
        assert n == "1", f"duplicate proposals created by concurrent GETs: {n}"

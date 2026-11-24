# Iteration 128: (1) AI learning of cost accounts from user corrections (db.ai_regole_conti, POST /api/ai/passive/{pid}/conti appreso, no AI call when all lines learned,
# cache hash changes when rules change), righe_costo aliquota/natura; (2) Cespiti API: categorie, config primo_anno, CRUD, piano meta/giorni/piena/fondo_iniziale,
# ammortamenti preview/register/duplicate/annulla, proposte from registered passive invoices, ignora, dismetti/riattiva, operatore 403.
# Real LLM calls. Run: cd /app/backend && pytest tests/test_iteration128_ai_learning_cespiti.py -v -n 0   (T128_KEEP=1 keeps data, prints ids)
import json
import os
import random
import sys
import uuid
from datetime import date

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402
from test_iteration101_ai_registrazione_consulente import COLLS  # noqa: E402
import test_iteration101_ai_registrazione_consulente as t101  # noqa: E402

RUN = str(random.randint(100000, 999999))
TOK, UID = "test_session_t128_admin", "test-user-t128-admin"
TOK_OP, UID_OP = "test_session_t128_oper", "test-user-t128-oper"
PIVA = "14" + RUN + "128"
ST = {"cids": []}
Y = date.today().year
SUP = "TEST_T128 Fornitore Learning Srl"
CED = "03344556611"
ALL_COLLS = COLLS + ["ai_regole_conti", "cespiti", "ai_consumi", "coa_esercizi", "iva_registri"]


def sess(tok=TOK, cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    c = cid or ST.get("cid")
    if c:
        s.headers["X-Company-Id"] = c
    return s


def clean():
    ids = json.dumps(ST["cids"])
    mongo(f'{ids}.forEach(id=>{{{json.dumps(ALL_COLLS)}.forEach(k=>db[k].deleteMany({{company_id:id}}));'
          f'db.counters.deleteMany({{key:{{$regex:id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:id}}}}); db.companies.deleteOne({{id:id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:["{UID}","{UID_OP}"]}}}}); db.user_sessions.deleteMany({{user_id:{{$in:["{UID}","{UID_OP}"]}}}});')


def xml(numero, righe, ced=CED, den=SUP):
    t101.PIVA = PIVA
    return t101.xml(numero, f"{Y}-01-15", ced, den, righe)


def upload(x):
    r = sess().post(f"{API}/passive/upload", files=[("files", (f"t128_{uuid.uuid4().hex[:6]}.xml", x, "application/octet-stream"))])
    assert r.status_code == 200, r.text
    j = r.json()[0]
    assert j["ok"], j
    return j["documenti"][0]["id"]


def crediti():
    return float(json.loads(mongo(f'print(JSON.stringify(db.companies.findOne({{id:"{ST["cid"]}"}},{{_id:0,ai_crediti:1}})))')).get("ai_crediti", 0))


def q(js):
    return json.loads(mongo(f"print(JSON.stringify({js}))") or "null")


def conti(pid):
    r = sess().post(f"{API}/ai/passive/{pid}/conti", timeout=180)
    assert r.status_code == 200, r.text
    return r.json()


def registra(pid, numero, riepilogo):
    body = {"data_registrazione": date.today().isoformat(), "numero": numero, "data": f"{Y}-01-15", "riepilogo": riepilogo, "detraibilita_iva": 100}
    r = sess().post(f"{API}/passive/{pid}/registrazione", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def regole():
    return q(f'db.ai_regole_conti.find({{company_id:"{ST["cid"]}"}},{{_id:0}}).toArray()')


def do_setup():
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t128.admin@example.com", name:"TEST_T128 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    r = sess(cid="").post(f"{API}/companies", json={"denominazione": f"TEST_T128 Cespiti {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                                  "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    ST["cids"].append(ST["cid"])
    mongo(f'db.users.insertOne({{user_id:"{UID_OP}", email:"test.user.t128.oper@example.com", name:"TEST_T128 oper", picture:"", role:"operatore", status:"approved", company_ids:["{ST["cid"]}"], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID_OP}", session_token:"{TOK_OP}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    s = sess()
    assert s.put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                              "corrispettivi": True, "contabilita": True}).status_code == 200
    assert s.get(f"{API}/contabilita/conti").status_code == 200
    pr = s.get(f"{API}/contabilita/parametri").json()
    p = pr["parametri"]
    body = {"conti": {k: p[k] for k, _ in pr["ruoli"]}, "contropartita_vendite": p["contropartita_vendite"],
            "contropartita_acquisti": p["contropartita_acquisti"], "aliquota_rc": 22, "categorie": p["categorie"]}
    assert s.put(f"{API}/contabilita/parametri", json=body).status_code == 200


@pytest.fixture(scope="module", autouse=True)
def setup():
    do_setup()
    yield
    if os.environ.get("T128_KEEP"):
        print("\nKEEP", json.dumps(ST))
    else:
        clean()


class TestLearning:
    # invoice A1 single line: IA proposes X, user saves Y (same 30.07 family different code) -> rule corretto=true
    def test_01_correction_learned(self):
        ST["A1"] = upload(xml("L-1", [("Consulenza tecnica mensile", 440.0)]))
        j = conti(ST["A1"])
        ia = j["righe"][0]["conto"]
        assert ia
        y = "30.07.011" if ia != "30.07.011" else "30.07.012"
        ST["Yconto"], ST["IAconto"] = y, ia
        riep = [{**x, "conto": y} for x in j["riepilogo"]]
        reg = registra(ST["A1"], "L-1", riep)
        rc = reg.get("righe_costo") or []
        print("RIGHE_COSTO", rc)
        assert rc and all("aliquota" in x and "natura" in x for x in rc), rc
        assert rc[0]["aliquota"] == 22
        rr = [x for x in regole() if x["chiave"] == "consulenza tecnica mensile"]
        print("RULE", rr)
        assert len(rr) == 1
        assert rr[0]["conto"] == y and rr[0]["conto_ia"] == ia and rr[0]["corretto"] is True and rr[0]["party_id"]

    # invoice N: notebook registered on 02.04.002 (kept/confirmed) -> rule corretto depends on IA
    def test_02_notebook(self):
        ST["N"] = upload(xml("L-2", [("Notebook Dell", 900.0)]))
        j = conti(ST["N"])
        ST["N_ia"] = j["righe"][0]["conto"]
        reg = registra(ST["N"], "L-2", [{**x, "conto": "02.04.002"} for x in j["riepilogo"]])
        assert reg["righe_costo"][0]["conto"] == "02.04.002"
        rr = [x for x in regole() if x["chiave"] == "notebook dell"]
        assert rr and rr[0]["conto"] == "02.04.002" and rr[0]["corretto"] == (ST["N_ia"] != "02.04.002")

    # new invoice with same description -> appreso, no AI call (credits unchanged)
    def test_03_all_learned_no_ai(self):
        ST["B"] = upload(xml("L-3", [("Consulenza tecnica mensile", 520.0)]))
        c0 = crediti()
        n0 = q(f'db.ai_consumi.countDocuments({{company_id:"{ST["cid"]}"}})')
        j = conti(ST["B"])
        x = j["righe"][0]
        print("LEARNED", x)
        assert x["conto"] == ST["Yconto"] and x["appreso"] is True
        assert x["motivo"] == "Appreso dalle tue registrazioni precedenti (correzione)"
        assert crediti() == c0
        assert q(f'db.ai_consumi.countDocuments({{company_id:"{ST["cid"]}"}})') == n0
        ST["B_at"] = j["at"]

    # case/punctuation-insensitive key
    def test_04_key_normalized(self):
        pid = upload(xml("L-4", [("CONSULENZA tecnica - mensile!", 100.0)]))
        c0 = crediti()
        j = conti(pid)
        assert j["righe"][0]["appreso"] is True and j["righe"][0]["conto"] == ST["Yconto"]
        assert crediti() == c0

    # partial: AI called (credits drop), learned line overridden
    def test_05_partial(self):
        pid = upload(xml("L-5", [("Consulenza tecnica mensile", 300.0), ("Trasporto merci corriere", 50.0)]))
        c0 = crediti()
        j = conti(pid)
        by = {x["descrizione"]: x for x in j["righe"]}
        print("PARTIAL", by)
        assert by["Consulenza tecnica mensile"]["conto"] == ST["Yconto"] and by["Consulenza tecnica mensile"]["appreso"]
        assert by["Trasporto merci corriere"]["conto"] and not by["Trasporto merci corriere"]["appreso"]
        assert crediti() < c0

    # rule changes -> hash changes -> B recomputed with new conto
    def test_06_hash_changes(self):
        assert conti(ST["B"])["at"] == ST["B_at"]  # cached
        pid = upload(xml("L-6", [("Consulenza tecnica mensile", 200.0)]))
        j = conti(pid)
        registra(pid, "L-6", [{**x, "conto": "30.07.013"} for x in j["riepilogo"]])
        rr = [x for x in regole() if x["chiave"] == "consulenza tecnica mensile"][0]
        assert rr["conto"] == "30.07.013" and rr["n"] >= 2
        j2 = conti(ST["B"])
        assert j2["at"] != ST["B_at"]
        assert j2["righe"][0]["conto"] == "30.07.013"

    # other supplier does not use these rules
    def test_07_rules_per_supplier(self):
        pid = upload(xml("O-1", [("Consulenza tecnica mensile", 440.0)], ced="03344556622", den="TEST_T128 Altro Fornitore Srl"))
        j = conti(pid)
        assert j["righe"][0]["appreso"] is False


class TestCespiti:
    def test_10_categorie(self):
        r = sess().get(f"{API}/cespiti/categorie")
        assert r.status_code == 200
        c = {x["id"]: x for x in r.json()}
        assert len(c) == 17
        assert c["macchine_ufficio"]["aliquota"] == 20 and c["autovetture"]["aliquota"] == 25 and c["software"]["aliquota"] == 33.33

    def test_11_config(self):
        s = sess()
        assert s.get(f"{API}/cespiti/config").json()["primo_anno"] == "meta"
        assert s.put(f"{API}/cespiti/config", json={"primo_anno": "xxx"}).status_code == 422
        assert s.put(f"{API}/cespiti/config", json={"primo_anno": "giorni"}).json()["primo_anno"] == "giorni"
        assert s.get(f"{API}/cespiti/config").json()["primo_anno"] == "giorni"
        assert s.put(f"{API}/cespiti/config", json={"primo_anno": "meta"}).status_code == 200

    def test_12_create_and_piano(self):
        s = sess()
        r = s.post(f"{API}/cespiti", json={"descrizione": "TEST_PC ufficio", "categoria": "macchine_ufficio", "data_acquisto": "2025-07-01", "costo": 1000, "aliquota": 20})
        assert r.status_code == 200, r.text
        c = r.json()
        ST["C1"] = c["id"]
        assert c["conto_cespite"] == "02.04.002" and c["conto_fondo"] == "02.09.005" and c["conto_ammortamento"] == "30.10.002"
        assert [x["quota"] for x in c["piano"]] == [100, 200, 200, 200, 200, 100], c["piano"]
        assert c["piano"][0]["anno"] == 2025
        s.put(f"{API}/cespiti/config", json={"primo_anno": "giorni"})
        p = [x for x in s.get(f"{API}/cespiti").json() if x["id"] == ST["C1"]][0]["piano"]
        print("GIORNI", p)
        assert p[0]["quota"] == 100.82 and all(x["quota"] == 200 for x in p[1:5])
        s.put(f"{API}/cespiti/config", json={"primo_anno": "piena"})
        p = [x for x in s.get(f"{API}/cespiti").json() if x["id"] == ST["C1"]][0]["piano"]
        assert [x["quota"] for x in p] == [200] * 5
        s.put(f"{API}/cespiti/config", json={"primo_anno": "meta"})

    def test_13_fondo_iniziale(self):
        r = sess().post(f"{API}/cespiti", json={"descrizione": "TEST_PC usato", "categoria": "macchine_ufficio", "data_acquisto": "2020-03-01", "costo": 1000, "aliquota": 20, "fondo_iniziale": 600})
        assert r.status_code == 200, r.text
        c = r.json()
        ST["C2"] = c["id"]
        assert [(x["anno"], x["quota"]) for x in c["piano"]] == [(Y, 200), (Y + 1, 200)], c["piano"]
        bad = sess().post(f"{API}/cespiti", json={"descrizione": "TEST_bad", "categoria": "macchine_ufficio", "data_acquisto": "2020-03-01", "costo": 100, "aliquota": 20, "fondo_iniziale": 600})
        assert bad.status_code == 400
        bad = sess().post(f"{API}/cespiti", json={"descrizione": "TEST_bad", "categoria": "nope", "data_acquisto": "2020-03-01", "costo": 100, "aliquota": 20})
        assert bad.status_code == 400
        bad = sess().post(f"{API}/cespiti", json={"descrizione": "TEST_bad", "categoria": "mobili", "data_acquisto": "2020-03-01", "costo": 100, "aliquota": 12, "conto_fondo": "99.99.999"})
        assert bad.status_code == 400

    def test_14_update_delete(self):
        s = sess()
        r = s.post(f"{API}/cespiti", json={"descrizione": "TEST_Sedia", "categoria": "mobili", "data_acquisto": f"{Y}-02-01", "costo": 300, "aliquota": 12})
        assert r.status_code == 200
        xid = r.json()["id"]
        u = s.put(f"{API}/cespiti/{xid}", json={"descrizione": "TEST_Sedia2", "categoria": "mobili", "data_acquisto": f"{Y}-02-01", "costo": 400, "aliquota": 15})
        assert u.status_code == 200 and u.json()["costo"] == 400 and u.json()["aliquota"] == 15
        assert s.delete(f"{API}/cespiti/{xid}").status_code == 200
        assert xid not in [x["id"] for x in s.get(f"{API}/cespiti").json()]
        assert q(f'db.cespiti.findOne({{id:"{xid}"}},{{_id:0,annullato:1}})')["annullato"] is True

    def test_15_operatore(self):
        r = sess(tok=TOK_OP).post(f"{API}/cespiti", json={"descrizione": "TEST_x", "categoria": "mobili", "data_acquisto": f"{Y}-02-01", "costo": 300, "aliquota": 12})
        assert r.status_code == 403

    def test_16_proposte(self):
        s = sess()
        r = s.get(f"{API}/cespiti/proposte", params={"passive_id": ST["N"]})
        assert r.status_code == 200
        p = r.json()
        print("PROPOSTE", p)
        assert len(p) == 1 and p[0]["conto"] == "02.04.002" and p[0]["categoria"] == "macchine_ufficio" and p[0]["aliquota"] == 20 and p[0]["costo"] == 900
        all_ = s.get(f"{API}/cespiti/proposte").json()
        assert all(x["conto"][:3] in ("01.", "02.") for x in all_)
        assert ST["A1"] not in [x["passive_id"] for x in all_]
        body = {"descrizione": p[0]["descrizione"], "categoria": p[0]["categoria"], "data_acquisto": p[0]["data_acquisto"], "costo": p[0]["costo"], "aliquota": p[0]["aliquota"],
                "fornitore": p[0]["fornitore"], "passive_id": ST["N"], "riga_n": p[0]["riga_n"]}
        c = s.post(f"{API}/cespiti", json=body)
        assert c.status_code == 200, c.text
        ST["C3"] = c.json()["id"]
        assert s.get(f"{API}/cespiti/proposte", params={"passive_id": ST["N"]}).json() == []
        assert s.post(f"{API}/cespiti", json=body).status_code == 400

    def test_17_ignora(self):
        s = sess()
        pid = upload(xml("L-7", [("Monitor Samsung 27 pollici", 300.0)]))
        j = conti(pid)
        registra(pid, "L-7", [{**x, "conto": "02.04.002"} for x in j["riepilogo"]])
        assert len(s.get(f"{API}/cespiti/proposte", params={"passive_id": pid}).json()) == 1
        assert s.post(f"{API}/cespiti/proposte/{pid}/ignora").status_code == 200
        assert s.get(f"{API}/cespiti/proposte", params={"passive_id": pid}).json() == []

    def test_18_dismetti(self):
        s = sess()
        assert s.post(f"{API}/cespiti/{ST['C2']}/dismetti", json={"data": "2019-01-01"}).status_code == 400
        r = s.post(f"{API}/cespiti/{ST['C2']}/dismetti", json={"data": f"{Y}-06-30"})
        assert r.status_code == 200 and r.json()["data_dismissione"] == f"{Y}-06-30"
        assert all(x["anno"] <= Y for x in r.json()["piano"])
        r = s.delete(f"{API}/cespiti/{ST['C2']}/dismetti")
        assert r.status_code == 200 and "data_dismissione" not in r.json()

    def test_19_ammortamenti(self):
        s = sess()
        a = s.get(f"{API}/cespiti/ammortamenti/2025").json()
        print("PREVIEW 2025", a)
        assert a["registrato"] is False
        assert [v["id"] for v in a["voci"]] == [ST["C1"]] and a["totale"] == 100
        assert a["righe"][0] == {"conto": "30.10.002", "dare": 100} and {"conto": "02.09.005", "avere": 100} in a["righe"]
        r = s.post(f"{API}/cespiti/ammortamenti/2025")
        print("REG 2025", r.status_code, r.text[:500])
        assert r.status_code == 200, r.text
        assert r.json()["registrato"] is True and r.json()["coge_rif"]
        e = q(f'db.coa_entries.findOne({{company_id:"{ST["cid"]}", origine:"ammortamento", ref_id:"amm-2025"}},{{_id:0}})')
        assert e and e["data"] == "2025-12-31", e
        assert s.post(f"{API}/cespiti/ammortamenti/2025").status_code == 400
        # blocked edits
        assert s.put(f"{API}/cespiti/config", json={"primo_anno": "giorni"}).status_code == 400
        assert s.put(f"{API}/cespiti/config", json={"primo_anno": "meta"}).status_code == 200
        assert s.put(f"{API}/cespiti/{ST['C1']}", json={"descrizione": "x", "categoria": "macchine_ufficio", "data_acquisto": "2025-07-01", "costo": 1000, "aliquota": 20}).status_code == 400
        assert s.delete(f"{API}/cespiti/{ST['C1']}").status_code == 400
        # year Y
        aY = s.get(f"{API}/cespiti/ammortamenti/{Y}").json()
        print("PREVIEW Y", aY["totale"], [(v["descrizione"], v["quota"]) for v in aY["voci"]])
        assert aY["totale"] == round(200 + 200 + 90 * 1.0 * 0 + sum(v["quota"] for v in aY["voci"] if v["id"] == ST["C3"]), 2)
        r = s.post(f"{API}/cespiti/ammortamenti/{Y}")
        assert r.status_code == 200, r.text
        assert s.delete(f"{API}/cespiti/ammortamenti/2025").status_code == 400
        assert s.delete(f"{API}/cespiti/ammortamenti/{Y}").status_code == 200
        r = s.delete(f"{API}/cespiti/ammortamenti/2025")
        assert r.status_code == 200 and r.json()["registrato"] is False
        assert not q(f'db.coa_entries.findOne({{company_id:"{ST["cid"]}", origine:"ammortamento", ref_id:"amm-2025", annullata:{{$ne:true}}}},{{_id:0,id:1}})')
        assert q(f'db.cespiti.countDocuments({{company_id:"{ST["cid"]}", "ammortamenti.0":{{$exists:true}}}})') == 0

# Iteration 127: AI classification of passive invoice lines into cost/asset accounts by CEE voice (POST /api/ai/passive/{pid}/conti),
# riepilogo split per conto (ripartisci), caching (no extra credits), errors (no lines/no COA/other company/operatore), registration with proposed conti,
# regression of batch POST /api/ai/passive/analizza. Real LLM calls. Run: pytest tests/test_iteration127_ai_conti_righe.py -v -n 0
# Set T127_KEEP=1 to keep data (prints company id + token + ui invoice id) for UI testing.
import json
import os
import random
import re
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
TOK, UID = "test_session_t127_admin", "test-user-t127-admin"
TOK_OP, UID_OP = "test_session_t127_oper", "test-user-t127-oper"
PIVA = "12" + RUN + "127"
ST = {"cids": []}
Y = date.today().year
RX = re.compile(r"^(01\.0[1-8]|02\.0[1-8]|07|30\.0[6-9]|30\.14|31|40\.02)\.")
RIGHE = [("Carta A4 risme", 84.0), ("Consulenza tecnica", 440.0), ("Canone noleggio stampante", 60.0), ("Notebook Dell", 900.0)]


def sess(tok=TOK, cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    c = cid or ST.get("cid")
    if c:
        s.headers["X-Company-Id"] = c
    return s


def clean():
    ids = json.dumps(ST["cids"])
    mongo(f'{ids}.forEach(id=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:id}}));'
          f'db.counters.deleteMany({{key:{{$regex:id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:id}}}}); db.companies.deleteOne({{id:id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:["{UID}","{UID_OP}"]}}}}); db.user_sessions.deleteMany({{user_id:{{$in:["{UID}","{UID_OP}"]}}}});')


def xml(numero, den, righe, ced="03344556677"):
    t101.PIVA = PIVA
    return t101.xml(numero, f"{Y}-01-15", ced, den, righe)


def upload(x, cid=None):
    r = sess(cid=cid).post(f"{API}/passive/upload", files=[("files", (f"t127_{uuid.uuid4().hex[:6]}.xml", x, "application/octet-stream"))])
    assert r.status_code == 200, r.text
    j = r.json()[0]
    assert j["ok"], j
    return j["documenti"][0]["id"]


def crediti():
    return float(json.loads(mongo(f'print(JSON.stringify(db.companies.findOne({{id:"{ST["cid"]}"}},{{_id:0,ai_crediti:1}})))'))["ai_crediti"])


def mk_company(name, piva=PIVA):
    r = sess(cid="").post(f"{API}/companies", json={"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01",
                                                  "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    ST["cids"].append(cid)
    return cid


def moduli(cid, coge):
    r = sess(cid=cid).put(f"{API}/companies/{cid}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                                "corrispettivi": True, "contabilita": coge})
    assert r.status_code == 200, r.text


@pytest.fixture(scope="module", autouse=True)
def setup():
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t127.admin@example.com", name:"TEST_T127 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    ST["cid"] = mk_company(f"TEST_T127 AI {RUN} Srl")
    mongo(f'db.users.insertOne({{user_id:"{UID_OP}", email:"test.user.t127.oper@example.com", name:"TEST_T127 oper", picture:"", role:"operatore", status:"approved", company_ids:["{ST["cid"]}"], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID_OP}", session_token:"{TOK_OP}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    yield
    if os.environ.get("T127_KEEP"):
        print("\nKEEP", json.dumps(ST))
    else:
        clean()


class TestAiContiRighe:
    # company without contabilita (no chart of accounts) -> 400/403
    def test_00_no_coa(self):
        moduli(ST["cid"], False)
        ST["A"] = upload(xml("MR-1", "TEST_T127 Forniture Miste Srl", RIGHE))
        r = sess().post(f"{API}/ai/passive/{ST['A']}/conti")
        print("NO COA", r.status_code, r.text)
        assert r.status_code in (400, 403), r.text

    # enable COGE + upload ui invoice
    def test_01_enable_coge(self):
        moduli(ST["cid"], True)
        s = sess()
        assert s.get(f"{API}/contabilita/conti").status_code == 200
        pr = s.get(f"{API}/contabilita/parametri").json()
        p = pr["parametri"]
        body = {"conti": {k: p[k] for k, _ in pr["ruoli"]}, "contropartita_vendite": p["contropartita_vendite"],
                "contropartita_acquisti": p["contropartita_acquisti"], "aliquota_rc": 22, "categorie": p["categorie"]}
        assert s.put(f"{API}/contabilita/parametri", json=body).status_code == 200
        ST["UI"] = upload(xml("MR-UI", "TEST_T127 Forniture UI Srl", RIGHE, ced="03344556688"))

    # multi-line classification: conti valid, voce_cee, motivo, riepilogo split sums
    def test_02_classify(self):
        ST["cred0"] = crediti()
        r = sess().post(f"{API}/ai/passive/{ST['A']}/conti", timeout=180)
        print("CONTI", r.status_code, json.dumps(r.json(), ensure_ascii=False, indent=1)[:3000])
        assert r.status_code == 200, r.text
        j = r.json()
        ST["res"] = j
        assert len(j["righe"]) == 4
        for x in j["righe"]:
            assert x["conto"] and RX.match(x["conto"]), x
            assert x["voce_cee"], x
            assert x["motivo"], x
            assert x["conto_nome"], x
        by = {x["descrizione"]: x for x in j["righe"]}
        print("VOCI", {k: (v["conto"], v["voce_cee"]) for k, v in by.items()})
        assert by["Consulenza tecnica"]["voce_cee"].startswith("B7"), by["Consulenza tecnica"]
        assert by["Canone noleggio stampante"]["voce_cee"].startswith("B8"), by["Canone noleggio stampante"]
        assert by["Carta A4 risme"]["voce_cee"].startswith("B6"), by["Carta A4 risme"]
        assert by["Notebook Dell"]["voce_cee"].startswith(("BII", "B6")), by["Notebook Dell"]
        imp = round(sum(x["imponibile"] for x in j["riepilogo"]), 2)
        iva = round(sum(x["imposta"] for x in j["riepilogo"]), 2)
        assert imp == 1484.0 and iva == 326.48, (imp, iva)
        assert len({x["conto"] for x in j["riepilogo"]}) >= 3
        assert crediti() < ST["cred0"]

    # second call cached: same 'at', credits unchanged
    def test_03_cache(self):
        c1 = crediti()
        r = sess().post(f"{API}/ai/passive/{ST['A']}/conti", timeout=180)
        assert r.status_code == 200
        assert r.json()["at"] == ST["res"]["at"]
        assert r.json()["righe"] == ST["res"]["righe"]
        assert crediti() == c1

    # invoice without lines -> 400
    def test_04_no_lines(self):
        pid = "t127-nolines-" + RUN
        mongo(f'db.passive_invoices.insertOne({{id:"{pid}", company_id:"{ST["cid"]}", numero:"NL-1", data:"{Y}-01-02", stato_reg:"da_registrare", lines:[], riepilogo:[{{aliquota:22, imponibile:10, imposta:2.2}}], fornitore:{{denominazione:"TEST_T127 nolines"}}}})')
        r = sess().post(f"{API}/ai/passive/{pid}/conti")
        print("NOLINES", r.status_code, r.text)
        assert r.status_code == 400

    # other company's invoice -> 404
    def test_05_other_company(self):
        cid2 = mk_company(f"TEST_T127 Altra {RUN} Srl", piva="13" + RUN + "127")
        moduli(cid2, True)
        assert sess(cid=cid2).get(f"{API}/contabilita/conti").status_code == 200
        r = sess(cid=cid2).post(f"{API}/ai/passive/{ST['A']}/conti")
        print("OTHER", r.status_code, r.text)
        assert r.status_code == 404

    # operatore -> 403
    def test_06_operatore(self):
        r = sess(tok=TOK_OP).post(f"{API}/ai/passive/{ST['A']}/conti")
        assert r.status_code == 403, r.text

    # registration with proposed conti -> coa entry Dare on those conti
    def test_07_register(self):
        j = ST["res"]
        body = {"data_registrazione": date.today().isoformat(), "numero": "MR-1", "data": f"{Y}-01-15", "riepilogo": j["riepilogo"], "detraibilita_iva": 100}
        pv = sess().post(f"{API}/passive/{ST['A']}/registrazione/anteprima", json=body)
        assert pv.status_code == 200, pv.text
        r = sess().post(f"{API}/passive/{ST['A']}/registrazione", json=body)
        assert r.status_code == 200, r.text
        es = json.loads(mongo(f'print(JSON.stringify(db.coa_entries.find({{company_id:"{ST["cid"]}", origine:"acquisto", ref_id:"{ST["A"]}"}},{{_id:0}}).toArray()))') or "[]")
        assert es
        dare = {}
        for e in es:
            for x in e["righe"]:
                if x.get("dare"):
                    dare[x["conto"]] = round(dare.get(x["conto"], 0) + x["dare"], 2)
        print("DARE", dare)
        for x in j["riepilogo"]:
            assert dare.get(x["conto"]) == x["imponibile"], (x, dare)

    # batch analizza regression
    def test_08_batch(self):
        upload(xml("CA-9", "TEST_T127 Cancelleria Srl", [("Toner stampante ufficio", 70.0)], ced="03344556699"))
        r = sess().post(f"{API}/ai/passive/analizza", timeout=240)
        print("BATCH", r.status_code, r.text)
        assert r.status_code == 200, r.text
        assert r.json()["analizzate"] >= 1 and not r.json()["errori"]

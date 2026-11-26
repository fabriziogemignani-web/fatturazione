# Iteration 133: per-supplier registration model (modelli_registrazione: salva_modello on registration, applica_modello in /ai/passive/{id}/conti
# without AI, GET/PUT /api/ai/modelli, attivo false -> AI fallback), regression of PUT /passive/{id}/detraibilita clearing row codes,
# pro rata IVA (PUT/GET /api/pro-rata, iva_pro_rata in liquidation, POST/DELETE conguaglio). Real LLM calls.
# Run: cd /app/backend/tests && pytest test_iteration133_modelli_prorata.py -n 0 -v   (T133_KEEP=1 keeps data for UI)
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
from test_iteration101_ai_registrazione_consulente import COLLS as C101  # noqa: E402
import test_iteration101_ai_registrazione_consulente as t101  # noqa: E402

COLLS = C101 + ["modelli_registrazione", "ai_regole_conti", "corrispettivi", "ai_crediti_log"]
RUN = str(random.randint(100000, 999999))
TOK, UID = f"test_session_t133_admin_{RUN}", f"test-user-t133-admin-{RUN}"
PIVA = "13" + RUN + "133"
CED = "03344556611"
ST = {}
Y = date.today().year
TODAY = date.today().isoformat()
RX = re.compile(r"^(30\.0[6-9]|30\.14|31)\.")


def sess(cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    s.headers["X-Requested-With"] = "invoix"
    c = cid if cid is not None else ST.get("cid")
    if c:
        s.headers["X-Company-Id"] = c
    return s


def mq(js):
    out = mongo(f"print(JSON.stringify({js}))")
    return json.loads(out) if out else None


def clean():
    for cid in ST.get("cids", []):
        mongo(f'{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:"{cid}"}})); db.counters.deleteMany({{key:{{$regex:"{cid}"}}}});'
              f'db.users.updateMany({{}}, {{$pull:{{company_ids:"{cid}"}}}}); db.companies.deleteOne({{id:"{cid}"}});')
    mongo(f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def xml(numero, righe, ced=CED, den="TEST_T133 Fornitore Srl"):
    t101.PIVA = PIVA
    return t101.xml(numero, f"{Y}-01-15", ced, den, righe)


def upload(x):
    r = sess().post(f"{API}/passive/upload", files=[("files", (f"t133_{uuid.uuid4().hex[:6]}.xml", x, "application/octet-stream"))])
    assert r.status_code == 200, r.text
    j = r.json()[0]
    assert j["ok"], j
    return j["documenti"][0]["id"]


def crediti():
    return float(mq(f'db.companies.findOne({{id:"{ST["cid"]}"}},{{_id:0,ai_crediti:1}})')["ai_crediti"])


def modello():
    return mq(f'db.modelli_registrazione.find({{company_id:"{ST["cid"]}"}},{{_id:0}}).toArray()')


def body(pid, riep):
    d = sess().get(f"{API}/passive/{pid}").json()
    return {"data_registrazione": TODAY, "numero": d["numero"], "data": d["data"], "riepilogo": riep, "detraibilita_iva": 100}


def mk_company(name, piva):
    r = sess(cid="").post(f"{API}/companies", json={"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01",
                                                  "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    ST.setdefault("cids", []).append(cid)
    s = sess(cid=cid)
    assert s.put(f"{API}/companies/{cid}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                        "corrispettivi": True, "contabilita": True}).status_code == 200
    pr = s.get(f"{API}/contabilita/parametri").json()
    p = pr["parametri"]
    b = {"conti": {k: p[k] for k, _ in pr["ruoli"]}, "contropartita_vendite": p["contropartita_vendite"],
         "contropartita_acquisti": p["contropartita_acquisti"], "aliquota_rc": 22, "categorie": p["categorie"]}
    assert s.put(f"{API}/contabilita/parametri", json=b).status_code == 200
    return cid


@pytest.fixture(scope="module", autouse=True)
def setup():
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t133.{RUN}@example.com", name:"TEST_T133 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    ST["cid"] = mk_company(f"TEST_T133 Modelli {RUN} Srl", PIVA)
    j = sess().get(f"{API}/contabilita/conti").json()
    items = j if isinstance(j, list) else j.get("conti") or j.get("items") or []
    ST["costi"] = [x["codice"] for x in items if x.get("livello") == 3 and RX.match(x["codice"])]
    assert len(ST["costi"]) >= 3
    yield
    if os.environ.get("T133_KEEP"):
        print("\nKEEP", json.dumps({k: ST[k] for k in ("cid", "cids")}), TOK)
    else:
        clean()


# Per-supplier registration model
class TestModello:
    def test_01_first_invoice_uses_ai(self):
        ST["A"] = upload(xml("M133-A", [("Carta A4 risme", 100.0), ("Consulenza tecnica fiscale", 300.0)]))
        c0 = crediti()
        r = sess().post(f"{API}/ai/passive/{ST['A']}/conti", timeout=180)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "modello" not in j, j
        assert crediti() < c0
        assert round(sum(x["imponibile"] for x in j["riepilogo"]), 2) == 400.0
        ST["resA"] = j

    def test_02_register_saves_model(self):
        c1, c2 = ST["costi"][0], ST["costi"][1]
        riep = [{"aliquota": 22, "natura": "", "imponibile": 100.0, "imposta": 22.0, "conto": c1},
                {"aliquota": 22, "natura": "", "imponibile": 300.0, "imposta": 66.0, "conto": c2}]
        r = sess().post(f"{API}/passive/{ST['A']}/registrazione", json=body(ST["A"], riep))
        assert r.status_code == 200, r.text
        m = modello()
        assert len(m) == 1, m
        m = m[0]
        pid = sess().get(f"{API}/passive/{ST['A']}").json()["party_id"]
        ST["party"] = pid
        assert m["party_id"] == pid and m["attivo"] is True and m["utilizzi"] == 1, m
        assert len(m["righe"]) == 1 and m["righe"][0]["aliquota"] == 22
        q = {c["conto"]: c["quota"] for c in m["righe"][0]["conti"]}
        assert q == {c2: 75.0, c1: 25.0}, q
        assert "ultima_fattura" in m and "M133-A" in m["ultima_fattura"]
        ST["mid"] = m["id"]

    def test_03_second_invoice_uses_model_no_ai(self):
        ST["B"] = upload(xml("M133-B", [("Toner stampante laser", 150.0), ("Manutenzione impianto", 650.0)]))
        c0 = crediti()
        r = sess().post(f"{API}/ai/passive/{ST['B']}/conti", timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("modello") and j["modello"]["id"] == ST["mid"], j
        assert crediti() == c0, "AI credits consumed when model exists"
        c1, c2 = ST["costi"][0], ST["costi"][1]
        rp = {x["conto"]: (x["imponibile"], x["imposta"]) for x in j["riepilogo"]}
        assert rp == {c2: (600.0, 132.0), c1: (200.0, 44.0)}, rp
        assert all(x["appreso"] and x["conto"] == c2 for x in j["righe"]), j["righe"]
        doc = mq(f'db.passive_invoices.findOne({{id:"{ST["B"]}"}},{{_id:0,ai_righe:1}})')
        assert not doc.get("ai_righe"), "ai_righe cache written although model used"

    def test_04_register_again_updates_model(self):
        c3 = ST["costi"][2]
        riep = [{"aliquota": 22, "natura": "", "imponibile": 800.0, "imposta": 176.0, "conto": c3}]
        r = sess().post(f"{API}/passive/{ST['B']}/registrazione", json=body(ST["B"], riep))
        assert r.status_code == 200, r.text
        m = modello()
        assert len(m) == 1
        m = m[0]
        assert m["utilizzi"] == 2 and m["righe"][0]["conti"] == [{"conto": c3, "quota": 100.0}], m

    def test_05_list_and_put_validation(self):
        s = sess()
        r = s.get(f"{API}/ai/modelli")
        assert r.status_code == 200, r.text
        lst = r.json()
        assert len(lst) == 1 and lst[0]["id"] == ST["mid"] and "_id" not in lst[0]
        g = lst[0]["righe"][0]
        bad = s.put(f"{API}/ai/modelli/{ST['mid']}", json={"attivo": True, "righe": [{**g, "conti": [{"conto": "99.99.999", "quota": 100}]}]})
        assert bad.status_code == 422, bad.text
        bad = s.put(f"{API}/ai/modelli/{ST['mid']}", json={"attivo": True, "righe": [{**g, "conti": [{"conto": ST["costi"][0], "quota": 50}, {"conto": ST["costi"][1], "quota": 40}]}]})
        assert bad.status_code == 422, bad.text
        assert s.put(f"{API}/ai/modelli/nonexistent", json={"attivo": True}).status_code == 404
        ok = s.put(f"{API}/ai/modelli/{ST['mid']}", json={"attivo": True, "righe": [{**g, "conti": [{"conto": ST["costi"][0], "quota": 60}, {"conto": ST["costi"][1], "quota": 40}]}]})
        assert ok.status_code == 200, ok.text
        assert [c["quota"] for c in ok.json()["righe"][0]["conti"]] == [60.0, 40.0]
        assert modello()[0]["righe"][0]["conti"][0]["conto"] == ST["costi"][0]

    def test_06_edited_model_applied(self):
        ST["C"] = upload(xml("M133-C", [("Servizi vari", 1000.0)]))
        r = sess().post(f"{API}/ai/passive/{ST['C']}/conti", timeout=60)
        assert r.status_code == 200 and r.json().get("modello"), r.text
        rp = {x["conto"]: x["imponibile"] for x in r.json()["riepilogo"]}
        assert rp == {ST["costi"][0]: 600.0, ST["costi"][1]: 400.0}, rp

    def test_07_other_company_404(self):
        cid2 = mk_company(f"TEST_T133 Altra {RUN} Srl", "14" + RUN + "133")
        assert sess(cid=cid2).put(f"{API}/ai/modelli/{ST['mid']}", json={"attivo": False}).status_code == 404
        assert sess(cid=cid2).get(f"{API}/ai/modelli").json() == []

    def test_08_inactive_falls_back_to_ai(self):
        r = sess().put(f"{API}/ai/modelli/{ST['mid']}", json={"attivo": False})
        assert r.status_code == 200 and r.json()["attivo"] is False and r.json()["righe"], r.text
        c0 = crediti()
        r = sess().post(f"{API}/ai/passive/{ST['C']}/conti", timeout=180)
        assert r.status_code == 200, r.text
        assert "modello" not in r.json()
        assert crediti() < c0
        sess().put(f"{API}/ai/modelli/{ST['mid']}", json={"attivo": True})


# Regression iteration 132: PUT detraibilita clears per-row codes
class TestDetraibilita:
    def test_01_clear_codes(self):
        s = sess()
        r = s.post(f"{API}/parties", json={"tipo": "fornitore", "denominazione": "TEST_T133 Auto Srl", "partita_iva": "02345670481", "codice_fiscale": "02345670481",
                                         "indirizzo": "Via Y 1", "cap": "50100", "comune": "Firenze", "provincia": "FI", "nazione": "IT", "codice_iva": "22D40"})
        assert r.status_code == 200, r.text
        pid = upload(xml("D133-1", [("Carburante", 500.0)], ced="02345670481", den="TEST_T133 Auto Srl"))
        d = s.get(f"{API}/passive/{pid}").json()
        assert d["riepilogo"][0].get("codice_iva") == "22D40" and d["riepilogo"][0].get("detraibilita") == 40, d["riepilogo"]
        r = s.put(f"{API}/passive/{pid}/detraibilita", json={"percentuale": 50})
        assert r.status_code == 200, r.text
        d = s.get(f"{API}/passive/{pid}").json()
        assert d["detraibilita_iva"] == 50
        assert "codice_iva" not in d["riepilogo"][0] and "detraibilita" not in d["riepilogo"][0], d["riepilogo"]
        assert s.post(f"{API}/parties", json={"tipo": "fornitore", "denominazione": "TEST_T133 Bad", "partita_iva": "00743110157", "codice_fiscale": "00743110157",
                                              "indirizzo": "Via Y 1", "cap": "50100", "comune": "Firenze", "provincia": "FI", "nazione": "IT", "aliquota_rc": 7}).status_code == 422


# Pro rata IVA
class TestProRata:
    def test_01_setup_sales_and_config(self):
        cid = ST["cid"]
        mongo(f'db.corrispettivi.insertOne({{id:"t133-corr-{RUN}", company_id:"{cid}", anno:{Y}, data:"{TODAY}", tipo_documento:"corrispettivo", totale:1176,'
              f'riepilogo:[{{aliquota:22, natura:"", imponibile:800, imposta:176}}, {{aliquota:0, natura:"N4", imponibile:200, imposta:0}}]}})')
        r = sess().put(f"{API}/pro-rata", json={"attivo": True, "anno": Y, "percentuale": 90})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["attivo"] and j["provvisorio"] == 90 and j["definitivo"] == 80.0, j
        assert j["operazioni_detraibili"] == 800 and j["operazioni_esenti"] == 200
        assert sess().put(f"{API}/pro-rata", json={"attivo": True, "anno": Y, "percentuale": 120}).status_code == 422

    def test_02_liquidation_iva_pro_rata(self):
        r = sess().get(f"{API}/liquidazione-iva", params={"anno": Y})
        assert r.status_code == 200, r.text
        per = [p for p in r.json()["periodi"] if p.get("iva_pro_rata")]
        assert per, "no iva_pro_rata in periods"
        p = per[0]
        gross = round(p["iva_credito"] + p["iva_pro_rata"], 2)
        assert p["iva_pro_rata"] == round(gross * 0.10, 2) and p["pro_rata"] == 90, p
        ST["gross"] = round(sum(x["iva_credito"] + (x.get("iva_pro_rata") or 0) for x in r.json()["periodi"]), 2)

    def test_03_get_conguaglio(self):
        j = sess().get(f"{API}/pro-rata", params={"anno": Y}).json()
        assert j["iva_base"] == ST["gross"], j
        assert j["iva_spettante"] == round(ST["gross"] * 0.8, 2)
        assert j["conguaglio"] == round(j["iva_spettante"] - j["iva_detratta"], 2) and j["conguaglio"] < 0, j
        assert j["registrazione"] is None
        ST["cong"] = j["conguaglio"]

    def test_04_register_and_delete_conguaglio(self):
        s = sess()
        r = s.post(f"{API}/pro-rata/conguaglio", json={"anno": Y})
        assert r.status_code == 200, r.text
        e = mq(f'db.coa_entries.findOne({{company_id:"{ST["cid"]}", origine:"prorata", ref_id:"PR-{Y}"}},{{_id:0}})')
        assert e, "entry not stored"
        dare = round(sum(x.get("dare") or 0 for x in e["righe"]), 2)
        assert dare == round(sum(x.get("avere") or 0 for x in e["righe"]), 2) == abs(ST["cong"]), e["righe"]
        assert s.get(f"{API}/pro-rata", params={"anno": Y}).json()["registrazione"]
        assert s.post(f"{API}/pro-rata/conguaglio", json={"anno": Y}).status_code == 400
        r = s.delete(f"{API}/pro-rata/conguaglio/{Y}")
        assert r.status_code == 200, r.text
        assert s.get(f"{API}/pro-rata", params={"anno": Y}).json()["registrazione"] is None

    def test_05_disable(self):
        j = sess().put(f"{API}/pro-rata", json={"attivo": False, "anno": Y, "percentuale": 90}).json()
        assert j["attivo"] is False and j["provvisorio"] is None and j["conguaglio"] == 0
        assert sess().post(f"{API}/pro-rata/conguaglio", json={"anno": Y}).status_code == 400

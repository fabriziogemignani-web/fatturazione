# Iteration 132: Codici IVA con % detraibilita (22D40, 22D50, 22IND, 10IND, 4IND), conto 30.14.008 IVA indetraibile,
# codice_iva + aliquota_rc nel fornitore, reg-veloce acquisto con split IVA detraibile/indetraibile, registro/liquidazione IVA,
# registrazione passiva XML con codice_iva per riga (anteprima + registrazione).
# Run with: pytest test_iteration132_codici_iva_detraibilita.py -n 0
import os
import random
from datetime import date, timedelta

import pytest
import requests

from test_iteration7_pa_scartate_registro import API, mongo

RUN = str(random.randint(100000, 999999))
TOK, UID = f"test_session_t132_admin_{RUN}", f"test-user-t132-admin-{RUN}"
PIVA = "01234567897"
TAG = f"TEST_T132 {RUN}"
FIX = open(os.path.join(os.path.dirname(__file__), "fixtures", "sample_fattura.xml")).read()
T = date.today()
Y = T.year
TODAY = T.isoformat()
D1 = max(T - timedelta(days=5), date(Y, 1, 1)).isoformat()
ST = {}
COLLS = ["invoices", "passive_invoices", "parties", "articles", "counters", "payments", "passive_payments", "bank_tx", "bank_accounts", "corrispettivi",
         "coa_accounts", "coa_causali", "coa_iva", "coa_entries", "audit", "sdi_events", "intenti", "partite_aperte", "ratei_risconti", "f24_versamenti"]


def sess():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    s.headers["X-Requested-With"] = "invoix"
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    cid = ST.get("cid")
    if cid:
        mongo(f'{COLLS}.forEach(k=>db[k].deleteMany({{company_id:"{cid}"}})); db.counters.deleteMany({{key:{{$regex:"{cid}"}}}});'
              f'db.users.updateMany({{}}, {{$pull:{{company_ids:"{cid}"}}}}); db.companies.deleteOne({{id:"{cid}"}});')
    mongo(f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def entries(ref):
    d = sess().get(f"{API}/contabilita/registrazioni", params={"origine": "acquisto"}).json()
    return [e for e in d["registrazioni"] if e.get("ref_id") == ref]


def side(e, conto):
    rows = [r for r in e["righe"] if r["conto"] == conto]
    return round(sum(r.get("dare") or 0 for r in rows), 2), round(sum(r.get("avere") or 0 for r in rows), 2)


def balanced(e):
    return round(sum(r.get("dare") or 0 for r in e["righe"]), 2) == round(sum(r.get("avere") or 0 for r in e["righe"]), 2)


def xml(num, idc):
    return FIX.replace("<IdCodice>01234567890</IdCodice>", f"<IdCodice>{PIVA}</IdCodice>").replace("<Numero>5674/2026</Numero>", f"<Numero>{num}</Numero>") \
        .replace("<Data>2026-10-30</Data>", f"<Data>{D1}</Data>").replace("<IdCodice>02345670481</IdCodice>", f"<IdCodice>{idc}</IdCodice>") \
        .replace("<CodiceFiscale>02345670481</CodiceFiscale>", f"<CodiceFiscale>{idc}</CodiceFiscale>")


@pytest.fixture(scope="module", autouse=True)
def setup():
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t132.{RUN}@example.com", name:"TEST_T132 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": f"{TAG} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                              "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    yield
    clean()


def sup(name, piva, **kw):
    return {"tipo": "fornitore", "denominazione": f"{TAG} {name}", "partita_iva": piva, "codice_fiscale": piva,
            "indirizzo": "Via Y 1", "cap": "50100", "comune": "Firenze", "provincia": "FI", "nazione": "IT", **kw}


# Seed: codici IVA con detraibilita, conto 30.14.008, parametro iva_indetraibile
class TestSeed:
    def test_01_codici(self):
        r = sess().get(f"{API}/contabilita/codici-iva")
        assert r.status_code == 200, r.text
        m = {c["codice"]: c for c in r.json()}
        exp = {"22D40": (22, 40), "22D50": (22, 50), "22IND": (22, 0), "10IND": (10, 0), "4IND": (4, 0)}
        for k, (a, d) in exp.items():
            assert k in m, k
            assert m[k]["aliquota"] == a and m[k]["detraibilita"] == d, m[k]
        assert "_id" not in m["22D40"]

    def test_02_conto_e_parametro(self):
        r = sess().get(f"{API}/contabilita/conti")
        assert r.status_code == 200, r.text
        d = r.json()
        items = d if isinstance(d, list) else d.get("conti") or d.get("items") or []
        assert any(x.get("codice") == "30.14.008" and "indetraibile" in x.get("descrizione", "").lower() for x in items)
        p = sess().get(f"{API}/contabilita/parametri").json()
        assert p["parametri"]["iva_indetraibile"] == "30.14.008", p["parametri"]
        assert any(k == "iva_indetraibile" for k, _ in p["ruoli"])

    def test_03_upsert_idempotent(self):
        n = mongo(f'print(db.coa_iva.countDocuments({{company_id:"{ST["cid"]}", codice:"22D40"}}))')
        assert n == "1"
        # remove one code -> ensure_seed on restart would re-add (simulate existing company); just check uniqueness here
        n2 = mongo(f'print(db.coa_accounts.countDocuments({{company_id:"{ST["cid"]}", codice:"30.14.008"}}))')
        assert n2 == "1"


# Fornitore: codice_iva + aliquota_rc
class TestParty:
    def test_01_create_update(self):
        s = sess()
        r = s.post(f"{API}/parties", json=sup("Auto", "02345670481", codice_iva="22D40", aliquota_rc=10))
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["codice_iva"] == "22D40" and j["aliquota_rc"] == 10, j
        ST["f40"] = j["id"]
        r = s.put(f"{API}/parties/{ST['f40']}", json=sup("Auto", "02345670481", codice_iva="22D40", aliquota_rc=5))
        assert r.status_code == 200, r.text
        g = s.get(f"{API}/parties", params={"tipo": "fornitore"}).json()
        items = g if isinstance(g, list) else g.get("items", [])
        p = next(x for x in items if x["id"] == ST["f40"])
        assert p["codice_iva"] == "22D40" and p["aliquota_rc"] == 5
        r = s.put(f"{API}/parties/{ST['f40']}", json=sup("Auto", "02345670481", codice_iva="22D40", aliquota_rc=10))
        assert r.status_code == 200

    def test_02_validation(self):
        s = sess()
        assert s.post(f"{API}/parties", json=sup("Bad", "00743110157", aliquota_rc=30)).status_code == 422
        assert s.post(f"{API}/parties", json=sup("Bad", "00743110157", codice_iva="TOOLONGCODE")).status_code == 422

    def test_03_aliquota_rc_non_standard(self):
        """Observation: aliquota_rc=7 (non 4/5/10/22) accepted?"""
        r = sess().post(f"{API}/parties", json=sup("Odd", "00743110157", aliquota_rc=7))
        print("aliquota_rc=7 ->", r.status_code)
        if r.status_code == 200:
            mongo(f'db.parties.deleteOne({{id:"{r.json()["id"]}"}})')
        assert r.status_code == 422, "aliquota_rc 7 accepted: should be limited to 4/5/10/22"


# Registrazione veloce acquisto con codice_iva fornitore 22D40
class TestRegVeloce:
    def test_01_split(self):
        b = {"tipo": "acquisto", "party_id": ST["f40"], "numero": f"RV132-{RUN}", "data_documento": D1, "data_registrazione": TODAY,
             "righe": [{"aliquota": 22, "totale": 1220}], "aliquota_rc": 22}
        r = sess().post(f"{API}/reg-veloce", json=b)
        assert r.status_code == 200, r.text
        ST["rv"] = r.json()["id"]
        doc = sess().get(f"{API}/passive/{ST['rv']}").json()
        row = doc["riepilogo"][0]
        assert row["codice_iva"] == "22D40" and row["detraibilita"] == 40, row
        e = entries(ST["rv"])
        assert len(e) == 1 and balanced(e[0]), e
        e = e[0]
        assert side(e, "30.06.001") == (1000.0, 0.0), e["righe"]
        assert side(e, "30.14.008") == (132.0, 0.0)
        assert side(e, "05.02.002") == (88.0, 0.0)
        assert side(e, "13.02.001") == (0.0, 1220.0)
        assert e["iva_indetraibile"] == 132.0

    def test_02_supplier_detraibilita_50_no_code(self):
        s = sess()
        r = s.post(f"{API}/parties", json=sup("Tel", "00743110157", detraibilita_iva=50))
        assert r.status_code == 200, r.text
        ST["f50"] = r.json()["id"]
        r = s.post(f"{API}/reg-veloce", json={"tipo": "acquisto", "party_id": ST["f50"], "numero": f"RV132B-{RUN}", "data_documento": D1,
                                              "data_registrazione": TODAY, "righe": [{"aliquota": 22, "totale": 610}], "aliquota_rc": 22})
        assert r.status_code == 200, r.text
        ST["rv50"] = r.json()["id"]
        e = entries(ST["rv50"])[0]
        assert balanced(e)
        assert side(e, "30.06.001") == (500.0, 0.0), e["righe"]
        assert side(e, "30.14.008") == (55.0, 0.0)
        assert side(e, "05.02.002") == (55.0, 0.0)

    def test_03_registro_e_liquidazione(self):
        r = sess().get(f"{API}/registro-iva-acquisti", params={"anno": Y})
        assert r.status_code == 200, r.text
        j = r.json()
        tot = j.get("totali") if isinstance(j.get("totali"), dict) else j
        rows = j.get("rows") or j.get("righe") or j.get("documenti") or []
        print("registro keys:", list(j.keys()))
        ind = tot.get("imposta_indetraibile") if isinstance(tot, dict) else None
        if ind is None:
            ind = j.get("riepilogo", {}).get("imposta_indetraibile")
        assert ind == 187.0, j  # 132 + 55
        r = sess().get(f"{API}/liquidazione-iva", params={"anno": Y})
        assert r.status_code == 200, r.text
        per = [p for p in r.json()["periodi"] if p.get("iva_indetraibile")]
        assert per, r.json()
        p = per[0]
        assert p["iva_indetraibile"] == 187.0 and p["iva_credito"] == 143.0, p  # 88 + 55

    def test_04_td16_regression(self):
        r = sess().post(f"{API}/reg-veloce", json={"tipo": "acquisto", "party_id": ST["f50"], "numero": f"RV132C-{RUN}", "data_documento": D1,
                                                   "data_registrazione": TODAY, "righe": [{"aliquota": 0, "natura": "N6.3", "totale": 1000}],
                                                   "aliquota_rc": 22, "autofattura": "TD16"})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("autofattura_id"), j
        e = entries(j["id"])[0]
        assert balanced(e)
        # RC 220 with detraibilita 50 -> 110 credit, 110 indetraibile
        assert side(e, "13.03.001") == (0.0, 220.0), e["righe"]
        assert side(e, "05.02.002") == (110.0, 0.0), e["righe"]
        assert side(e, "30.14.008") == (110.0, 0.0), e["righe"]


# Registrazione fattura passiva XML con codice IVA per riga
class TestPassiva:
    def test_01_upload(self):
        r = sess().post(f"{API}/passive/upload", files=[("files", ("p.xml", xml(f"T132-{RUN}", "02345670481"), "text/xml"))])
        assert r.status_code == 200, r.text
        res = r.json()[0]
        assert res.get("ok") and res.get("documenti"), res
        ST["pas"] = res["documenti"][0]["id"]
        d = sess().get(f"{API}/passive/{ST['pas']}").json()
        assert d["party_id"] == ST["f40"], d.get("party_id")
        ST["doc"] = d

    def test_02_auto_entry_on_import_uses_supplier_code(self):
        """Observation: entry generated at import time - does it honour supplier codice_iva 22D40?"""
        e = entries(ST["pas"])
        assert e, "no entry on import"
        print("import entry rows:", [(r["conto"], r.get("dare"), r.get("avere")) for r in e[0]["righe"]])
        assert side(e[0], "05.02.002") == (41.47, 0.0), "import entry ignores supplier codice_iva (full IVA detraibile)"

    def _body(self, **kw):
        d = ST["doc"]
        b = {"data_registrazione": TODAY, "numero": d["numero"], "data": d["data"], "aliquota_rc": 22, "detraibilita_iva": 100,
             "riepilogo": [{"aliquota": r["aliquota"], "natura": r.get("natura"), "imponibile": r["imponibile"], "imposta": r["imposta"], "conto": ""} for r in d["riepilogo"]]}
        b.update(kw)
        return b

    def test_03_anteprima_proposes_supplier_code(self):
        r = sess().post(f"{API}/passive/{ST['pas']}/registrazione/anteprima", json=self._body())
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["aliquota_rc_fornitore"] == 10, j.get("aliquota_rc_fornitore")
        assert j["iva_indetraibile"] == 62.21, j.get("iva_indetraibile")
        assert j["riepilogo"][0]["codice_iva"] == "22D40" and j["riepilogo"][0]["detraibilita"] == 40
        rows = {x["conto"]: x for x in j["righe"]}
        assert rows["30.14.008"]["dare"] == 62.21 and rows["05.02.002"]["dare"] == 41.47

    def test_04_anteprima_explicit_code_22IND(self):
        rie = [{**x, "codice_iva": "22IND"} for x in self._body()["riepilogo"]]
        j = sess().post(f"{API}/passive/{ST['pas']}/registrazione/anteprima", json=self._body(riepilogo=rie)).json()
        assert j["iva_indetraibile"] == 103.68, j
        assert not any(x["conto"] == "05.02.002" and x.get("dare") for x in j["righe"])

    def test_05_anteprima_split_two_rows(self):
        rie = [{"aliquota": 22, "imponibile": 400, "imposta": 88, "conto": "", "codice_iva": "22D50"},
               {"aliquota": 22, "imponibile": 71.25, "imposta": 15.68, "conto": "", "detraibilita": 100}]
        j = sess().post(f"{API}/passive/{ST['pas']}/registrazione/anteprima", json=self._body(riepilogo=rie)).json()
        assert len(j["riepilogo"]) == 2, j["riepilogo"]
        assert j["iva_indetraibile"] == 44.0, j.get("iva_indetraibile")

    def test_06_bad_detraibilita_422(self):
        rie = [{**x, "detraibilita": 150} for x in self._body()["riepilogo"]]
        assert sess().post(f"{API}/passive/{ST['pas']}/registrazione/anteprima", json=self._body(riepilogo=rie)).status_code == 422

    def test_07_registrazione(self):
        r = sess().post(f"{API}/passive/{ST['pas']}/registrazione", json=self._body())
        assert r.status_code == 200, r.text
        e = entries(ST["pas"])
        assert len(e) == 1 and balanced(e[0])
        e = e[0]
        assert side(e, "30.14.008") == (62.21, 0.0) and side(e, "05.02.002") == (41.47, 0.0), e["righe"]
        assert side(e, "13.02.001") == (0.0, 574.93)
        d = sess().get(f"{API}/passive/{ST['pas']}").json()
        assert d["stato_reg"] == "registrata" and d["riepilogo"][0]["codice_iva"] == "22D40"
        j = sess().get(f"{API}/registro-iva-acquisti", params={"anno": Y}).json()
        row = next(x for x in (j.get("rows") or []) if x["id"] == ST["pas"])
        assert row["iva_indetraibile"] == 62.21, row

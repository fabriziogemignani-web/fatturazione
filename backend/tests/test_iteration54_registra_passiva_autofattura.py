# Iteration 54: Fatture passive - registrazione manuale con editing (anteprima/registrazione), reverse charge, autofattura TD16-19 (bozza AF, XML, invio SDI),
# esclusione autofatture da registro IVA vendite/scadenzario/contabilità vendite, registrazione veloce acquisto estero con RC+autofattura, prima nota editabile.
# Run: pytest tests/test_iteration54_registra_passiva_autofattura.py -v -n 0
import json
import random
import xml.etree.ElementTree as ET
from datetime import date, timedelta

import pytest
import requests

from test_iteration7_pa_scartate_registro import API, mongo
from test_iteration13_reverse_charge import rc_xml

RUN = str(random.randint(100000, 999999))
TOK, UID = f"test_session_t54_admin_{RUN}", f"test-user-t54-admin-{RUN}"
PIVA = "87" + RUN + "541"
T = date.today()
Y = T.year
TODAY = T.isoformat()
D1 = max(T - timedelta(days=5), date(Y, 1, 1)).isoformat()
ST = {}
COLLS = ["invoices", "passive_invoices", "parties", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "intenti", "partite_aperte", "counters"]


def sess():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{partita_iva:"{PIVA}"}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def mk(numero, rc=(("N6.3", 1000.0),), keep22=True, foreign=False):
    x = rc_xml(numero, data=D1, rc=rc, keep22=keep22).decode().replace("<IdCodice>01234567890</IdCodice>", f"<IdCodice>{PIVA}</IdCodice>")
    if foreign:
        x = x.replace("<IdPaese>IT</IdPaese>\n          <IdCodice>02345670481</IdCodice>", "<IdPaese>DE</IdPaese>\n          <IdCodice>DE811" + RUN + "</IdCodice>", 1)
        x = x.replace("<CodiceFiscale>02345670481</CodiceFiscale>", "").replace("DEMO Energia Toscana SpA", f"TEST_T54 GmbH {RUN}")
        x = x.replace("<CAP>50126</CAP>", "<CAP>10115</CAP>").replace("<Comune>Firenze</Comune>", "<Comune>Berlin</Comune>").replace("<Provincia>FI</Provincia>", "")
        x = x.replace("<Nazione>IT</Nazione>", "<Nazione>DE</Nazione>", 1)
    return x.encode()


def up(name, xml):
    r = sess().post(f"{API}/passive/upload", files=[("files", (name, xml, "application/octet-stream"))])
    assert r.status_code == 200, r.text
    res = r.json()[0]
    assert res.get("documenti"), res
    return res["documenti"][0]["id"]


def entry_for(ref, origine="acquisto"):
    d = sess().get(f"{API}/contabilita/registrazioni", params={"origine": origine}).json()
    return [e for e in d["registrazioni"] if e.get("ref_id") == ref]


def side(e, conto):
    rows = [r for r in e["righe"] if r["conto"] == conto]
    return round(sum(r["dare"] for r in rows), 2), round(sum(r["avere"] for r in rows), 2)


def balanced(rows):
    return round(sum(r.get("dare") or 0 for r in rows), 2) == round(sum(r.get("avere") or 0 for r in rows), 2)


def body_for(doc, **kw):
    b = {"data_registrazione": TODAY, "numero": doc["numero"], "data": doc["data"], "aliquota_rc": 22, "detraibilita_iva": 100,
         "riepilogo": [{"aliquota": r["aliquota"], "natura": r.get("natura"), "imponibile": r["imponibile"], "imposta": r["imposta"], "conto": ""} for r in doc["riepilogo"]]}
    return b | kw


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    try:
        mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t54.{RUN}@example.com", name:"TEST_T54 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
              f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
        r = sess().post(f"{API}/companies", json={"denominazione": f"TEST_T54 Passive {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                                 "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
        assert r.status_code == 200, r.text
        ST["cid"] = r.json()["id"]
        sess().get(f"{API}/contabilita/conti")
        ST["A"] = up("a.xml", mk(f"T54A-{RUN}"))                       # 22% 471.25 + N6.3 1000 (IT)
        ST["B"] = up("b.xml", mk(f"T54B-{RUN}", rc=()))                # 22% only
        ST["C"] = up("c.xml", mk(f"T54C-{RUN}", rc=(("N2.1", 500.0),), keep22=False, foreign=True))  # DE supplier, N2.1 500
        yield
    finally:
        clean()


class TestAutomaticFlow:
    def test_01_upload_creates_entry_without_registration(self):
        for k in ("A", "B", "C"):
            d = sess().get(f"{API}/passive/{k and ST[k]}").json()
            assert d["stato_reg"] == "da_registrare", d
            es = entry_for(ST[k])
            assert len(es) == 1 and es[0]["causale"] == "FA", (k, es)
            ST[f"E_{k}"] = es[0]["id"]


class TestAnteprima:
    def test_01_proposta_td16_and_rc(self):
        d = sess().get(f"{API}/passive/{ST['A']}").json()
        ST["docA"] = d
        r = sess().post(f"{API}/passive/{ST['A']}/registrazione/anteprima", json=body_for(d))
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["autofattura_proposta"] == "TD16"
        assert [(x["natura"], x["imponibile"], x["imposta"]) for x in j["reverse_charge"]] == [("N6.3", 1000.0, 220.0)]
        assert balanced(j["righe"]) and j["causale"] == "FA"
        iva_v = [x for x in j["righe"] if x["conto"] == "13.03.001"]
        assert iva_v and iva_v[0]["avere"] == 220.0
        # anteprima must not persist
        assert sess().get(f"{API}/passive/{ST['A']}").json()["stato_reg"] == "da_registrare"

    def test_02_proposta_td17_foreign(self):
        d = sess().get(f"{API}/passive/{ST['C']}").json()
        assert (d["fornitore"].get("nazione") or "").upper() == "DE", d["fornitore"]
        r = sess().post(f"{API}/passive/{ST['C']}/registrazione/anteprima", json=body_for(d))
        assert r.status_code == 200, r.text
        assert r.json()["autofattura_proposta"] == "TD17"
        assert r.json()["reverse_charge"][0]["imposta"] == 110.0

    def test_03_no_proposta_normal(self):
        d = sess().get(f"{API}/passive/{ST['B']}").json()
        r = sess().post(f"{API}/passive/{ST['B']}/registrazione/anteprima", json=body_for(d))
        assert r.status_code == 200 and r.json()["autofattura_proposta"] is None and not r.json()["reverse_charge"]

    def test_04_validations(self):
        d = ST["docA"]
        bad = [body_for(d, data_registrazione="2000-01-01"), body_for(d, aliquota_rc=7),
               body_for(d, riepilogo=[{"aliquota": 22, "imponibile": 10, "imposta": 2.2, "conto": "99.99.999"}]),
               body_for(d, riepilogo=[{"aliquota": 0, "natura": None, "imponibile": 10, "imposta": 0}])]
        for b in bad:
            r = sess().post(f"{API}/passive/{ST['A']}/registrazione/anteprima", json=b)
            assert r.status_code == 422, (b, r.text)
        r = sess().post(f"{API}/passive/{ST['B']}/registrazione", json=body_for(sess().get(f"{API}/passive/{ST['B']}").json(), autofattura="TD16"))
        assert r.status_code == 422 and "autofattura" in r.text, r.text


class TestRegistra:
    def test_01_register_with_edits_and_autofattura(self):
        d = ST["docA"]
        conti = sess().get(f"{API}/contabilita/conti").json()
        leafs = [c["codice"] for c in (conti if isinstance(conti, list) else conti.get("conti", [])) if c["codice"].startswith("30.") and len(c["codice"]) == 9]
        assert len(leafs) >= 2
        ST["c1"], ST["c2"] = leafs[0], leafs[1]
        rie = [{"aliquota": 22, "natura": None, "imponibile": 500.0, "imposta": 110.0, "conto": ST["c1"]},
               {"aliquota": 0, "natura": "N6.3", "imponibile": 1000.0, "imposta": 0, "conto": ST["c2"]}]
        r = sess().post(f"{API}/passive/{ST['A']}/registrazione", json=body_for(d, numero=f"T54A-{RUN}-M", riepilogo=rie, autofattura="TD16"))
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["stato_reg"] == "registrata" and j["protocollo"] >= 1 and j["autofattura_id"]
        ST["AF"] = j["autofattura_id"]
        g = sess().get(f"{API}/passive/{ST['A']}").json()
        assert g["numero"] == f"T54A-{RUN}-M" and g["imponibile"] == 1500.0 and g["iva"] == 110.0 and g["totale"] == 1610.0
        assert g["originale"]["numero"] == f"T54A-{RUN}" and g["originale"]["imponibile"] == 1471.25
        assert g["autofattura_numero"] == f"AF1/{Y}"

    def test_02_entry_recreated(self):
        es = entry_for(ST["A"])
        assert len(es) == 1 and es[0]["id"] != ST["E_A"], es
        e = es[0]
        assert balanced(e["righe"])
        assert side(e, "13.03.001") == (0, 220.0)
        assert side(e, "05.02.002") == (330.0, 0)
        d1, d2 = side(e, ST["c1"])[0], side(e, ST["c2"])[0]
        assert round(d1 + d2, 2) == 1500.0 and d1 == 500.0, e["righe"]
        assert side(e, "13.02.001") == (0, 1610.0)

    def test_03_double_register_400(self):
        r = sess().post(f"{API}/passive/{ST['A']}/registrazione", json=body_for(ST["docA"]))
        assert r.status_code == 400

    def test_04_registro_acquisti(self):
        r = sess().get(f"{API}/registro-iva-acquisti", params={"anno": Y}).json()
        row = next(x for x in r["rows"] if x["id"] == ST["A"])
        assert row["numero"] == f"T54A-{RUN}-M" and row["data_registrazione"] == TODAY

    def test_05_autofattura_draft(self):
        r = sess().get(f"{API}/invoices/{ST['AF']}")
        assert r.status_code == 200, r.text
        a = r.json()
        assert a["status"] == "bozza" and a["autofattura"] is True and a["sezionale"] == "AF" and a["tipo_documento"] == "TD16"
        assert a["numero_display"] == f"AF1/{Y}" and a["cedente"]["partita_iva"] == "02345670481"
        assert a["cliente"]["partita_iva"] == PIVA and a["imponibile"] == 1000.0 and a["iva"] == 220.0

    def test_06_autofattura_xml(self):
        r = sess().get(f"{API}/invoices/{ST['AF']}/xml")
        assert r.status_code == 200, r.text
        root = ET.fromstring(r.content)
        f = lambda p: root.find(p)
        assert f(".//CedentePrestatore//IdFiscaleIVA/IdCodice").text == "02345670481"
        assert f(".//CessionarioCommittente//IdFiscaleIVA/IdCodice").text == PIVA
        assert f(".//TipoDocumento").text == "TD16"
        assert f(".//DatiFattureCollegate/IdDocumento").text == f"T54A-{RUN}-M"
        assert f(".//DatiPagamento") is None

    def test_07_send_and_exclusions(self):
        r = sess().post(f"{API}/invoices/{ST['AF']}/send")
        assert r.status_code == 200, r.text
        sess().post(f"{API}/invoices/{ST['AF']}/refresh")
        st = sess().get(f"{API}/invoices/{ST['AF']}").json()["status"]
        print("autofattura status after send/refresh:", st)
        assert st != "bozza"
        assert entry_for(ST["AF"], "vendita") == []
        rv = sess().get(f"{API}/registro-iva-vendite", params={"anno": Y}).json()
        assert all(x.get("id") != ST["AF"] for x in rv["rows"])
        sc = sess().get(f"{API}/scadenzario").json()
        assert ST["AF"] not in json.dumps(sc)

    def test_08_duplicate_autofattura_400(self):
        r = sess().post(f"{API}/passive/{ST['A']}/autofattura", params={"tipo": "TD16"})
        assert r.status_code == 400 and "già" in r.text

    def test_09_autofattura_on_unregistered_400(self):
        r = sess().post(f"{API}/passive/{ST['C']}/autofattura", params={"tipo": "TD17"})
        assert r.status_code == 400

    def test_10_foreign_register_then_create_td17(self):
        d = sess().get(f"{API}/passive/{ST['C']}").json()
        r = sess().post(f"{API}/passive/{ST['C']}/registrazione", json=body_for(d))
        assert r.status_code == 200 and r.json()["autofattura_id"] is None, r.text
        e = entry_for(ST["C"])[0]
        assert side(e, "13.03.001") == (0, 110.0) and balanced(e["righe"])
        r = sess().post(f"{API}/passive/{ST['C']}/autofattura", params={"tipo": "TD17"})
        assert r.status_code == 200, r.text
        a = r.json()
        assert a["numero_display"] == f"AF2/{Y}" and a["tipo_documento"] == "TD17"
        x = sess().get(f"{API}/invoices/{a['id']}/xml")
        assert x.status_code == 200, x.text
        root = ET.fromstring(x.content)
        ced = root.find(".//CedentePrestatore")
        assert ced.find(".//IdFiscaleIVA/IdPaese").text == "DE" and ced.find(".//Sede/CAP").text == "00000"
        assert ced.find(".//Sede/Nazione").text == "DE"
        assert sess().post(f"{API}/passive/{ST['C']}/autofattura", params={"tipo": "TD17"}).status_code == 400


class TestRegVeloce:
    def test_01_foreign_supplier_rc_autofattura(self):
        r = sess().post(f"{API}/parties", json={"tipo": "fornitore", "denominazione": f"TEST_T54 Fr SARL {RUN}", "partita_iva": "FR12345678901", "codice_fiscale": "",
                                                "indirizzo": "Rue X 1", "cap": "75001", "comune": "Paris", "provincia": "", "nazione": "FR"})
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        b = {"tipo": "acquisto", "party_id": pid, "numero": f"RV54-{RUN}", "data_documento": D1, "data_registrazione": TODAY,
             "righe": [{"aliquota": 0, "natura": "N2.1", "totale": 800}], "aliquota_rc": 22, "autofattura": "TD17"}
        r = sess().post(f"{API}/reg-veloce", json=b)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("autofattura_id") and j["autofattura_numero"] == f"AF3/{Y}", j
        doc = sess().get(f"{API}/passive/{j['id']}").json()
        assert doc["reverse_charge"][0]["imposta"] == 176.0
        e = entry_for(j["id"])[0]
        assert side(e, "13.03.001") == (0, 176.0) and balanced(e["righe"])
        a = sess().get(f"{API}/invoices/{j['autofattura_id']}").json()
        assert a["status"] == "bozza" and a["tipo_documento"] == "TD17" and a["cedente"]["nazione"] == "FR"

    def test_02_bad_aliquota_rc_422(self):
        r = sess().post(f"{API}/reg-veloce", json={"tipo": "acquisto", "party_id": "x", "numero": "X", "data_documento": D1, "data_registrazione": TODAY,
                                                   "righe": [{"aliquota": 22, "totale": 100}], "aliquota_rc": 7})
        assert r.status_code in (400, 422)


class TestPrimaNota:
    def test_01_edit_automatic_entry(self):
        e = entry_for(ST["B"])[0]
        righe = [{"conto": x["conto"], "dare": x["dare"], "avere": x["avere"], "party_id": x.get("party_id")} for x in e["righe"]]
        r = sess().put(f"{API}/contabilita/registrazioni/{e['id']}", json={"data": e["data"], "causale": e["causale"], "descrizione": "TEST_T54 modificata", "righe": righe})
        assert r.status_code == 200, r.text
        assert r.json()["modificata"] is True
        g = next(x for x in entry_for(ST["B"]) if x["id"] == e["id"])
        assert g["descrizione"] == "TEST_T54 modificata" and g["modificata"] is True
        ST["EB"], ST["EB_body"] = e["id"], {"data": e["data"], "causale": e["causale"], "descrizione": "x", "righe": righe}

    def test_02_delete_automatic_400(self):
        r = sess().delete(f"{API}/contabilita/registrazioni/{ST['EB']}")
        assert r.status_code == 400

    def test_03_year_change_400(self):
        r = sess().put(f"{API}/contabilita/registrazioni/{ST['EB']}", json={**ST["EB_body"], "data": f"{Y - 1}-12-31"})
        assert r.status_code == 400 and "anno" in r.text

    def test_04_unbalanced_400(self):
        b = json.loads(json.dumps(ST["EB_body"]))
        b["righe"][0]["dare"] = (b["righe"][0]["dare"] or 0) + 1 if b["righe"][0]["dare"] else 0
        if not b["righe"][0]["dare"]:
            b["righe"][0]["avere"] += 1
        r = sess().put(f"{API}/contabilita/registrazioni/{ST['EB']}", json=b)
        assert r.status_code == 400

    def test_05_closed_year_blocked(self):
        mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}}, {{$set:{{coge_chiusi:[{Y}]}}}})')
        try:
            r = sess().put(f"{API}/contabilita/registrazioni/{ST['EB']}", json=ST["EB_body"])
            assert r.status_code == 400 and "chiuso" in r.text
        finally:
            mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}}, {{$set:{{coge_chiusi:[]}}}})')

    def test_06_entry_date_follows_data_registrazione(self):
        """Observation: register B with data_registrazione = document date; prima nota date should match it."""
        d = sess().get(f"{API}/passive/{ST['B']}").json()
        r = sess().post(f"{API}/passive/{ST['B']}/registrazione", json=body_for(d, data_registrazione=D1))
        assert r.status_code == 200, r.text
        e = entry_for(ST["B"])[0]
        print("entry data:", e["data"], "data_registrazione:", D1, "modificata:", e.get("modificata"))
        assert e["data"] == D1, f"prima nota date {e['data']} != data_registrazione {D1}"

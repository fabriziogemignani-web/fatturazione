# Iteration 73: ritenuta d'acconto in registrazione veloce (acquisto/vendita) + registra fattura ricevuta (anteprima/registrazione),
# prima nota 13.03.002 / 05.02.003, pagamento netto via distinta, /ritenute/mese, scadenze fiscali RIT (1040), versamento -> saldo 13.03.002 = 0;
# liquidazione IVA API (mensile/trimestrale/pdf).
# Run: pytest tests/test_iteration73_ritenute_reg_liquidazione.py -v -n 0   (T73_KEEP=1 keeps data; `python tests/<file> clean`)
import json
import os
import random
import sys

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402
from test_iteration13_reverse_charge import rc_xml  # noqa: E402

RUN = os.environ.get("T73_RUN") or str(random.randint(100000, 999999))
TOK, UID = "test_session_t73_admin", "test-user-t73-admin"
PIVA = "87" + RUN + "731"
IBAN = "IT60X0542811101000000123456"
IBAN_F = "IT07X0542811101000000654321"
DD, DP, MESE = "2026-10-05", "2026-10-20", "2026-10"
ST = {}
COLLS = ["invoices", "passive_invoices", "parties", "articles", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "partite_aperte", "f24_versamenti", "distinte_pagamento", "pagamenti_distinte", "counters"]


def sess():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{denominazione:/^TEST_T73/}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.getCollectionNames().forEach(n=>{{ if(n.indexOf("distint")>=0) db[n].deleteMany({{company_id:c.id}}); }});'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def entries(origine, ref):
    q = {"company_id": ST["cid"], "origine": origine, "ref_id": ref}
    return json.loads(mongo(f'print(JSON.stringify(db.coa_entries.find({json.dumps(q)},{{_id:0}}).toArray()))') or "[]")


def side(e, conto):
    rows = [r for r in e["righe"] if r["conto"] == conto]
    return round(sum(r.get("dare") or 0 for r in rows), 2), round(sum(r.get("avere") or 0 for r in rows), 2)


def party(tipo, name, piva, **kw):
    r = sess().post(f"{API}/parties", json={"tipo": tipo, "denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "codice_destinatario": "ABC1234",
                                           "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT", **kw})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def rv(**kw):
    b = {"tipo": "acquisto", "party_id": ST["F"], "numero": f"T73-{random.randint(1000, 99999)}", "data_documento": DD, "data_registrazione": DD,
         "scadenza": "2026-10-31", "righe": [{"aliquota": 22, "totale": 1220}]}
    return sess().post(f"{API}/reg-veloce", json=b | kw)


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t73.admin@example.com", name:"TEST_T73 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": f"TEST_T73 Ritenute {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    sess().put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                            "corrispettivi": True, "contabilita": True})
    s = sess()
    c = s.get(f"{API}/company").json()
    c["banche"] = [{"nome": "TEST Banca Uno", "iban": IBAN, "abi": "05428", "cab": "11101", "sia": "A1B2C", "predefinita": True}]
    assert s.put(f"{API}/company", json=c).status_code == 200
    s.get(f"{API}/contabilita/conti")
    ST["F"] = party("fornitore", "TEST_T73 Professionista Rossi", "01234567890", soggetto_ritenuta=True, ritenuta_aliquota=20, ritenuta_base=100, iban=IBAN_F)
    ST["F50"] = party("fornitore", "TEST_T73 Agente Base50", "09876543217", soggetto_ritenuta=True, ritenuta_aliquota=23, ritenuta_base=50, iban=IBAN_F)
    ST["C"] = party("cliente", "TEST_T73 Cliente Srl", "02345670481")
    yield
    if os.environ.get("T73_KEEP"):
        print("\nKEEP", RUN, ST["cid"])
    else:
        clean()


# Registrazione veloce acquisto/vendita con ritenuta
class TestRegVeloce:
    def test_01_explicit_ritenuta_acquisto(self):
        r = rv(ritenuta_aliquota=20, ritenuta_imponibile=1000)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ritenuta"] == 200 and j["netto"] == 1020 and j["totale"] == 1220
        ST["P1"] = j["id"]
        d = sess().get(f"{API}/passive/{j['id']}").json()
        assert d["ritenuta_importo"] == 200 and d["netto"] == 1020
        assert d["rate"][0]["importo"] == 1020
        assert d.get("ritenuta_tipo") == "RT01"
        e = entries("acquisto", j["id"])
        assert len(e) == 1
        assert side(e[0], "13.03.002") == (0, 200)
        fa = [x for x in e[0]["righe"] if x.get("avere") and x.get("party_id")]
        assert round(sum(x["avere"] for x in fa), 2) == 1020
        assert side(e[0], "05.02.002")[0] == 220
        assert round(sum(x.get("dare") or 0 for x in e[0]["righe"]), 2) == round(sum(x.get("avere") or 0 for x in e[0]["righe"]), 2) == 1220

    def test_02_auto_from_anagrafica(self):
        r = rv(party_id=ST["F50"])  # omitted -> 23% on 50% of 1000
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ritenuta"] == 115 and j["netto"] == 1105
        ST["P2"] = j["id"]
        assert side(entries("acquisto", j["id"])[0], "13.03.002") == (0, 115)

    def test_03_zero_means_none(self):
        r = rv(ritenuta_aliquota=0)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ritenuta"] == 0 and j["netto"] == 1220
        d = sess().get(f"{API}/passive/{j['id']}").json()
        assert not d.get("ritenuta_importo")
        assert side(entries("acquisto", j["id"])[0], "13.03.002") == (0, 0)
        ST["P3"] = j["id"]

    def test_04_ritenuta_ge_totale_422(self):
        r = rv(ritenuta_aliquota=100, ritenuta_imponibile=1300)
        assert r.status_code == 422, r.text

    def test_05_vendita_ritenuta_subita(self):
        r = rv(tipo="vendita", party_id=ST["C"], ritenuta_aliquota=20, ritenuta_imponibile=1000)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ritenuta"] == 200 and j["netto"] == 1020
        e = entries("vendita", j["id"])
        assert len(e) == 1
        assert side(e[0], "05.02.003") == (200, 0)
        cl = [x for x in e[0]["righe"] if x.get("party_id") and x.get("dare")]
        assert round(sum(x["dare"] for x in cl), 2) == 1020


# Registra fattura ricevuta (XML) con ritenuta
class TestRegistraPassiva:
    def _body(self, d, **kw):
        b = {"data_registrazione": DD, "numero": d["numero"], "data": d["data"], "aliquota_rc": 22, "detraibilita_iva": 100,
             "riepilogo": [{"aliquota": r["aliquota"], "natura": r.get("natura"), "imponibile": r["imponibile"], "imposta": r["imposta"], "conto": ""} for r in d["riepilogo"]]}
        return b | kw

    def test_01_upload(self):
        x = rc_xml(f"T73X-{RUN}", data=DD, rc=()).decode().replace("<IdCodice>01234567890</IdCodice>", f"<IdCodice>{PIVA}</IdCodice>")
        r = sess().post(f"{API}/passive/upload", files=[("files", ("x.xml", x.encode(), "application/octet-stream"))])
        assert r.status_code == 200, r.text
        ST["X"] = r.json()[0]["documenti"][0]["id"]
        d = sess().get(f"{API}/passive/{ST['X']}").json()
        assert d["stato_reg"] == "da_registrare"
        ST["Xd"] = d

    def test_02_anteprima_ritenuta(self):
        d = ST["Xd"]
        imp = d["imponibile"]
        r = sess().post(f"{API}/passive/{ST['X']}/registrazione/anteprima", json=self._body(d, ritenuta_aliquota=20, ritenuta_imponibile=imp))
        assert r.status_code == 200, r.text
        j = r.json()
        rit = round(imp * 0.2, 2)
        assert j["ritenuta_importo"] == rit
        assert j["netto"] == round(j["totale"] - rit, 2)
        assert any(x["conto"] == "13.03.002" and x.get("avere") == rit for x in j["righe"]), j["righe"]
        assert sess().get(f"{API}/passive/{ST['X']}").json()["stato_reg"] == "da_registrare"

    def test_03_ritenuta_ge_totale_422(self):
        d = ST["Xd"]
        r = sess().post(f"{API}/passive/{ST['X']}/registrazione/anteprima", json=self._body(d, ritenuta_aliquota=100, ritenuta_imponibile=d["totale"] + 1))
        assert r.status_code == 422, r.text

    def test_04_registra(self):
        d = ST["Xd"]
        r = sess().post(f"{API}/passive/{ST['X']}/registrazione", json=self._body(d, ritenuta_aliquota=20, ritenuta_imponibile=d["imponibile"]))
        assert r.status_code == 200, r.text
        g = sess().get(f"{API}/passive/{ST['X']}").json()
        rit = round(d["imponibile"] * 0.2, 2)
        assert g["stato_reg"] == "registrata" and g["ritenuta_importo"] == rit
        assert g["netto"] == round(g["totale"] - rit, 2)
        assert round(sum(x["importo"] for x in g["rate"]), 2) == g["netto"]
        e = entries("acquisto", ST["X"])
        assert len(e) == 1 and side(e[0], "13.03.002") == (0, rit)
        ST["Xg"] = g


# Chiusura: pagamento netto -> ritenute mese -> scadenza F24 -> versamento -> saldo 13.03.002 = 0
class TestClosing:
    def test_01_distinta_pay_netto(self):
        sc = sess().get(f"{API}/pagamenti-fornitori/scadenze").json()
        keys = {x["invoice_id"]: x for x in sc}
        assert keys[ST["P1"]]["residuo"] == 1020
        voci = [{"key": keys[i]["key"], "importo": keys[i]["residuo"], "iban": IBAN_F} for i in (ST["P1"], ST["P2"], ST["X"]) if i in keys]
        assert len(voci) == 3
        r = sess().post(f"{API}/pagamenti-fornitori/distinte", json={"banca_iban": IBAN, "data": DP, "voci": voci})
        assert r.status_code == 200, r.text
        ST["dist"] = r.json()

    def test_02_ritenute_mese(self):
        r = sess().get(f"{API}/ritenute/mese", params={"mese": MESE})
        assert r.status_code == 200, r.text
        j = r.json()
        exp = round(200 + 115 + ST["Xg"]["ritenuta_importo"], 2)
        assert j["totale"] == exp, j
        assert not j["provvisorio"]
        ST["rit_tot"] = exp

    def test_03_scadenza_fiscale(self):
        j = sess().get(f"{API}/scadenze-fiscali").json()
        x = next((x for x in j["scadenze"] if x["key"] == f"RIT-{MESE}"), None)
        assert x, [s["key"] for s in j["scadenze"]]
        assert x["codice"] == "1040" and x["importo"] == ST["rit_tot"] and x["scadenza"] == "2026-11-16"

    def test_04_saldo_before(self):
        m = sess().get(f"{API}/contabilita/mastrino", params={"conto": "13.03.002"}).json()
        assert m["saldo_finale"] == -ST["rit_tot"], m["saldo_finale"]

    def test_05_versato_closes_account(self):
        r = sess().post(f"{API}/scadenze-fiscali/versato", json={"key": f"RIT-{MESE}", "data": "2026-11-13"})
        assert r.status_code == 200, r.text
        e = entries("ritenute", f"RIT-{MESE}")
        assert len(e) == 1 and side(e[0], "13.03.002") == (ST["rit_tot"], 0)
        m = sess().get(f"{API}/contabilita/mastrino", params={"conto": "13.03.002"}).json()
        assert m["saldo_finale"] == 0, m

    def test_06_bilancio_ok(self):
        r = sess().get(f"{API}/contabilita/bilancio", params={"anno": 2026})
        assert r.status_code == 200, r.text
        assert "13.03.002" not in json.dumps([x for x in json.dumps(r.json()).split("},") if "13.03.002" in x and '"saldo": -' in x])


# Liquidazione IVA API
class TestLiquidazione:
    @pytest.mark.parametrize("per", ["mensile", "trimestrale"])
    def test_01_liq(self, per):
        r = sess().get(f"{API}/liquidazione-iva", params={"anno": 2026, "periodicita": per})
        assert r.status_code == 200, r.text
        j = r.json()
        assert len(j["periodi"]) == (12 if per == "mensile" else 4)

    @pytest.mark.parametrize("q", [{}, {"periodo": 10}])
    def test_02_pdf(self, q):
        r = sess().get(f"{API}/liquidazione-iva/pdf", params={"anno": 2026, "periodicita": "mensile", **q})
        assert r.status_code == 200, r.text[:200]
        assert r.content[:4] == b"%PDF"


if __name__ == "__main__" and sys.argv[-1] == "clean":
    clean()

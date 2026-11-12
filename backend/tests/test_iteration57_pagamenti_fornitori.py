# Iteration 57: Pagamenti fornitori - scadenze da/a, distinta (validazioni, passive_payments, prima nota PG, conto banca auto),
# pagamento parziale, flusso CBI XML (CUC), annullamento, IBAN fornitore, isolamento aziende, modulo/menu off.
# Run: pytest tests/test_iteration57_pagamenti_fornitori.py -v -n 0   |  UI fixtures: python tests/test_iteration57_pagamenti_fornitori.py setup|clean
import json
import os
import random
import sys
import xml.etree.ElementTree as ET
from datetime import date, timedelta

import pytest
import requests

from test_iteration7_pa_scartate_registro import API, mongo

RUN = os.environ.get("T57_RUN") or str(random.randint(100000, 999999))  # set T57_RUN to reuse setup|clean across CLI calls
TOK, UID = f"test_session_t57_admin_{RUN}", f"test-user-t57-admin-{RUN}"
TOK_OP, UID_OP = f"test_session_t57_op_{RUN}", f"test-user-t57-op-{RUN}"
PIVA, PIVA2 = "88" + RUN + "571", "88" + RUN + "572"
SUP_B = "08" + RUN + "573"
IBAN1, IBAN2 = "IT60X0542811101000000123456", "IT40S0542811101000000123456"
IBAN_A = "IT02A0306902887100000001234"
IBAN_B = "IT07X0542811101000000654321"
T = date.today()
d = lambda n: (T + timedelta(days=n)).isoformat()  # noqa: E731
ST = {}
COLLS = ["invoices", "passive_invoices", "parties", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "partite_aperte", "pag_distinte"]
NSX = {"c": "urn:CBI:xsd:CBIPaymentRequest.00.04.00"}


def sess(tok=TOK, cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    if cid or ST.get("cid"):
        s.headers["X-Company-Id"] = cid or ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{partita_iva:{{$in:["{PIVA}","{PIVA2}"]}}}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:["{UID}","{UID_OP}"]}}}}); db.user_sessions.deleteMany({{user_id:{{$in:["{UID}","{UID_OP}"]}}}});')


def xml(numero, piva_sup="02345670481", nome="TEST_T57 Fornitore A SpA", iban=True):
    x = open(__file__.replace("test_iteration57_pagamenti_fornitori.py", "fixtures/sample_fattura.xml")).read()
    x = x.replace("<IdCodice>01234567890</IdCodice>", f"<IdCodice>{PIVA}</IdCodice>").replace("02345670481", piva_sup)
    x = x.replace("<Numero>5674/2026</Numero>", f"<Numero>{numero}</Numero>").replace("<Data>2026-10-30</Data>", f"<Data>{d(-10)}</Data>")
    x = x.replace("DEMO Energia Toscana SpA", nome).replace("<DataScadenzaPagamento>2026-11-29</DataScadenzaPagamento>", f"<DataScadenzaPagamento>{d(20)}</DataScadenzaPagamento>")
    if not iban:
        x = x.replace(f"<IBAN>{IBAN_A}</IBAN>", "")
    return x


def up(name, x):
    r = sess().post(f"{API}/passive/upload", files=[("files", (name, x, "text/xml"))])
    assert r.status_code == 200, r.text
    assert r.json()[0]["ok"], r.text
    return r.json()[0]["documenti"][0]


def company(name, piva):
    r = sess(cid="").post(f"{API}/companies", json={"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01",
                                                   "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    sess(cid=cid).put(f"{API}/companies/{cid}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                             "corrispettivi": True, "contabilita": True})
    return cid


def put_banche(**cuc):
    s = sess()
    c = s.get(f"{API}/company").json()
    cur = {b["iban"]: b for b in c.get("banche") or []}
    c["banche"] = [{**cur.get(IBAN1, {}), "nome": "TEST Banca Uno", "iban": IBAN1, "predefinita": True, "cuc": cuc.get("uno", cur.get(IBAN1, {}).get("cuc", ""))},
                   {**cur.get(IBAN2, {}), "nome": "TEST Banca Due", "iban": IBAN2, "predefinita": False, "cuc": cuc.get("due", cur.get(IBAN2, {}).get("cuc", ""))}]
    return s.put(f"{API}/company", json=c)


def setup_data():
    clean()
    for uid, tok, role in ((UID, TOK, "admin"), (UID_OP, TOK_OP, "operatore")):
        mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.t57.{uid}@example.com", name:"TEST_T57 {role}", picture:"", role:"{role}", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
              f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    ST["cid"] = company(f"TEST_T57 Pagamenti {RUN} Srl", PIVA)
    mongo(f'db.users.updateOne({{user_id:"{UID_OP}"}}, {{$set:{{company_ids:["{ST["cid"]}"]}}}})')
    ST["cid2"] = company(f"TEST_T57 Altra {RUN} Srl", PIVA2)
    assert put_banche().status_code == 200
    a1 = up("a1.xml", xml("T57-A1"))
    ST["A1"], ST["forn_a"] = a1["id"], a1["nuovo_fornitore_id"]
    ST["A2"] = up("a2.xml", xml("T57-A2"))["id"]
    b1 = up("b1.xml", xml("T57-B1", SUP_B, "TEST_T57 Fornitore B Srl", iban=False))
    ST["B1"], ST["forn_b"] = b1["id"], b1["nuovo_fornitore_id"]
    r = sess().put(f"{API}/scadenze/passive/{ST['A1']}", json={"rate": [{"scadenza": d(5), "importo": 300}, {"scadenza": d(40), "importo": 274.93}]})
    assert r.status_code == 200, r.text
    ST["PA"] = f"t57pa-{RUN}"
    mongo(f'db.partite_aperte.insertOne({{id:"{ST["PA"]}", company_id:"{ST["cid"]}", tipo:"fornitore", party_id:"{ST["forn_a"]}", numero:0, numero_display:"TEST_T57 PA-1",'
          f'data:"{d(-30)}", scadenza:"{d(10)}", totale:100, netto:100, rate:[{{scadenza:"{d(10)}", importo:100}}], tipo_documento:"TD01", status:"storico",'
          f'stato_reg:"registrata", fornitore:{{denominazione:"TEST_T57 Fornitore A SpA"}}, created_at:new Date().toISOString()}})')
    return ST


@pytest.fixture(scope="module", autouse=True)
def setup():
    setup_data()
    yield
    clean()


def scad(**params):
    r = sess().get(f"{API}/pagamenti-fornitori/scadenze", params=params)
    assert r.status_code == 200, r.text
    return {x["key"]: x for x in r.json()}


def entry(ref):
    return json.loads(mongo(f'print(JSON.stringify(db.coa_entries.find({{company_id:"{ST["cid"]}", origine:"pagamenti", ref_id:"{ref}"}},{{_id:0}}).toArray()))') or "[]")


def getp(pid):
    return next(x for x in sess().get(f"{API}/parties").json() if x["id"] == pid)


def post_dist(voci, iban=IBAN1, data=None, tok=TOK):
    return sess(tok).post(f"{API}/pagamenti-fornitori/distinte", json={"banca_iban": iban, "data": data or T.isoformat(), "voci": [{"key": k, "importo": v} for k, v in voci]})


# Listing scadenze
class TestScadenze:
    def test_01_list(self):
        s = scad()
        for k in (f"{ST['A1']}:1", f"{ST['A1']}:2", f"{ST['A2']}:1", f"{ST['B1']}:1", f"{ST['PA']}:1"):
            assert k in s, (k, list(s))
        assert s[f"{ST['A1']}:1"]["residuo"] == 300 and s[f"{ST['A1']}:2"]["residuo"] == 274.93
        assert s[f"{ST['A1']}:1"]["iban"] == IBAN_A and s[f"{ST['PA']}:1"]["iban"] == IBAN_A
        assert s[f"{ST['B1']}:1"]["iban"] == ""
        assert s[f"{ST['A1']}:1"]["fornitore"] == "TEST_T57 Fornitore A SpA" and s[f"{ST['A1']}:2"]["rate_totali"] == 2

    def test_02_filter(self):
        s = scad(dal=d(30), al=d(60))
        assert list(s) == [f"{ST['A1']}:2"], list(s)
        s = scad(al=d(6))
        assert list(s) == [f"{ST['A1']}:1"], list(s)


# Supplier IBAN
class TestPartyIban:
    def test_01_invalid(self):
        p = getp(ST["forn_b"])
        r = sess().put(f"{API}/parties/{ST['forn_b']}", json={**p, "iban": "IT00X123"})
        assert r.status_code == 422, r.text


# Distinta validations
class TestValidazioni:
    def test_01_operatore_forbidden(self):
        r = post_dist([(f"{ST['A2']}:1", 10)], tok=TOK_OP)
        assert r.status_code == 403, r.text

    def test_02_bad_bank(self):
        r = post_dist([(f"{ST['A2']}:1", 10)], iban="IT60X0542811101000000999999")
        assert r.status_code == 400 and "banca" in r.text.lower(), r.text

    def test_03_over_residuo(self):
        r = post_dist([(f"{ST['A2']}:1", 600)])
        assert r.status_code == 400 and "residuo" in r.text, r.text

    def test_04_rata_order(self):
        r = post_dist([(f"{ST['A1']}:2", 10)])
        assert r.status_code == 400 and "rata 1" in r.text, r.text
        r = post_dist([(f"{ST['A1']}:1", 100), (f"{ST['A1']}:2", 10)])
        assert r.status_code == 400 and "rata 1" in r.text, r.text

    def test_05_data_before_invoice(self):
        r = post_dist([(f"{ST['A2']}:1", 10)], data=d(-20))
        assert r.status_code == 400 and "precedere" in r.text, r.text

    def test_06_missing_iban(self):
        r = post_dist([(f"{ST['B1']}:1", 10)])
        assert r.status_code == 400 and "IBAN" in r.text, r.text

    def test_07_unknown_key(self):
        assert post_dist([("nope:1", 10)]).status_code == 400
        assert sess().post(f"{API}/pagamenti-fornitori/distinte", json={"banca_iban": IBAN1, "data": "2026-02-30", "voci": [{"key": "x", "importo": 1}]}).status_code == 422
        assert post_dist([(f"{ST['A2']}:1", 0)]).status_code == 422
        assert mongo(f'print(db.passive_payments.countDocuments({{company_id:"{ST["cid"]}"}}))') == "0"


# Create distinta on default bank
class TestDistinta:
    def test_01_create(self):
        r = post_dist([(f"{ST['A1']}:1", 300), (f"{ST['A1']}:2", 100), (f"{ST['A2']}:1", 574.93), (f"{ST['PA']}:1", 100)])
        assert r.status_code == 200, r.text
        dd = r.json()
        ST["D1"] = dd["id"]
        assert dd["totale"] == 1074.93 and dd["n_partite"] == 4 and dd["n_bonifici"] == 1
        assert dd["conto_banca"] == "06.01.001" and dd["coge_entry_id"] and dd["coge_rif"].startswith("prima nota n.")
        assert dd["disposizioni"][0]["iban"] == IBAN_A and dd["disposizioni"][0]["importo"] == 1074.93
        assert "T57-A1" in dd["disposizioni"][0]["causale"]
        g = sess().get(f"{API}/pagamenti-fornitori/distinte/{ST['D1']}")
        assert g.status_code == 200 and g.json()["totale"] == 1074.93

    def test_02_payments(self):
        pays = json.loads(mongo(f'print(JSON.stringify(db.passive_payments.find({{distinta_pag_id:"{ST["D1"]}"}},{{_id:0}}).toArray()))'))
        assert len(pays) == 4
        assert all(p["metodo"] == "bonifico" and p["coge_entry_id"] and p["data"] == T.isoformat() for p in pays)
        assert round(sum(p["importo"] for p in pays), 2) == 1074.93

    def test_03_prima_nota(self):
        e = entry(ST["D1"])
        assert len(e) == 1, e
        e = e[0]
        ST["E1"] = e["id"]
        assert e["causale"] == "PG" and e["totale"] == 1074.93
        dare = [x for x in e["righe"] if x.get("dare")]
        avere = [x for x in e["righe"] if x.get("avere")]
        assert len(dare) == 1 and dare[0]["conto"] == "13.02.001" and dare[0]["party_id"] == ST["forn_a"] and dare[0]["dare"] == 1074.93
        assert len(avere) == 1 and avere[0]["conto"] == "06.01.001" and avere[0]["avere"] == 1074.93

    def test_04_scadenzario_updated(self):
        s = scad()
        assert f"{ST['A1']}:1" not in s and f"{ST['A2']}:1" not in s and f"{ST['PA']}:1" not in s
        assert s[f"{ST['A1']}:2"]["residuo"] == 174.93
        rate = sess().get(f"{API}/scadenzario-passivo", params={"party_id": ST["forn_a"]}).json()["rate"]
        by = {(x["invoice_id"], x.get("n")): x for x in rate}
        a2 = [x for x in rate if x["invoice_id"] == ST["A2"]]
        assert a2 and all(x["residuo"] == 0 for x in a2), a2
        a1 = sorted([x for x in rate if x["invoice_id"] == ST["A1"]], key=lambda x: x["scadenza"])
        assert a1[0]["residuo"] == 0 and a1[1]["residuo"] == 174.93, a1
        assert by is not None

    def test_05_list_distinte(self):
        r = sess().get(f"{API}/pagamenti-fornitori/distinte")
        assert r.status_code == 200 and [x["id"] for x in r.json()] == [ST["D1"]]

    def test_06_partial_not_over(self):
        r = post_dist([(f"{ST['A1']}:2", 200)])
        assert r.status_code == 400 and "residuo" in r.text, r.text

    def test_07_payment_delete_blocked(self):
        pid = mongo(f'print(db.passive_payments.findOne({{distinta_pag_id:"{ST["D1"]}"}}).id)')
        r = sess().delete(f"{API}/passive-pagamenti/{pid}")
        assert r.status_code == 400, r.text


# CBI flow
class TestCBI:
    def test_01_no_cuc(self):
        r = sess().get(f"{API}/pagamenti-fornitori/distinte/{ST['D1']}/cbi")
        assert r.status_code == 400 and "CUC" in r.text and "TEST Banca Uno" in r.text, r.text

    def test_02_invalid_cuc(self):
        assert put_banche(uno="ABC").status_code == 422

    def test_03_xml(self):
        r = put_banche(uno="ab12cd34")
        assert r.status_code == 200, r.text
        assert next(b for b in sess().get(f"{API}/company").json()["banche"] if b["iban"] == IBAN1)["cuc"] == "AB12CD34"
        r = sess().get(f"{API}/pagamenti-fornitori/distinte/{ST['D1']}/cbi")
        assert r.status_code == 200, r.text
        assert "xml" in r.headers["content-type"] and "BONIFICI_" in r.headers.get("content-disposition", "")
        root = ET.fromstring(r.content)
        assert root.tag == "{urn:CBI:xsd:CBIPaymentRequest.00.04.00}CBIPaymentRequest"
        assert root.find("c:GrpHdr/c:NbOfTxs", NSX).text == "1" and root.find("c:GrpHdr/c:CtrlSum", NSX).text == "1074.93"
        assert root.find("c:GrpHdr/c:InitgPty/c:Id/c:OrgId/c:Othr/c:Id", NSX).text == "AB12CD34"
        assert root.find("c:PmtInf/c:DbtrAcct/c:Id/c:IBAN", NSX).text == IBAN1
        tx = root.findall("c:PmtInf/c:CdtTrfTxInf", NSX)
        assert len(tx) == 1 and tx[0].find("c:CdtrAcct/c:Id/c:IBAN", NSX).text == IBAN_A
        assert tx[0].find("c:Amt/c:InstdAmt", NSX).text == "1074.93"


# Second bank (non default) -> auto account; supplier IBAN added
class TestBanca2:
    def test_01_set_iban_b(self):
        p = getp(ST["forn_b"])
        r = sess().put(f"{API}/parties/{ST['forn_b']}", json={**p, "iban": "it07 x054 2811 1010 0000 0654 321"})
        assert r.status_code == 200, r.text
        assert getp(ST["forn_b"])["iban"] == IBAN_B
        assert scad()[f"{ST['B1']}:1"]["iban"] == IBAN_B

    def test_02_create_bank2(self):
        r = post_dist([(f"{ST['B1']}:1", 74.93), (f"{ST['A1']}:2", 174.93)], iban=IBAN2)
        assert r.status_code == 200, r.text
        dd = r.json()
        ST["D2"] = dd["id"]
        assert dd["n_bonifici"] == 2 and dd["numero"] == 2
        assert dd["conto_banca"].startswith("06.01.1") and dd["conto_banca"] != "06.01.001", dd["conto_banca"]
        ST["conto2"] = dd["conto_banca"]
        b2 = next(b for b in sess().get(f"{API}/company").json()["banche"] if b["iban"] == IBAN2)
        assert b2.get("conto_coge") == dd["conto_banca"]
        e = entry(ST["D2"])[0]
        ST["E2"] = e["id"]
        assert {(x["conto"], x.get("party_id")) for x in e["righe"] if x.get("dare")} == {("13.02.001", ST["forn_a"]), ("13.02.001", ST["forn_b"])}
        assert [x["conto"] for x in e["righe"] if x.get("avere")] == [dd["conto_banca"]]
        s = scad()
        assert f"{ST['A1']}:2" not in s and s[f"{ST['B1']}:1"]["residuo"] == 500

    def test_03_reuse_account(self):
        r = post_dist([(f"{ST['B1']}:1", 10)], iban=IBAN2)
        assert r.status_code == 200, r.text
        assert r.json()["conto_banca"] == ST["conto2"]
        ST["D3"] = r.json()["id"]
        cnt = mongo(f'print(db.coa_accounts.countDocuments({{company_id:"{ST["cid"]}", codice:{{$regex:"^06\\\\.01\\\\.1"}}}}))')
        assert cnt == "1", cnt

    def test_04_concurrent_serialized(self):
        # Fix 6: two parallel POSTs paying the full residuo -> only one succeeds
        from concurrent.futures import ThreadPoolExecutor
        res = scad()[f"{ST['B1']}:1"]["residuo"]
        with ThreadPoolExecutor(2) as ex:
            rs = list(ex.map(lambda _: post_dist([(f"{ST['B1']}:1", res)], iban=IBAN2), range(2)))
        codes = sorted(r.status_code for r in rs)
        ok = [r for r in rs if r.status_code == 200]
        if ok:
            ST["D4"] = ok[0].json()["id"]
        assert codes == [200, 400], [(r.status_code, r.text[:200]) for r in rs]
        assert mongo(f'print(db.passive_payments.countDocuments({{company_id:"{ST["cid"]}", invoice_id:"{ST["B1"]}"}}))') == "3"


# Prima nota edit/delete rules
class TestPrimaNota:
    def test_01_delete_blocked(self):
        r = sess().delete(f"{API}/contabilita/registrazioni/{ST['E1']}")
        assert r.status_code == 400, r.text

    def _body(self, e, suffix=" TEST_mod"):
        return {"data": e["data"], "causale": e["causale"], "descrizione": e["descrizione"] + suffix,
                "righe": [{k: x.get(k) for k in ("conto", "dare", "avere", "party_id") if x.get(k) not in (None, "")} for x in e["righe"]]}

    def test_02_edit_without_saldaconto_rejected(self):
        # Fix 2: PUT without saldaconto on a distinta entry -> 400, payments kept
        e = entry(ST["D1"])[0]
        r = sess().put(f"{API}/contabilita/registrazioni/{ST['E1']}", json=self._body(e))
        assert r.status_code == 400 and "distinta" in r.text.lower(), r.text
        assert not entry(ST["D1"])[0]["descrizione"].endswith("TEST_mod")
        assert mongo(f'print(db.passive_payments.countDocuments({{company_id:"{ST["cid"]}", distinta_pag_id:"{ST["D1"]}"}}))') == "4"

    def test_03_links_aggregated(self):
        # Fix 4: one row per invoice with summed importo (A1 rata1 300 + rata2 100)
        links = sess().get(f"{API}/contabilita/saldaconto/registrazione/{ST['E1']}").json()
        by = {x["invoice_id"]: x for x in links}
        assert len(links) == 3 and set(by) == {ST["A1"], ST["A2"], ST["PA"]}, links
        assert by[ST["A1"]]["importo"] == 400 and by[ST["A2"]]["importo"] == 574.93 and by[ST["PA"]]["importo"] == 100
        assert all(x["passivo"] is True for x in links)

    def test_04_edit_with_partita_aperta(self):
        # Fix 1: entry including a partita_aperta fornitore can be saved with saldaconto
        links = sess().get(f"{API}/contabilita/saldaconto/registrazione/{ST['E1']}").json()
        body = {**self._body(entry(ST["D1"])[0]), "saldaconto": [{"invoice_id": x["invoice_id"], "importo": x["importo"], "passivo": True} for x in links]}
        r = sess().put(f"{API}/contabilita/registrazioni/{ST['E1']}", json=body)
        assert r.status_code == 200, r.text
        assert entry(ST["D1"])[0]["descrizione"].endswith("TEST_mod")
        pays = json.loads(mongo(f'print(JSON.stringify(db.passive_payments.find({{company_id:"{ST["cid"]}", coge_entry_id:"{ST["E1"]}"}},{{_id:0}}).toArray()))'))
        assert len(pays) == 3 and all(p.get("distinta_pag_id") == ST["D1"] for p in pays), pays
        assert round(sum(p["importo"] for p in pays), 2) == 1074.93
        s = scad()
        assert f"{ST['PA']}:1" not in s and f"{ST['A2']}:1" not in s and f"{ST['A1']}:1" not in s

    def test_05_edit_amount_recalculates_distinta(self):
        # Fix 3: change A2 from 574.93 to 500 -> distinta snapshot + CBI updated
        e = entry(ST["D1"])[0]
        body = self._body(e, "")
        for x in body["righe"]:
            if x.get("dare"):
                x["dare"] = 1000
            if x.get("avere"):
                x["avere"] = 1000
        body["saldaconto"] = [{"invoice_id": ST["A1"], "importo": 400, "passivo": True}, {"invoice_id": ST["A2"], "importo": 500, "passivo": True},
                              {"invoice_id": ST["PA"], "importo": 100, "passivo": True}]
        r = sess().put(f"{API}/contabilita/registrazioni/{ST['E1']}", json=body)
        assert r.status_code == 200, r.text
        dd = sess().get(f"{API}/pagamenti-fornitori/distinte/{ST['D1']}").json()
        assert dd["totale"] == 1000 and dd["n_partite"] == 3 and dd["n_bonifici"] == 1 and dd.get("modificata_prima_nota") is True, dd
        assert dd["disposizioni"][0]["importo"] == 1000 and dd["disposizioni"][0]["iban"] == IBAN_A, dd["disposizioni"]
        assert {x["invoice_id"]: x["importo"] for x in dd["partite"]} == {ST["A1"]: 400, ST["A2"]: 500, ST["PA"]: 100}
        assert mongo(f'print(db.passive_payments.countDocuments({{distinta_pag_id:"{ST["D1"]}"}}))') == "3"
        assert scad()[f"{ST['A2']}:1"]["residuo"] == 74.93
        x = sess().get(f"{API}/pagamenti-fornitori/distinte/{ST['D1']}/cbi")
        assert x.status_code == 200, x.text
        root = ET.fromstring(x.content)
        assert root.find("c:GrpHdr/c:CtrlSum", NSX).text == "1000.00"
        assert root.find("c:PmtInf/c:CdtTrfTxInf/c:Amt/c:InstdAmt", NSX).text == "1000.00"

    def test_06_edit_with_saldaconto_links_e2(self):
        links = sess().get(f"{API}/contabilita/saldaconto/registrazione/{ST['E2']}").json()
        assert len(links) == 2, links
        body = {**self._body(entry(ST["D2"])[0]), "saldaconto": [{"invoice_id": x["invoice_id"], "importo": x["importo"], "passivo": True} for x in links]}
        r = sess().put(f"{API}/contabilita/registrazioni/{ST['E2']}", json=body)
        assert r.status_code == 200, r.text
        assert len(sess().get(f"{API}/contabilita/saldaconto/registrazione/{ST['E2']}").json()) == 2
        assert mongo(f'print(db.passive_payments.countDocuments({{distinta_pag_id:"{ST["D2"]}"}}))') == "2"


# Company isolation, module/menu off
class TestIsolamento:
    def test_01_other_company(self):
        s2 = sess(cid=ST["cid2"])
        assert s2.get(f"{API}/pagamenti-fornitori/distinte").json() == []
        assert s2.get(f"{API}/pagamenti-fornitori/distinte/{ST['D1']}").status_code == 404
        assert s2.get(f"{API}/pagamenti-fornitori/distinte/{ST['D1']}/cbi").status_code == 404
        assert s2.delete(f"{API}/pagamenti-fornitori/distinte/{ST['D1']}").status_code == 404
        assert s2.get(f"{API}/pagamenti-fornitori/scadenze").json() == []

    def test_02_module_off(self):
        u = f"{API}/companies/{ST['cid']}/moduli"
        sess().put(u, json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": False, "corrispettivi": True, "contabilita": True})
        try:
            assert sess().get(f"{API}/pagamenti-fornitori/scadenze").status_code == 403
        finally:
            sess().put(u, json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True, "corrispettivi": True, "contabilita": True})
        assert sess().get(f"{API}/pagamenti-fornitori/scadenze").status_code == 200

    def test_03_menu_off(self):
        u = f"{API}/companies/{ST['cid']}/menu"
        assert sess().put(u, json={"off": ["pagamenti-fornitori"]}).status_code == 200
        try:
            r = sess().get(f"{API}/pagamenti-fornitori/distinte")
            assert r.status_code == 403, r.text
        finally:
            sess().put(u, json={"off": []})
        assert sess().get(f"{API}/pagamenti-fornitori/distinte").status_code == 200


# Annul distinta
class TestAnnulla:
    def test_01_operatore_forbidden(self):
        assert sess(TOK_OP).delete(f"{API}/pagamenti-fornitori/distinte/{ST['D1']}").status_code == 403

    def test_02_annulla(self):
        r = sess().delete(f"{API}/pagamenti-fornitori/distinte/{ST['D1']}")
        assert r.status_code == 200, r.text
        assert sess().get(f"{API}/pagamenti-fornitori/distinte/{ST['D1']}").status_code == 404
        assert entry(ST["D1"]) == []
        assert mongo(f'print(db.passive_payments.countDocuments({{distinta_pag_id:"{ST["D1"]}"}}))') == "0"
        s = scad()
        assert s[f"{ST['A2']}:1"]["residuo"] == 574.93 and s[f"{ST['PA']}:1"]["residuo"] == 100
        # payments are per invoice (FIFO over rate): D2 still pays 174.93 on A1 -> rata1 residuo 125.07, rata2 274.93
        assert s[f"{ST['A1']}:1"]["residuo"] == 125.07 and s[f"{ST['A1']}:2"]["residuo"] == 274.93, (s[f"{ST['A1']}:1"], s.get(f"{ST['A1']}:2"))

    def test_03_annulla_rest(self):
        for k in [k for k in ("D2", "D3", "D4") if k in ST]:
            assert sess().delete(f"{API}/pagamenti-fornitori/distinte/{ST[k]}").status_code == 200
        assert scad()[f"{ST['A1']}:2"]["residuo"] == 274.93
        assert mongo(f'print(db.coa_entries.countDocuments({{company_id:"{ST["cid"]}", origine:"pagamenti"}}))') == "0"


if __name__ == "__main__":
    if sys.argv[1] == "setup":
        print(json.dumps(setup_data()))
    else:
        clean()

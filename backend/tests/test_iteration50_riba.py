# Iteration 50: Ri.Ba. (distinte, CBI flow, SBF account, maturazione, insoluti, esiti CBI), modifica scadenze,
# auto-created supplier from passive XML (da_verificare), party appoggio ABI/CAB, bank SIA.
# Run: pytest tests/test_iteration50_riba.py -v -n 0
import json
import random
from datetime import date, timedelta

import pytest
import requests

from test_iteration7_pa_scartate_registro import API, mongo

RUN = str(random.randint(100000, 999999))
TOK, UID = f"test_session_t50_admin_{RUN}", f"test-user-t50-admin-{RUN}"
PIVA = "86" + RUN + "501"
SUP_PIVA = "07" + RUN + "502"
IBAN = "IT60X0542811101000000123456"
T = date.today()
d = lambda n: (T + timedelta(days=n)).isoformat()  # noqa: E731
ST = {}
COLLS = ["invoices", "passive_invoices", "parties", "articles", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "riba_distinte", "riba_effetti", "partite_aperte"]


def sess():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{partita_iva:"{PIVA}"}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def entries(origine, ref=None):
    q = {"company_id": ST["cid"], "origine": origine} | ({"ref_id": ref} if ref else {})
    return json.loads(mongo(f'print(JSON.stringify(db.coa_entries.find({json.dumps(q)},{{_id:0}}).toArray()))') or "[]")


def client(name, piva, **kw):
    r = sess().post(f"{API}/parties", json={"tipo": "cliente", "denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "codice_destinatario": "ABC1234",
                                           "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT", **kw})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def inv(pid, data, rate, mp="MP12", price=100):
    s = sess()
    r = s.post(f"{API}/invoices", json={"tipo_documento": "TD01", "data": data, "party_id": pid, "modalita_pagamento": mp, "scadenza": rate[-1][0],
                                        "rate": [{"scadenza": a, "importo": b} for a, b in rate],
                                        "lines": [{"descrizione": "TEST_riga", "quantita": 1, "prezzo_unitario": price, "aliquota": 22}]})
    assert r.status_code == 200, r.text
    iid = r.json()["id"]
    assert s.post(f"{API}/invoices/{iid}/send").status_code == 200
    assert s.post(f"{API}/invoices/{iid}/refresh").status_code == 200
    return iid


def put_company(sia):
    s = sess()
    c = s.get(f"{API}/company").json()
    c["banche"] = [{**(c.get("banche") or [{}])[0], "nome": "TEST Banca Uno", "iban": IBAN, "sia": sia, "predefinita": True}]
    return s.put(f"{API}/company", json=c)


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t50.{UID}@example.com", name:"TEST_T50 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": f"TEST_T50 Riba {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT", "iban": IBAN})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    sess().put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                            "corrispettivi": True, "contabilita": True})
    ST["A"] = client("TEST_T50 Cliente A Srl", "01234567890", appoggio_banca="TEST Intesa", appoggio_abi="03069", appoggio_cab="09606")
    ST["B"] = client("TEST_T50 Cliente B Srl", "09876543217")
    ST["Q"] = inv(ST["A"], d(-60), [(d(-30), 50), (d(-20), 72)])
    ST["P"] = inv(ST["A"], d(-40), [(d(-10), 122)])
    ST["F"] = inv(ST["A"], d(-5), [(d(30), 60), (d(60), 62)])
    ST["R"] = inv(ST["B"], d(-5), [(d(30), 122)])
    ST["S"] = inv(ST["A"], d(-5), [(d(30), 122)], mp="MP05")
    yield
    clean()


def getp(pid):
    return next(x for x in sess().get(f"{API}/parties").json() if x["id"] == pid)


def da_presentare():
    r = sess().get(f"{API}/riba/da-presentare")
    assert r.status_code == 200, r.text
    return {x["key"]: x for x in r.json()}


class TestSetup:
    def test_01_sia_validation(self):
        r = put_company("AB1")
        assert r.status_code == 422, r.text

    def test_02_appoggio_validation(self):
        s = sess()
        p = getp(ST['A'])
        r = s.put(f"{API}/parties/{ST['A']}", json={**p, "appoggio_abi": "1234"})
        assert r.status_code == 422, r.text
        assert "5 cifre" in r.text

    def test_03_da_presentare(self):
        dp = da_presentare()
        for k in (f"{ST['Q']}:1", f"{ST['Q']}:2", f"{ST['P']}:1", f"{ST['F']}:1", f"{ST['F']}:2", f"{ST['R']}:1"):
            assert k in dp, k
        assert not any(k.startswith(ST["S"]) for k in dp)
        assert dp[f"{ST['R']}:1"]["manca_appoggio"] is True
        assert dp[f"{ST['Q']}:2"]["importo"] == 72

    def test_04_distinta_requires_sia(self):
        r = sess().post(f"{API}/riba/distinte", json={"banca_iban": IBAN, "data": T.isoformat(), "effetti": [f"{ST['P']}:1"]})
        assert r.status_code == 400 and "SIA" in r.text, r.text
        r = put_company("A1B2C")
        assert r.status_code == 200, r.text

    def test_05_distinta_validations(self):
        s = sess()
        u = f"{API}/riba/distinte"
        assert s.post(u, json={"banca_iban": "IT00X", "data": T.isoformat(), "effetti": [f"{ST['P']}:1"]}).status_code == 400
        r = s.post(u, json={"banca_iban": IBAN, "data": T.isoformat(), "effetti": [f"{ST['R']}:1"]})
        assert r.status_code == 400 and "ABI e CAB" in r.text, r.text
        r = s.post(u, json={"banca_iban": IBAN, "data": T.isoformat(), "effetti": [f"{ST['Q']}:2"]})
        assert r.status_code == 400 and "rata 1" in r.text, r.text
        assert s.post(u, json={"banca_iban": IBAN, "data": T.isoformat(), "effetti": ["nope:1"]}).status_code == 400


class TestDistinta:
    def test_01_create(self):
        keys = [f"{ST['Q']}:1", f"{ST['Q']}:2", f"{ST['P']}:1", f"{ST['F']}:1"]
        r = sess().post(f"{API}/riba/distinte", json={"banca_iban": IBAN, "data": T.isoformat(), "effetti": keys})
        assert r.status_code == 200, r.text
        dist = r.json()
        ST["D1"] = dist["id"]
        assert dist["n_effetti"] == 4 and dist["totale"] == 304
        assert dist["conto_sbf"].startswith("13.01.1")
        comp = sess().get(f"{API}/company").json()
        assert comp["banche"][0]["conto_sbf"] == dist["conto_sbf"]
        acc = mongo(f'print(db.coa_accounts.findOne({{company_id:"{ST["cid"]}", codice:"{dist["conto_sbf"]}"}}).descrizione)')
        assert acc == "Banca c/effetti SBF - TEST Banca Uno"
        dp = da_presentare()
        assert not any(k in dp for k in keys)
        assert f"{ST['F']}:2" in dp

    def test_02_accounting_rb(self):
        e = entries("riba", ST["D1"])
        assert len(e) == 1, e
        e = e[0]
        assert e["causale"] == "RB" and e["totale"] == 608
        dare = {(x["conto"], x["dare"]) for x in e["righe"] if x["dare"]}
        avere = {(x["conto"], x["avere"]) for x in e["righe"] if x["avere"]}
        assert ("06.01.001", 304) in dare and any(c.startswith("13.01.1") and v == 304 for c, v in avere)
        assert ("05.01.004", 122) in dare and ("05.01.001", 122) in avere

    def test_03_maturazione(self):
        r = sess().get(f"{API}/riba/distinte/{ST['D1']}")
        assert r.status_code == 200
        eff = {(x["invoice_id"], x["rata_n"]): x for x in r.json()["effetti"]}
        ST["eff"] = eff
        assert eff[(ST["P"], 1)]["stato"] == "maturato"
        assert eff[(ST["Q"], 1)]["stato"] == "maturato" and eff[(ST["Q"], 2)]["stato"] == "maturato"
        assert eff[(ST["F"], 1)]["stato"] == "presentato"
        rs = entries("riba_scadenza", eff[(ST["P"], 1)]["id"])
        assert len(rs) == 1 and rs[0]["causale"] == "RS"
        assert {(x["conto"], x["dare"], x["avere"]) for x in rs[0]["righe"]} >= {("05.01.004", 0, 122)}
        assert not entries("riba_scadenza", eff[(ST["F"], 1)]["id"])
        lst = sess().get(f"{API}/riba/distinte").json()
        assert lst[0]["stati"] == {"maturato": 3, "presentato": 1}

    def test_04_scadenzario_closed(self):
        rate = sess().get(f"{API}/scadenzario", params={"party_id": ST["A"]}).json()["rate"]
        p = [x for x in rate if x["invoice_id"] == ST["P"]][0]
        assert p["residuo"] == 0

    def test_05_cbi(self):
        r = sess().get(f"{API}/riba/distinte/{ST['D1']}/cbi")
        assert r.status_code == 200
        txt = r.content.decode("ascii")
        ST["cbi"] = txt
        assert txt.endswith("\r\n")
        lines = txt.split("\r\n")[:-1]
        assert all(len(x) == 120 for x in lines), [len(x) for x in lines]
        tipi = [x[1:3] for x in lines]
        assert tipi[0] == "IB" and tipi[-1] == "EF"
        assert tipi[1:-1] == ["14", "20", "30", "40", "50", "51", "70"] * 4
        ef = lines[-1]
        assert int(ef[45:52]) == 4 and int(ef[52:67]) == 30400 and int(ef[82:89]) == len(lines)
        r14 = lines[1]
        assert r14[47:52] == "05428" and r14[52:57] == "11101" and r14[69:74] == "03069" and r14[74:79] == "09606"

    def test_06_delete_payment_blocked(self):
        pid = ST["eff"][(ST["P"], 1)]["payment_id"]
        r = sess().delete(f"{API}/pagamenti/{pid}")
        assert r.status_code == 400 and "Ri.Ba" in r.text, r.text

    def test_07_scadenze_blocked(self):
        r = sess().put(f"{API}/scadenze/invoices/{ST['P']}", json={"rate": [{"scadenza": d(5), "importo": 122}]})
        assert r.status_code == 400, r.text

    def test_08_delete_distinta_blocked(self):
        assert sess().delete(f"{API}/riba/distinte/{ST['D1']}").status_code == 400

    def test_09_esiti(self):
        r = sess().post(f"{API}/riba/esiti", files={"file": ("esiti.txt", ST["cbi"].encode(), "text/plain")})
        assert r.status_code == 200, r.text
        out = r.json()
        assert len(out) == 4 and all(x["effetto"] for x in out)
        assert {x["effetto"]["id"] for x in out} == {e["id"] for e in ST["eff"].values()}
        bad = sess().post(f"{API}/riba/esiti", files={"file": ("x.txt", b"hello", "text/plain")})
        assert bad.status_code == 400


class TestInsoluto:
    def test_01_presentato_rejected(self):
        e = ST["eff"][(ST["F"], 1)]
        r = sess().post(f"{API}/riba/effetti/{e['id']}/insoluto", json={"data": T.isoformat(), "spese_banca": 5, "spese_cliente": 7, "nuova_scadenza": d(30)})
        assert r.status_code == 400, r.text

    def test_02_validations(self):
        e = ST["eff"][(ST["P"], 1)]
        u = f"{API}/riba/effetti/{e['id']}/insoluto"
        assert sess().post(u, json={"data": d(1), "nuova_scadenza": d(30)}).status_code == 400
        assert sess().post(u, json={"data": T.isoformat(), "nuova_scadenza": d(-1)}).status_code == 400

    def test_03_insoluto_p(self):
        e = ST["eff"][(ST["P"], 1)]
        r = sess().post(f"{API}/riba/effetti/{e['id']}/insoluto", json={"data": T.isoformat(), "spese_banca": 5, "spese_cliente": 7.5, "nuova_scadenza": d(40)})
        assert r.status_code == 200, r.text
        assert r.json()["stato"] == "insoluto"
        assert mongo(f'print(db.payments.countDocuments({{id:"{e["payment_id"]}"}}))') == "0"
        rm = json.loads(mongo(f'print(JSON.stringify(db.invoices.findOne({{id:"{ST["P"]}"}}).rate_mod))'))
        assert rm[0]["scadenza"] == d(40)
        pa = json.loads(mongo(f'print(JSON.stringify(db.partite_aperte.findOne({{riba_effetto_id:"{e["id"]}"}},{{_id:0}})))'))
        assert pa["totale"] == 7.5 and pa["modalita_pagamento"] == "MP12" and pa["numero_display"].startswith("Spese insoluto")
        ri = entries("riba_insoluto", e["id"])
        assert len(ri) == 1 and ri[0]["causale"] == "RI"
        rows = {(x["conto"], x["dare"], x["avere"]) for x in ri[0]["righe"]}
        assert ("06.01.001", 0, 127) in rows or {("06.01.001", 0, 122), ("06.01.001", 0, 5)} <= rows, rows
        assert ("30.07.011", 5, 0) in rows and ("20.05.001", 0, 7.5) in rows
        dp = da_presentare()
        assert dp[f"{ST['P']}:1"]["scadenza"] == d(40) and dp[f"{ST['P']}:1"]["importo"] == 122
        assert any(x["numero_display"].startswith("Spese insoluto") for x in dp.values())
        again = sess().post(f"{API}/riba/effetti/{e['id']}/insoluto", json={"data": T.isoformat(), "nuova_scadenza": d(40)})
        assert again.status_code == 400

    def test_04_insoluto_first_rata_moved_after_second(self):
        # Q rata 1 (50, d-30) insoluta, new due date after rata 2 (72, d-20, still presented/maturato)
        e = ST["eff"][(ST["Q"], 1)]
        r = sess().post(f"{API}/riba/effetti/{e['id']}/insoluto", json={"data": T.isoformat(), "nuova_scadenza": d(20)})
        assert r.status_code == 200, r.text
        dp = da_presentare()
        q = [x for x in dp.values() if x["invoice_id"] == ST["Q"]]
        assert len(q) == 1 and q[0]["importo"] == 50 and q[0]["scadenza"] == d(20), q


class TestDistinta2:
    def test_01_create_and_delete(self):
        s = sess()
        r = s.post(f"{API}/riba/distinte", json={"banca_iban": IBAN, "data": T.isoformat(), "effetti": [f"{ST['F']}:2"]})
        assert r.status_code == 200, r.text
        did = r.json()["id"]
        assert r.json()["conto_sbf"] == ST.get("sbf", r.json()["conto_sbf"])
        assert len(entries("riba", did)) == 1
        r = s.delete(f"{API}/riba/distinte/{did}")
        assert r.status_code == 200, r.text
        assert not entries("riba", did)
        assert mongo(f'print(db.payments.countDocuments({{company_id:"{ST["cid"]}", metodo:"riba", invoice_id:"{ST["F"]}"}}))') == "1"
        assert f"{ST['F']}:2" in da_presentare()
        assert s.get(f"{API}/riba/distinte/{did}").status_code == 404


class TestScadenze:
    def test_01_validations(self):
        u = f"{API}/scadenze/invoices/{ST['S']}"
        r = sess().put(u, json={"rate": [{"scadenza": d(10), "importo": 100}]})
        assert r.status_code == 422 and "somma" in r.text
        r = sess().put(u, json={"rate": [{"scadenza": d(-30), "importo": 122}]})
        assert r.status_code == 422
        assert sess().put(f"{API}/scadenze/invoices/nope", json={"rate": [{"scadenza": d(10), "importo": 1}]}).status_code == 404
        assert sess().put(f"{API}/scadenze/foo/{ST['S']}", json={"rate": [{"scadenza": d(10), "importo": 1}]}).status_code == 422

    def test_02_ok(self):
        r = sess().put(f"{API}/scadenze/invoices/{ST['S']}", json={"rate": [{"scadenza": d(70), "importo": 22}, {"scadenza": d(15), "importo": 100}]})
        assert r.status_code == 200, r.text
        rate = [x for x in sess().get(f"{API}/scadenzario", params={"party_id": ST["A"]}).json()["rate"] if x["invoice_id"] == ST["S"]]
        assert [(x["scadenza"], x["importo"]) for x in rate] == [(d(15), 100), (d(70), 22)]


class TestPassive:
    def xml(self, numero):
        x = open(__file__.replace("test_iteration50_riba.py", "fixtures/sample_fattura.xml")).read()
        x = x.replace("<IdCodice>01234567890</IdCodice>", f"<IdCodice>{PIVA}</IdCodice>").replace("02345670481", SUP_PIVA)
        x = x.replace(f"<CodiceFiscale>{SUP_PIVA}</CodiceFiscale>", "").replace("<Numero>5674/2026</Numero>", f"<Numero>{numero}</Numero>")
        x = x.replace("<Data>2026-10-30</Data>", f"<Data>{d(-3)}</Data>").replace("DEMO Energia Toscana SpA", "TEST_T50 Fornitore Nuovo SpA")
        x = x.replace("</Sede>\n    </CedentePrestatore>", "</Sede>\n<IscrizioneREA><Ufficio>FI</Ufficio><NumeroREA>123456</NumeroREA><StatoLiquidazione>LN</StatoLiquidazione></IscrizioneREA>"
                      "<Contatti><Telefono>055123456</Telefono><Email>forn@example.com</Email></Contatti>\n    </CedentePrestatore>", 1)
        return x

    def test_01_new_supplier(self):
        r = sess().post(f"{API}/passive/upload", files=[("files", ("p1.xml", self.xml("T50-1"), "text/xml"))])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body[0]["ok"], body
        doc = body[0]["documenti"][0]
        ST["pas"] = doc["id"]
        fid = doc["nuovo_fornitore_id"]
        assert fid
        ST["forn"] = fid
        p = getp(fid)
        assert p["da_verificare"] is True and p["tipo"] == "fornitore"
        assert p["codice_fiscale"] == SUP_PIVA and p["partita_iva"] == SUP_PIVA
        assert p["telefono"] == "055123456" and p["rea"] == "FI 123456" and p["iban"] == "IT02A0306902887100000001234"
        assert p["email"] == "forn@example.com" and p["comune"] == "Firenze"

    def test_02_second_upload_existing(self):
        r = sess().post(f"{API}/passive/upload", files=[("files", ("p2.xml", self.xml("T50-2"), "text/xml"))])
        assert r.status_code == 200, r.text
        assert r.json()[0]["ok"], r.text
        assert r.json()[0]["documenti"][0]["nuovo_fornitore_id"] is None

    def test_03_confirm(self):
        s = sess()
        p = getp(ST['forn'])
        r = s.put(f"{API}/parties/{ST['forn']}", json=p)
        assert r.status_code == 200, r.text
        p2 = getp(ST['forn'])
        assert p2["da_verificare"] is False and p2["rea"] == "FI 123456" and p2["iban"]

    def test_04_scadenze_passive(self):
        u = f"{API}/scadenze/passive/{ST['pas']}"
        r = sess().put(u, json={"rate": [{"scadenza": d(10), "importo": 300}, {"scadenza": d(40), "importo": 274.93}]})
        assert r.status_code == 200, r.text
        rate = [x for x in sess().get(f"{API}/scadenzario-passivo", params={"party_id": ST["forn"]}).json()["rate"] if x["invoice_id"] == ST["pas"]]
        assert [(x["scadenza"], x["importo"]) for x in rate] == [(d(10), 300), (d(40), 274.93)]

# Iteration 52: Dichiarazioni d'intento with plafond (/api/intenti + invoice N3.5 block) and Registrazione veloce (/api/reg-veloce)
# Run: pytest tests/test_iteration52_intenti_regveloce.py -v -n 0
import json
import os
import random
from datetime import date

import pytest
import requests

from test_iteration7_pa_scartate_registro import API, mongo

RUN = str(random.randint(100000, 999999))
TOK, UID = f"test_session_t52_admin_{RUN}", f"test-user-t52-admin-{RUN}"
PIVA = "86" + RUN + "521"
T = date.today()
Y = T.year
TODAY = T.isoformat()
ST = {}
COLLS = ["invoices", "passive_invoices", "parties", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "intenti", "partite_aperte"]
PROT1, PROT2, PROT3 = f"{RUN}00000000001-000001", f"{RUN}00000000002-000002", f"{RUN}00000000003-000003"


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


def party(tipo, name, piva, cf, **kw):
    r = sess().post(f"{API}/parties", json={"tipo": tipo, "denominazione": name, "partita_iva": piva, "codice_fiscale": cf, "codice_destinatario": "ABC1234",
                                             "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT", **kw})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def inv_body(pid, n35=0.0, iva22=0.0, td="TD01", **kw):
    lines = []
    if n35:
        lines.append({"descrizione": "TEST_n35", "quantita": 1, "prezzo_unitario": n35, "aliquota": 0, "natura": "N3.5"})
    if iva22:
        lines.append({"descrizione": "TEST_22", "quantita": 1, "prezzo_unitario": iva22, "aliquota": 22})
    return {"tipo_documento": td, "data": TODAY, "party_id": pid, "modalita_pagamento": "MP05", "lines": lines, **kw}


def intento(pid, prot, data, importo, **kw):
    return sess().post(f"{API}/intenti", json={"party_id": pid, "protocollo": prot, "data": data, "anno": int(data[:4]), "importo": importo, **kw})


def decl(iid):
    return next(x for x in sess().get(f"{API}/intenti", params={"party_id": ST["A"]}).json() if x["id"] == iid)


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    try:
        mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t52.{UID}@example.com", name:"TEST_T52 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
              f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
        r = sess().post(f"{API}/companies", json={"denominazione": f"TEST_T52 Intenti {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                                 "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
        assert r.status_code == 200, r.text
        ST["cid"] = r.json()["id"]
        s = sess()
        s.put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                           "corrispettivi": True, "contabilita": True})
        assert s.get(f"{API}/contabilita/registrazioni").status_code == 200
        ST["A"] = party("cliente", "TEST_T52 Esportatore Srl", "01234567890", "RSSMRA80A01H501U", natura_default="N3.5")
        ST["B"] = party("cliente", "TEST_T52 Senza Dich Srl", "09876543210", "VRDLGU80A01H501X")
        ST["F"] = party("fornitore", "TEST_T52 Fornitore Srl", "11122233344", "BNCGNN80A01H501Y", detraibilita_iva=50)
        yield
    finally:
        if not os.environ.get("T52_KEEP"):
            clean()
        else:
            print("KEEP", ST.get("cid"), TOK)


# ---------- Intenti CRUD ----------
class TestIntentiCrud:
    def test_01_create_slash_normalized(self):
        r = intento(ST["A"], PROT1.replace("-", "/"), f"{Y}-01-10", 1000, verificata=True)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["protocollo"] == PROT1 and d["utilizzato"] == 0 and d["residuo"] == 1000 and d["percentuale_residua"] == 100
        ST["D1"] = d["id"]
        r = intento(ST["A"], PROT2, f"{Y}-06-01", 5000)
        assert r.status_code == 200, r.text
        ST["D2"] = r.json()["id"]

    def test_02_validation(self):
        assert intento(ST["A"], "123-456", f"{Y}-01-10", 100).status_code == 422
        r = intento(ST["A"], PROT1, f"{Y}-01-10", 100)
        assert r.status_code == 400 and "protocollo" in r.text
        assert intento(ST["F"], PROT3, f"{Y}-01-10", 100).status_code == 400
        assert intento(ST["A"], PROT3, f"{Y}-13-40", 100).status_code == 422
        assert intento(ST["A"], PROT3, f"{Y}-01-10", 0).status_code == 422

    def test_03_list_by_party(self):
        rows = sess().get(f"{API}/intenti", params={"party_id": ST["A"]}).json()
        assert {x["id"] for x in rows} == {ST["D1"], ST["D2"]}
        assert sess().get(f"{API}/intenti", params={"party_id": ST["B"]}).json() == []


# ---------- Invoice N3.5 plafond ----------
class TestInvoicePlafond:
    def test_01_no_declaration_blocked(self):
        r = sess().post(f"{API}/invoices", json=inv_body(ST["B"], n35=100))
        assert r.status_code == 422, r.text
        assert "dichiarazione d'intento" in r.text.lower()

    def test_02_picks_first_declaration(self):
        r = sess().post(f"{API}/invoices", json=inv_body(ST["A"], n35=800, iva22=100))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["intento"]["id"] == ST["D1"] and d["intento"]["protocollo"] == PROT1 and d["intento"]["data"] == f"{Y}-01-10"
        assert d["cliente"]["intento_protocollo"] == PROT1
        ST["I1"] = d["id"]
        x = decl(ST["D1"])
        assert x["utilizzato"] == 800 and x["residuo"] == 200

    def test_03_falls_to_second_declaration(self):
        r = sess().post(f"{API}/invoices", json=inv_body(ST["A"], n35=900))
        assert r.status_code == 200, r.text
        assert r.json()["intento"]["id"] == ST["D2"]
        ST["I2"] = r.json()["id"]
        assert decl(ST["D2"])["residuo"] == 4100

    def test_04_over_plafond_blocked(self):
        r = sess().post(f"{API}/invoices", json=inv_body(ST["A"], n35=5000))
        assert r.status_code == 422, r.text
        assert "Plafond superato" in r.text and PROT2 in r.text

    def test_05_avvisi_under_10pct(self):
        r = sess().post(f"{API}/invoices", json=inv_body(ST["A"], n35=150))
        assert r.status_code == 200, r.text
        assert r.json()["intento"]["id"] == ST["D1"]
        ST["I3"] = r.json()["id"]
        av = sess().get(f"{API}/intenti/avvisi").json()
        a = next((x for x in av if x["id"] == ST["D1"]), None)
        assert a and a["residuo"] == 50 and a["cliente"] == "TEST_T52 Esportatore Srl" and a["percentuale_residua"] == 5
        assert ST["D2"] not in [x["id"] for x in av]

    def test_06_put_and_delete_guards(self):
        s = sess()
        body = {"party_id": ST["A"], "protocollo": PROT1, "data": f"{Y}-01-10", "anno": Y, "importo": 900}
        r = s.put(f"{API}/intenti/{ST['D1']}", json=body)
        assert r.status_code == 400 and "importo" in r.text
        r = s.put(f"{API}/intenti/{ST['D1']}", json={**body, "importo": 1200, "note": "TEST_note"})
        assert r.status_code == 200 and r.json()["residuo"] == 250, r.text
        r = s.put(f"{API}/intenti/{ST['D1']}", json={**body, "protocollo": PROT3, "importo": 1200})
        assert r.status_code == 400
        assert s.delete(f"{API}/intenti/{ST['D1']}").status_code == 400
        r = s.put(f"{API}/intenti/{ST['D1']}", json={**body, "importo": 1000})
        assert r.status_code == 200 and r.json()["residuo"] == 50

    def test_07_update_invoice_excludes_self(self):
        s = sess()
        # I3 is 150 on D1 (residuo 50). Raising to 200 still fits D1 when excluding itself (1000-800=200)
        r = s.put(f"{API}/invoices/{ST['I3']}", json=inv_body(ST["A"], n35=200))
        assert r.status_code == 200, r.text
        assert r.json()["intento"]["id"] == ST["D1"]
        # 250 does not fit D1 -> moves to D2
        r = s.put(f"{API}/invoices/{ST['I3']}", json=inv_body(ST["A"], n35=250))
        assert r.status_code == 200, r.text
        assert r.json()["intento"]["id"] == ST["D2"]
        assert decl(ST["D1"])["residuo"] == 200 and decl(ST["D2"])["residuo"] == 3850
        r = s.put(f"{API}/invoices/{ST['I3']}", json=inv_body(ST["A"], n35=5000))
        assert r.status_code == 422 and "Plafond superato" in r.text

    def test_08_xml_intento(self):
        r = sess().get(f"{API}/invoices/{ST['I1']}/xml")
        assert r.status_code == 200, r.text
        x = r.text
        assert "<TipoDato>INTENTO</TipoDato>" in x and f"<RiferimentoTesto>{PROT1}</RiferimentoTesto>" in x and f"<RiferimentoData>{Y}-01-10</RiferimentoData>" in x
        assert "N3.5" in x

    def test_09_send_and_credit_note(self):
        s = sess()
        r = s.post(f"{API}/invoices/{ST['I1']}/send")
        assert r.status_code == 200, r.text
        s.post(f"{API}/invoices/{ST['I1']}/refresh")
        r = s.post(f"{API}/invoices", json=inv_body(ST["A"], n35=100, td="TD04", fattura_collegata_id=ST["I1"]))
        assert r.status_code == 200, r.text
        ST["NC"] = r.json()["id"]
        assert r.json()["intento"]["id"] == ST["D1"]
        assert decl(ST["D1"])["utilizzato"] == 700

    def test_10_send_recheck_blocks(self):
        s = sess()
        # Reduce D2 so the draft I2 (900 on D2) no longer fits anywhere at send time
        r = s.post(f"{API}/invoices", json=inv_body(ST["A"], n35=3000))
        assert r.status_code == 200, r.text
        ST["I4"] = r.json()["id"]
        assert r.json()["intento"]["id"] == ST["D2"]
        # D2 residuo now 850; D1 residuo 300. I2 (900) at send: excl self D2 residuo 1750 -> ok
        r = s.post(f"{API}/invoices/{ST['I2']}/send")
        assert r.status_code == 200, r.text
        # Revoke D2 -> draft I4 (3000) can not be sent: D1 has only 300
        body = {"party_id": ST["A"], "protocollo": PROT2, "data": f"{Y}-06-01", "anno": Y, "importo": 5000, "revocata": True}
        assert s.put(f"{API}/intenti/{ST['D2']}", json=body).status_code == 200
        r = s.post(f"{API}/invoices/{ST['I4']}/send")
        assert r.status_code == 422 and "Plafond superato" in r.text, r.text
        assert s.put(f"{API}/intenti/{ST['D2']}", json={**body, "revocata": False}).status_code == 200

    def test_11_future_declaration_ignored_and_year(self):
        s = sess()
        r = intento(ST["B"], PROT3, f"{Y + 1}-01-05", 10000)
        assert r.status_code == 200, r.text
        ST["D3"] = r.json()["id"]
        r = s.post(f"{API}/invoices", json=inv_body(ST["B"], n35=100))
        assert r.status_code == 422, r.text
        assert s.delete(f"{API}/intenti/{ST['D3']}").status_code == 200
        assert sess().get(f"{API}/intenti", params={"party_id": ST["B"]}).json() == []

    def test_12_regression_normal_invoice(self):
        r = sess().post(f"{API}/invoices", json=inv_body(ST["B"], iva22=100))
        assert r.status_code == 200, r.text
        assert r.json()["intento"] is None and r.json()["totale"] == 122
        assert "INTENTO" not in sess().get(f"{API}/invoices/{r.json()['id']}/xml").text


# ---------- Registrazione veloce ----------
def rv(**kw):
    b = {"tipo": "vendita", "party_id": ST["A"], "numero": f"T52-{RUN}", "data_documento": TODAY, "data_registrazione": TODAY, "scadenza": f"{Y}-12-31",
         "righe": [{"aliquota": 22, "totale": 122}, {"aliquota": 10, "totale": 110}]}
    return sess().post(f"{API}/reg-veloce", json={**b, **kw})


def entry(ref):
    return [x for x in sess().get(f"{API}/contabilita/registrazioni").json()["registrazioni"] if x.get("ref_id") == ref]


class TestRegVeloce:
    def test_01_anteprima(self):
        r = sess().post(f"{API}/reg-veloce/anteprima", json={"tipo": "vendita", "party_id": ST["A"], "numero": "X", "data_documento": TODAY, "data_registrazione": TODAY,
                                                             "righe": [{"aliquota": 22, "totale": 122}, {"aliquota": 10, "totale": 110}, {"aliquota": 4, "totale": 33.33}]})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["riepilogo"][0]["imponibile"] == 100 and d["riepilogo"][0]["imposta"] == 22
        assert d["riepilogo"][1]["imponibile"] == 100 and d["riepilogo"][1]["imposta"] == 10
        assert d["riepilogo"][2]["imponibile"] == 32.05 and d["riepilogo"][2]["imposta"] == 1.28
        assert d["totale"] == 265.33

    def test_02_vendita(self):
        r = rv()
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["imponibile"] == 200 and d["iva"] == 32 and d["totale"] == 232
        ST["V"] = d["id"]
        inv = sess().get(f"{API}/invoices/{ST['V']}").json()
        assert inv["status"] == "manuale" and inv["sezionale"] == "MAN" and inv["manuale"] is True and inv["numero_display"] == f"T52-{RUN}"
        reg = sess().get(f"{API}/registro-iva-vendite", params={"anno": Y}).json()
        assert ST["V"] in [x["id"] for x in reg["rows"]]
        sc = sess().get(f"{API}/scadenzario", params={"party_id": ST["A"]}).json()
        rate = [x for x in sc["rate"] if x["invoice_id"] == ST["V"]]
        assert len(rate) == 1 and rate[0]["scadenza"] == f"{Y}-12-31" and rate[0]["importo"] == 232
        e = entry(ST["V"])
        assert len(e) == 1 and e[0]["causale"] == "FV"
        dare = [x for x in e[0]["righe"] if x["dare"]]
        avere = sum(x["avere"] for x in e[0]["righe"])
        assert len(dare) == 1 and dare[0]["dare"] == 232 and avere == 232
        assert sorted(x["avere"] for x in e[0]["righe"] if x["avere"]) == [32, 200]

    def test_03_vendita_validations(self):
        assert rv().status_code == 400
        r = rv(numero=f"T52B-{RUN}", data_registrazione=f"{Y}-01-01", data_documento=f"{Y}-02-01")
        assert r.status_code == 422 and "data_registrazione" in r.text
        assert rv(numero=f"T52C-{RUN}", righe=[{"aliquota": 0, "totale": 100}]).status_code == 422
        assert rv(numero=f"T52C-{RUN}", righe=[{"aliquota": 7, "totale": 100}]).status_code == 422
        assert rv(numero=f"T52C-{RUN}", party_id=ST["F"]).status_code == 400
        assert rv(numero=f"T52C-{RUN}", scadenza=f"{Y - 1}-01-01").status_code == 422

    def test_04_incasso_on_manual(self):
        r = sess().post(f"{API}/invoices/{ST['V']}/pagamenti", json={"data": TODAY, "importo": 32, "metodo": "bonifico"})
        assert r.status_code == 200, r.text
        r = sess().delete(f"{API}/reg-veloce/vendita/{ST['V']}")
        assert r.status_code == 400, r.text

    def test_05_nc_vendita_natura(self):
        r = rv(tipo="nc_vendita", numero=f"NC52-{RUN}", righe=[{"aliquota": 0, "natura": "N2.2", "totale": 50}, {"aliquota": 22, "totale": 61}])
        assert r.status_code == 200, r.text
        ST["NV"] = r.json()["id"]
        inv = sess().get(f"{API}/invoices/{ST['NV']}").json()
        assert inv["sezionale"] == "MANNC" and inv["tipo_documento"] == "TD04" and inv["imponibile"] == 100 and inv["iva"] == 11
        e = entry(ST["NV"])
        assert len(e) == 1 and e[0]["causale"] == "NV"

    def test_06_acquisto(self):
        r = rv(tipo="acquisto", party_id=ST["F"], numero=f"FA52-{RUN}")
        assert r.status_code == 200, r.text
        ST["A1"] = r.json()["id"]
        r2 = rv(tipo="nc_acquisto", party_id=ST["F"], numero=f"NA52-{RUN}", righe=[{"aliquota": 22, "totale": 12.2}])
        assert r2.status_code == 200, r2.text
        ST["A2"] = r2.json()["id"]
        reg = sess().get(f"{API}/registro-iva-acquisti", params={"anno": Y}).json()
        rows = {x["id"]: x for x in reg["rows"]}
        assert ST["A1"] in rows and ST["A2"] in rows
        assert rows[ST["A2"]]["protocollo"] == rows[ST["A1"]]["protocollo"] + 1
        assert rows[ST["A1"]]["detraibilita_iva"] == 50
        sc = sess().get(f"{API}/scadenzario-passivo", params={"party_id": ST["F"]}).json()
        assert any(x["invoice_id"] == ST["A1"] and x["importo"] == 232 for x in sc["rate"])
        e = entry(ST["A1"])
        assert len(e) == 1 and e[0]["causale"] == "FA"
        assert entry(ST["A2"])[0]["causale"] == "NA"
        assert rv(tipo="acquisto", party_id=ST["F"], numero=f"FA52-{RUN}").status_code == 400
        assert rv(tipo="acquisto", party_id=ST["A"], numero=f"FAX-{RUN}").status_code == 400

    def test_07_liquidazione(self):
        r = sess().get(f"{API}/liquidazione-iva", params={"anno": Y})
        assert r.status_code == 200, r.text
        m = next(p for p in r.json()["periodi"] if p.get("periodo") == T.month or str(p.get("periodo", "")).endswith(f"{T.month:02d}") or p.get("mese") == T.month)
        # sale 32 - NC 11 (manual) = 21 debito at least
        assert m["iva_debito"] >= 21, m

    def test_08_list_and_delete(self):
        rows = sess().get(f"{API}/reg-veloce").json()
        ids = {x["id"]: x for x in rows}
        assert {ST["V"], ST["NV"], ST["A1"], ST["A2"]} <= set(ids)
        assert ids[ST["A1"]]["kind"] == "acquisto" and ids[ST["V"]]["anagrafica"] == "TEST_T52 Esportatore Srl"
        s = sess()
        assert s.delete(f"{API}/reg-veloce/vendita/{ST['NV']}").status_code == 200
        assert s.get(f"{API}/invoices/{ST['NV']}").status_code == 404 and entry(ST["NV"]) == []
        assert s.delete(f"{API}/reg-veloce/acquisto/{ST['A2']}").status_code == 200
        assert entry(ST["A2"]) == []
        assert s.delete(f"{API}/reg-veloce/vendita/{ST['I1']}").status_code == 404

    def test_09_closed_year(self):
        mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}}, {{$set:{{coge_chiusi:[{Y - 1}]}}}})')
        r = rv(numero=f"OLD-{RUN}", data_documento=f"{Y - 1}-03-01", data_registrazione=f"{Y - 1}-03-01")
        assert r.status_code == 400 and "chiuso" in r.text, r.text
        mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}}, {{$unset:{{coge_chiusi:1}}}})')

    def test_10_operatore_forbidden(self):
        mongo(f'db.users.updateOne({{user_id:"{UID}"}}, {{$set:{{role:"operatore", company_ids:["{ST["cid"]}"]}}}})')
        try:
            r = rv(numero=f"OP-{RUN}")
            assert r.status_code == 403, r.text
            # operatore can still read intenti (tenant) and create drafts
            assert sess().get(f"{API}/intenti").status_code == 200
        finally:
            mongo(f'db.users.updateOne({{user_id:"{UID}"}}, {{$set:{{role:"admin"}}}})')

    def test_11_module_off_gating(self):
        s = sess()
        all_on = {"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True, "corrispettivi": True, "contabilita": True}
        assert s.put(f"{API}/companies/{ST['cid']}/moduli", json={**all_on, "contabilita": False}).status_code == 200
        try:
            r = s.get(f"{API}/reg-veloce")
            assert r.status_code in (403, 404), r.text
            # intenti stay available (fatture_attive)
            assert s.get(f"{API}/intenti/avvisi").status_code == 200
        finally:
            s.put(f"{API}/companies/{ST['cid']}/moduli", json=all_on)

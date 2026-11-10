# Iteration 39: Saldaconto (partite aperte/chiuse) in prima nota - partite, auto allocation (oldest due date first),
# registrazioni with saldaconto (validation, payments linked via coge_entry_id, scadenzario update), PUT replace/rollback,
# DELETE removal, payment delete guard, passive (fornitori) side.
# Run with: pytest test_iteration39_saldaconto.py -n 0
import os
import random
from datetime import date, timedelta

import pytest
import requests

from test_iteration7_pa_scartate_registro import API, mongo

RUN = str(random.randint(100000, 999999))
TOK, UID = f"test_session_t39_admin_{RUN}", f"test-user-t39-admin-{RUN}"
PIVA = "87" + RUN + "391"
FIX = open(os.path.join(os.path.dirname(__file__), "fixtures", "sample_fattura.xml")).read()
TODAY = date.today()
D1 = (TODAY - timedelta(days=5)).isoformat()
ST = {}


def sess():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{partita_iva:"{PIVA}"}}).forEach(c=>{{["invoices","passive_invoices","parties","articles","counters","payments","passive_payments","bank_tx","bank_accounts","coa_accounts","coa_causali","coa_iva","coa_entries","sdi_events","audit"].forEach(k=>db[k].deleteMany({{company_id:c.id}})); db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def make_inv(pid, scad, price=100):
    s = sess()
    r = s.post(f"{API}/invoices", json={"tipo_documento": "TD01", "data": D1, "party_id": pid, "modalita_pagamento": "MP05", "scadenza": scad,
                                        "lines": [{"descrizione": "TEST_riga", "quantita": 1, "prezzo_unitario": price, "aliquota": 22}]})
    assert r.status_code == 200, r.text
    iid = r.json()["id"]
    assert s.post(f"{API}/invoices/{iid}/send").status_code == 200
    assert s.post(f"{API}/invoices/{iid}/refresh").status_code == 200
    return iid


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t39.{UID}@example.com", name:"TEST_T39 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    s = sess()
    r = s.post(f"{API}/companies", json={"denominazione": f"TEST_T39 Saldaconto {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                         "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    s = sess()
    s.put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True, "corrispettivi": True, "contabilita": True})
    p = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": "TEST_T39 Cliente Srl", "partita_iva": "01234567890", "codice_fiscale": "",
                                       "codice_destinatario": "ABC1234", "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"})
    assert p.status_code == 200, p.text
    ST["cli"] = p.json()["id"]
    p2 = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": "TEST_T39 Altro Cliente", "partita_iva": "09876543217", "codice_fiscale": "",
                                        "codice_destinatario": "ABC1234", "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"})
    ST["cli2"] = p2.json()["id"]
    # created out of order: oldest due date is B, then C, then A
    ST["A"] = make_inv(ST["cli"], (TODAY + timedelta(days=30)).isoformat())
    ST["B"] = make_inv(ST["cli"], (TODAY + timedelta(days=10)).isoformat())
    ST["C"] = make_inv(ST["cli"], (TODAY + timedelta(days=20)).isoformat())
    f = s.post(f"{API}/parties", json={"tipo": "fornitore", "denominazione": "TEST_T39 Fornitore", "partita_iva": "02345670481", "codice_fiscale": "",
                                       "indirizzo": "Via Y 1", "cap": "50100", "comune": "Firenze", "provincia": "FI", "nazione": "IT"})
    assert f.status_code == 200, f.text
    ST["forn"] = f.json()["id"]
    xml = FIX.replace("<IdCodice>01234567890</IdCodice>", f"<IdCodice>{PIVA}</IdCodice>").replace("<Numero>5674/2026</Numero>", "<Numero>TEST39-1</Numero>") \
             .replace("<Data>2026-10-30</Data>", f"<Data>{D1}</Data>")
    up = s.post(f"{API}/passive/upload", files=[("files", ("p1.xml", xml, "text/xml"))])
    assert up.status_code == 200, up.text
    ST["pas"] = mongo(f'print(db.passive_invoices.findOne({{company_id:"{ST["cid"]}"}}).id)')
    ST["p"] = s.get(f"{API}/contabilita/parametri").json()["parametri"]
    yield
    clean()


def incasso(importo, sc, party=None, data=None):
    p = ST["p"]
    return {"data": data or TODAY.isoformat(), "causale": "IN", "descrizione": "TEST_incasso",
            "righe": [{"conto": p["banca"], "dare": importo, "avere": 0}, {"conto": p["clienti"], "dare": 0, "avere": importo, "party_id": party or ST["cli"]}],
            "saldaconto": sc}


def residui():
    d = sess().get(f"{API}/scadenzario", params={"party_id": ST["cli"]}).json()
    return {r["invoice_id"]: r["residuo_documento"] for r in d["rate"]}


class TestPartite:
    def test_01_partite_sorted(self):
        r = sess().get(f"{API}/contabilita/saldaconto/partite", params={"party_id": ST["cli"], "tipo": "cliente"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert [x["invoice_id"] for x in d["aperte"]] == [ST["B"], ST["C"], ST["A"]]
        assert d["chiuse"] == []
        x = d["aperte"][0]
        for k in ("invoice_id", "numero_display", "data", "scadenza", "netto", "residuo", "pagato", "stato", "pagamenti"):
            assert k in x
        assert x["netto"] == 122 and x["residuo"] == 122 and x["pagato"] == 0 and x["stato"] == "aperta"

    def test_02_partite_unknown_party(self):
        assert sess().get(f"{API}/contabilita/saldaconto/partite", params={"party_id": "nope", "tipo": "cliente"}).status_code == 404

    def test_03_auto(self):
        r = sess().post(f"{API}/contabilita/saldaconto/auto", json={"party_id": ST["cli"], "tipo": "cliente", "importo": 200})
        assert r.status_code == 200, r.text
        d = r.json()
        assert [(x["invoice_id"], x["importo"]) for x in d["righe"]] == [(ST["B"], 122), (ST["C"], 78)]
        assert d["non_abbinato"] == 0
        d = sess().post(f"{API}/contabilita/saldaconto/auto", json={"party_id": ST["cli"], "tipo": "cliente", "importo": 400}).json()
        assert len(d["righe"]) == 3 and d["non_abbinato"] == 34
        assert sess().post(f"{API}/contabilita/saldaconto/auto", json={"party_id": ST["cli"], "tipo": "cliente", "importo": 0}).status_code == 422

    def test_04_partite_passive(self):
        d = sess().get(f"{API}/contabilita/saldaconto/partite", params={"party_id": ST["forn"], "tipo": "fornitore"}).json()
        assert [x["invoice_id"] for x in d["aperte"]] == [ST["pas"]]
        assert d["aperte"][0]["residuo"] == 574.93


class TestRegistrazione:
    def test_01_validations(self):
        s = sess()
        u = f"{API}/contabilita/registrazioni"
        # importo > residuo
        r = s.post(u, json=incasso(200, [{"invoice_id": ST["A"], "importo": 130}]))
        assert r.status_code == 400 and "residuo" in r.text, r.text
        # total > line amount
        r = s.post(u, json=incasso(100, [{"invoice_id": ST["A"], "importo": 60}, {"invoice_id": ST["C"], "importo": 60}]))
        assert r.status_code == 400 and "supera" in r.text, r.text
        # party mismatch (line on other client)
        r = s.post(u, json=incasso(100, [{"invoice_id": ST["A"], "importo": 50}], party=ST["cli2"]))
        assert r.status_code == 400, r.text
        # passive invoice on an incasso line
        r = s.post(u, json=incasso(100, [{"invoice_id": ST["pas"], "importo": 50, "passivo": True}]))
        assert r.status_code == 400, r.text
        # date before invoice
        r = s.post(u, json=incasso(100, [{"invoice_id": ST["A"], "importo": 50}], data=(TODAY - timedelta(days=10)).isoformat()))
        assert r.status_code == 400 and "precedere" in r.text, r.text
        # no payment was created by failed attempts
        assert mongo(f'print(db.payments.countDocuments({{company_id:"{ST["cid"]}"}}))') == "0"
        assert mongo(f'print(db.coa_entries.countDocuments({{company_id:"{ST["cid"]}", origine:"manuale"}}))') == "0"

    def test_02_create_with_saldaconto(self):
        r = sess().post(f"{API}/contabilita/registrazioni", json=incasso(200, [{"invoice_id": ST["B"], "importo": 122}, {"invoice_id": ST["C"], "importo": 78}]))
        assert r.status_code == 200, r.text
        ST["reg"] = r.json()["id"]
        res = residui()
        assert res[ST["B"]] == 0 and res[ST["C"]] == 44 and res[ST["A"]] == 122
        links = sess().get(f"{API}/contabilita/saldaconto/registrazione/{ST['reg']}").json()
        assert sorted((x["invoice_id"], x["importo"], x["passivo"]) for x in links) == sorted([(ST["B"], 122, False), (ST["C"], 78, False)])
        d = sess().get(f"{API}/contabilita/saldaconto/partite", params={"party_id": ST["cli"], "tipo": "cliente"}).json()
        assert [x["invoice_id"] for x in d["chiuse"]] == [ST["B"]]
        c = next(x for x in d["aperte"] if x["invoice_id"] == ST["C"])
        assert c["stato"] == "parziale" and c["pagato"] == 78 and c["residuo"] == 44
        assert d["chiuse"][0]["pagamenti"][0]["coge_entry_id"] == ST["reg"]
        # escludi_reg -> as if the registration did not exist
        d2 = sess().get(f"{API}/contabilita/saldaconto/partite", params={"party_id": ST["cli"], "tipo": "cliente", "escludi_reg": ST["reg"]}).json()
        assert len(d2["aperte"]) == 3 and all(x["residuo"] == 122 for x in d2["aperte"])
        # auto after: starts from C (residual 44)
        a = sess().post(f"{API}/contabilita/saldaconto/auto", json={"party_id": ST["cli"], "tipo": "cliente", "importo": 50}).json()
        assert [(x["invoice_id"], x["importo"]) for x in a["righe"]] == [(ST["C"], 44), (ST["A"], 6)]

    def test_03_delete_payment_blocked(self):
        pid = mongo(f'print(db.payments.findOne({{company_id:"{ST["cid"]}", coge_entry_id:"{ST["reg"]}"}}).id)')
        r = sess().delete(f"{API}/pagamenti/{pid}")
        assert r.status_code == 400 and "prima nota" in r.text, r.text

    def test_04_put_rollback_on_error(self):
        r = sess().put(f"{API}/contabilita/registrazioni/{ST['reg']}", json=incasso(200, [{"invoice_id": ST["A"], "importo": 150}]))
        assert r.status_code == 400, r.text
        links = sess().get(f"{API}/contabilita/saldaconto/registrazione/{ST['reg']}").json()
        assert len(links) == 2
        res = residui()
        assert res[ST["B"]] == 0 and res[ST["C"]] == 44

    def test_05_put_replace(self):
        r = sess().put(f"{API}/contabilita/registrazioni/{ST['reg']}", json=incasso(100, [{"invoice_id": ST["A"], "importo": 100}]))
        assert r.status_code == 200, r.text
        links = sess().get(f"{API}/contabilita/saldaconto/registrazione/{ST['reg']}").json()
        assert [(x["invoice_id"], x["importo"]) for x in links] == [(ST["A"], 100)]
        res = residui()
        assert res[ST["B"]] == 122 and res[ST["C"]] == 122 and res[ST["A"]] == 22

    def test_06_put_reuse_own_residual(self):
        # editing with the full 122 on A must be allowed (own payment excluded from residuo check)
        r = sess().put(f"{API}/contabilita/registrazioni/{ST['reg']}", json=incasso(122, [{"invoice_id": ST["A"], "importo": 122}]))
        assert r.status_code == 200, r.text
        assert residui()[ST["A"]] == 0

    def test_07_delete_reg_removes_payments(self):
        assert sess().delete(f"{API}/contabilita/registrazioni/{ST['reg']}").status_code == 200
        assert sess().get(f"{API}/contabilita/saldaconto/registrazione/{ST['reg']}").json() == []
        assert all(v == 122 for v in residui().values())


class TestPassivo:
    def test_01_pagamento_fornitore(self):
        p = ST["p"]
        body = {"data": TODAY.isoformat(), "causale": "PG", "descrizione": "TEST_pagamento",
                "righe": [{"conto": p["fornitori"], "dare": 300, "avere": 0, "party_id": ST["forn"]}, {"conto": p["banca"], "dare": 0, "avere": 300}],
                "saldaconto": [{"invoice_id": ST["pas"], "importo": 300, "passivo": True}]}
        r = sess().post(f"{API}/contabilita/registrazioni", json=body)
        assert r.status_code == 200, r.text
        ST["regp"] = r.json()["id"]
        d = sess().get(f"{API}/scadenzario-passivo", params={"party_id": ST["forn"]}).json()
        assert d["rate"][0]["residuo_documento"] == 274.93
        pp = mongo(f'print(db.passive_payments.findOne({{company_id:"{ST["cid"]}", coge_entry_id:"{ST["regp"]}"}}).id)')
        r = sess().delete(f"{API}/passive-pagamenti/{pp}")
        assert r.status_code == 400, r.text
        # passivo on an Avere-fornitori line (wrong side) -> rejected
        bad = {**body, "righe": [{"conto": p["banca"], "dare": 10, "avere": 0}, {"conto": p["fornitori"], "dare": 0, "avere": 10, "party_id": ST["forn"]}],
               "saldaconto": [{"invoice_id": ST["pas"], "importo": 10, "passivo": True}]}
        assert sess().post(f"{API}/contabilita/registrazioni", json=bad).status_code == 400
        assert sess().delete(f"{API}/contabilita/registrazioni/{ST['regp']}").status_code == 200
        d = sess().get(f"{API}/scadenzario-passivo", params={"party_id": ST["forn"]}).json()
        assert d["rate"][0]["residuo_documento"] == 574.93

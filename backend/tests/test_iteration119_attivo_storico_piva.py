# Iteration 119: Disattiva invece di cancellare (parties/articles/codici IVA), storicizzazione ragione sociale/indirizzo
# con variazione_dal, cambio partita IVA -> nuova anagrafica + vecchia sospesa.
# Run: pytest tests/test_iteration119_attivo_storico_piva.py -v -n 0 -s   (T119_KEEP=1 keeps data for UI tests)
import json
import os
import random
import sys
from datetime import date

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

RUN = os.environ.get("T119_RUN", str(random.randint(100000, 999999)))
TOK, UID = f"test_session_t119_admin_{RUN}", f"test-user-t119-admin-{RUN}"
PIVA = "19" + RUN + "119"
ST = {}
Y = date.today().year
COLLS = ["invoices", "passive_invoices", "parties", "articles", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "audit_log", "partite_aperte", "counters", "ddts", "orders", "stampe_fiscali", "stock_moves", "intenti"]


def sess():
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {TOK}", "X-Requested-With": "invoix"})
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{partita_iva:"{PIVA}"}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def rpiva():
    return "".join(str(random.randint(0, 9)) for _ in range(11))


def pbody(tipo, name, pi=None, **kw):
    pi = pi or rpiva()
    return {"tipo": tipo, "denominazione": name, "partita_iva": pi, "codice_fiscale": pi, "indirizzo": "Via Verdi 1", "cap": "20100", "comune": "Milano",
            "provincia": "MI", "nazione": "IT", "codice_destinatario": "0000000", **kw}


def party(tipo, name):
    b = pbody(tipo, name)
    r = sess().post(f"{API}/parties", json=b)
    assert r.status_code == 200, r.text
    ST.setdefault("bodies", {})[r.json()["id"]] = b
    return r.json()["id"]


def get_party(pid):
    return next((p for p in sess().get(f"{API}/parties", params={"tutti": True}).json() if p["id"] == pid), None)


def inv(pid, data):
    return sess().post(f"{API}/invoices", json={"tipo_documento": "TD01", "data": data, "party_id": pid, "modalita_pagamento": "MP05", "scadenza": f"{Y}-12-31",
                                               "lines": [{"descrizione": "TEST_T119 servizio", "quantita": 1, "prezzo_unitario": 100, "aliquota": 22}]})


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t119.admin.{RUN}@example.com", name:"TEST_T119 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": "TEST_T119 Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    assert sess().put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                                   "corrispettivi": True, "contabilita": True}).status_code == 200
    sess().get(f"{API}/contabilita/conti")
    ST["cli"] = party("cliente", "TEST_T119 Cliente Vecchio")       # movimentato (variazioni)
    ST["cli2"] = party("cliente", "TEST_T119 Cliente Nuovo")        # non movimentato
    ST["cli3"] = party("cliente", "TEST_T119 Cliente PIVA")         # movimentato (cambio piva)
    ST["cli4"] = party("cliente", "TEST_T119 Cliente Attivo")       # disattiva
    r = sess().post(f"{API}/articles", json={"codice": f"T119{RUN}", "descrizione": "TEST_T119 art", "prezzo": 10, "aliquota": 22})
    assert r.status_code == 200, r.text
    ST["art"] = r.json()["id"]
    yield
    if os.environ.get("T119_KEEP"):
        print("\nKEEP", RUN, ST["cid"], TOK, json.dumps({k: v for k, v in ST.items() if k != "bodies"}))
    else:
        clean()


class TestAttivo:
    def test_01_party_disattiva_list(self):
        pid = ST["cli4"]
        r = sess().put(f"{API}/parties/{pid}/attivo", json={"attivo": False})
        assert r.status_code == 200 and r.json()["attivo"] is False, r.text
        ids = [p["id"] for p in sess().get(f"{API}/parties").json()]
        assert pid not in ids
        assert pid not in [p["id"] for p in sess().get(f"{API}/parties", params={"tipo": "cliente"}).json()]
        assert get_party(pid)["attivo"] is False

    def test_02_invoice_disattivato_400(self):
        r = inv(ST["cli4"], f"{Y}-01-10")
        assert r.status_code == 400 and "disattivato" in r.text.lower(), r.text

    def test_03_riattiva(self):
        pid = ST["cli4"]
        r = sess().put(f"{API}/parties/{pid}/attivo", json={"attivo": True})
        assert r.status_code == 200, r.text
        assert pid in [p["id"] for p in sess().get(f"{API}/parties").json()]
        r = inv(pid, f"{Y}-01-02")
        assert r.status_code == 200, r.text
        ST["inv4"] = r.json()["id"]

    def test_04_update_invoice_disattivato_400(self):
        sess().put(f"{API}/parties/{ST['cli4']}/attivo", json={"attivo": False})
        i = sess().get(f"{API}/invoices/{ST['inv4']}").json()
        r = sess().put(f"{API}/invoices/{ST['inv4']}", json={"tipo_documento": "TD01", "data": i["data"], "party_id": ST["cli4"], "modalita_pagamento": "MP05",
                                                              "scadenza": f"{Y}-12-31", "lines": [{"descrizione": "x", "quantita": 1, "prezzo_unitario": 100, "aliquota": 22}]})
        assert r.status_code == 400 and "disattivato" in r.text.lower(), r.text
        sess().put(f"{API}/parties/{ST['cli4']}/attivo", json={"attivo": True})

    def test_05_attivo_404_and_validation(self):
        assert sess().put(f"{API}/parties/nope/attivo", json={"attivo": False}).status_code == 404
        assert sess().put(f"{API}/parties/{ST['cli4']}/attivo", json={}).status_code == 422
        assert sess().put(f"{API}/articles/nope/attivo", json={"attivo": False}).status_code == 404

    def test_06_article(self):
        aid = ST["art"]
        assert sess().put(f"{API}/articles/{aid}/attivo", json={"attivo": False}).status_code == 200
        assert aid not in [a["id"] for a in sess().get(f"{API}/articles").json()]
        a = next(a for a in sess().get(f"{API}/articles", params={"tutti": True}).json() if a["id"] == aid)
        assert a["attivo"] is False
        assert sess().put(f"{API}/articles/{aid}/attivo", json={"attivo": True}).status_code == 200
        assert aid in [a["id"] for a in sess().get(f"{API}/articles").json()]

    def test_07_codice_iva(self):
        rows = sess().get(f"{API}/contabilita/codici-iva").json()
        assert rows, "no seeded codici iva"
        x = rows[-1]
        assert sess().put(f"{API}/contabilita/codici-iva/{x['id']}/attivo", json={"attivo": False}).status_code == 200
        assert x["id"] not in [r["id"] for r in sess().get(f"{API}/contabilita/codici-iva").json()]
        assert x["id"] in [r["id"] for r in sess().get(f"{API}/contabilita/codici-iva", params={"tutti": True}).json()]
        assert sess().put(f"{API}/contabilita/codici-iva/{x['id']}/attivo", json={"attivo": True}).status_code == 200
        assert x["id"] in [r["id"] for r in sess().get(f"{API}/contabilita/codici-iva").json()]
        assert sess().put(f"{API}/contabilita/codici-iva/nope/attivo", json={"attivo": False}).status_code == 404


class TestStorico:
    def test_10_make_movimentato(self):
        r = inv(ST["cli"], f"{Y}-01-03")
        assert r.status_code == 200, r.text
        ST["inv_old"] = r.json()["id"]
        assert r.json()["cliente"]["denominazione"] == "TEST_T119 Cliente Vecchio"

    def test_11_variazione_requires_date(self):
        b = {**ST["bodies"][ST["cli"]], "denominazione": "TEST_T119 Cliente Rinominato", "indirizzo": "Via Nuova 2"}
        r = sess().put(f"{API}/parties/{ST['cli']}", json=b)
        assert r.status_code == 400 and "variazione_dal" in r.text, r.text

    def test_12_variazione_saved(self):
        b = {**ST["bodies"][ST["cli"]], "denominazione": "TEST_T119 Cliente Rinominato", "indirizzo": "Via Nuova 2", "variazione_dal": f"{Y}-03-01"}
        r = sess().put(f"{API}/parties/{ST['cli']}", json=b)
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["denominazione"] == "TEST_T119 Cliente Rinominato" and p["indirizzo"] == "Via Nuova 2"
        assert "variazione_dal" not in p
        st = p["storico"]
        assert len(st) == 1 and st[0]["valido_al"] in (f"{Y}-02-28", f"{Y}-02-29")
        assert st[0]["denominazione"] == "TEST_T119 Cliente Vecchio" and st[0]["indirizzo"] == "Via Verdi 1" and st[0]["comune"] == "Milano"
        ST["bodies"][ST["cli"]] = {k: v for k, v in b.items() if k != "variazione_dal"}

    def test_13_existing_invoice_unchanged(self):
        i = sess().get(f"{API}/invoices/{ST['inv_old']}").json()
        assert i["cliente"]["denominazione"] == "TEST_T119 Cliente Vecchio" and i["cliente"]["indirizzo"] == "Via Verdi 1"

    def test_14_new_invoice_before_date_old_data(self):
        r = inv(ST["cli"], f"{Y}-02-10")
        assert r.status_code == 200, r.text
        c = r.json()["cliente"]
        assert c["denominazione"] == "TEST_T119 Cliente Vecchio" and c["indirizzo"] == "Via Verdi 1", c
        r = inv(ST["cli"], f"{Y}-02-28")
        assert r.status_code == 200 and r.json()["cliente"]["denominazione"] == "TEST_T119 Cliente Vecchio", r.text

    def test_15_new_invoice_after_date_new_data(self):
        r = inv(ST["cli"], f"{Y}-03-01")
        assert r.status_code == 200, r.text
        c = r.json()["cliente"]
        assert c["denominazione"] == "TEST_T119 Cliente Rinominato" and c["indirizzo"] == "Via Nuova 2", c
        ST["inv_new"] = r.json()["id"]

    def test_16_update_invoice_redates_snapshot(self):
        # update the Feb invoice to a Jan date -> snapshot should follow the date
        i = sess().get(f"{API}/invoices/{ST['inv_new']}").json()
        r = sess().put(f"{API}/invoices/{ST['inv_new']}", json={"tipo_documento": "TD01", "data": f"{Y}-02-28", "party_id": ST["cli"], "modalita_pagamento": "MP05",
                                                                 "scadenza": f"{Y}-12-31", "lines": [{"descrizione": "x", "quantita": 1, "prezzo_unitario": 100, "aliquota": 22}]},
                       headers={"If-Match": str(i.get("version") or "")} if i.get("version") else {})
        assert r.status_code == 200, r.text
        assert r.json()["cliente"]["denominazione"] == "TEST_T119 Cliente Vecchio"

    def test_17_second_variation_must_be_later(self):
        b = {**ST["bodies"][ST["cli"]], "indirizzo": "Via Terza 3", "variazione_dal": f"{Y}-03-01"}
        r = sess().put(f"{API}/parties/{ST['cli']}", json=b)
        assert r.status_code == 400 and "variazione_dal" in r.text, r.text
        b["variazione_dal"] = f"{Y}-02-15"
        assert sess().put(f"{API}/parties/{ST['cli']}", json=b).status_code == 400
        b["variazione_dal"] = f"{Y}-05-01"
        r = sess().put(f"{API}/parties/{ST['cli']}", json=b)
        assert r.status_code == 200, r.text
        st = r.json()["storico"]
        assert len(st) == 2 and st[1]["valido_al"] == f"{Y}-04-30"
        assert st[1]["indirizzo"] == "Via Nuova 2" and st[1]["denominazione"] == "TEST_T119 Cliente Rinominato"
        # 3 epochs
        assert inv(ST["cli"], f"{Y}-04-10").json()["cliente"]["indirizzo"] == "Via Nuova 2"
        assert inv(ST["cli"], f"{Y}-05-10").json()["cliente"]["indirizzo"] == "Via Terza 3"

    def test_18_non_field_change_no_date(self):
        b = {**ST["bodies"][ST["cli"]], "indirizzo": "Via Terza 3", "email": "test_t119@example.com"}
        r = sess().put(f"{API}/parties/{ST['cli']}", json=b)
        assert r.status_code == 200, r.text
        assert len(r.json()["storico"]) == 2

    def test_19_non_movimentato_no_date_no_storico(self):
        b = {**ST["bodies"][ST["cli2"]], "denominazione": "TEST_T119 Cliente Nuovo Bis", "indirizzo": "Via X 9"}
        r = sess().put(f"{API}/parties/{ST['cli2']}", json=b)
        assert r.status_code == 200, r.text
        assert r.json()["denominazione"] == "TEST_T119 Cliente Nuovo Bis" and not r.json().get("storico")

    def test_20_invalid_date_format(self):
        b = {**ST["bodies"][ST["cli"]], "indirizzo": "Via Quarta 4", "variazione_dal": "01/04/2026"}
        assert sess().put(f"{API}/parties/{ST['cli']}", json=b).status_code == 422


class TestPiva:
    def test_30_non_movimentato_piva_update(self):
        npi = rpiva()
        b = {**ST["bodies"][ST["cli2"]], "partita_iva": npi}
        r = sess().put(f"{API}/parties/{ST['cli2']}", json=b)
        assert r.status_code == 200, r.text
        assert r.json()["id"] == ST["cli2"] and r.json()["partita_iva"] == npi and not r.json().get("nuova_anagrafica")

    def test_31_movimentato_piva_creates_new(self):
        assert inv(ST["cli3"], f"{Y}-06-01").status_code == 200
        old = ST["cli3"]
        npi = rpiva()
        b = {**ST["bodies"][old], "partita_iva": npi, "denominazione": "TEST_T119 Cliente PIVA Nuova"}
        r = sess().put(f"{API}/parties/{old}", json=b)
        assert r.status_code == 200, r.text
        n = r.json()
        assert n["nuova_anagrafica"] is True and n["id"] != old and n["sostituisce_id"] == old and n["partita_iva"] == npi
        assert n["denominazione"] == "TEST_T119 Cliente PIVA Nuova"
        ST["cli3_new"] = n["id"]
        o = get_party(old)
        assert o["attivo"] is False and o["sospeso"] is True and o["sostituito_da"] == n["id"] and npi in o["sospeso_motivo"]
        assert o["partita_iva"] == ST["bodies"][old]["partita_iva"] and o["denominazione"] == "TEST_T119 Cliente PIVA"
        ids = [p["id"] for p in sess().get(f"{API}/parties").json()]
        assert old not in ids and n["id"] in ids

    def test_32_old_invoice_still_linked_and_blocked(self):
        assert inv(ST["cli3"], f"{Y}-06-02").status_code == 400
        assert inv(ST["cli3_new"], f"{Y}-06-02").status_code == 200

    def test_33_riattiva_sospeso_clears_sospeso(self):
        r = sess().put(f"{API}/parties/{ST['cli3']}/attivo", json={"attivo": True})
        assert r.status_code == 200
        o = get_party(ST["cli3"])
        assert o.get("attivo") is True and not o.get("sospeso"), o

    def test_34_delete_movimentato_message(self):
        r = sess().delete(f"{API}/parties/{ST['cli']}")
        assert r.status_code == 400 and "movimentat" in r.text.lower(), r.text

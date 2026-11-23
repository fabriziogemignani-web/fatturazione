# Iteration 123: party storicization only for fiscal fields (denominazione/nome/cognome/indirizzo/cap/comune/provincia).
# Non-fiscal changes (telefono, email, pec, iban, pagamento, nazione) on a movimentato party must save without variazione_dal.
# Run: pytest tests/test_iteration123_party_storico_fiscali.py -v -n 0 -s   (T123_KEEP=1 keeps data for UI tests, writes /tmp/t123.json)
import json
import os
import random
import sys
from datetime import date

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

RUN = os.environ.get("T123_RUN", str(random.randint(100000, 999999)))
TOK, UID = f"test_session_t123_admin_{RUN}", f"test-user-t123-admin-{RUN}"
PIVA = "23" + RUN + "123"
ST = {}
Y = date.today().year
COLLS = ["invoices", "passive_invoices", "parties", "articles", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "audit_log", "partite_aperte", "counters", "ddts", "orders", "stampe_fiscali", "stock_moves", "intenti"]


def sess(ver=None):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {TOK}", "X-Requested-With": "invoix"})
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    if ver is not None:
        s.headers["If-Match"] = str(ver)
    return s


def clean():
    mongo(f'db.companies.find({{partita_iva:"{PIVA}"}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def rpiva():
    return "".join(str(random.randint(0, 9)) for _ in range(11))


def pbody(tipo, name, **kw):
    pi = rpiva()
    return {"tipo": tipo, "denominazione": name, "partita_iva": pi, "codice_fiscale": pi, "indirizzo": "Via Verdi 1", "cap": "20100", "comune": "Milano",
            "provincia": "MI", "nazione": "IT", "codice_destinatario": "0000000", **kw}


def get_party(pid):
    return next((p for p in sess().get(f"{API}/parties", params={"tutti": True}).json() if p["id"] == pid), None)


def put(pid, body):
    cur = get_party(pid)
    return sess(cur.get("version") or 0).put(f"{API}/parties/{pid}", json=body)


def mk(tipo, name, **kw):
    b = pbody(tipo, name, **kw)
    r = sess().post(f"{API}/parties", json=b)
    assert r.status_code == 200, r.text
    ST.setdefault("bodies", {})[r.json()["id"]] = b
    return r.json()["id"]


def inv(pid, data):
    return sess().post(f"{API}/invoices", json={"tipo_documento": "TD01", "data": data, "party_id": pid, "modalita_pagamento": "MP05", "scadenza": f"{Y}-12-31",
                                               "lines": [{"descrizione": "TEST_T123 servizio", "quantita": 1, "prezzo_unitario": 100, "aliquota": 22}]})


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t123.admin.{RUN}@example.com", name:"TEST_T123 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": "TEST_T123 Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    assert sess().put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                                   "corrispettivi": True, "contabilita": True}).status_code == 200
    ST["cli"] = mk("cliente", "TEST_T123 Cliente Mov")           # movimentato: non-fiscal + fiscal changes
    ST["cli_nonaz"] = mk("cliente", "TEST_T123 Cliente NoNaz")   # movimentato, nazione removed in DB
    ST["pf"] = mk("cliente", "", persona="fisica", nome="Mario", cognome="Rossi")  # persona fisica movimentata
    ST["forn"] = mk("fornitore", "TEST_T123 Fornitore Storico")  # for UI: storico with 2 rows
    ST["forn_ui"] = mk("fornitore", "TEST_T123 Fornitore UI")    # for UI: non-fiscal change, no storico
    for k in ("cli", "cli_nonaz", "pf"):
        r = inv(ST[k], f"{Y}-01-05")
        assert r.status_code == 200, r.text
    for k in ("forn", "forn_ui"):  # make suppliers movimentato with a minimal passive invoice marker
        mongo(f'db.passive_invoices.insertOne({{id:"t123-pi-{RUN}-{k}", company_id:"{ST["cid"]}", party_id:"{ST[k]}", numero:"TEST_T123_{k}", hash:"t123-{RUN}-{k}", data:"{Y}-01-05"}})')
    mongo(f'db.parties.updateOne({{id:"{ST["cli_nonaz"]}"}}, {{$unset:{{nazione:""}}}})')
    yield
    if os.environ.get("T123_KEEP"):
        with open("/tmp/t123.json", "w") as f:
            json.dump({"run": RUN, "tok": TOK, **{k: v for k, v in ST.items() if k != "bodies"}}, f)
        print("\nKEEP", RUN, ST["cid"], TOK)
    else:
        clean()


class TestNonFiscali:
    def test_01_non_fiscal_change_no_variazione(self):
        pid = ST["cli"]
        b = {**ST["bodies"][pid], "telefono": "0551234567", "email": "test.t123@example.com", "pec": "test.t123@pec.example.com",
             "iban": "IT60X0542811101000000123456", "pagamento_modalita": "MP05", "pagamento_giorni": 60}
        r = put(pid, b)
        assert r.status_code == 200, r.text
        p = get_party(pid)
        assert p["telefono"] == "0551234567" and p["email"] == "test.t123@example.com" and p["pec"] == "test.t123@pec.example.com"
        assert p["iban"] == "IT60X0542811101000000123456" and p["pagamento_giorni"] == 60
        assert not p.get("storico")
        ST["bodies"][pid] = b

    def test_02_nazione_change_no_variazione(self):
        pid = ST["cli"]
        b = {**ST["bodies"][pid], "nazione": "SM"}
        r = put(pid, b)
        assert r.status_code == 200, r.text
        assert get_party(pid)["nazione"] == "SM" and not get_party(pid).get("storico")
        b["nazione"] = "IT"
        assert put(pid, b).status_code == 200
        ST["bodies"][pid] = b

    def test_03_case_whitespace_no_variazione(self):
        pid = ST["cli"]
        b = {**ST["bodies"][pid], "denominazione": "  test_t123 cliente mov ", "indirizzo": "VIA VERDI 1", "comune": "milano ", "provincia": "mi"}
        r = put(pid, b)
        assert r.status_code == 200, r.text
        assert not get_party(pid).get("storico")

    def test_04_missing_nazione_party_non_fiscal(self):
        pid = ST["cli_nonaz"]
        assert "nazione" not in get_party(pid)
        b = {**ST["bodies"][pid], "telefono": "0559999999"}
        r = put(pid, b)
        assert r.status_code == 200, r.text
        assert not get_party(pid).get("storico")


class TestFiscali:
    @pytest.mark.parametrize("field,val", [("denominazione", "TEST_T123 Cliente Nuovo Nome"), ("indirizzo", "Via Nuova 9"), ("cap", "20121"),
                                           ("comune", "Monza"), ("provincia", "MB")])
    def test_10_fiscal_requires_date(self, field, val):
        pid = ST["cli"]
        r = put(pid, {**ST["bodies"][pid], field: val})
        assert r.status_code == 400 and "variazione_dal" in r.text, f"{field}: {r.status_code} {r.text}"

    def test_11_fiscal_with_date_pushes_storico(self):
        pid = ST["cli"]
        b = {**ST["bodies"][pid], "denominazione": "TEST_T123 Cliente Nuovo Nome", "variazione_dal": f"{Y}-03-01"}
        r = put(pid, b)
        assert r.status_code == 200, r.text
        p = get_party(pid)
        assert p["denominazione"] == "TEST_T123 Cliente Nuovo Nome"
        assert len(p["storico"]) == 1 and p["storico"][0]["denominazione"].strip().upper() == "TEST_T123 CLIENTE MOV"  # test_03 saved a case variant
        assert p["storico"][0]["valido_al"] in (f"{Y}-02-28", f"{Y}-02-29")

    def test_12_persona_fisica_nome_requires_date(self):
        pid = ST["pf"]
        r = put(pid, {**ST["bodies"][pid], "nome": "Luigi"})
        assert r.status_code == 400 and "variazione_dal" in r.text, r.text
        r = put(pid, {**ST["bodies"][pid], "telefono": "0551111111"})
        assert r.status_code == 200, r.text

    def test_13_storico_two_rows_for_ui(self):
        pid = ST["forn"]
        b = ST["bodies"][pid]
        assert put(pid, {**b, "indirizzo": "Via Seconda 2", "variazione_dal": f"{Y}-02-01"}).status_code == 200
        r = put(pid, {**b, "indirizzo": "Via Terza 3", "variazione_dal": f"{Y}-04-15"})
        assert r.status_code == 200, r.text
        st = sorted(get_party(pid)["storico"], key=lambda s: s["valido_al"])
        assert [s["valido_al"] for s in st] == [f"{Y}-01-31", f"{Y}-04-14"]
        assert [s["indirizzo"] for s in st] == ["Via Verdi 1", "Via Seconda 2"]

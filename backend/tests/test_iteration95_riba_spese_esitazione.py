# Iteration 95: Ri.Ba. bank fees (spese_emissione / spese_insoluto on company banks), client flag riba_spese_addebito,
# distinta prima nota with emission fees, /riba/scaduti?in_scadenza=true, /riba/insoluti default fees from bank.
# Run: pytest tests/test_iteration95_riba_spese_esitazione.py -v -n 0
import json
import os
import random
import sys
from datetime import date, timedelta

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

RUN = str(random.randint(100000, 999999))
TOK, UID = f"test_session_t95_{RUN}", f"test-user-t95-{RUN}"
PIVA = "95" + RUN + "951"
IBAN = "IT60X0542811101000000123456"
IBAN2 = "IT61X0306909606100000012345"
T = date.today()
d = lambda n: (T + timedelta(days=n)).isoformat()  # noqa: E731
ST = {}
COLLS = ["invoices", "passive_invoices", "parties", "articles", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "riba_distinte", "riba_effetti", "partite_aperte"]
NAME = f"TEST_T95 Riba {RUN} Srl"


def sess():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{denominazione:"{NAME}"}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def client(name, piva, flag):
    r = sess().post(f"{API}/parties", json={"tipo": "cliente", "denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "codice_destinatario": "ABC1234",
                                           "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT",
                                           "appoggio_banca": "TEST Intesa", "appoggio_abi": "03069", "appoggio_cab": "09606", "riba_spese_addebito": flag})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def inv(pid, data, rate):
    s = sess()
    r = s.post(f"{API}/invoices", json={"tipo_documento": "TD01", "data": data, "party_id": pid, "modalita_pagamento": "MP12", "scadenza": rate[-1][0],
                                        "rate": [{"scadenza": a, "importo": b} for a, b in rate],
                                        "lines": [{"descrizione": "TEST_riga", "quantita": 1, "prezzo_unitario": 100, "aliquota": 22}]})
    assert r.status_code == 200, r.text
    iid = r.json()["id"]
    assert s.post(f"{API}/invoices/{iid}/send").status_code == 200
    assert s.post(f"{API}/invoices/{iid}/refresh").status_code == 200
    return iid


def getp(pid):
    return next(x for x in sess().get(f"{API}/parties").json() if x["id"] == pid)


def entries(origine, ref):
    q = {"company_id": ST["cid"], "origine": origine, "ref_id": ref}
    return json.loads(mongo(f'print(JSON.stringify(db.coa_entries.find({json.dumps(q)},{{_id:0}}).toArray()))') or "[]")


def side(e, conto):
    rows = [r for r in e["righe"] if r["conto"] == conto]
    return round(sum(r.get("dare") or 0 for r in rows), 2), round(sum(r.get("avere") or 0 for r in rows), 2)


BANKS = [{"nome": "TEST Banca Uno", "iban": IBAN, "abi": "05428", "cab": "11101", "sia": "A1B2C", "predefinita": True, "spese_emissione": 2.5, "spese_insoluto": 7},
         {"nome": "TEST Banca Due", "iban": IBAN2, "abi": "03069", "cab": "09606", "sia": "Z9Y8X", "spese_emissione": 0, "spese_insoluto": 0}]


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t95.{RUN}@example.com", name:"TEST_T95 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": NAME, "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    sess().put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                            "corrispettivi": True, "contabilita": True})
    yield
    if os.environ.get("T95_KEEP"):
        print("\nKEEP", RUN, ST["cid"], TOK)
    else:
        clean()


class TestBanks:
    def test_01_negative_rejected(self):
        s = sess()
        c = s.get(f"{API}/company").json()
        for k in ("spese_emissione", "spese_insoluto"):
            c["banche"] = [{**BANKS[0], k: -1}]
            r = s.put(f"{API}/company", json=c)
            assert r.status_code == 422, (k, r.status_code, r.text[:200])

    def test_02_save_reload(self):
        s = sess()
        c = s.get(f"{API}/company").json()
        c["banche"] = BANKS
        r = s.put(f"{API}/company", json=c)
        assert r.status_code == 200, r.text
        b = {x["iban"]: x for x in s.get(f"{API}/company").json()["banche"]}
        assert b[IBAN]["spese_emissione"] == 2.5 and b[IBAN]["spese_insoluto"] == 7, b[IBAN]
        assert b[IBAN2]["spese_emissione"] == 0


class TestParty:
    def test_01_flag(self):
        ST["A"] = client("TEST_T95 Cliente A Srl", "01234567890", True)
        ST["B"] = client("TEST_T95 Cliente B Srl", "09876543217", False)
        a = getp(ST["A"])
        b = getp(ST["B"])
        assert a["riba_spese_addebito"] is True and b.get("riba_spese_addebito") is False, (a.get("riba_spese_addebito"), b.get("riba_spese_addebito"))

    def test_02_flag_update(self):
        s = sess()
        p = getp(ST["B"])
        p["riba_spese_addebito"] = True
        assert s.put(f"{API}/parties/{ST['B']}", json=p).status_code == 200
        assert getp(ST["B"])["riba_spese_addebito"] is True
        p["riba_spese_addebito"] = False
        assert s.put(f"{API}/parties/{ST['B']}", json=p).status_code == 200
        assert getp(ST["B"])["riba_spese_addebito"] is False


class TestDistinta:
    def test_01_create_with_spese(self):
        ST["Q"] = inv(ST["A"], d(-60), [(d(-30), 50), (d(-20), 72)])
        ST["R"] = inv(ST["B"], d(-45), [(d(-15), 122)])
        ST["S"] = inv(ST["A"], d(-45), [(d(-12), 122)])
        ST["F"] = inv(ST["A"], d(-45), [(d(30), 122)])
        keys = [f"{ST['Q']}:1", f"{ST['Q']}:2", f"{ST['R']}:1", f"{ST['S']}:1", f"{ST['F']}:1"]
        r = sess().post(f"{API}/riba/distinte", json={"banca_iban": IBAN, "data": d(-40), "effetti": keys})
        assert r.status_code == 200, r.text
        j = r.json()
        ST["D"] = j["id"]
        assert j["spese_emissione"] == 12.5, j
        assert sess().get(f"{API}/riba/distinte/{ST['D']}").json().get("spese_emissione") == 12.5
        eff = sess().get(f"{API}/riba/distinte/{ST['D']}").json()["effetti"]
        ST["E"] = {(e["invoice_id"], e["rata_n"]): e["id"] for e in eff}

    def test_02_prima_nota_rb(self):
        en = entries("riba", ST["D"])
        assert len(en) == 1, en
        e = en[0]
        assert e["causale"] == "RB"
        assert side(e, "30.07.011") == (12.5, 0), e["righe"]
        dare = round(sum(r.get("dare") or 0 for r in e["righe"]), 2)
        avere = round(sum(r.get("avere") or 0 for r in e["righe"]), 2)
        assert dare == avere
        # bank default (parametro banca) 06.01.001: dare totale, avere spese
        assert side(e, "06.01.001") == (488.0, 12.5), e["righe"]

    def test_03_no_spese_bank2_conto_coge(self):
        s = sess()
        c = s.get(f"{API}/company").json()
        for b in c["banche"]:
            if b["iban"] == IBAN2:
                b["spese_emissione"] = 1
                b["conto_coge"] = "06.01.002"
        r = s.put(f"{API}/company", json=c)
        assert r.status_code == 200, r.text
        ST["G"] = inv(ST["B"], d(-10), [(d(20), 122)])
        r = s.post(f"{API}/riba/distinte", json={"banca_iban": IBAN2, "data": d(-5), "effetti": [f"{ST['G']}:1"]})
        assert r.status_code == 200, r.text
        ST["D2"] = r.json()["id"]
        e = entries("riba", ST["D2"])
        assert len(e) == 1, e
        print("D2 righe", e[0]["righe"])
        assert side(e[0], "30.07.011") == (1, 0), e[0]["righe"]
        assert side(e[0], "06.01.002") == (122, 1), e[0]["righe"]
        assert side(e[0], "06.01.001") == (0, 0), e[0]["righe"]


class TestScaduti:
    def test_01_in_scadenza(self):
        r = sess().get(f"{API}/riba/scaduti", params={"in_scadenza": "true"})
        assert r.status_code == 200, r.text
        st = {x["id"]: x["stato"] for x in r.json()}
        E = ST["E"]
        for k in [(ST["Q"], 1), (ST["Q"], 2), (ST["R"], 1), (ST["S"], 1)]:
            assert st.get(E[k]) == "maturato", (k, st)
        assert st.get(E[(ST["F"], 1)]) == "presentato", st
        r2 = sess().get(f"{API}/riba/scaduti").json()
        assert E[(ST["F"], 1)] not in {x["id"] for x in r2} and all(x["stato"] == "maturato" for x in r2)


class TestInsoluti:
    def test_01_defaults_flagged_and_unflagged(self):
        E = ST["E"]
        r = sess().post(f"{API}/riba/insoluti", json={"effetti": [E[(ST["Q"], 1)], E[(ST["R"], 1)]], "data": d(-5), "giorni": 30,
                                                    "spese_banca": None, "spese_cliente": None})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["registrati"] == 2 and not j["errori"], j

    def test_02_entries_flagged(self):
        eid = ST["E"][(ST["Q"], 1)]
        en = entries("riba_insoluto", eid)
        assert len(en) == 1, en
        e = en[0]
        assert e["causale"] == "RI"
        assert side(e, "30.07.011") == (7, 0), e["righe"]
        assert side(e, "20.05.001") == (0, 7), e["righe"]
        assert side(e, "05.01.001") == (57, 0), e["righe"]
        assert side(e, "06.01.001") == (0, 57), e["righe"]
        p = json.loads(mongo(f'print(JSON.stringify(db.partite_aperte.find({{company_id:"{ST["cid"]}", riba_effetto_id:"{eid}"}},{{_id:0}}).toArray()))'))
        assert len(p) == 1 and p[0]["totale"] == 7 and p[0]["numero_display"].startswith("Spese insoluto"), p
        ins = sess().get(f"{API}/riba/distinte/{ST['D']}").json()["effetti"]
        x = next(z for z in ins if z["id"] == eid)
        assert x["insoluto"]["spese_banca"] == 7 and x["insoluto"]["spese_cliente"] == 7, x["insoluto"]

    def test_03_entries_unflagged(self):
        eid = ST["E"][(ST["R"], 1)]
        e = entries("riba_insoluto", eid)[0]
        assert side(e, "30.07.011") == (7, 0), e["righe"]
        assert side(e, "20.05.001") == (0, 0), e["righe"]
        assert side(e, "05.01.001") == (122, 0) and side(e, "06.01.001") == (0, 129), e["righe"]
        n = mongo(f'print(db.partite_aperte.countDocuments({{company_id:"{ST["cid"]}", riba_effetto_id:"{eid}"}}))')
        assert n == "0", n

    def test_04_explicit_override(self):
        eid = ST["E"][(ST["S"], 1)]
        r = sess().post(f"{API}/riba/insoluti", json={"effetti": [eid], "data": d(-3), "spese_banca": 1.5, "spese_cliente": 0})
        assert r.status_code == 200 and r.json()["registrati"] == 1, r.text
        e = entries("riba_insoluto", eid)[0]
        assert side(e, "30.07.011") == (1.5, 0) and side(e, "20.05.001") == (0, 0), e["righe"]
        n = mongo(f'print(db.partite_aperte.countDocuments({{company_id:"{ST["cid"]}", riba_effetto_id:"{eid}"}}))')
        assert n == "0", n

    def test_05_single_endpoint_defaults(self):
        eid = ST["E"][(ST["Q"], 2)]
        r = sess().post(f"{API}/riba/effetti/{eid}/insoluto", json={"data": d(-1), "nuova_scadenza": d(30)})
        assert r.status_code == 200, r.text
        e = entries("riba_insoluto", eid)[0]
        assert side(e, "30.07.011") == (7, 0) and side(e, "20.05.001") == (0, 7), e["righe"]
        s1 = round(sum(r.get("dare") or 0 for r in e["righe"]), 2)
        s2 = round(sum(r.get("avere") or 0 for r in e["righe"]), 2)
        assert s1 == s2

    def test_06_negative_spese_422(self):
        r = sess().post(f"{API}/riba/insoluti", json={"effetti": ["x"], "data": d(0), "spese_banca": -1})
        assert r.status_code == 422

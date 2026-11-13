# Iteration 72: Ri.Ba. insoluti in blocco (/api/riba/scaduti, /api/riba/insoluti), prima nota RI, rate reopened,
# spese cliente partita, per-effect errors, role check; bilancio contrapposte balance (attivita-passivita == risultato).
# Run: pytest tests/test_iteration72_riba_insoluti_blocco_bilancio.py -v -n 0   (T72_KEEP=1 keeps data; `python tests/<file> clean`)
import json
import os
import random
import sys
from datetime import date, timedelta

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

RUN = os.environ.get("T72_RUN") or str(random.randint(100000, 999999))
TOK, UID = "test_session_t72_admin", "test-user-t72-admin"
TOKO, UIDO = "test_session_t72_oper", "test-user-t72-oper"
PIVA = "87" + RUN + "721"
IBAN = "IT60X0542811101000000123456"
T = date.today()
d = lambda n: (T + timedelta(days=n)).isoformat()  # noqa: E731
ST = {}
COLLS = ["invoices", "passive_invoices", "parties", "articles", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "riba_distinte", "riba_effetti", "partite_aperte"]


def sess(tok=TOK):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{denominazione:/^TEST_T72/}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:["{UID}","{UIDO}"]}}}}); db.user_sessions.deleteMany({{user_id:{{$in:["{UID}","{UIDO}"]}}}});')


def client(name, piva):
    r = sess().post(f"{API}/parties", json={"tipo": "cliente", "denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "codice_destinatario": "ABC1234",
                                           "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT",
                                           "appoggio_banca": "TEST Intesa", "appoggio_abi": "03069", "appoggio_cab": "09606"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def inv(pid, data, rate, mp="MP12"):
    s = sess()
    r = s.post(f"{API}/invoices", json={"tipo_documento": "TD01", "data": data, "party_id": pid, "modalita_pagamento": mp, "scadenza": rate[-1][0],
                                        "rate": [{"scadenza": a, "importo": b} for a, b in rate],
                                        "lines": [{"descrizione": "TEST_riga", "quantita": 1, "prezzo_unitario": 100, "aliquota": 22}]})
    assert r.status_code == 200, r.text
    iid = r.json()["id"]
    assert s.post(f"{API}/invoices/{iid}/send").status_code == 200
    assert s.post(f"{API}/invoices/{iid}/refresh").status_code == 200
    return iid


def entries(origine, ref):
    q = {"company_id": ST["cid"], "origine": origine, "ref_id": ref}
    return json.loads(mongo(f'print(JSON.stringify(db.coa_entries.find({json.dumps(q)},{{_id:0}}).toArray()))') or "[]")


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t72.admin@example.com", name:"TEST_T72 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": f"TEST_T72 Insoluti {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    mongo(f'db.users.insertOne({{user_id:"{UIDO}", email:"test.user.t72.oper@example.com", name:"TEST_T72 oper", picture:"", role:"operatore", status:"approved", company_ids:["{ST["cid"]}"], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UIDO}", session_token:"{TOKO}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    sess().put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                            "corrispettivi": True, "contabilita": True})
    s = sess()
    c = s.get(f"{API}/company").json()
    c["banche"] = [{"nome": "TEST Banca Uno", "iban": IBAN, "abi": "05428", "cab": "11101", "sia": "A1B2C", "predefinita": True}]
    assert s.put(f"{API}/company", json=c).status_code == 200
    ST["A"] = client("TEST_T72 Cliente A Srl", "01234567890")
    ST["B"] = client("TEST_T72 Cliente B Srl", "09876543217")
    ST["Q"] = inv(ST["A"], d(-60), [(d(-30), 50), (d(-20), 72)])
    ST["P"] = inv(ST["A"], d(-45), [(d(-10), 122)])
    ST["R"] = inv(ST["B"], d(-45), [(d(-15), 122)])
    ST["F"] = inv(ST["B"], d(-45), [(d(30), 122)])
    r = sess().post(f"{API}/riba/distinte", json={"banca_iban": IBAN, "data": d(-40), "effetti": [f"{ST['Q']}:1", f"{ST['Q']}:2", f"{ST['P']}:1", f"{ST['R']}:1", f"{ST['F']}:1"]})
    assert r.status_code == 200, r.text
    ST["D"] = r.json()["id"]
    eff = sess().get(f"{API}/riba/distinte/{ST['D']}").json()["effetti"]
    ST["E"] = {(e["invoice_id"], e["rata_n"]): e for e in eff}
    yield
    if os.environ.get("T72_KEEP"):
        print("\nKEEP", RUN, ST["cid"])
    else:
        clean()


def eid(k, n=1):
    return ST["E"][(ST[k], n)]["id"]


# GET /api/riba/scaduti
class TestScaduti:
    def test_01_lists_maturato_only(self):
        r = sess().get(f"{API}/riba/scaduti")
        assert r.status_code == 200, r.text
        ids = {x["id"] for x in r.json()}
        assert {eid("Q"), eid("Q", 2), eid("P"), eid("R")} <= ids
        assert eid("F") not in ids
        assert all(x["stato"] == "maturato" for x in r.json())
        sc = [x["scadenza"] for x in r.json()]
        assert sc == sorted(sc, reverse=True)


# POST /api/riba/insoluti
class TestInsolutiBlocco:
    def test_01_operatore_403(self):
        r = sess(TOKO).post(f"{API}/riba/insoluti", json={"effetti": [eid("P")], "data": d(0)})
        assert r.status_code == 403, r.text

    def test_02_future_date_errors(self):
        r = sess().post(f"{API}/riba/insoluti", json={"effetti": [eid("P"), eid("R")], "data": d(2), "giorni": 10})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["registrati"] == 0 and len(j["errori"]) == 2
        assert all("futura" in x["errore"] for x in j["errori"]), j

    def test_03_before_distinta_errors(self):
        r = sess().post(f"{API}/riba/insoluti", json={"effetti": [eid("P")], "data": d(-41)})
        j = r.json()
        assert r.status_code == 200 and j["registrati"] == 0
        assert "precedere" in j["errori"][0]["errore"], j

    def test_04_invalid_calendar_date(self):
        r = sess().post(f"{API}/riba/insoluti", json={"effetti": [eid("P")], "data": "2025-02-30"})
        assert r.status_code in (400, 422), f"{r.status_code} {r.text[:200]}"

    def test_05_empty_list_422(self):
        r = sess().post(f"{API}/riba/insoluti", json={"effetti": [], "data": d(0)})
        assert r.status_code == 422

    def test_06_mixed_batch(self):
        body = {"effetti": [eid("Q"), eid("P"), eid("R"), eid("F"), "nonexistent-id"], "data": d(-5), "giorni": 30, "spese_banca": 4.5, "spese_cliente": 3}
        r = sess().post(f"{API}/riba/insoluti", json=body)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["registrati"] == 3, j
        assert j["nuova_scadenza"] == d(25)
        errs = {x["id"]: x["errore"] for x in j["errori"]}
        assert set(errs) == {eid("F"), "nonexistent-id"}, errs
        assert "scadenza" in errs[eid("F")] and "non trovato" in errs["nonexistent-id"]

    def test_07_effect_state_and_scaduti(self):
        e = sess().get(f"{API}/riba/distinte/{ST['D']}").json()["effetti"]
        st = {x["id"]: x for x in e}
        for k in ("Q", "P", "R"):
            assert st[eid(k)]["stato"] == "insoluto"
            assert st[eid(k)]["insoluto"]["nuova_scadenza"] == d(25)
            assert st[eid(k)]["insoluto"]["data"] == d(-5)
        assert st[eid("Q", 2)]["stato"] == "maturato"
        assert st[eid("F")]["stato"] == "presentato"
        ids = {x["id"] for x in sess().get(f"{API}/riba/scaduti").json()}
        assert ids == {eid("Q", 2)}

    def test_08_prima_nota_RI(self):
        en = entries("riba_insoluto", eid("P"))
        assert len(en) == 1
        x = en[0]
        assert x["causale"] == "RI" and x["data"] == d(-5)
        dare = round(sum(r.get("dare", 0) for r in x["righe"]), 2)
        avere = round(sum(r.get("avere", 0) for r in x["righe"]), 2)
        assert dare == avere == 129.5, (dare, avere, x["righe"])
        assert any(r["conto"] == "30.07.011" and r.get("dare") == 4.5 for r in x["righe"])
        assert any(r["conto"] == "20.05.001" and r.get("avere") == 3 for r in x["righe"])

    def test_09_rata_reopened_scadenzario(self):
        sc = sess().get(f"{API}/scadenzario").json()
        rp = [r for r in sc["rate"] if r["invoice_id"] == ST["P"]]
        assert rp and rp[0]["scadenza"] == d(25) and rp[0]["residuo"] == 122, rp
        rq = sorted([r for r in sc["rate"] if r["invoice_id"] == ST["Q"]], key=lambda r: r["scadenza"])
        assert any(r["scadenza"] == d(25) and r["residuo"] == 50 for r in rq), rq

    def test_10_spese_partita(self):
        n = mongo(f'print(db.partite_aperte.countDocuments({{company_id:"{ST["cid"]}", riba_effetto_id:{{$in:["{eid("Q")}","{eid("P")}","{eid("R")}"]}}, totale:3}}))')
        assert n == "3", n

    def test_11_repeat_is_error(self):
        r = sess().post(f"{API}/riba/insoluti", json={"effetti": [eid("P")], "data": d(-5)})
        j = r.json()
        assert j["registrati"] == 0 and "già" in j["errori"][0]["errore"], j

    def test_12_q2_nuova_scadenza_before_other_rata(self):
        # Q:1 is now insoluto -> Q:2 alone; giorni 0 -> nuova == data OK
        r = sess().post(f"{API}/riba/insoluti", json={"effetti": [eid("Q", 2)], "data": d(-1), "giorni": 0})
        j = r.json()
        assert r.status_code == 200 and j["registrati"] == 1, j


# Bilancio: sides of contrapposte match
class TestBilancio:
    def test_01_quadra_and_sides(self):
        r = sess().get(f"{API}/contabilita/bilancio", params={"dal": d(-400), "al": d(30)})
        assert r.status_code == 200, r.text
        b = r.json()
        assert abs(b["dare"] - b["avere"]) < 0.01
        ris = b["risultato"]
        att = b["attivita"] + (-ris if ris < 0 else 0)
        pas = b["passivita"] + (ris if ris >= 0 else 0)
        assert abs(att - pas) < 0.01, (b["attivita"], b["passivita"], ris)
        assert abs((b["costi"] + max(ris, 0)) - (b["ricavi"] + max(-ris, 0))) < 0.01
        ST["bil"] = b


if __name__ == "__main__" and sys.argv[-1] == "clean":
    clean()

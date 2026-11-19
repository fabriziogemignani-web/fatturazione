# Iteration 111: Comunicazioni ai clienti - "Clienti da sollecitare" list (GET /elenco, POST /elenco/aggiorna, POST /elenco/invia, daily auto refresh via loop_tick)
# Requires local SMTP sink on 127.0.0.1:1025 (python3 -m smtpd -n -c DebuggingServer 127.0.0.1:1025)
# Run: pytest tests/test_iteration111_solleciti_elenco.py -v -n 0   (T111_KEEP=1 keeps data for UI tests)
import json
import os
import sys
import time
from datetime import date, timedelta

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

RUN = os.environ.get("T111_RUN", "111111")
TOK, UID = f"test_session_t111_admin_{RUN}", f"test-user-t111-admin-{RUN}"
TOK2, UID2 = f"test_session_t111_op_{RUN}", f"test-user-t111-op-{RUN}"
PIVA = "19" + RUN + "111"
ST = {}
T = date.today()
D = lambda n: (T + timedelta(days=n)).isoformat()  # noqa: E731
COLLS = ["invoices", "parties", "payments", "com_log", "com_elenco", "sdi_events", "audit", "audit_log", "partite_aperte", "coa_entries", "coa_accounts",
         "coa_causali", "coa_iva", "smtp_config", "company_smtp"]


def sess(tok=TOK):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "X-Requested-With": "invoix"})
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{partita_iva:"{PIVA}"}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:["{UID}","{UID2}"]}}}}); db.user_sessions.deleteMany({{user_id:{{$in:["{UID}","{UID2}"]}}}});')


def mk_party(s, name, email, piva):
    r = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "codice_destinatario": "ABC1234",
                                       "email": email, "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def mk_inv(s, pid, data, scad, price):
    r = s.post(f"{API}/invoices", json={"tipo_documento": "TD01", "data": data, "party_id": pid, "modalita_pagamento": "MP05", "scadenza": scad,
                                        "lines": [{"descrizione": "TEST_T111 servizio", "quantita": 1, "prezzo_unitario": price, "aliquota": 22}]})
    assert r.status_code == 200, r.text
    iid = r.json()["id"]
    assert s.post(f"{API}/invoices/{iid}/send").status_code == 200
    st = s.post(f"{API}/invoices/{iid}/refresh").json().get("status")
    assert st == "consegnata", st
    return iid


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t111.admin.{RUN}@example.com", name:"TEST_T111 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": "TEST_T111 Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT", "iban": "IT60X0542811101000000123456"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    # keep the background loop from refreshing before our manual checks
    mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}}, {{$set:{{com_elenco_day:"{T.isoformat()}"}}}})')
    s = sess()
    s.put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True, "corrispettivi": True, "contabilita": True})
    assert s.put(f"{API}/company/smtp", json={"host": "127.0.0.1", "port": 1025, "security": "none", "username": "", "password": "",
                                              "from_email": "noreply@example.com", "from_name": "TEST_T111"}).status_code == 200
    ST["pa"] = mk_party(s, "TEST_T111 Cliente Alfa", "alfa111@example.com", "0123456789" + "2")
    ST["pb"] = mk_party(s, "TEST_T111 Cliente Beta", "", "1234567890" + "3")  # no email
    ST["pc"] = mk_party(s, "TEST_T111 Cliente Gamma", "gamma111@example.com", "0987654321" + "0")  # only far invoice -> not listed
    ST["i_old"] = mk_inv(s, ST["pa"], D(-40), D(-30), 1000)   # overdue 30 gg -> livello 2
    ST["i_beta"] = mk_inv(s, ST["pb"], D(-20), D(-10), 200)   # overdue 10 gg -> livello 1
    ST["i_near"] = mk_inv(s, ST["pa"], D(-1), D(3), 500)      # due in 3 days
    ST["i_far"] = mk_inv(s, ST["pc"], D(-1), D(60), 300)      # due in 60 days
    mongo(f'db.user_sessions.insertOne({{user_id:"{UID2}", session_token:"{TOK2}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});'
          f'db.users.insertOne({{user_id:"{UID2}", email:"test.user.t111.op.{RUN}@example.com", name:"TEST_T111 op", picture:"", role:"operatore", status:"approved", company_ids:["{ST["cid"]}"], created_at:new Date().toISOString()}});')
    yield
    if os.environ.get("T111_KEEP"):
        print("\nKEEP", RUN, ST["cid"], TOK, json.dumps(ST))
    else:
        clean()


def row(j, pid):
    return next((x for x in j["righe"] if x["party_id"] == pid), None)


class TestElenco:
    def test_01_first_get_computes(self):
        j = sess().get(f"{API}/comunicazioni/elenco").json()
        assert set(j) == {"righe", "stato"}
        assert j["stato"]["auto"] is False and j["stato"]["clienti"] == 2, j["stato"]
        a = row(j, ST["pa"])
        assert a and a["cliente"] == "TEST_T111 Cliente Alfa" and a["email"] == "alfa111@example.com"
        assert a["n_scadute"] == 1 and a["scaduto"] == 1220 and a["max_ritardo"] == 30 and a["livello"] == 2
        assert a["n_in_scadenza"] == 1 and a["in_scadenza"] == 610 and a["prossima_scadenza"] == D(3)
        assert a["fatture_aperte"] == 2 and a["ultimo_invio"] is None and a["auto"] is False and a["aggiornato_il"] == j["stato"]["at"]
        b = row(j, ST["pb"])
        assert b and b["email"] == "" and b["livello"] == 1 and b["in_scadenza"] == 0 and b["prossima_scadenza"] is None
        assert row(j, ST["pc"]) is None
        assert "_id" not in a and "company_id" not in a
        assert [x["scaduto"] for x in j["righe"]] == sorted([x["scaduto"] for x in j["righe"]], reverse=True)

    def test_02_get_cached(self):
        a = sess().get(f"{API}/comunicazioni/elenco").json()
        b = sess().get(f"{API}/comunicazioni/elenco").json()
        assert a["stato"]["at"] == b["stato"]["at"]

    def test_03_aggiorna(self):
        before = sess().get(f"{API}/comunicazioni/elenco").json()["stato"]["at"]
        time.sleep(1)
        r = sess().post(f"{API}/comunicazioni/elenco/aggiorna")
        assert r.status_code == 200, r.text
        st = r.json()
        assert st["auto"] is False and st["clienti"] == 2 and st["at"] > before
        j = sess().get(f"{API}/comunicazioni/elenco").json()
        assert j["stato"]["at"] == st["at"] and all(x["aggiornato_il"] == st["at"] for x in j["righe"])

    def test_04_promemoria_giorni_widened(self):
        s = sess()
        cfg = s.get(f"{API}/comunicazioni/config").json()["config"]
        assert s.put(f"{API}/comunicazioni/config", json={**cfg, "promemoria_giorni": 30}).status_code == 200
        st = s.post(f"{API}/comunicazioni/elenco/aggiorna").json()
        assert st["clienti"] == 2  # 60 days still out
        assert s.put(f"{API}/comunicazioni/config", json={**cfg, "promemoria_giorni": 5}).status_code == 200

    def test_05_operatore_forbidden(self):
        s = sess(TOK2)
        assert s.get(f"{API}/comunicazioni/elenco").status_code == 200
        assert s.post(f"{API}/comunicazioni/elenco/aggiorna").status_code == 403
        assert s.post(f"{API}/comunicazioni/elenco/invia", json={"party_ids": [ST["pa"]], "cosa": ["scadenze"]}).status_code == 403

    def test_06_validation(self):
        s = sess()
        assert s.post(f"{API}/comunicazioni/elenco/invia", json={"party_ids": [], "cosa": ["scadenze"]}).status_code == 422
        assert s.post(f"{API}/comunicazioni/elenco/invia", json={"party_ids": [ST["pa"]], "cosa": []}).status_code == 422
        assert s.post(f"{API}/comunicazioni/elenco/invia", json={"party_ids": [ST["pa"]], "cosa": ["xx"]}).status_code == 422

    def test_07_invia_all(self):
        s = sess()
        r = s.post(f"{API}/comunicazioni/elenco/invia", json={"party_ids": [ST["pa"]], "cosa": ["fatture", "promemoria", "scadenze"]})
        assert r.status_code == 200, r.text
        o = r.json()
        assert o["fatture"] == 2 and o["promemoria"] == 1 and o["solleciti"] == 1 and o["errori"] == [] and o["saltati"] == [], o
        logs = s.get(f"{API}/comunicazioni/log").json()["log"]
        mine = [x for x in logs if x["party_id"] == ST["pa"]]
        assert sorted(x["tipo"] for x in mine) == ["cortesia", "cortesia", "promemoria", "sollecito"]
        sol = next(x for x in mine if x["tipo"] == "sollecito")
        assert sol["livello"] == 2 and sol["esito"] == "ok" and sol["auto"] is False and sol["to"] == "alfa111@example.com" and sol["importo"] == 1220
        a = row(s.get(f"{API}/comunicazioni/elenco").json(), ST["pa"])
        assert a["ultimo_invio"] and a["ultimo_invio"]["tipo"] in ("sollecito", "promemoria", "cortesia")
        ST["ultimo"] = a["ultimo_invio"]

    def test_08_saltati_and_errori(self):
        s = sess()
        o = s.post(f"{API}/comunicazioni/elenco/invia", json={"party_ids": [ST["pb"], ST["pc"], "nonexistent"], "cosa": ["promemoria", "scadenze"]}).json()
        assert o["solleciti"] == 0
        assert any(e["cliente"] == "TEST_T111 Cliente Beta" and "email" in e["errore"] for e in o["errori"]), o
        assert any(x["cliente"] == "TEST_T111 Cliente Beta" and x["motivo"] == "nessuna rata ancora da scadere" for x in o["saltati"]), o
        assert any(x["cliente"] == "TEST_T111 Cliente Gamma" and x["motivo"] == "nessuna rata scaduta" for x in o["saltati"]), o
        assert o["promemoria"] == 1  # gamma has a not-yet-due rate (60 days)
        assert any(x["motivo"] == "nessuna rata aperta" for x in o["saltati"])

    def test_09_sollecito_level_min_1(self):
        # overdue but under first level (7 days): set livelli high so computed level is 0 -> min 1
        s = sess()
        cfg = s.get(f"{API}/comunicazioni/config").json()["config"]
        assert s.put(f"{API}/comunicazioni/config", json={**cfg, "livelli": [50, 60, 70]}).status_code == 200
        mongo(f'db.parties.updateOne({{id:"{ST["pb"]}"}}, {{$set:{{email:"beta111@example.com"}}}})')
        o = s.post(f"{API}/comunicazioni/elenco/invia", json={"party_ids": [ST["pb"]], "cosa": ["scadenze"]}).json()
        assert o["solleciti"] == 1, o
        lg = next(x for x in s.get(f"{API}/comunicazioni/log").json()["log"] if x["party_id"] == ST["pb"] and x["esito"] == "ok")
        assert lg["livello"] == 1
        assert s.put(f"{API}/comunicazioni/config", json={**cfg}).status_code == 200

    def test_10_auto_refresh_loop(self):
        s = sess()
        cfg = s.get(f"{API}/comunicazioni/config").json()["config"]
        assert s.put(f"{API}/comunicazioni/config", json={**cfg, "ora": 6}).status_code == 200
        mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}}, {{$unset:{{com_elenco_day:""}}}})')
        ok = False
        for _ in range(16):
            time.sleep(6)
            j = s.get(f"{API}/comunicazioni/elenco").json()
            if j["stato"]["auto"]:
                ok = True
                break
        assert ok, j["stato"]
        assert all(x["auto"] is True for x in j["righe"])
        a = row(j, ST["pa"])
        assert a["ultimo_invio"] is not None  # recomputed from com_log
        assert mongo(f'print(db.companies.findOne({{id:"{ST["cid"]}"}}).com_elenco_day)') == T.isoformat()
        assert s.put(f"{API}/comunicazioni/config", json={**cfg, "ora": 8}).status_code == 200

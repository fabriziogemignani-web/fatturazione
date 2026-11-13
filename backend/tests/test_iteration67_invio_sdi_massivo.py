# Iteration 67: Invio massivo SDI - GET /api/invio-sdi/da-inviare (filtro date, solo bozza/scartata, ordinamento, isolamento, 403 operatore/modulo/menu)
# and POST /api/invio-sdi (ordine data/numero, errori non bloccanti, id altra azienda ignorato, gia inviata, ids vuoti 422, scartata -> nuovo progressivo).
# Run: pytest tests/test_iteration67_invio_sdi_massivo.py -v -n 0
# UI fixtures: T67_RUN=123456 python tests/test_iteration67_invio_sdi_massivo.py setup|clean
import json
import os
import random
import sys
from datetime import date, timedelta

import pytest
import requests

from test_iteration7_pa_scartate_registro import API, mongo

RUN = os.environ.get("T67_RUN") or str(random.randint(100000, 999999))
TOK, UID = f"test_session_t67_admin_{RUN}", f"test-user-t67-admin-{RUN}"
TOK_OP, UID_OP = f"test_session_t67_op_{RUN}", f"test-user-t67-op-{RUN}"
TOK_CO, UID_CO = f"test_session_t67_co_{RUN}", f"test-user-t67-co-{RUN}"
PIVA, PIVA2 = "87" + RUN + "671", "87" + RUN + "672"
T = date.today()
M1 = T.replace(day=1)
COLLS = ["invoices", "passive_invoices", "parties", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "partite_aperte", "comunicazioni"]
ST = {}
ON = {"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True, "corrispettivi": True, "contabilita": True}


def sess(tok=TOK, cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    if cid or ST.get("cid"):
        s.headers["X-Company-Id"] = cid or ST["cid"]
    return s


def clean():
    uids = json.dumps([UID, UID_OP, UID_CO])
    mongo(f'db.companies.find({{partita_iva:{{$in:["{PIVA}","{PIVA2}"]}}}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:{uids}}}}}); db.user_sessions.deleteMany({{user_id:{{$in:{uids}}}}});')


def company(name, piva):
    r = sess(cid="").post(f"{API}/companies", json={"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01",
                                                   "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    assert sess(cid=cid).put(f"{API}/companies/{cid}/moduli", json=ON).status_code == 200
    return cid


def party(name, piva, cid=None, codice="ABC1234"):
    r = sess(cid=cid).post(f"{API}/parties", json={"tipo": "cliente", "denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "codice_destinatario": codice,
                                                   "indirizzo": "Via Milano 2", "cap": "20100", "comune": "Milano", "provincia": "MI"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def ln(desc, prezzo):
    return {"descrizione": desc, "quantita": 1, "prezzo_unitario": prezzo, "aliquota": 22}


def inv(party_id, prezzo, data, cid=None, **k):
    r = sess(cid=cid).post(f"{API}/invoices", json={"tipo_documento": "TD01", "data": data, "party_id": party_id, "lines": [ln("TEST_T67 riga", prezzo)], **k})
    assert r.status_code == 200, r.text
    return r.json()


def d(n):
    return (M1 + timedelta(days=n)).isoformat()


def setup_data():
    clean()
    for uid, tok, role in ((UID, TOK, "admin"), (UID_OP, TOK_OP, "operatore"), (UID_CO, TOK_CO, "contabile")):
        mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.t67.{uid}@example.com", name:"TEST_T67 {role}", picture:"", role:"{role}", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
              f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    ST["cid"] = company(f"TEST_T67 Invio {RUN} Srl", PIVA)
    ST["cid2"] = company(f"TEST_T67 Altra {RUN} Srl", PIVA2)
    mongo(f'db.users.updateMany({{user_id:{{$in:["{UID_OP}","{UID_CO}"]}}}}, {{$set:{{company_ids:["{ST["cid"]}"]}}}})')
    ST["c1"] = party("TEST_T67 Cliente Uno", "0" + RUN + "6711")
    ST["c_bad"] = party("TEST_T67 Cliente SenzaCodice", "0" + RUN + "6712", codice="0000000")
    ST["c_x"] = party("TEST_T67 Cliente Altra", "0" + RUN + "6713", ST["cid2"])
    # previous month (outside default range)
    ST["prev"] = inv(ST["c1"], 10, (M1 - timedelta(days=1)).isoformat())["id"]
    # 3 drafts in month: created in reverse date order to check sort
    ST["b1"] = inv(ST["c1"], 100, M1.isoformat())["id"]
    ST["b2"] = inv(ST["c1"], 200, M1.isoformat())["id"]
    # sent invoice (inviata) -> excluded
    ST["sent"] = inv(ST["c1"], 50, M1.isoformat())["id"]
    assert sess().post(f"{API}/invoices/{ST['sent']}/send").status_code == 200
    # base invoice for NC (consegnata)
    ST["base"] = inv(ST["c1"], 100, M1.isoformat())["id"]
    sess().post(f"{API}/invoices/{ST['base']}/send")
    sess().post(f"{API}/invoices/{ST['base']}/refresh")
    # scartata: client 0000000 without PEC
    ST["scart"] = inv(ST["c_bad"], 70, M1.isoformat())["id"]
    sess().post(f"{API}/invoices/{ST['scart']}/send")
    sess().post(f"{API}/invoices/{ST['scart']}/refresh")
    ST["b3"] = inv(ST["c1"], 300, T.isoformat())["id"]
    # credit notes: valid (50) and exceeding residual (500) -> created via API (draft creation may block >residuo, then patch via mongo)
    r = sess().post(f"{API}/invoices", json={"tipo_documento": "TD04", "data": T.isoformat(), "party_id": ST["c1"], "lines": [ln("TEST_T67 NC", 50)], "fattura_collegata_id": ST["base"]})
    assert r.status_code == 200, r.text
    ST["nc"] = r.json()["id"]
    r = sess().post(f"{API}/invoices", json={"tipo_documento": "TD04", "data": T.isoformat(), "party_id": ST["c1"], "lines": [ln("TEST_T67 NC big", 40)], "fattura_collegata_id": ST["base"]})
    assert r.status_code == 200, r.text
    ST["nc_big"] = r.json()["id"]
    # autofattura flag on own draft
    ST["af"] = inv(ST["c1"], 40, T.isoformat())["id"]
    mongo(f'db.invoices.updateOne({{id:"{ST["af"]}"}}, {{$set:{{autofattura:true}}}})')
    # other company draft
    ST["x"] = inv(ST["c_x"], 999, M1.isoformat(), cid=ST["cid2"])["id"]
    return ST


def lista(dal=M1.isoformat(), al=T.isoformat(), **k):
    return sess(**k).get(f"{API}/invio-sdi/da-inviare", params={"dal": dal, "al": al})


@pytest.fixture(scope="module", autouse=True)
def setup():
    try:
        setup_data()
    except Exception:
        clean()
        raise
    yield
    clean()


class TestLista:
    def test_01_status_and_range(self):
        r = lista()
        assert r.status_code == 200, r.text
        ids = [x["id"] for x in r.json()]
        for k in ("b1", "b2", "b3", "scart", "nc", "nc_big", "af"):
            assert ST[k] in ids, k
        for k in ("prev", "sent", "base", "x"):
            assert ST[k] not in ids, k
        assert all(x["status"] in ("bozza", "scartata") for x in r.json())
        assert "_id" not in r.json()[0]

    def test_02_sort(self):
        rows = lista().json()
        keys = [(x["data"], x["anno"], x["numero"]) for x in rows]
        assert keys == sorted(keys)
        ids = [x["id"] for x in rows]
        assert ids.index(ST["b1"]) < ids.index(ST["b2"]) < ids.index(ST["b3"])

    def test_03_range_narrow_and_open(self):
        ids = [x["id"] for x in lista(dal=(M1 - timedelta(days=1)).isoformat(), al=(M1 - timedelta(days=1)).isoformat()).json()]
        assert ids == [ST["prev"]]
        r = sess().get(f"{API}/invio-sdi/da-inviare")
        assert ST["prev"] in [x["id"] for x in r.json()]

    def test_04_fields(self):
        row = next(x for x in lista().json() if x["id"] == ST["af"])
        assert row["autofattura"] is True and row["cliente"]["denominazione"] == "TEST_T67 Cliente Uno"
        nc = next(x for x in lista().json() if x["id"] == ST["nc"])
        assert nc["tipo_documento"] == "TD04" and nc["totale"] == 61

    def test_05_isolation_other_company(self):
        ids = [x["id"] for x in lista(cid=ST["cid2"]).json()]
        assert ids == [ST["x"]]

    def test_06_roles(self):
        assert lista(tok=TOK_OP).status_code == 403
        assert sess(tok=TOK_OP).post(f"{API}/invio-sdi", json={"ids": [ST["b1"]]}).status_code == 403
        assert lista(tok=TOK_CO).status_code == 200

    def test_07_module_and_menu_off(self):
        mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}}, {{$set:{{"moduli.fatture_attive":false}}}})')
        try:
            r = lista()
            assert r.status_code == 403 and "Fatture attive" in r.text
        finally:
            mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}}, {{$set:{{"moduli.fatture_attive":true}}}})')
        mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}}, {{$set:{{menu_off:["invio-sdi"]}}}})')
        try:
            r = lista()
            assert r.status_code == 403 and "Invio massivo SDI" in r.text, r.text
            assert sess().post(f"{API}/invio-sdi", json={"ids": [ST["b1"]]}).status_code == 403
        finally:
            mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}}, {{$unset:{{menu_off:1}}}})')
        assert lista().status_code == 200


class TestInvio:
    def test_10_empty_ids(self):
        assert sess().post(f"{API}/invio-sdi", json={"ids": []}).status_code == 422
        assert sess().post(f"{API}/invio-sdi", json={}).status_code == 422

    def test_11_mass_send(self):
        old_prog = sess().get(f"{API}/invoices/{ST['scart']}").json().get("progressivo_invio")
        # mark nc_big as exceeding: bump totale over residual (base 122 - nc 61 = 61)
        mongo(f'db.invoices.updateOne({{id:"{ST["nc_big"]}"}}, {{$set:{{"fattura_collegata.totale":10}}}})')
        ids = [ST["b3"], ST["nc"], ST["nc_big"], ST["b2"], ST["b1"], ST["scart"], ST["sent"], ST["x"], ST["b1"]]
        r = sess().post(f"{API}/invio-sdi", json={"ids": ids})
        assert r.status_code == 200, r.text
        j = r.json()
        res = {x["id"]: x for x in j["risultati"]}
        assert ST["x"] not in res
        assert len(j["risultati"]) == 7
        assert res[ST["sent"]]["ok"] is False and res[ST["sent"]]["errore"] == "Fattura già inviata"
        assert res[ST["nc_big"]]["ok"] is False and "residuo" in res[ST["nc_big"]]["errore"]
        for k in ("b1", "b2", "b3", "nc", "scart"):
            assert res[ST[k]]["ok"] is True and res[ST[k]]["status"] == "inviata", k
            assert res[ST[k]]["numero_display"]
        assert j["inviate"] == 5 and j["errori"] == 2
        order = [x["id"] for x in j["risultati"]]
        assert order.index(ST["b1"]) < order.index(ST["b2"]) < order.index(ST["b3"])
        ST["old_prog"] = old_prog

    def test_12_after_send(self):
        ids = [x["id"] for x in lista().json()]
        for k in ("b1", "b2", "b3", "nc", "scart"):
            assert ST[k] not in ids
            assert sess().get(f"{API}/invoices/{ST[k]}").json()["status"] == "inviata"
        assert ST["nc_big"] in ids and ST["af"] in ids
        new_prog = sess().get(f"{API}/invoices/{ST['scart']}").json().get("progressivo_invio")
        assert new_prog and new_prog != ST["old_prog"]
        x = sess(cid=ST["cid2"]).get(f"{API}/invoices/{ST['x']}").json()
        assert x["status"] == "bozza"

    def test_13_resend_all_already(self):
        j = sess().post(f"{API}/invio-sdi", json={"ids": [ST["b1"]]}).json()
        assert j["inviate"] == 0 and j["errori"] == 1 and j["risultati"][0]["errore"] == "Fattura già inviata"

    def test_14_unknown_ids(self):
        j = sess().post(f"{API}/invio-sdi", json={"ids": ["nonexistent"]}).json()
        assert j == {"inviate": 0, "errori": 0, "risultati": []}

    def test_15_contabile_send(self):
        j = sess(tok=TOK_CO).post(f"{API}/invio-sdi", json={"ids": [ST["af"]]}).json()
        assert j["inviate"] == 1, j


if __name__ == "__main__":
    if sys.argv[1] == "setup":
        setup_data()
        print(json.dumps({**ST, "tok": TOK, "tok_op": TOK_OP, "tok_co": TOK_CO}))
    else:
        clean()

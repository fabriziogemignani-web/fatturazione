# Iteration 104: Porto turistico module (marina management) - config, listino, pontili/posti, barche, prezzo, contratti+rate,
# fatturazione rate, transiti+partenza, mappa, planning, tenant isolation, CSRF header.
# Run: cd /app/backend && set -a && . ./.env && . ../frontend/.env && set +a && pytest tests/test_iteration104_porto.py -v -n 0
import os
import sys
from datetime import date, timedelta

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

UID, TOK = "test-user-t104-admin", "test_session_t104_admin"
ST = {}
TODAY = date.today()


def s(cid=None):
    x = requests.Session()
    x.headers["Authorization"] = f"Bearer {TOK}"
    x.headers["X-Requested-With"] = "invoix"
    if cid or ST.get("cid"):
        x.headers["X-Company-Id"] = cid or ST["cid"]
    return x


def clean():
    mongo('db.companies.find({denominazione:/^TEST_T104/}).forEach(c=>{["parties","invoices","porto_config","porto_pontili","porto_posti","porto_barche","porto_contratti","porto_transiti","payments","scadenze"].forEach(k=>db[k].deleteMany({company_id:c.id}));'
          'db.counters.deleteMany({key:{$regex:c.id}}); db.users.updateMany({}, {$pull:{company_ids:c.id}}); db.companies.deleteOne({id:c.id});});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def company(name, piva):
    r = s(cid="x").post(f"{API}/companies", headers={"X-Company-Id": None}, json={"denominazione": name, "partita_iva": piva, "codice_fiscale": piva,
                        "regime_fiscale": "RF01", "indirizzo": "Via Roma 1", "cap": "57100", "comune": "Livorno", "provincia": "LI", "nazione": "IT"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def party(cid, name, tipo="cliente"):
    r = s(cid).post(f"{API}/parties", json={"tipo": tipo, "denominazione": name, "partita_iva": "01234567897", "codice_fiscale": "01234567897",
                                            "codice_destinatario": "0000000", "indirizzo": "Via Mare 2", "cap": "57100", "comune": "Livorno", "provincia": "LI", "nazione": "IT"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t104@example.com", name:"TEST_T104 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    ST["cid"] = company("TEST_T104 Marina Srl", "10410410410")
    ST["cid2"] = company("TEST_T104 Altro Srl", "10410410411")
    ST["cli"] = party(ST["cid"], "TEST_T104 Armatore Rossi")
    ST["forn"] = party(ST["cid"], "TEST_T104 Fornitore", "fornitore")
    yield
    if not os.environ.get("KEEP_T104"):
        clean()


FASCE = [{"da_m": 0, "a_m": 10, "giorno_alta": 50, "giorno_bassa": 30, "mese_alta": 1000, "mese_bassa": 600, "annuale": 5000},
         {"da_m": 10.01, "a_m": 15, "giorno_alta": 80, "giorno_bassa": 50, "mese_alta": 1600, "mese_bassa": 900, "annuale": 8000}]


class TestConfig:
    def test_csrf_required(self):
        r = s().put(f"{API}/porto/config", headers={"X-Requested-With": None}, json={"alta_da": "06-01", "alta_a": "09-30", "aliquota": 10})
        assert r.status_code == 403

    def test_config_save(self):
        r = s().put(f"{API}/porto/config", json={"alta_da": "06-01", "alta_a": "09-30", "aliquota": 10})
        assert r.status_code == 200, r.text
        g = s().get(f"{API}/porto/config").json()
        assert g["aliquota"] == 10 and g["alta_da"] == "06-01" and g["alta_a"] == "09-30"

    def test_config_bad_format(self):
        assert s().put(f"{API}/porto/config", json={"alta_da": "6-1", "alta_a": "09-30", "aliquota": 10}).status_code == 422
        assert s().put(f"{API}/porto/config", json={"alta_da": "06-01", "alta_a": "09-30", "aliquota": 0}).status_code == 422

    def test_listino_overlap(self):
        r = s().put(f"{API}/porto/listino", json={"fasce": [FASCE[0], {**FASCE[1], "da_m": 9}]})
        assert r.status_code == 422 and "sovrappongono" in r.json()["detail"]
        r = s().put(f"{API}/porto/listino", json={"fasce": [{**FASCE[0], "da_m": 12}]})
        assert r.status_code == 422

    def test_listino_save(self):
        r = s().put(f"{API}/porto/listino", json={"fasce": FASCE})
        assert r.status_code == 200, r.text
        g = s().get(f"{API}/porto/config").json()
        assert len(g["listino"]) == 2 and g["listino"][1]["giorno_alta"] == 80 and g["aliquota"] == 10


class TestPontiliPosti:
    def test_pontile_and_serie(self):
        r = s().post(f"{API}/porto/pontili", json={"nome": "TEST_A", "ordine": 1})
        assert r.status_code == 200
        ST["pont"] = r.json()["id"]
        r = s().post(f"{API}/porto/posti/serie", json={"pontile_id": ST["pont"], "prefisso": "A", "da": 1, "a": 5, "lunghezza_max": 12})
        assert r.json() == {"creati": 5, "saltati": 0}
        r = s().post(f"{API}/porto/posti/serie", json={"pontile_id": ST["pont"], "prefisso": "A", "da": 4, "a": 7, "lunghezza_max": 12})
        assert r.json() == {"creati": 2, "saltati": 2}
        posti = s().get(f"{API}/porto/posti").json()
        assert len(posti) == 7
        ST["posti"] = {p["codice"]: p for p in posti}

    def test_serie_max_300(self):
        r = s().post(f"{API}/porto/posti/serie", json={"pontile_id": ST["pont"], "prefisso": "Z", "da": 1, "a": 301, "lunghezza_max": 12})
        assert r.status_code == 422

    def test_posto_duplicate_409(self):
        r = s().post(f"{API}/porto/posti", json={"pontile_id": ST["pont"], "codice": "A1", "lunghezza_max": 12})
        assert r.status_code == 409

    def test_posto_fuori_servizio_toggle(self):
        p = ST["posti"]["A7"]
        r = s().put(f"{API}/porto/posti/{p['id']}", json={**{k: p[k] for k in ("pontile_id", "codice", "lunghezza_max", "larghezza_max", "tipo", "note")}, "fuori_servizio": True})
        assert r.status_code == 200 and r.json()["fuori_servizio"] is True

    def test_delete_pontile_with_posti_400(self):
        assert s().delete(f"{API}/porto/pontili/{ST['pont']}").status_code == 400

    def test_delete_empty_pontile(self):
        pid = s().post(f"{API}/porto/pontili", json={"nome": "TEST_tmp"}).json()["id"]
        assert s().delete(f"{API}/porto/pontili/{pid}").status_code == 200
        assert all(x["id"] != pid for x in s().get(f"{API}/porto/pontili").json())


class TestBarche:
    def test_barca_requires_cliente(self):
        r = s().post(f"{API}/porto/barche", json={"nome": "TEST_X", "party_id": ST["forn"], "lunghezza": 9})
        assert r.status_code == 400
        r = s().post(f"{API}/porto/barche", json={"nome": "TEST_X", "party_id": "nope", "lunghezza": 9})
        assert r.status_code == 400

    def test_barca_crud(self):
        r = s().post(f"{API}/porto/barche", json={"nome": "TEST_Gabbiano", "party_id": ST["cli"], "lunghezza": 9.5, "tipo": "vela"})
        assert r.status_code == 200, r.text
        ST["b1"] = r.json()["id"]
        ST["b2"] = s().post(f"{API}/porto/barche", json={"nome": "TEST_Delfino", "party_id": ST["cli"], "lunghezza": 11}).json()["id"]
        ST["big"] = s().post(f"{API}/porto/barche", json={"nome": "TEST_Big", "party_id": ST["cli"], "lunghezza": 14}).json()["id"]
        ST["nob"] = s().post(f"{API}/porto/barche", json={"nome": "TEST_NoBand", "party_id": ST["cli"], "lunghezza": 20}).json()["id"]
        r = s().put(f"{API}/porto/barche/{ST['b1']}", json={"nome": "TEST_Gabbiano II", "party_id": ST["cli"], "lunghezza": 9.5, "tipo": "vela"})
        assert r.json()["nome"] == "TEST_Gabbiano II"
        lst = s().get(f"{API}/porto/barche").json()
        b = next(x for x in lst if x["id"] == ST["b1"])
        assert b["armatore"] == "TEST_T104 Armatore Rossi"
        tmp = s().post(f"{API}/porto/barche", json={"nome": "TEST_Tmp", "party_id": ST["cli"], "lunghezza": 5}).json()["id"]
        assert s().delete(f"{API}/porto/barche/{tmp}").status_code == 200


class TestPrezzo:
    def test_transito_season_split(self):
        r = s().get(f"{API}/porto/prezzo", params={"barca_id": ST["b1"], "da": "2025-05-30", "a": "2025-06-03", "tipo": "transito"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["imponibile"] == 30 * 2 + 50 * 2 and d["aliquota"] == 10 and d["totale"] == 176.0

    def test_annuale(self):
        r = s().get(f"{API}/porto/prezzo", params={"barca_id": ST["b2"], "da": "2025-01-01", "a": "2025-12-31", "tipo": "annuale"})
        assert r.json()["imponibile"] == 8000

    def test_missing_band(self):
        r = s().get(f"{API}/porto/prezzo", params={"barca_id": ST["nob"], "da": "2025-01-01", "a": "2025-01-05"})
        assert r.status_code == 400 and "Nessuna fascia" in r.json()["detail"]


class TestContratti:
    def test_too_long_400(self):
        r = s().post(f"{API}/porto/contratti", json={"barca_id": ST["big"], "posto_id": ST["posti"]["A1"]["id"], "data_inizio": "2025-01-01", "data_fine": "2025-12-31"})
        assert r.status_code == 400 and "non entra" in r.json()["detail"]

    def test_fuori_servizio_400(self):
        r = s().post(f"{API}/porto/contratti", json={"barca_id": ST["b1"], "posto_id": ST["posti"]["A7"]["id"], "data_inizio": "2025-01-01", "data_fine": "2025-12-31"})
        assert r.status_code == 400 and "fuori servizio" in r.json()["detail"]

    def test_create_rate(self):
        di = TODAY - timedelta(days=200)
        df = di + timedelta(days=364)
        r = s().post(f"{API}/porto/contratti", json={"barca_id": ST["b1"], "posto_id": ST["posti"]["A1"]["id"], "tipo": "annuale",
                                                   "data_inizio": di.isoformat(), "data_fine": df.isoformat(), "n_rate": 3})
        assert r.status_code == 200, r.text
        k = r.json()
        ST["k1"] = k["id"]
        assert k["importo"] == 5000 and len(k["rate"]) == 3
        assert round(sum(x["importo"] for x in k["rate"]), 2) == 5000
        assert k["rate"][0]["scadenza"] == di.isoformat() and k["stato"] == "attivo"

    def test_rate_sum_odd(self):
        r = s().post(f"{API}/porto/contratti", json={"barca_id": ST["b2"], "posto_id": ST["posti"]["A2"]["id"], "tipo": "stagionale",
                                                   "data_inizio": "2030-06-01", "data_fine": "2030-09-30", "n_rate": 6, "importo": 1000})
        assert r.status_code == 200, r.text
        k = r.json()
        ST["k2"] = k["id"]
        assert round(sum(x["importo"] for x in k["rate"]), 2) == 1000 and len(k["rate"]) == 6

    def test_overlap_409(self):
        r = s().post(f"{API}/porto/contratti", json={"barca_id": ST["b2"], "posto_id": ST["posti"]["A1"]["id"], "data_inizio": TODAY.isoformat(), "data_fine": (TODAY + timedelta(days=10)).isoformat()})
        assert r.status_code == 409
        r = s().post(f"{API}/porto/transiti", json={"barca_id": ST["b2"], "posto_id": ST["posti"]["A1"]["id"], "arrivo": TODAY.isoformat(), "partenza_prevista": (TODAY + timedelta(days=2)).isoformat()})
        assert r.status_code == 409

    def test_edit_delete_unbilled(self):
        r = s().put(f"{API}/porto/contratti/{ST['k2']}", json={"barca_id": ST["b2"], "posto_id": ST["posti"]["A2"]["id"], "tipo": "stagionale",
                                                             "data_inizio": "2030-06-01", "data_fine": "2030-09-30", "n_rate": 2, "importo": 1200})
        assert r.status_code == 200 and len(r.json()["rate"]) == 2 and r.json()["importo"] == 1200
        assert s().delete(f"{API}/porto/contratti/{ST['k2']}").status_code == 200

    def test_barca_posto_with_contract_not_deletable(self):
        assert s().delete(f"{API}/porto/barche/{ST['b1']}").status_code == 400
        assert s().delete(f"{API}/porto/posti/{ST['posti']['A1']['id']}").status_code == 400


class TestFatturaRate:
    def test_list_due(self):
        r = s().get(f"{API}/porto/rate", params={"fino_al": TODAY.isoformat()})
        due = [x for x in r.json() if x["contratto_id"] == ST["k1"]]
        assert len(due) == 2  # rate 1 (day 0) and 2 (day ~121) due, rata 3 (~243) future

    def test_fattura_and_no_dup(self):
        r = s().post(f"{API}/porto/rate/fattura", json={"fino_al": TODAY.isoformat()})
        assert r.status_code == 200, r.text
        d = r.json()
        assert len(d["create"]) == 2 and not d["errori"], d
        inv = s().get(f"{API}/invoices/{d['create'][0]['fattura_id']}").json()
        assert inv["status"] == "bozza" and inv["data"] == TODAY.isoformat()
        assert inv["lines"][0]["aliquota"] == 10
        assert inv.get("scadenza") >= TODAY.isoformat()
        k = next(x for x in s().get(f"{API}/porto/contratti").json() if x["id"] == ST["k1"])
        assert k["rate"][0]["fattura_id"] and k["rate"][0]["fattura_numero"]
        r2 = s().post(f"{API}/porto/rate/fattura", json={"fino_al": TODAY.isoformat()})
        assert r2.json()["create"] == []
        assert [x for x in s().get(f"{API}/porto/rate", params={"fino_al": TODAY.isoformat()}).json() if x["contratto_id"] == ST["k1"]] == []

    def test_billed_contract_locked(self):
        assert s().delete(f"{API}/porto/contratti/{ST['k1']}").status_code == 400
        k = next(x for x in s().get(f"{API}/porto/contratti").json() if x["id"] == ST["k1"])
        r = s().put(f"{API}/porto/contratti/{ST['k1']}", json={"barca_id": ST["b1"], "posto_id": ST["posti"]["A1"]["id"], "data_inizio": k["data_inizio"], "data_fine": k["data_fine"]})
        assert r.status_code == 400


class TestTransiti:
    def test_invalid_dates(self):
        r = s().post(f"{API}/porto/transiti", json={"barca_id": ST["b2"], "posto_id": ST["posti"]["A3"]["id"], "arrivo": "2025-05-05", "partenza_prevista": "2025-05-05"})
        assert r.status_code == 422

    def test_arrival_departure_invoice(self):
        arr = TODAY - timedelta(days=3)
        r = s().post(f"{API}/porto/transiti", json={"barca_id": ST["b2"], "posto_id": ST["posti"]["A3"]["id"], "arrivo": arr.isoformat(), "partenza_prevista": (TODAY + timedelta(days=2)).isoformat()})
        assert r.status_code == 200, r.text
        ST["t1"] = r.json()["id"]
        assert r.json()["stato"] == "presente"
        r = s().post(f"{API}/porto/transiti", json={"barca_id": ST["b1"], "posto_id": ST["posti"]["A3"]["id"], "arrivo": TODAY.isoformat(), "partenza_prevista": (TODAY + timedelta(days=1)).isoformat()})
        assert r.status_code == 409
        r = s().post(f"{API}/porto/transiti/{ST['t1']}/partenza", json={"partenza": (TODAY + timedelta(days=1)).isoformat()})
        assert r.status_code == 422
        exp = s().get(f"{API}/porto/prezzo", params={"barca_id": ST["b2"], "da": arr.isoformat(), "a": TODAY.isoformat()}).json()["imponibile"]
        r = s().post(f"{API}/porto/transiti/{ST['t1']}/partenza", json={"partenza": TODAY.isoformat()})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["stato"] == "partito" and d["importo"] == exp and d["fattura_id"]
        inv = s().get(f"{API}/invoices/{d['fattura_id']}").json()
        assert inv["status"] == "bozza" and inv["lines"][0]["prezzo_unitario"] == exp and "3 notti" in inv["lines"][0]["descrizione"]
        assert s().post(f"{API}/porto/transiti/{ST['t1']}/partenza", json={"partenza": TODAY.isoformat()}).status_code == 400
        assert s().delete(f"{API}/porto/transiti/{ST['t1']}").status_code == 400

    def test_manual_importo(self):
        r = s().post(f"{API}/porto/transiti", json={"barca_id": ST["b1"], "posto_id": ST["posti"]["A4"]["id"], "arrivo": (TODAY - timedelta(days=1)).isoformat(), "partenza_prevista": (TODAY + timedelta(days=3)).isoformat()})
        assert r.status_code == 409 and "barca" in r.json()["detail"]
        b3 = s().post(f"{API}/porto/barche", json={"nome": "TEST_Sirena", "party_id": ST["cli"], "lunghezza": 8}).json()["id"]
        r = s().post(f"{API}/porto/transiti", json={"barca_id": b3, "posto_id": ST["posti"]["A4"]["id"], "arrivo": (TODAY - timedelta(days=1)).isoformat(), "partenza_prevista": (TODAY + timedelta(days=3)).isoformat()})
        ST["t2"] = r.json()["id"]
        r = s().post(f"{API}/porto/transiti/{ST['t2']}/partenza", json={"partenza": TODAY.isoformat(), "importo": 77.5})
        assert r.status_code == 200 and r.json()["importo"] == 77.5

    def test_presente_for_map(self):
        r = s().post(f"{API}/porto/transiti", json={"barca_id": ST["b2"], "posto_id": ST["posti"]["A5"]["id"], "arrivo": TODAY.isoformat(), "partenza_prevista": (TODAY + timedelta(days=4)).isoformat()})
        assert r.status_code == 200, r.text
        ST["t3"] = r.json()["id"]


class TestViste:
    def test_mappa(self):
        r = s().get(f"{API}/porto/mappa", params={"data": TODAY.isoformat()})
        assert r.status_code == 200
        d = r.json()
        assert d["conteggi"]["fuori_servizio"] == 1 and d["conteggi"]["contratto"] == 1 and d["conteggi"]["transito"] >= 1
        assert sum(d["conteggi"].values()) == 7
        posti = {p["codice"]: p for pt in d["pontili"] for p in pt["posti"]}
        assert posti["A1"]["occupazione"]["barca"] == "TEST_Gabbiano II"
        assert posti["A5"]["stato"] == "transito"

    def test_planning(self):
        r = s().get(f"{API}/porto/planning", params={"da": (TODAY - timedelta(days=7)).isoformat(), "giorni": 14})
        assert r.status_code == 200
        d = r.json()
        assert len(d["posti"]) == 7 and d["giorni"] == 14
        tipi = {o["tipo"] for o in d["occupazioni"]}
        assert tipi == {"contratto", "transito"}

    def test_chiudi(self):
        assert s().post(f"{API}/porto/contratti/{ST['k1']}/chiudi").status_code == 200
        k = next(x for x in s().get(f"{API}/porto/contratti").json() if x["id"] == ST["k1"])
        assert k["stato"] == "chiuso"
        assert s().get(f"{API}/porto/mappa").json()["conteggi"]["contratto"] == 0


class TestIsolation:
    def test_other_company_empty(self):
        o = s(ST["cid2"])
        for ep in ("barche", "posti", "pontili", "contratti", "transiti"):
            assert o.get(f"{API}/porto/{ep}").json() == [], ep
        assert o.get(f"{API}/porto/mappa").json()["conteggi"] == {"libero": 0, "contratto": 0, "transito": 0, "fuori_servizio": 0}
        assert o.get(f"{API}/porto/config").json()["listino"] == []

    def test_other_company_cannot_touch(self):
        o = s(ST["cid2"])
        assert o.delete(f"{API}/porto/barche/{ST['b2']}").status_code in (200, 404)
        assert any(b["id"] == ST["b2"] for b in s().get(f"{API}/porto/barche").json())
        assert o.post(f"{API}/porto/contratti/{ST['k1']}/chiudi").status_code == 404
        assert o.get(f"{API}/porto/prezzo", params={"barca_id": ST["b1"], "da": "2025-01-01", "a": "2025-01-02"}).status_code == 404
        assert o.post(f"{API}/porto/transiti/{ST['t3']}/partenza", json={"partenza": TODAY.isoformat()}).status_code == 404

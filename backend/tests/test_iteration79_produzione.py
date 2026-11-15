# Iteration 79: Modulo Produzione - centri di lavoro, distinte base multilivello (costi, cicli), ordini di produzione (impegni, versamenti, annulla),
# OP da ordine cliente, MRP. Run: pytest tests/test_iteration79_produzione.py -v -n 0   (T79_KEEP=1 keeps data for UI)
import json
import os
import random
import sys
from datetime import date, timedelta

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

RUN = os.environ.get("T79_RUN") or str(random.randint(100000, 999999))
TOK, UID = "test_session_t79_admin", "test-user-t79-admin"
D = lambda n: (date.today() + timedelta(days=n)).isoformat()  # noqa: E731
ST = {}
P = f"{API}/produzione"


def sess(cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    c = cid or ST.get("cid")
    if c:
        s.headers["X-Company-Id"] = c
    return s


def clean():
    mongo('db.companies.find({denominazione:/^TEST_T79/}).forEach(c=>{db.getCollectionNames().forEach(k=>{if(k!=="companies") db[k].deleteMany({company_id:c.id})});'
          'db.users.updateMany({}, {$pull:{company_ids:c.id}}); db.companies.deleteOne({id:c.id});});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def art(codice, **kw):
    r = sess().post(f"{API}/articles", json={"codice": codice, "descrizione": f"TEST_T79 {codice}", "unita_misura": "PZ", "prezzo": 10, "aliquota": 22,
                                              "gestione_magazzino": True, **kw})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def carico(aid, q, c):
    r = sess().post(f"{API}/magazzino/movimenti", json={"article_id": aid, "tipo": "carico", "data": D(-10), "quantita": q, "costo_unitario": c, "causale": "Acquisto"})
    assert r.status_code == 200, r.text


def giac():
    return {a["id"]: a for a in sess().get(f"{API}/magazzino/articoli").json()["articoli"]}


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t79.admin@example.com", name:"TEST_T79 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    piva = "79" + RUN + "791"
    r = sess("x").post(f"{API}/companies", json={"denominazione": f"TEST_T79 Produzione {RUN} Srl", "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01",
                                                 "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    ST["RM1"] = art("TEST_RM1")
    ST["RM2"] = art("TEST_RM2", scorta_riordino=20, fornitore_abituale="TEST_T79 Fornitore")
    ST["SL"] = art("TEST_SL")
    ST["PF"] = art("TEST_PF", scorta_minima=5)
    ST["NB"] = art("TEST_NOBOM")
    carico(ST["RM1"], 100, 2)
    carico(ST["RM2"], 5, 5)
    yield
    if os.environ.get("T79_KEEP"):
        print("\nKEEP", RUN, json.dumps({k: v for k, v in ST.items() if isinstance(v, str)}))
    else:
        clean()


class TestProduzione:
    # Centri di lavoro CRUD
    def test_01_centri(self):
        s = sess()
        c1 = s.post(f"{P}/centri", json={"codice": "C1", "descrizione": "TEST Taglio", "costo_orario": 60})
        assert c1.status_code == 200, c1.text
        c2 = s.post(f"{P}/centri", json={"codice": "C2", "descrizione": "TEST Montaggio", "costo_orario": 20})
        ST["C1"], ST["C2"] = c1.json()["id"], c2.json()["id"]
        assert s.post(f"{P}/centri", json={"codice": "C1", "descrizione": "dup", "costo_orario": 1}).status_code == 409
        assert s.put(f"{P}/centri/{ST['C2']}", json={"codice": "C2", "descrizione": "TEST Montaggio", "costo_orario": 30}).status_code == 200
        assert s.put(f"{P}/centri/{ST['C2']}", json={"codice": "C1", "descrizione": "x", "costo_orario": 30}).status_code == 409
        rows = {c["id"]: c for c in s.get(f"{P}/centri").json()}
        assert rows[ST["C2"]]["costo_orario"] == 30 and "_id" not in rows[ST["C2"]]
        c3 = s.post(f"{P}/centri", json={"codice": "C3", "descrizione": "TEST tmp", "costo_orario": 1}).json()["id"]
        assert s.delete(f"{P}/centri/{c3}").status_code == 200
        assert c3 not in {c["id"] for c in s.get(f"{P}/centri").json()}

    # Distinte base: costing multilivello, 409 dup, cicli 422, centro non valido 422
    def test_02_distinte(self):
        s = sess()
        sl = s.post(f"{P}/distinte", json={"article_id": ST["SL"], "lotto": 10, "componenti": [{"article_id": ST["RM1"], "quantita": 2}, {"article_id": ST["RM2"], "quantita": 1}],
                                           "fasi": [{"descrizione": "Taglio", "centro_id": ST["C1"], "setup_min": 30, "minuti_pezzo": 6}]})
        assert sl.status_code == 200, sl.text
        ST["DSL"] = sl.json()["id"]
        pf = s.post(f"{P}/distinte", json={"article_id": ST["PF"], "lotto": 1, "componenti": [{"article_id": ST["SL"], "quantita": 1}, {"article_id": ST["RM1"], "quantita": 3}],
                                           "fasi": [{"descrizione": "Montaggio", "centro_id": ST["C2"], "setup_min": 0, "minuti_pezzo": 12}]})
        assert pf.status_code == 200, pf.text
        ST["DPF"] = pf.json()["id"]
        dup = s.post(f"{P}/distinte", json={"article_id": ST["PF"], "componenti": [{"article_id": ST["RM1"], "quantita": 1}]})
        assert dup.status_code == 409, dup.text
        cyc = s.put(f"{P}/distinte/{ST['DSL']}", json={"article_id": ST["SL"], "lotto": 10, "componenti": [{"article_id": ST["PF"], "quantita": 1}]})
        assert cyc.status_code == 422, cyc.text
        self_ = s.post(f"{P}/distinte", json={"article_id": ST["RM1"], "componenti": [{"article_id": ST["RM1"], "quantita": 1}]})
        assert self_.status_code == 422, self_.text
        bad = s.post(f"{P}/distinte", json={"article_id": ST["NB"], "componenti": [{"article_id": ST["RM1"], "quantita": 1}],
                                            "fasi": [{"descrizione": "x", "centro_id": "nope", "setup_min": 0, "minuti_pezzo": 1}]})
        assert bad.status_code == 422, bad.text
        rows = {d["article_id"]: d for d in s.get(f"{P}/distinte").json()}
        # SL: mat 2*2+1*5=9 ; lav (30/10+6)/60*60 = 9
        assert rows[ST["SL"]]["costo"] == {"materiali": 9, "lavorazioni": 9}, rows[ST["SL"]]["costo"]
        # PF: mat 1*18 + 3*2 = 24 ; lav 12/60*30 = 6
        assert rows[ST["PF"]]["costo"] == {"materiali": 24, "lavorazioni": 6}, rows[ST["PF"]]["costo"]
        # centro in use cannot be deleted
        assert s.delete(f"{P}/centri/{ST['C1']}").status_code == 400

    # MRP with low-level code: PF sottoscorta -> SL needed -> RM2 to purchase
    def test_03_mrp(self):
        m = sess().get(f"{P}/mrp").json()
        prod = {x["article_id"]: x for x in m["produrre"]}
        acq = {x["article_id"]: x for x in m["acquistare"]}
        assert prod[ST["PF"]]["quantita"] == 5, m
        assert prod[ST["SL"]]["quantita"] == 10, m  # need 5, lotto 10
        assert [x["article_id"] for x in m["produrre"]].index(ST["PF"]) < [x["article_id"] for x in m["produrre"]].index(ST["SL"])
        assert ST["RM1"] not in acq  # 100 - 15 - 20 = 65
        assert acq[ST["RM2"]]["quantita"] == 20 and acq[ST["RM2"]]["fornitore_abituale"] == "TEST_T79 Fornitore", m  # 5-10=-5 -> max(5, 20)
        assert ST["NB"] not in prod and ST["NB"] not in acq

    # OP creation -> ordinato/impegnato; no BOM 422
    def test_04_op_crea(self):
        s = sess()
        assert s.post(f"{P}/ordini", json={"article_id": ST["NB"], "quantita": 1, "data": D(0)}).status_code == 422
        r = s.post(f"{P}/ordini", json={"article_id": ST["SL"], "quantita": 10, "data": D(0)})
        assert r.status_code == 200, r.text
        op = r.json()
        ST["OP"] = op["id"]
        assert op["status"] == "pianificato" and op["numero_display"] == f"OP 1/{date.today().year}" and op["origine"] == "manuale"
        g = giac()
        assert g[ST["SL"]]["ordinato"] == 10 and g[ST["RM1"]]["impegnato"] == 20 and g[ST["RM2"]]["impegnato"] == 10, (g[ST["SL"]], g[ST["RM1"]])
        assert g[ST["RM2"]]["disponibilita"] == -5

    def test_05_versa_pianificato_and_future(self):
        s = sess()
        assert s.post(f"{P}/ordini/{ST['OP']}/versa", json={"data": D(0), "quantita": 1}).status_code == 400
        assert s.post(f"{P}/ordini/{ST['OP']}/stato/lanciato").json()["status"] == "lanciato"
        assert s.post(f"{P}/ordini/{ST['OP']}/versa", json={"data": D(1), "quantita": 1}).status_code == 400

    def test_06_versa(self):
        r = sess().post(f"{P}/ordini/{ST['OP']}/versa", json={"data": D(0), "quantita": 4})
        assert r.status_code == 200, r.text
        o = r.json()
        v = o["versamenti"][-1]
        # mat 4*2*2 + 4*1*5 = 36 ; lav (30 + 24)/60*60 = 54 -> 90/4 = 22.5
        assert o["prodotta"] == 4 and o["status"] == "in_corso"
        assert v["costo_materiali"] == 36 and v["costo_lavorazioni"] == 54 and v["costo_unitario"] == 22.5, v
        ST["V1"] = v["id"]
        g = giac()
        assert g[ST["RM1"]]["giacenza"] == 92 and g[ST["RM2"]]["giacenza"] == 1 and g[ST["SL"]]["giacenza"] == 4
        assert g[ST["SL"]]["costo_medio"] == 22.5
        assert g[ST["RM1"]]["impegnato"] == 12 and g[ST["SL"]]["ordinato"] == 6
        mv = sess().get(f"{API}/magazzino/movimenti", params={"article_id": ST["RM1"]}).json()
        assert any(m["causale"] == "Produzione" and m["tipo"] == "scarico" and m["quantita"] == 8 for m in mv)

    def test_07_carenze_forza_annulla(self):
        s = sess()
        r = s.post(f"{P}/ordini/{ST['OP']}/versa", json={"data": D(0), "quantita": 4})
        assert r.status_code == 409, r.text
        det = r.json()["detail"]
        assert det["carenze"][0]["codice"] == "TEST_RM2" and det["carenze"][0]["richiesta"] == 4, det
        r = s.post(f"{P}/ordini/{ST['OP']}/versa", json={"data": D(0), "quantita": 4, "forza": True})
        assert r.status_code == 200, r.text
        o = r.json()
        v2 = o["versamenti"][-1]
        assert v2["forzato"] and v2["costo_lavorazioni"] == 24 and o["prodotta"] == 8  # no setup on 2nd
        r = s.post(f"{P}/ordini/{ST['OP']}/versamenti/{v2['id']}/annulla")
        assert r.status_code == 200, r.text
        assert r.json()["prodotta"] == 4 and r.json()["status"] == "in_corso"
        g = giac()
        assert g[ST["RM2"]]["giacenza"] == 1 and g[ST["SL"]]["giacenza"] == 4 and g[ST["RM1"]]["impegnato"] == 12

    def test_08_elimina_blocked_and_chiudi(self):
        s = sess()
        assert s.delete(f"{P}/ordini/{ST['OP']}").status_code == 400
        r = s.post(f"{P}/ordini/{ST['OP']}/versa", json={"data": D(0), "quantita": 1, "chiudi": True})
        assert r.status_code == 200 and r.json()["status"] == "chiuso", r.text
        g = giac()
        assert g[ST["SL"]]["ordinato"] == 0 and g[ST["RM1"]]["impegnato"] == 0 and g[ST["RM2"]]["impegnato"] == 0
        assert s.post(f"{P}/ordini/{ST['OP']}/versa", json={"data": D(0), "quantita": 1}).status_code == 400

    def test_09_op_chiudi_and_elimina(self):
        s = sess()
        o = s.post(f"{P}/ordini", json={"article_id": ST["SL"], "quantita": 3, "data": D(0)}).json()
        assert o["numero"] == 2
        assert giac()[ST["SL"]]["ordinato"] == 3
        assert s.post(f"{P}/ordini/{o['id']}/stato/chiuso").json()["status"] == "chiuso"
        assert giac()[ST["SL"]]["ordinato"] == 0
        o2 = s.post(f"{P}/ordini", json={"article_id": ST["SL"], "quantita": 3, "data": D(0)}).json()
        assert s.delete(f"{P}/ordini/{o2['id']}").status_code == 200
        assert o2["id"] not in {x["id"] for x in s.get(f"{P}/ordini").json()}
        assert giac()[ST["SL"]]["ordinato"] == 0

    def test_10_da_ordine(self):
        s = sess()
        p = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": "TEST_T79 Cliente", "partita_iva": "09876543217", "codice_fiscale": "09876543217",
                                           "codice_destinatario": "ABC1234", "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"}).json()
        o = s.post(f"{API}/ordini/cliente", json={"data": D(0), "party_id": p["id"], "data_consegna": D(10), "lines": [
            {"descrizione": "PF", "article_id": ST["PF"], "quantita": 7, "prezzo_unitario": 50, "aliquota": 22, "unita_misura": "PZ"},
            {"descrizione": "NB", "article_id": ST["NB"], "quantita": 2, "prezzo_unitario": 5, "aliquota": 22, "unita_misura": "PZ"}]})
        assert o.status_code == 200, o.text
        ST["OC"] = o.json()["id"]
        r = s.post(f"{P}/da-ordine/{ST['OC']}")
        assert r.status_code == 200, r.text
        ops = r.json()
        assert len(ops) == 1 and ops[0]["article_id"] == ST["PF"] and ops[0]["quantita"] == 7, ops
        assert ops[0]["origine"] == "ordine_cliente" and ops[0]["ordine_cliente_id"] == ST["OC"] and ops[0]["cliente"] == "TEST_T79 Cliente"
        ST["OPPF"] = ops[0]["id"]
        r2 = s.post(f"{P}/da-ordine/{ST['OC']}")
        assert r2.status_code == 400 and "Nessun prodotto" in r2.json()["detail"], r2.text
        g = giac()
        # PF: impegnato 7 (ordine) ordinato 7 (OP) ; SL impegnato 7 by OP
        assert g[ST["PF"]]["impegnato"] == 7 and g[ST["PF"]]["ordinato"] == 7 and g[ST["SL"]]["impegnato"] == 7

    def test_11_mrp_genera(self):
        s = sess()
        m = s.get(f"{P}/mrp").json()
        prod = {x["article_id"]: x for x in m["produrre"]}
        # PF disp 0 -> need 5 ; SL disp 4.0 - 7 - 5 = -8 -> 10
        assert prod[ST["PF"]]["quantita"] == 5 and prod[ST["SL"]]["quantita"] == 10, m
        r = s.post(f"{P}/ordini/genera", json={"righe": [{"article_id": x["article_id"], "quantita": x["quantita"], "data": D(0)} for x in m["produrre"]]})
        assert r.status_code == 200, r.text
        assert all(x["origine"] == "mrp" for x in r.json()) and len(r.json()) == 2
        assert ST["PF"] not in {x["article_id"] for x in s.get(f"{P}/mrp").json()["produrre"]}

    def test_12_isolation(self):
        r = sess("bogus").get(f"{P}/ordini")
        assert r.status_code == 404

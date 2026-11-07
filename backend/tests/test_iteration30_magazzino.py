# Iteration 30: Magazzino (carichi/scarichi/rettifiche, costo medio ponderato, sottoscorta, riepilogo, roles, module gating)
# Run with: pytest test_iteration30_magazzino.py -n 0
import random

import pytest
import requests

from test_iteration7_pa_scartate_registro import API, mongo

RUN = str(random.randint(100000, 999999))
TOK, UID = f"test_session_t30_admin_{RUN}", f"test-user-t30-admin-{RUN}"
CTOK, CUID = f"test_session_t30_cont_{RUN}", f"test-user-t30-cont-{RUN}"
OTOK, OUID = f"test_session_t30_oper_{RUN}", f"test-user-t30-oper-{RUN}"
PIVA = "87" + RUN + "301"
ST = {}
ALL = {"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True, "corrispettivi": True}


def sess(tok):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def user(uid, tok, role, cids):
    mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.t30.{uid}@example.com", name:"TEST_T30 {role}", picture:"", role:"{role}", status:"approved", company_ids:{cids}, created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')


def clean():
    ids = f'["{UID}","{CUID}","{OUID}"]'
    mongo(f'db.companies.find({{partita_iva:"{PIVA}"}}).forEach(c=>{{["articles","stock_moves","counters"].forEach(k=>db[k].deleteMany({{company_id:c.id}})); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:{ids}}}}}); db.user_sessions.deleteMany({{user_id:{{$in:{ids}}}}});')


def art(codice, **kw):
    return {"codice": codice, "descrizione": f"TEST_T30 {codice}", "unita_misura": "pz", "prezzo": 1, "aliquota": 22} | kw


def mv(aid, tipo, data, q, costo=None, causale=None, tok=None):
    body = {"article_id": aid, "tipo": tipo, "data": data, "quantita": q,
            "causale": causale or {"carico": "Acquisto", "scarico": "Vendita", "rettifica": "Inventario"}[tipo]}
    if costo is not None:
        body["costo_unitario"] = costo
    return sess(tok or TOK).post(f"{API}/magazzino/movimenti", json=body)


def get_art(aid):
    return next(a for a in sess(TOK).get(f"{API}/magazzino/articoli").json()["articoli"] if a["id"] == aid)


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    user(UID, TOK, "admin", "[]")
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    r = s.post(f"{API}/companies", json={"denominazione": f"TEST_T30 Mag {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                         "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    user(CUID, CTOK, "contabile", f'["{ST["cid"]}"]')
    user(OUID, OTOK, "operatore", f'["{ST["cid"]}"]')
    yield
    clean()


# Articles: magazzino fields persist
class TestArticles:
    def test_01_create_managed_article(self):
        r = sess(TOK).post(f"{API}/articles", json=art("VITE10", gestione_magazzino=True, scorta_minima=100, scorta_riordino=500, fornitore_abituale="TEST_Forn Srl"))
        assert r.status_code == 200, r.text
        a = r.json()
        assert a["gestione_magazzino"] is True and a["scorta_minima"] == 100 and a["scorta_riordino"] == 500 and a["fornitore_abituale"] == "TEST_Forn Srl"
        ST["a"] = a["id"]
        r = sess(TOK).post(f"{API}/articles", json=art("NOMAG"))
        assert r.status_code == 200 and r.json()["gestione_magazzino"] is False
        ST["nomag"] = r.json()["id"]

    def test_02_negative_scorta_rejected(self):
        r = sess(TOK).post(f"{API}/articles", json=art("NEG", gestione_magazzino=True, scorta_minima=-1))
        assert r.status_code in (400, 422)

    def test_03_list_only_managed(self):
        d = sess(OTOK).get(f"{API}/magazzino/articoli").json()
        ids = [a["id"] for a in d["articoli"]]
        assert ST["a"] in ids and ST["nomag"] not in ids
        assert "Acquisto" in d["causali"]["carico"]


# Movements: validation + weighted average
class TestMovements:
    def test_01_validations(self):
        assert mv(ST["nomag"], "carico", "2026-01-02", 10, 1).status_code == 400
        assert mv(ST["a"], "carico", "2026-01-02", 0, 1).status_code == 400
        assert mv(ST["a"], "scarico", "2026-01-02", -5).status_code == 400
        assert mv(ST["a"], "rettifica", "2026-01-02", 0).status_code == 400
        r = mv(ST["a"], "carico", "2026-01-02", 10)
        assert r.status_code == 400 and "costo" in r.json()["detail"].lower()
        assert mv(ST["a"], "carico", "2026-01-02", 10, 1, causale="Vendita").status_code == 400
        assert mv(ST["a"], "carico", "2026-01-02", 10, -1).status_code == 422
        assert mv(ST["a"], "carico", "02/01/2026", 10, 1).status_code == 422
        assert mv("nonexistent", "carico", "2026-01-02", 10, 1).status_code == 404
        r = mv(ST["a"], "scarico", "2026-01-02", 1)
        assert r.status_code == 400 and "Giacenza insufficiente" in r.json()["detail"]

    def test_02_weighted_average(self):
        r = mv(ST["a"], "carico", "2026-01-02", 200, 0.10)
        assert r.status_code == 200, r.text
        ST["c1"] = r.json()["id"]
        r = mv(ST["a"], "carico", "2026-01-05", 100, 0.40, causale="Produzione", tok=OTOK)  # operatore can register
        assert r.status_code == 200, r.text
        ST["c2"] = r.json()["id"]
        a = r.json()["articolo"]
        assert a["giacenza"] == 300 and abs(a["costo_medio"] - 0.20) < 1e-9 and a["valore_magazzino"] == 60

    def test_03_scarico_at_avg(self):
        r = mv(ST["a"], "scarico", "2026-01-10", 250)
        assert r.status_code == 200, r.text
        ST["s1"] = r.json()["id"]
        assert r.json()["costo_unitario"] is None
        a = get_art(ST["a"])
        assert a["giacenza"] == 50 and abs(a["costo_medio"] - 0.20) < 1e-9 and a["valore_magazzino"] == 10
        assert a["stato_scorta"] == "sottoscorta" and a["da_ordinare"] == 500

    def test_04_backdated_scarico_negative_refused(self):
        # on 2026-01-03 stock is 200; a scarico of 190 there would leave -40 after the 01-10 scarico
        r = mv(ST["a"], "scarico", "2026-01-03", 190)
        assert r.status_code == 400 and "Giacenza insufficiente" in r.json()["detail"], r.text
        # before first carico
        r = mv(ST["a"], "scarico", "2026-01-01", 1)
        assert r.status_code == 400

    def test_05_rettifica_plus_minus(self):
        r = mv(ST["a"], "rettifica", "2026-01-11", -2)
        assert r.status_code == 200, r.text
        ST["r1"] = r.json()["id"]
        r = mv(ST["a"], "rettifica", "2026-01-12", 5)
        assert r.status_code == 200
        ST["r2"] = r.json()["id"]
        a = get_art(ST["a"])
        assert a["giacenza"] == 53 and abs(a["costo_medio"] - 0.20) < 1e-9
        assert mv(ST["a"], "rettifica", "2026-01-12", -1000).status_code == 400
        assert mv(ST["a"], "rettifica", "2026-01-12", 1, causale="Acquisto").status_code == 400

    def test_06_movimenti_list_with_giacenza_dopo(self):
        rows = sess(OTOK).get(f"{API}/magazzino/movimenti", params={"article_id": ST["a"]}).json()
        assert len(rows) == 5
        by = {m["id"]: m["giacenza_dopo"] for m in rows}
        assert by[ST["c1"]] == 200 and by[ST["c2"]] == 300 and by[ST["s1"]] == 50 and by[ST["r1"]] == 48 and by[ST["r2"]] == 53
        assert rows[0]["data"] >= rows[-1]["data"]
        assert all("_id" not in m for m in rows)
        rows = sess(TOK).get(f"{API}/magazzino/movimenti", params={"tipo": "carico"}).json()
        assert len(rows) == 2
        rows = sess(TOK).get(f"{API}/magazzino/movimenti", params={"dal": "2026-01-05", "al": "2026-01-10"}).json()
        assert len(rows) == 2

    def test_07_sottoscorta_and_riepilogo(self):
        s = sess(OTOK).get(f"{API}/magazzino/sottoscorta").json()
        assert [a["id"] for a in s] == [ST["a"]] and s[0]["da_ordinare"] == 500
        r = sess(TOK).get(f"{API}/magazzino/riepilogo").json()
        assert r["articoli"] == 1 and r["sottoscorta"] == 1 and r["esauriti"] == 0
        assert abs(r["valore_totale"] - 10.6) < 0.01 and r["elenco"][0]["codice"] == "VITE10"

    def test_08_da_ordinare_uses_minus_gap(self):
        # scorta minima 1000 -> gap 947 > lotto 500
        a = get_art(ST["a"])
        r = sess(TOK).put(f"{API}/articles/{ST['a']}", json=art("VITE10", gestione_magazzino=True, scorta_minima=1000, scorta_riordino=500))
        assert r.status_code == 200
        assert r.json()["giacenza"] == a["giacenza"]  # PUT must not wipe stock fields
        assert get_art(ST["a"])["da_ordinare"] == 947
        sess(TOK).put(f"{API}/articles/{ST['a']}", json=art("VITE10", gestione_magazzino=True, scorta_minima=100, scorta_riordino=500))


# Delete: roles, recompute, negative refusal, article delete
class TestDelete:
    def test_01_operatore_403(self):
        assert sess(OTOK).delete(f"{API}/magazzino/movimenti/{ST['r2']}").status_code == 403

    def test_02_delete_carico_would_go_negative(self):
        r = sess(CTOK).delete(f"{API}/magazzino/movimenti/{ST['c1']}")
        assert r.status_code == 400, r.text
        assert get_art(ST["a"])["giacenza"] == 53

    def test_03_delete_recomputes(self):
        assert sess(CTOK).delete(f"{API}/magazzino/movimenti/{ST['r2']}").status_code == 200
        a = get_art(ST["a"])
        assert a["giacenza"] == 48
        assert sess(CTOK).delete(f"{API}/magazzino/movimenti/{ST['r2']}").status_code == 404

    def test_04_article_with_moves_cannot_be_deleted(self):
        r = sess(TOK).delete(f"{API}/articles/{ST['a']}")
        assert r.status_code == 400 and "movimenti" in r.json()["detail"]
        assert sess(TOK).delete(f"{API}/articles/{ST['nomag']}").status_code == 200

    def test_05_esaurito(self):
        r = mv(ST["a"], "scarico", "2026-01-20", 48)
        assert r.status_code == 200
        a = get_art(ST["a"])
        assert a["giacenza"] == 0 and a["stato_scorta"] == "esaurito" and a["da_ordinare"] == 500 and a["valore_magazzino"] == 0
        assert sess(TOK).get(f"{API}/magazzino/riepilogo").json()["esauriti"] == 1


# Module gating
class TestGating:
    def test_01_fatturazione_off_403(self):
        r = sess(TOK).put(f"{API}/companies/{ST['cid']}/moduli", json={**ALL, "fatturazione": False})
        assert r.status_code == 200, r.text
        for p in ("articoli", "sottoscorta", "movimenti", "riepilogo"):
            assert sess(TOK).get(f"{API}/magazzino/{p}").status_code == 403, p
        assert mv(ST["a"], "carico", "2026-01-21", 1, 1).status_code == 403
        assert sess(TOK).put(f"{API}/companies/{ST['cid']}/moduli", json=ALL).status_code == 200
        assert sess(TOK).get(f"{API}/magazzino/articoli").status_code == 200

    def test_02_no_company_header(self):
        s = requests.Session()
        s.headers["Authorization"] = f"Bearer {TOK}"
        assert s.get(f"{API}/magazzino/articoli").status_code == 400
        assert requests.get(f"{API}/magazzino/articoli", headers={"X-Company-Id": ST["cid"]}).status_code == 401

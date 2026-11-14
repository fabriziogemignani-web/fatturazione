# Iteration 75: Ordini clienti/fornitori (impegnato/ordinato/disponibilita), evasione totale/parziale/forzata -> DDT / BEM, annulla storno, destinazioni cliente, isolation, menu_off.
# Run: pytest tests/test_iteration75_ordini_bem.py -v -n 0   (T75_KEEP=1 keeps data for UI; `python tests/<file> clean`)
import json
import os
import random
import sys
from datetime import date, timedelta

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

RUN = os.environ.get("T75_RUN") or str(random.randint(100000, 999999))
TOK, UID = "test_session_t75_admin", "test-user-t75-admin"
PIVA = "75" + RUN + "751"
TODAY = date.today().isoformat()
ST = {}
COLLS = ["invoices", "parties", "articles", "orders", "ddts", "bem", "stock_moves", "audit", "counters", "coa_accounts", "coa_causali", "coa_iva"]


def sess(cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    c = cid or ST.get("cid")
    if c:
        s.headers["X-Company-Id"] = c
    return s


def clean():
    mongo(f'db.companies.find({{denominazione:/^TEST_T75/}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def company(name, piva=PIVA):
    r = sess("x").post(f"{API}/companies", json={"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01",
                                                 "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def party(tipo, name, piva, **kw):
    r = sess().post(f"{API}/parties", json={"tipo": tipo, "denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "codice_destinatario": "ABC1234", "indirizzo": "Via X 1",
                                           "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT", **kw})
    assert r.status_code == 200, r.text
    return r.json()


def article(cod, carico=0):
    r = sess().post(f"{API}/articles", json={"codice": cod, "descrizione": f"TEST_T75 {cod}", "unita_misura": "PZ", "prezzo": 10, "aliquota": 22, "gestione_magazzino": True})
    assert r.status_code == 200, r.text
    aid = r.json()["id"]
    if carico:
        m = sess().post(f"{API}/magazzino/movimenti", json={"article_id": aid, "tipo": "carico", "data": (date.today() - timedelta(days=5)).isoformat(),
                                                          "quantita": carico, "costo_unitario": 5, "causale": "Acquisto"})
        assert m.status_code == 200, m.text
    return aid


def art(aid):
    rows = sess().get(f"{API}/magazzino/articoli").json()["articoli"]
    return next(a for a in rows if a["id"] == aid)


def ordine(tipo, pid, lines, **kw):
    r = sess().post(f"{API}/ordini/{tipo}", json={"data": TODAY, "party_id": pid, "lines": lines, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def ln(aid, q, p=10):
    return {"article_id": aid, "descrizione": "TEST_T75 riga", "quantita": q, "prezzo_unitario": p, "aliquota": 22, "unita_misura": "PZ"}


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t75.admin@example.com", name:"TEST_T75 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    ST["cid"] = company(f"TEST_T75 Ordini {RUN} Srl")
    ST["cid2"] = company(f"TEST_T75 Altra {RUN} Srl", "76" + RUN + "761")
    ST["cli"] = party("cliente", "TEST_T75 Cliente", "01234567890", destinazioni=[{"denominazione": "Magazzino Nord", "indirizzo": "Via Dest 5", "cap": "10100", "comune": "Torino", "provincia": "TO"}])
    ST["for"] = party("fornitore", "TEST_T75 Fornitore", "09876543217")
    ST["A"] = article(f"T75A{RUN}", 100)
    ST["B"] = article(f"T75B{RUN}", 5)
    ST["C"] = article(f"T75C{RUN}", 0)
    yield
    if os.environ.get("T75_KEEP"):
        print("\nKEEP", RUN, ST["cid"])
    else:
        clean()


class TestDestinazioni:
    def test_01_party_destinazioni_saved(self):
        p = sess().get(f"{API}/parties").json()
        c = next(x for x in p if x["id"] == ST["cli"]["id"])
        assert c["destinazioni"][0]["comune"] == "Torino" and c["destinazioni"][0]["denominazione"] == "Magazzino Nord"

    def test_02_destinazione_required_fields(self):
        r = sess().post(f"{API}/parties", json={"tipo": "cliente", "denominazione": "TEST_T75 Bad", "partita_iva": "01234567890", "codice_fiscale": "01234567890", "indirizzo": "Via X", "cap": "20100",
                                               "comune": "Milano", "nazione": "IT", "destinazioni": [{"indirizzo": "", "comune": ""}]})
        assert r.status_code == 422, r.text


class TestOrdiniCliente:
    def test_10_create_impegnato(self):
        dest = ST["cli"]["destinazioni"][0]
        o = ordine("cliente", ST["cli"]["id"], [ln(ST["A"], 10), ln(ST["B"], 8)], destinazione=dest, riferimento="PO-77")
        assert o["numero_display"].startswith("OC ") and o["numero_display"].endswith(f"/{date.today().year}")
        assert o["status"] == "aperto" and o["imponibile"] == 180
        ST["oc"] = o
        a = art(ST["A"])
        assert (a["giacenza"], a["impegnato"], a["disponibilita"]) == (100, 10, 90), a
        b = art(ST["B"])
        assert (b["giacenza"], b["impegnato"], b["disponibilita"]) == (5, 8, -3), b

    def test_11_list_filter(self):
        rows = sess().get(f"{API}/ordini/cliente", params={"stato": "aperto"}).json()
        assert any(x["id"] == ST["oc"]["id"] for x in rows)
        assert not any(x["id"] == ST["oc"]["id"] for x in sess().get(f"{API}/ordini/cliente", params={"stato": "evaso"}).json())

    def test_12_evadi_errors(self):
        o = ST["oc"]
        la, lb = o["lines"]
        r = sess().post(f"{API}/ordini/cliente/{o['id']}/evadi", json={"data": TODAY, "righe": [{"line_id": la["id"], "quantita": 11}]})
        assert r.status_code == 422, r.text
        fut = (date.today() + timedelta(days=3)).isoformat()
        r = sess().post(f"{API}/ordini/cliente/{o['id']}/evadi", json={"data": fut, "righe": [{"line_id": la["id"], "quantita": 1}]})
        assert r.status_code == 400, r.text
        r = sess().post(f"{API}/ordini/cliente/{o['id']}/evadi", json={"data": TODAY, "righe": [{"line_id": lb["id"], "quantita": 8}]})
        assert r.status_code == 409, r.text
        assert "carenze" in json.dumps(r.json())
        assert not sess().get(f"{API}/ddt").json() or all(d.get("ordine_id") != o["id"] for d in sess().get(f"{API}/ddt").json() if isinstance(d, dict))

    def test_13_evadi_parziale(self):
        o = ST["oc"]
        la = o["lines"][0]
        r = sess().post(f"{API}/ordini/cliente/{o['id']}/evadi", json={"data": TODAY, "righe": [{"line_id": la["id"], "quantita": 4}]})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "parziale" and j["documento"]["tipo"] == "ddt"
        d = sess().get(f"{API}/ddt/{j['documento']['doc_id']}").json()
        assert d["status"] == "confermato" and d["ordine_id"] == o["id"] and "Rif. ordine" in d["note"] and "PO-77" in d["note"]
        assert d["destinazione"]["comune"] == "Torino"
        ST["ddt1"] = d["id"]
        a = art(ST["A"])
        assert (a["giacenza"], a["impegnato"], a["disponibilita"]) == (96, 6, 90), a
        pdf = sess().get(f"{API}/ddt/{d['id']}/pdf")
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"

    def test_14_edit_rules(self):
        o = sess().get(f"{API}/ordini/cliente/{ST['oc']['id']}").json()
        body = {"data": o["data"], "party_id": o["party_id"], "lines": [{**x, "quantita": 2} if x["article_id"] == ST["A"] else x for x in o["lines"]]}
        r = sess().put(f"{API}/ordini/cliente/{o['id']}", json=body)
        assert r.status_code == 422, r.text  # below evasa (4)
        body = {"data": o["data"], "party_id": o["party_id"], "lines": [x for x in o["lines"] if x["article_id"] != ST["A"]]}
        r = sess().put(f"{API}/ordini/cliente/{o['id']}", json=body)
        assert r.status_code == 400, r.text  # removing evaded line
        r = sess().delete(f"{API}/ordini/cliente/{o['id']}")
        assert r.status_code == 400, r.text
        body = {"data": o["data"], "party_id": o["party_id"], "lines": [{**x, "quantita": 12} if x["article_id"] == ST["A"] else x for x in o["lines"]]}
        r = sess().put(f"{API}/ordini/cliente/{o['id']}", json=body)
        assert r.status_code == 200, r.text
        assert art(ST["A"])["impegnato"] == 8

    def test_15_annulla_ddt_reverts(self):
        r = sess().post(f"{API}/ddt/{ST['ddt1']}/annulla")
        assert r.status_code == 200, r.text
        o = sess().get(f"{API}/ordini/cliente/{ST['oc']['id']}").json()
        assert o["status"] == "aperto" and o["lines"][0]["evasa"] == 0
        a = art(ST["A"])
        assert (a["giacenza"], a["impegnato"], a["disponibilita"]) == (100, 12, 88), a

    def test_16_evadi_forza_and_chiudi(self):
        o = sess().get(f"{API}/ordini/cliente/{ST['oc']['id']}").json()
        la, lb = o["lines"]
        r = sess().post(f"{API}/ordini/cliente/{o['id']}/evadi", json={"data": TODAY, "forza": True, "chiudi": True,
                                                                     "righe": [{"line_id": la["id"], "quantita": 5}, {"line_id": lb["id"], "quantita": 6}]})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "chiuso"
        ST["ddt2"] = j["documento"]["doc_id"]
        a, b = art(ST["A"]), art(ST["B"])
        assert (a["giacenza"], a["impegnato"]) == (95, 0), a
        assert (b["giacenza"], b["impegnato"], b["disponibilita"]) == (-1, 0, -1), b
        r = sess().post(f"{API}/ordini/cliente/{o['id']}/evadi", json={"data": TODAY, "righe": [{"line_id": la["id"], "quantita": 1}]})
        assert r.status_code == 400

    def test_17_riapri_chiudi(self):
        oid = ST["oc"]["id"]
        r = sess().post(f"{API}/ordini/cliente/{oid}/riapri")
        assert r.status_code == 200 and r.json()["status"] == "parziale", r.text
        assert art(ST["A"])["impegnato"] == 7 and art(ST["B"])["impegnato"] == 2
        r = sess().post(f"{API}/ordini/cliente/{oid}/chiudi")
        assert r.status_code == 200 and r.json()["status"] == "chiuso"
        assert art(ST["A"])["impegnato"] == 0
        assert sess().post(f"{API}/ordini/cliente/{oid}/chiudi").status_code == 400

    def test_18_annulla_on_chiuso_stays_chiuso(self):
        r = sess().post(f"{API}/ddt/{ST['ddt2']}/annulla")
        assert r.status_code == 200, r.text
        o = sess().get(f"{API}/ordini/cliente/{ST['oc']['id']}").json()
        assert o["status"] == "chiuso" and all(x["evasa"] == 0 for x in o["lines"])
        assert art(ST["A"])["impegnato"] == 0 and art(ST["A"])["giacenza"] == 100

    def test_19_evadi_totale_and_delete(self):
        o = ordine("cliente", ST["cli"]["id"], [ln(ST["A"], 3)])
        r = sess().post(f"{API}/ordini/cliente/{o['id']}/evadi", json={"data": TODAY, "righe": [{"line_id": o["lines"][0]["id"], "quantita": 3}]})
        assert r.status_code == 200 and r.json()["status"] == "evaso", r.text
        assert sess().put(f"{API}/ordini/cliente/{o['id']}", json={"data": TODAY, "party_id": ST["cli"]["id"], "lines": [ln(ST["A"], 3)]}).status_code == 400
        o2 = ordine("cliente", ST["cli"]["id"], [ln(ST["A"], 2)])
        assert art(ST["A"])["impegnato"] == 2
        assert sess().delete(f"{API}/ordini/cliente/{o2['id']}").status_code == 200
        assert sess().get(f"{API}/ordini/cliente/{o2['id']}").status_code == 404
        assert art(ST["A"])["impegnato"] == 0


class TestOrdiniFornitore:
    def test_20_create_ordinato(self):
        o = ordine("fornitore", ST["for"]["id"], [ln(ST["C"], 20, 7.5)])
        assert o["numero_display"].startswith("OF ")
        ST["of"] = o
        c = art(ST["C"])
        assert (c.get("giacenza") or 0, c["ordinato"], c["disponibilita"]) == (0, 20, 20), c
        assert sess().post(f"{API}/ordini/cliente", json={"data": TODAY, "party_id": ST["for"]["id"], "lines": [ln(ST["C"], 1)]}).status_code == 400

    def test_21_evadi_bem_parziale(self):
        o = ST["of"]
        r = sess().post(f"{API}/ordini/fornitore/{o['id']}/evadi", json={"data": TODAY, "documento_fornitore": "DDT-F 99", "righe": [{"line_id": o["lines"][0]["id"], "quantita": 12}]})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "parziale" and j["documento"]["tipo"] == "bem"
        b = next(x for x in sess().get(f"{API}/bem").json() if x["id"] == j["documento"]["doc_id"])
        assert b["documento_fornitore"] == "DDT-F 99" and b["status"] == "confermato" and b["ordine_id"] == o["id"]
        ST["bem1"] = b["id"]
        c = art(ST["C"])
        assert (c["giacenza"], c["ordinato"], c["disponibilita"]) == (12, 8, 20), c
        mv = sess().get(f"{API}/magazzino/movimenti", params={"article_id": ST["C"]}).json()
        m = next(x for x in mv if x.get("bem_id") == b["id"])
        assert m["costo_unitario"] == 7.5 and m["causale"] == "Acquisto" and m["tipo"] == "carico"
        ST["bem_move"] = m["id"]

    def test_22_bem_move_not_deletable(self):
        r = sess().delete(f"{API}/magazzino/movimenti/{ST['bem_move']}")
        assert r.status_code == 400, r.text

    def test_23_bem_annulla_blocked_negative(self):
        s = sess().post(f"{API}/magazzino/movimenti", json={"article_id": ST["C"], "tipo": "scarico", "data": TODAY, "quantita": 10, "causale": "Uso interno"})
        assert s.status_code == 200, s.text
        r = sess().post(f"{API}/bem/{ST['bem1']}/annulla")
        assert r.status_code == 400, r.text
        assert sess().delete(f"{API}/magazzino/movimenti/{s.json()['id']}").status_code == 200

    def test_24_bem_annulla_reverts(self):
        r = sess().post(f"{API}/bem/{ST['bem1']}/annulla")
        assert r.status_code == 200, r.text
        o = sess().get(f"{API}/ordini/fornitore/{ST['of']['id']}").json()
        assert o["status"] == "aperto" and o["lines"][0]["evasa"] == 0
        c = art(ST["C"])
        assert (c["giacenza"], c["ordinato"]) == (0, 20), c
        assert sess().post(f"{API}/bem/{ST['bem1']}/annulla").status_code == 400

    def test_25_evadi_totale(self):
        o = ST["of"]
        r = sess().post(f"{API}/ordini/fornitore/{o['id']}/evadi", json={"data": TODAY, "righe": [{"line_id": o["lines"][0]["id"], "quantita": 20}]})
        assert r.status_code == 200 and r.json()["status"] == "evaso", r.text
        c = art(ST["C"])
        assert (c["giacenza"], c["ordinato"], c["disponibilita"]) == (20, 0, 20), c


class TestIsolationPerms:
    def test_30_isolation(self):
        s2 = sess(ST["cid2"])
        assert s2.get(f"{API}/ordini/cliente/{ST['oc']['id']}").status_code == 404
        assert not s2.get(f"{API}/ordini/cliente").json()
        assert not s2.get(f"{API}/bem").json()
        assert s2.post(f"{API}/bem/{ST['bem1']}/annulla").status_code == 404

    def test_31_menu_off(self):
        cid = ST["cid"]
        mongo(f'db.companies.updateOne({{id:"{cid}"}}, {{$set:{{menu_off:["ordini-fornitori","bem"]}}}})')
        try:
            assert sess().get(f"{API}/ordini/fornitore").status_code == 403
            assert sess().get(f"{API}/bem").status_code == 403
            assert sess().get(f"{API}/ordini/cliente").status_code == 200
        finally:
            mongo(f'db.companies.updateOne({{id:"{cid}"}}, {{$set:{{menu_off:[]}}}})')


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "clean":
    clean()

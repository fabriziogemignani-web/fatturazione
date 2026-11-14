# Iteration 77: Article conto_costo (validation), GET /passive/{pid}/proposta-bem (split per aliquota across conti costo, rounding),
# registrazione with BEM proposal -> prima nota cost accounts, GET /magazzino/proposta-ordine (grouping by supplier, quantities, price) + order creation.
# Run: pytest tests/test_iteration77_proposta_bem_sottoscorta.py -v -n 0   (T77_KEEP=1 keeps data for UI)
import json
import os
import random
import sys
from datetime import date

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

RUN = os.environ.get("T77_RUN") or str(random.randint(100000, 999999))
TOK, UID = "test_session_t77_admin", "test-user-t77-admin"
PIVA = "77" + RUN + "771"
TODAY = date.today().isoformat()
ST = {}


def sess(cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    c = cid or ST.get("cid")
    if c:
        s.headers["X-Company-Id"] = c
    return s


def clean():
    mongo('db.companies.find({denominazione:/^TEST_T77/}).forEach(c=>{db.getCollectionNames().forEach(k=>{if(k!=="companies") db[k].deleteMany({company_id:c.id})});'
          'db.users.updateMany({}, {$pull:{company_ids:c.id}}); db.companies.deleteOne({id:c.id});});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def party(tipo, name, piva):
    r = sess().post(f"{API}/parties", json={"tipo": tipo, "denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "codice_destinatario": "ABC1234",
                                           "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"})
    assert r.status_code == 200, r.text
    return r.json()


def article(cod, aliquota=22, **kw):
    body = {"codice": cod, "descrizione": f"TEST_T77 {cod}", "unita_misura": "PZ", "prezzo": 10, "aliquota": aliquota, "gestione_magazzino": True} | kw
    r = sess().post(f"{API}/articles", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def ordine(pid, lines, **kw):
    r = sess().post(f"{API}/ordini/fornitore", json={"data": TODAY, "party_id": pid, "lines": lines, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def ln(a, q, p):
    return {"article_id": a["id"], "descrizione": a["descrizione"], "quantita": q, "prezzo_unitario": p, "aliquota": a["aliquota"], "unita_misura": "PZ"}


def evadi_tutto(o):
    r = sess().post(f"{API}/ordini/fornitore/{o['id']}/evadi", json={"data": TODAY, "righe": [{"line_id": x["id"], "quantita": x["quantita"]} for x in o["lines"]]})
    assert r.status_code == 200, r.text
    return r.json()["documento"]["doc_id"]


def passiva(numero, riepilogo):
    pid = f"t77-{numero}-{RUN}"
    imp = round(sum(x["imponibile"] for x in riepilogo), 2)
    iva = round(sum(x["imposta"] for x in riepilogo), 2)
    f = ST["F"]
    doc = {"id": pid, "company_id": ST["cid"], "origine": "upload", "numero": numero, "numero_display": numero, "data": TODAY, "tipo_documento": "TD01",
           "fornitore": {"denominazione": f["denominazione"], "partita_iva": f["partita_iva"], "codice_fiscale": f["partita_iva"], "nazione": "IT"}, "party_id": f["id"],
           "riepilogo": riepilogo, "imponibile": imp, "iva": iva, "totale": round(imp + iva, 2), "netto": round(imp + iva, 2), "rate": [], "lines": [],
           "stato_reg": "da_registrare", "stato_pagamento": "da_pagare", "detraibilita_iva": 100, "scadenza": TODAY, "note": "", "ricevuta_at": TODAY + "T08:00:00+00:00",
           "hash": pid, "created_at": TODAY}
    mongo(f"db.passive_invoices.insertOne({json.dumps(doc)})")
    return pid


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t77.admin@example.com", name:"TEST_T77 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess("x").post(f"{API}/companies", json={"denominazione": f"TEST_T77 Riordino {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                                 "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    sess().put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                            "corrispettivi": True, "contabilita": True})
    conti = sess().get(f"{API}/contabilita/conti").json()["conti"]
    costi = [c["codice"] for c in conti if c.get("tipo") == "costo" and c.get("livello") == 3]
    assert len(costi) >= 3, costi
    ST["c1"], ST["c2"] = costi[1], costi[2]
    ST["F"] = party("fornitore", "TEST_T77 Fornitore Alfa", "09876543217")
    ST["F2"] = party("fornitore", "TEST_T77 Fornitore Beta", "12345678903")
    yield
    if os.environ.get("T77_KEEP"):
        print("\nKEEP", RUN, ST["cid"], json.dumps({k: v for k, v in ST.items() if isinstance(v, str)}))
    else:
        clean()


# --- Article conto_costo ---
class TestArticleConto:
    def test_01_invalid_conto_post_put(self):
        r = sess().post(f"{API}/articles", json={"codice": f"T77X{RUN}", "descrizione": "TEST_T77 X", "prezzo": 1, "aliquota": 22, "conto_costo": "99.99.999"})
        assert r.status_code in (400, 422), r.text
        ST["conto_invalid_status"] = r.status_code
        a = article(f"T77OK{RUN}", conto_costo=ST["c1"])
        assert a["conto_costo"] == ST["c1"]
        r = sess().put(f"{API}/articles/{a['id']}", json={"codice": a["codice"], "descrizione": a["descrizione"], "prezzo": 1, "aliquota": 22, "conto_costo": "12.34"})
        assert r.status_code in (400, 422), r.text
        got = next(x for x in sess().get(f"{API}/articles").json() if x["id"] == a["id"])
        assert got["conto_costo"] == ST["c1"]
        sess().delete(f"{API}/articles/{a['id']}")

    def test_02_invalid_conto_status_is_422(self):
        assert ST["conto_invalid_status"] == 422, f"invalid conto_costo returns {ST['conto_invalid_status']} (spec says 422)"


# --- Proposta ordine sottoscorta ---
class TestPropostaOrdine:
    def test_10_setup_articles(self):
        ST["A"] = article(f"T77A{RUN}", conto_costo=ST["c1"], scorta_minima=10, scorta_riordino=20, fornitore_abituale="  test_t77 FORNITORE alfa ")
        ST["B"] = article(f"T77B{RUN}", conto_costo=ST["c2"], scorta_minima=5, scorta_riordino=0, fornitore_abituale="TEST_T77 Fornitore Alfa")
        ST["C"] = article(f"T77C{RUN}", aliquota=10, conto_costo=ST["c1"], fornitore_abituale="TEST_T77 Fornitore Alfa")
        ST["D"] = article(f"T77D{RUN}", fornitore_abituale="TEST_T77 Fornitore Alfa")
        ST["E"] = article(f"T77E{RUN}", scorta_minima=3, fornitore_abituale="TEST_T77 Ditta Sconosciuta")
        ST["G"] = article(f"T77G{RUN}", scorta_minima=5, fornitore_abituale="TEST_T77 Fornitore Alfa", gestione_magazzino=False)
        ST["H"] = article(f"T77H{RUN}", scorta_minima=2, fornitore_abituale="TEST_T77 Fornitore Beta")

    def test_11_groups(self):
        r = sess().get(f"{API}/magazzino/proposta-ordine")
        assert r.status_code == 200, r.text
        g = r.json()["gruppi"]
        assert [x["fornitore"] for x in g] == ["TEST_T77 Fornitore Alfa", "TEST_T77 Fornitore Beta", "TEST_T77 Ditta Sconosciuta"], g
        assert g[0]["party_id"] == ST["F"]["id"] and g[1]["party_id"] == ST["F2"]["id"] and g[2]["party_id"] == ""
        q = {x["codice"]: x["quantita"] for x in g[0]["lines"]}
        assert q == {ST["A"]["codice"]: 20, ST["B"]["codice"]: 5}, q
        all_cod = [x["codice"] for gg in g for x in gg["lines"]]
        assert ST["G"]["codice"] not in all_cod and ST["C"]["codice"] not in all_cod
        ST["gA"] = g[0]

    def test_12_create_order_from_proposal_removes_articles(self):
        lines = [{k: x[k] for k in ("article_id", "descrizione", "quantita", "unita_misura", "aliquota")} | {"prezzo_unitario": 7.5} for x in ST["gA"]["lines"]]
        o = ordine(ST["F"]["id"], lines, note="Riordino articoli sottoscorta")
        assert o["numero_display"].startswith("OF ")
        ST["of_riordino"] = o
        g = sess().get(f"{API}/magazzino/proposta-ordine").json()["gruppi"]
        cod = [x["codice"] for gg in g for x in gg["lines"]]
        assert ST["A"]["codice"] not in cod and ST["B"]["codice"] not in cod, g
        assert ST["E"]["codice"] in cod and ST["H"]["codice"] in cod

    def test_13_price_last_carico_and_partial_disp(self):
        evadi_tutto(ST["of_riordino"])  # A giacenza 20 @7.5, B 5 @7.5
        r = sess().post(f"{API}/magazzino/movimenti", json={"article_id": ST["A"]["id"], "tipo": "scarico", "data": TODAY, "quantita": 15, "causale": "Vendita"})
        assert r.status_code == 200, r.text
        g = sess().get(f"{API}/magazzino/proposta-ordine").json()["gruppi"]
        la = next(x for gg in g for x in gg["lines"] if x["codice"] == ST["A"]["codice"])
        assert la["disponibilita"] == 5 and la["quantita"] == 20 and la["prezzo_unitario"] == 7.5, la

    def test_14_qty_min_minus_disp_when_bigger(self):
        r = sess().put(f"{API}/articles/{ST['A']['id']}", json={**{k: ST["A"][k] for k in ("codice", "descrizione", "unita_misura", "prezzo", "aliquota", "fornitore_abituale", "conto_costo")},
                                                                 "gestione_magazzino": True, "scorta_minima": 40, "scorta_riordino": 20})
        assert r.status_code == 200, r.text
        g = sess().get(f"{API}/magazzino/proposta-ordine").json()["gruppi"]
        la = next(x for gg in g for x in gg["lines"] if x["codice"] == ST["A"]["codice"])
        assert la["quantita"] == 35, la


# --- Proposta registrazione da BEM ---
class TestPropostaBem:
    def test_20_setup_bem_and_invoice(self):
        A, B, C, D = ST["A"], ST["B"], ST["C"], ST["D"]
        o = ordine(ST["F"]["id"], [ln(A, 2, 10), ln(B, 1, 30), ln(C, 4, 5), ln(D, 1, 50)])
        ST["bem2"] = evadi_tutto(o)
        ST["pid"] = passiva(f"F77-{RUN}", [{"aliquota": 22, "natura": None, "imponibile": 100.01, "imposta": 22.01},
                                         {"aliquota": 10, "natura": None, "imponibile": 20, "imposta": 2},
                                         {"aliquota": 4, "natura": None, "imponibile": 5, "imposta": 0.2}])
        ST["pid_nobem"] = passiva(f"F77N-{RUN}", [{"aliquota": 22, "natura": None, "imponibile": 10, "imposta": 2.2}])

    def test_21_no_bem_empty(self):
        r = sess().get(f"{API}/passive/{ST['pid_nobem']}/proposta-bem")
        assert r.status_code == 200 and r.json()["riepilogo"] == [], r.text
        assert sess().get(f"{API}/passive/nope/proposta-bem").status_code == 404

    def test_22_split(self):
        assert sess().post(f"{API}/passive/{ST['pid']}/bem", json={"bem_id": ST["bem2"]}).status_code == 200
        d = sess().get(f"{API}/passive/{ST['pid']}/proposta-bem").json()
        print(json.dumps(d))
        rows = d["riepilogo"]
        assert d["senza_conto"] == 1 and len(d["bem"]) == 1
        r22 = [x for x in rows if x["aliquota"] == 22]
        assert {x["conto"] for x in r22} == {ST["c1"], ST["c2"], ""}
        assert round(sum(x["imponibile"] for x in r22), 2) == 100.01 and round(sum(x["imposta"] for x in r22), 2) == 22.01
        byc = {x["conto"]: x for x in r22}
        assert abs(byc[ST["c1"]]["imponibile"] - 20) <= 0.01 and abs(byc[ST["c2"]]["imponibile"] - 30) <= 0.01 and abs(byc[""]["imponibile"] - 50.01) <= 0.01
        r10 = [x for x in rows if x["aliquota"] == 10]
        assert r10 == [{"aliquota": 10, "natura": "", "imponibile": 20, "imposta": 2, "conto": ST["c1"]}]
        r4 = [x for x in rows if x["aliquota"] == 4]
        assert len(r4) == 1 and r4[0]["conto"] == "" and r4[0]["imponibile"] == 5
        ST["prop"] = rows

    def _body(self):
        return {"numero": f"F77-{RUN}", "data": TODAY, "data_registrazione": TODAY, "aliquota_rc": 22, "detraibilita_iva": 100,
                "riepilogo": [{**x, "natura": x["natura"] or None} for x in ST["prop"]]}

    def test_23_anteprima_dare_on_article_accounts(self):
        r = sess().post(f"{API}/passive/{ST['pid']}/registrazione/anteprima", json=self._body())
        assert r.status_code == 200, r.text
        dare = {}
        for x in r.json()["righe"]:
            if x.get("dare"):
                dare[x["conto"]] = round(dare.get(x["conto"], 0) + x["dare"], 2)
        print("DARE", dare)
        ST["dare"] = dare
        assert dare.get(ST["c1"]) and dare.get(ST["c2"])

    def test_24_anteprima_default_cost_keeps_share(self):
        """Rows without conto (article without conto_costo, aliquota 4% not in BEM) must go to the default cost account, not be absorbed by article accounts."""
        dare = ST["dare"]
        # c1 = 20 (22%) + 20 (10%) imponibile -> cost 40 ; c2 = 30 ; default = 50.01 + 5 = 55.01
        assert abs(dare[ST["c1"]] - 40) < 0.02 and abs(dare[ST["c2"]] - 30) < 0.02, dare

    def test_25_register_creates_prima_nota(self):
        r = sess().post(f"{API}/passive/{ST['pid']}/registrazione", json=self._body())
        assert r.status_code == 200, r.text
        regs = sess().get(f"{API}/contabilita/registrazioni", params={"q": f"F77-{RUN}"}).json()
        rows = regs if isinstance(regs, list) else regs.get("registrazioni") or regs.get("rows") or []
        assert rows, regs
        conti = {x["conto"] for e in rows for x in e["righe"] if x.get("dare")}
        assert ST["c1"] in conti and ST["c2"] in conti, conti
        p = sess().get(f"{API}/passive/{ST['pid']}").json()
        assert round(p["imponibile"], 2) == 125.01 and p["stato_reg"] == "registrata"
        ST["originale_set"] = bool(p.get("originale"))
        ST["riep_rows"] = len(p["riepilogo"])

    def test_26_invoice_not_marked_modified(self):
        """Splitting riepilogo per conto should not mark the invoice as modified vs XML nor change the stored riepilogo row count."""
        assert not ST["originale_set"] and ST["riep_rows"] == 3, (ST["originale_set"], ST["riep_rows"])

    def test_27_ui_invoice_kept(self):
        """Unregistered invoice with BEM linked for UI tests."""
        o = ordine(ST["F"]["id"], [ln(ST["A"], 3, 10), ln(ST["B"], 2, 20)])
        ST["bem3"] = evadi_tutto(o)
        ST["pid_ui"] = passiva(f"F77UI-{RUN}", [{"aliquota": 22, "natura": None, "imponibile": 70, "imposta": 15.4}])
        assert sess().post(f"{API}/passive/{ST['pid_ui']}/bem", json={"bem_id": ST["bem3"]}).status_code == 200
        d = sess().get(f"{API}/passive/{ST['pid_ui']}/proposta-bem").json()
        assert [(x["conto"], x["imponibile"]) for x in d["riepilogo"]] == [(ST["c2"], 40), (ST["c1"], 30)], d

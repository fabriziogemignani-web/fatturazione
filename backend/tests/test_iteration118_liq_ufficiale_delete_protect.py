# Iteration 118: Liquidazione IVA stampa di prova / ufficiale / ristampa (stampe_fiscali key liq:<periodicita>) and
# delete protection of movimentati parties, articles, codici IVA.
# Run: pytest tests/test_iteration118_liq_ufficiale_delete_protect.py -v -n 0 -s   (T118_KEEP=1 keeps data for UI tests)
import io
import json
import os
import random
import sys
from datetime import date

import pytest
import requests
from pypdf import PdfReader

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

RUN = os.environ.get("T118_RUN", str(random.randint(100000, 999999)))
TOK, UID = f"test_session_t118_admin_{RUN}", f"test-user-t118-admin-{RUN}"
PIVA = "18" + RUN + "118"
ST = {}
Y = date.today().year
COLLS = ["invoices", "passive_invoices", "parties", "articles", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "audit_log", "partite_aperte", "f24_versamenti", "pag_distinte", "ratei_risconti", "counters", "corrispettivi",
         "ddts", "orders", "ordini_produzione", "porto_barche", "porto_contratti", "stampe_fiscali", "stock_moves", "distinte", "intenti"]


def sess():
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {TOK}", "X-Requested-With": "invoix"})
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{partita_iva:"{PIVA}"}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def party(tipo, name):
    pi = "".join(str(random.randint(0, 9)) for _ in range(11))
    r = sess().post(f"{API}/parties", json={"tipo": tipo, "denominazione": name, "partita_iva": pi, "codice_fiscale": pi, "indirizzo": "Via Verdi 1",
                                            "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT", "codice_destinatario": "0000000"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def article(cod):
    r = sess().post(f"{API}/articles", json={"codice": cod, "descrizione": f"TEST_{cod}", "prezzo": 10, "aliquota": 22})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def rv(tipo, pid, data, righe):
    r = sess().post(f"{API}/reg-veloce", json={"tipo": tipo, "party_id": pid, "numero": f"T118-{random.randint(1000, 9999)}", "data_documento": data,
                                               "data_registrazione": data, "scadenza": f"{Y}-12-31", "righe": righe})
    assert r.status_code == 200, r.text
    return r.json()


def pdf_text(content):
    return "".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(content)).pages)


def uff(periodo, per="mensile"):
    return sess().post(f"{API}/liquidazione-iva/ufficiale", json={"anno": Y, "periodicita": per, "periodo": periodo})


REQ = {"invoices": {"numero": 9999, "status": "manuale", "data": f"{Y}-03-01"}, "payments": {"invoice_id": "t118-x", "importo": 1, "data": f"{Y}-03-01"},
       "passive_payments": {"importo": 1, "data": f"{Y}-03-01"}, "coa_entries": {"numero": 9999, "data": f"{Y}-03-01"}}


def ins(coll, doc):
    d = {"company_id": ST["cid"], "id": "t118-" + coll, **REQ.get(coll, {}), **doc}
    if coll == "coa_entries":
        d["righe"] = [{"conto": "X", "dare": 1, "avere": 0, **d["righe"][0]}, {"conto": "Y", "dare": 0, "avere": 1}]
    anno = ", anno: NumberInt(%d)" % Y if coll in ("invoices", "coa_entries") else ""
    out = mongo(f'db.{coll}.insertOne(Object.assign({json.dumps(d)}, {{{anno[2:]}}}))')
    assert "acknowledged" in out or "insertedId" in out, out


def rm(coll):
    mongo(f'db.{coll}.deleteMany({{company_id:"{ST["cid"]}", id:"t118-{coll}"}})')


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t118.admin.{RUN}@example.com", name:"TEST_T118 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": "TEST_T118 Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    assert sess().put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                                   "corrispettivi": True, "contabilita": True}).status_code == 200
    sess().get(f"{API}/contabilita/conti")
    ST["cli"] = party("cliente", "TEST_T118 Cliente")
    ST["for"] = party("fornitore", "TEST_T118 Fornitore")
    rv("vendita", ST["cli"], f"{Y}-01-15", [{"aliquota": 22, "totale": 1220}])          # Jan IVA debito 220
    rv("acquisto", ST["for"], f"{Y}-02-10", [{"aliquota": 22, "totale": 610}])           # Feb IVA credito 110
    yield
    if os.environ.get("T118_KEEP"):
        print("\nKEEP", RUN, ST["cid"], TOK)
    else:
        clean()


# ---------- Liquidazione: prova / ufficiale / ristampa ----------
class TestLiqUfficiale:
    def test_01_prova_pdf(self):
        r = sess().get(f"{API}/liquidazione-iva/pdf", params={"anno": Y, "periodicita": "mensile", "periodo": 1})
        assert r.status_code == 200 and r.content[:4] == b"%PDF"
        assert "STAMPA DI PROVA" in pdf_text(r.content)
        assert sess().get(f"{API}/liquidazione-iva/pdf", params={"anno": Y, "periodo": 13}).status_code == 422

    def test_02_not_concluded(self):
        m = date.today().month
        r = uff(m)
        assert r.status_code == 400 and "concluso" in r.json()["detail"], r.text

    def test_03_order(self):
        r = uff(2)
        assert r.status_code == 400 and "periodo 1" in r.json()["detail"], r.text

    def test_04_invalid_trimestrale(self):
        assert uff(5, "trimestrale").status_code == 400

    def test_05_ufficiale_1(self):
        r = uff(1)
        assert r.status_code == 200, r.text
        assert r.content[:4] == b"%PDF"
        txt = pdf_text(r.content)
        assert "STAMPA UFFICIALE" in txt and "PROVA" not in txt
        ST["pages1"] = len(PdfReader(io.BytesIO(r.content)).pages)

    def test_06_dup(self):
        r = uff(1)
        assert r.status_code == 400 and "già stato stampato in ufficiale" in r.json()["detail"], r.text

    def test_07_ufficiale_2_pages(self):
        r = uff(2)
        assert r.status_code == 200, r.text
        rows = sess().get(f"{API}/liquidazione-iva/ufficiali", params={"anno": Y, "periodicita": "mensile"}).json()["stampe"]
        print(rows)
        assert [x["periodo"] for x in rows] == [1, 2]
        a, b = rows
        assert a["key"] == "liq:mensile" and a["pagina_da"] == 1 and a["pagina_a"] == ST["pages1"]
        assert b["pagina_da"] == a["pagina_a"] + 1
        assert a["dal"] == f"{Y}-01-01" and a["al"] == f"{Y}-01-31" and b["dal"] == f"{Y}-02-01"
        assert a["dati"]["iva_debito"] == 220 and a["dati"]["da_versare"] == 220
        assert b["dati"]["iva_credito"] == 110
        assert "pdf" not in a
        ST["sid"] = a["id"]
        # trimestrale list separate
        assert sess().get(f"{API}/liquidazione-iva/ufficiali", params={"anno": Y, "periodicita": "trimestrale"}).json()["stampe"] == []

    def test_08_ristampa(self):
        r = sess().get(f"{API}/stampe-fiscali/stampe/{ST['sid']}/pdf")
        assert r.status_code == 200 and r.content[:4] == b"%PDF"
        assert "STAMPA UFFICIALE" in pdf_text(r.content)

    def test_09_in_stampe_definitive(self):
        r = sess().get(f"{API}/stampe-fiscali/stampe", params={"anno": Y})
        assert r.status_code == 200
        assert len([x for x in r.json() if x["key"] == "liq:mensile"]) == 2

    def test_10_stampe_fiscali_ui_list_ok(self):
        # other stampe-fiscali endpoints keep working with liq rows present
        r = sess().get(f"{API}/stampe-fiscali/registri")
        print("registri", r.status_code)
        assert r.status_code in (200, 404)


# ---------- Delete protection ----------
class TestDeleteProtection:
    def test_01_party_used_in_invoices(self):
        r = sess().delete(f"{API}/parties/{ST['cli']}")
        assert r.status_code == 400 and "Anagrafica movimentata" in r.json()["detail"] and "fatture emesse" in r.json()["detail"], r.text
        r = sess().delete(f"{API}/parties/{ST['for']}")
        assert r.status_code == 400 and "fatture ricevute" in r.json()["detail"], r.text

    @pytest.mark.parametrize("coll,field", [("ddts", "party_id"), ("orders", "party_id"), ("partite_aperte", "party_id"), ("payments", "party_id"),
                                            ("passive_payments", "party_id"), ("porto_barche", "party_id"), ("porto_contratti", "party_id"), ("coa_entries", "righe")])
    def test_02_party_used_each(self, coll, field):
        pid = party("cliente", f"TEST_T118 P {coll}")
        ins(coll, {"righe": [{"party_id": pid}]} if field == "righe" else {field: pid})
        try:
            r = sess().delete(f"{API}/parties/{pid}")
            assert r.status_code == 400 and "Anagrafica movimentata" in r.json()["detail"], r.text
        finally:
            rm(coll)
        r = sess().delete(f"{API}/parties/{pid}")
        assert r.status_code == 200, r.text
        assert all(p["id"] != pid for p in sess().get(f"{API}/parties").json())

    @pytest.mark.parametrize("coll,doc", [("invoices", "lines"), ("passive_invoices", "lines"), ("ddts", "lines"), ("orders", "lines"), ("ordini_produzione", "article_id")])
    def test_03_article_used_each(self, coll, doc):
        aid = article(f"T118{coll[:6].upper()}{random.randint(10, 99)}")
        ins(coll, {"lines": [{"article_id": aid}]} if doc == "lines" else {"article_id": aid})
        try:
            r = sess().delete(f"{API}/articles/{aid}")
            assert r.status_code == 400 and "Articolo movimentato" in r.json()["detail"], r.text
        finally:
            rm(coll)
        r = sess().delete(f"{API}/articles/{aid}")
        assert r.status_code == 200, r.text
        assert all(a["id"] != aid for a in sess().get(f"{API}/articles").json())

    def test_04_article_stock_moves(self):
        aid = article(f"T118SM{random.randint(10, 99)}")
        ins("stock_moves", {"article_id": aid})
        try:
            assert sess().delete(f"{API}/articles/{aid}").status_code == 400
        finally:
            rm("stock_moves")
        assert sess().delete(f"{API}/articles/{aid}").status_code == 200

    @pytest.mark.parametrize("coll,doc", [("coa_entries", "righe"), ("passive_invoices", "riepilogo"), ("passive_invoices", "righe_costo"), ("parties", "flat"), ("articles", "flat")])
    def test_05_codice_iva(self, coll, doc):
        cod = f"T{random.randint(1000, 9999)}"
        r = sess().post(f"{API}/contabilita/codici-iva", json={"codice": cod, "descrizione": "TEST_T118 iva", "aliquota": 22})
        assert r.status_code == 200, r.text
        xid = r.json()["id"]
        ins(coll, {"codice_iva": cod} if doc == "flat" else {doc: [{"codice_iva": cod}]})
        try:
            r = sess().delete(f"{API}/contabilita/codici-iva/{xid}")
            assert r.status_code == 400, r.text
            print(coll, doc, r.json()["detail"])
        finally:
            rm(coll)
        r = sess().delete(f"{API}/contabilita/codici-iva/{xid}")
        assert r.status_code == 200, r.text

    def test_06_conto_movimentato(self):
        conti = sess().get(f"{API}/contabilita/conti").json()
        conti = conti.get("conti", conti) if isinstance(conti, dict) else conti
        used = [c for c in conti if c.get("movimentato")]
        if not used:
            pytest.skip("no movimentato non-system conto")
        r = sess().delete(f"{API}/contabilita/conti/{used[0]['id']}")
        print(used[0].get("codice"), r.status_code, r.text[:200])
        assert r.status_code == 400

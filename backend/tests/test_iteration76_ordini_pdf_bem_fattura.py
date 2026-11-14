# Iteration 76: Ordini PDF (ordine/conferma), email preview/send (SMTP missing -> 400, invalid -> 422, local debug SMTP -> email_inviate),
# BEM <-> fattura passiva link/unlink, confronto (ok/quantita/prezzo/mancante/extra), annulla guard, delete passive orphan check.
# Run: pytest tests/test_iteration76_ordini_pdf_bem_fattura.py -v -n 0   (T76_KEEP=1 keeps data for UI)
import json
import os
import random
import sys
from datetime import date

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

RUN = os.environ.get("T76_RUN") or str(random.randint(100000, 999999))
TOK, UID = "test_session_t76_admin", "test-user-t76-admin"
PIVA = "76" + RUN + "761"
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
    mongo('db.companies.find({denominazione:/^TEST_T76/}).forEach(c=>{db.getCollectionNames().forEach(k=>{if(k!=="companies") db[k].deleteMany({company_id:c.id})});'
          'db.users.updateMany({}, {$pull:{company_ids:c.id}}); db.companies.deleteOne({id:c.id});});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def party(tipo, name, piva, **kw):
    r = sess().post(f"{API}/parties", json={"tipo": tipo, "denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "codice_destinatario": "ABC1234", "indirizzo": "Via X 1",
                                           "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT", **kw})
    assert r.status_code == 200, r.text
    return r.json()


def article(cod, prezzo):
    r = sess().post(f"{API}/articles", json={"codice": cod, "descrizione": f"TEST_T76 {cod}", "unita_misura": "PZ", "prezzo": prezzo, "aliquota": 22, "gestione_magazzino": True})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def ordine(tipo, pid, lines, **kw):
    r = sess().post(f"{API}/ordini/{tipo}", json={"data": TODAY, "party_id": pid, "lines": lines, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def ln(aid, q, p, d="TEST_T76 riga"):
    return {"article_id": aid, "descrizione": d, "quantita": q, "prezzo_unitario": p, "aliquota": 22, "unita_misura": "PZ"}


def evadi_tutto(o, **kw):
    r = sess().post(f"{API}/ordini/fornitore/{o['id']}/evadi", json={"data": TODAY, "righe": [{"line_id": x["id"], "quantita": x["quantita"]} for x in o["lines"]], **kw})
    assert r.status_code == 200, r.text
    return r.json()["documento"]["doc_id"]


def passiva(party_id, numero, imponibile, lines):
    r = sess().post(f"{API}/reg-veloce", json={"tipo": "acquisto", "party_id": party_id, "numero": numero, "data_documento": TODAY, "data_registrazione": TODAY,
                                               "righe": [{"aliquota": 22, "totale": round(imponibile * 1.22, 2)}]})
    assert r.status_code == 200, r.text
    rows = json.loads(mongo(f'print(JSON.stringify(db.passive_invoices.find({{company_id:"{ST["cid"]}", numero:"{numero}"}},{{_id:0,id:1,imponibile:1}}).toArray()))') or "[]")
    assert rows, "passive not created"
    pid = rows[0]["id"]
    set_lines(pid, lines)
    return pid


def set_lines(pid, lines):
    mongo(f'db.passive_invoices.updateOne({{id:"{pid}"}}, {{$set:{{lines:{json.dumps(lines)}}}}})')


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t76.admin@example.com", name:"TEST_T76 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess("x").post(f"{API}/companies", json={"denominazione": f"TEST_T76 Ordini {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                                 "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    ST["cli"] = party("cliente", "TEST_T76 Cliente", "01234567890", email="cliente.t76@example.com")
    ST["for"] = party("fornitore", "TEST_T76 Fornitore", "09876543217", pec="fornitore.t76@pec.example.com")
    ST["for2"] = party("fornitore", "TEST_T76 Fornitore Due", "12345678903")
    ST["A"] = article(f"T76A{RUN}", 10)
    ST["B"] = article(f"T76B{RUN}", 20)
    yield
    if os.environ.get("T76_KEEP"):
        print("\nKEEP", RUN, ST["cid"])
    else:
        clean()


# --- PDF ---
class TestPdf:
    def test_01_pdf_cliente_ordine_conferma(self):
        dest = {"denominazione": "Magazzino Nord", "indirizzo": "Via Dest 5", "cap": "10100", "comune": "Torino", "provincia": "TO"}
        o = ordine("cliente", ST["cli"]["id"], [ln(ST["A"], 2, 10), ln(ST["B"], 1, 20)], destinazione=dest, riferimento="PO-76")
        ST["oc"] = o
        for conf, title in ((False, "ORDINE CLIENTE"), (True, "CONFERMA D'ORDINE")):
            r = sess().get(f"{API}/ordini/cliente/{o['id']}/pdf", params={"conferma": str(conf).lower()})
            assert r.status_code == 200, r.text
            assert r.headers["content-type"].startswith("application/pdf") and r.content[:4] == b"%PDF"
            assert ("Conferma_ordine" if conf else "Ordine_") in r.headers.get("content-disposition", "")
            ST[f"pdf_{conf}"] = r.content

    def test_02_pdf_text_content(self):
        try:
            from pypdf import PdfReader
        except ImportError:
            try:
                from PyPDF2 import PdfReader
            except ImportError:
                pytest.skip("no pdf reader")
        from io import BytesIO
        t0 = "".join(p.extract_text() for p in PdfReader(BytesIO(ST["pdf_False"])).pages)
        t1 = "".join(p.extract_text() for p in PdfReader(BytesIO(ST["pdf_True"])).pages)
        assert "ORDINE CLIENTE" in t0 and "CONFERMA D" in t1
        assert "Torino" in t0 and "PO-76" in t0
        assert "48,80" in t0  # totale 40 + 8.80 IVA

    def test_03_pdf_fornitore(self):
        o = ordine("fornitore", ST["for"]["id"], [ln(ST["A"], 5, 10, "Articolo A"), ln(ST["B"], 3, 20, "Articolo B")])
        ST["of1"] = o
        r = sess().get(f"{API}/ordini/fornitore/{o['id']}/pdf", params={"conferma": "true"})
        assert r.status_code == 200 and r.content[:4] == b"%PDF"
        assert "Ordine_OF" in r.headers.get("content-disposition", "")

    def test_04_pdf_404(self):
        assert sess().get(f"{API}/ordini/cliente/nope/pdf").status_code == 404


# --- Email ---
class TestEmail:
    def test_10_preview_cliente(self):
        o = ST["oc"]
        d = sess().get(f"{API}/ordini/cliente/{o['id']}/email", params={"conferma": "true"}).json()
        assert d["to"] == "cliente.t76@example.com"
        assert o["numero_display"] in d["oggetto"] and "conferma" in d["oggetto"].lower()
        assert "TEST_T76 Cliente" in d["messaggio"] and d["inviate"] == []

    def test_11_preview_fornitore_pec(self):
        d = sess().get(f"{API}/ordini/fornitore/{ST['of1']['id']}/email").json()
        assert d["to"] == "fornitore.t76@pec.example.com"
        assert "ordine di acquisto" in d["oggetto"].lower()

    def test_12_send_no_smtp_400(self):
        r = sess().post(f"{API}/ordini/cliente/{ST['oc']['id']}/email", json={"to": "cliente.t76@example.com", "oggetto": "x", "messaggio": "y", "conferma": True})
        assert r.status_code == 400 and "SMTP" in r.text, r.text

    def test_13_send_invalid_email_422(self):
        r = sess().post(f"{API}/ordini/cliente/{ST['oc']['id']}/email", json={"to": "not-an-email", "oggetto": "x", "messaggio": "y"})
        assert r.status_code == 422

    def test_14_send_local_smtp_records(self):
        r = sess().put(f"{API}/company/smtp", json={"host": "127.0.0.1", "port": 1025, "security": "none", "username": "", "from_email": "noreply@example.com"})
        assert r.status_code == 200, r.text
        r = sess().post(f"{API}/ordini/cliente/{ST['oc']['id']}/email", json={"to": "cliente.t76@example.com", "oggetto": "TEST_T76", "messaggio": "Ciao\n<b>x</b>", "conferma": True})
        sess().delete(f"{API}/company/smtp")
        assert r.status_code == 200, r.text
        assert r.json()["conferma"] is True
        o = sess().get(f"{API}/ordini/cliente/{ST['oc']['id']}").json()
        assert len(o.get("email_inviate") or []) == 1 and o["email_inviate"][0]["to"] == "cliente.t76@example.com"
        d = sess().get(f"{API}/ordini/cliente/{ST['oc']['id']}/email").json()
        assert len(d["inviate"]) == 1


# --- BEM <-> fattura passiva ---
class TestBemFattura:
    def test_20_setup_bem_and_passive(self):
        ST["bem1"] = evadi_tutto(ST["of1"], documento_fornitore="DDT-9")
        o2 = ordine("fornitore", ST["for2"]["id"], [ln(ST["A"], 1, 10)])
        ST["bem_other"] = evadi_tutto(o2)
        o3 = ordine("fornitore", ST["for"]["id"], [ln(ST["A"], 1, 10)])
        ST["bem_ann"] = evadi_tutto(o3)
        assert sess().post(f"{API}/bem/{ST['bem_ann']}/annulla").status_code == 200
        lines = [{"n": 1, "descrizione": f"T76A{RUN} Articolo A fornitore", "quantita": 5, "prezzo_unitario": 10, "prezzo_totale": 50, "aliquota": 22},
                 {"n": 2, "descrizione": "articolo   B", "quantita": 3, "prezzo_unitario": 20, "prezzo_totale": 60, "aliquota": 22}]
        ST["pid"] = passiva(ST["for"]["id"], f"F76-{RUN}", 110, lines)
        ST["pid2"] = passiva(ST["for"]["id"], f"F76B-{RUN}", 10, [])

    def test_21_get_candidates(self):
        d = sess().get(f"{API}/passive/{ST['pid']}/bem").json()
        ids = [b["id"] for b in d["candidate"]]
        assert ST["bem1"] in ids and ST["bem_other"] not in ids and ST["bem_ann"] not in ids
        assert d["collegate"] == [] and d["confronto"] is None

    def test_22_link_invalid(self):
        for bid in (ST["bem_other"], ST["bem_ann"], "nope"):
            r = sess().post(f"{API}/passive/{ST['pid']}/bem", json={"bem_id": bid})
            assert r.status_code == 400, (bid, r.text)
        assert sess().post(f"{API}/passive/nope/bem", json={"bem_id": ST["bem1"]}).status_code == 404

    def test_23_link_ok_confronto_all_ok(self):
        r = sess().post(f"{API}/passive/{ST['pid']}/bem", json={"bem_id": ST["bem1"]})
        assert r.status_code == 200, r.text
        d = r.json()
        assert [b["id"] for b in d["collegate"]] == [ST["bem1"]] and ST["bem1"] not in [b["id"] for b in d["candidate"]]
        c = d["confronto"]
        assert [x["esito"] for x in c["righe"]] == ["ok", "ok"], c
        assert c["extra_fattura"] == [] and c["imponibile_bem"] == 110 and c["imponibile_fattura"] == 110 and c["differenza"] == 0 and c["tutto_ok"] is True
        b = next(x for x in sess().get(f"{API}/bem").json() if x["id"] == ST["bem1"])
        assert b["passive_id"] == ST["pid"] and b.get("passive_numero")

    def test_24_already_linked_other_invoice(self):
        r = sess().post(f"{API}/passive/{ST['pid2']}/bem", json={"bem_id": ST["bem1"]})
        assert r.status_code == 400

    def test_25_confronto_differences(self):
        set_lines(ST["pid"], [{"n": 1, "descrizione": f"T76A{RUN} Articolo A", "quantita": 4, "prezzo_unitario": 10, "prezzo_totale": 40, "aliquota": 22},
                              {"n": 2, "descrizione": "Trasporto", "quantita": 1, "prezzo_unitario": 15, "prezzo_totale": 15, "aliquota": 22}])
        c = sess().get(f"{API}/passive/{ST['pid']}/bem").json()["confronto"]
        es = {x["descrizione"]: x["esito"] for x in c["righe"]}
        assert es == {"Articolo A": "quantita", "Articolo B": "mancante"}, c
        assert c["extra_fattura"][0]["descrizione"] == "Trasporto" and c["tutto_ok"] is False
        set_lines(ST["pid"], [{"n": 1, "descrizione": f"T76A{RUN} Articolo A", "quantita": 5, "prezzo_unitario": 11, "prezzo_totale": 55, "aliquota": 22},
                              {"n": 2, "descrizione": "Articolo B", "quantita": 3, "prezzo_unitario": 20, "prezzo_totale": 60, "aliquota": 22}])
        c = sess().get(f"{API}/passive/{ST['pid']}/bem").json()["confronto"]
        assert [x["esito"] for x in c["righe"]] == ["prezzo", "ok"] and c["righe"][0]["diff_prezzo"] == 1

    def test_26_annulla_linked_blocked(self):
        r = sess().post(f"{API}/bem/{ST['bem1']}/annulla")
        assert r.status_code == 400 and "scollega" in r.text.lower(), r.text

    def test_27_unlink(self):
        r = sess().delete(f"{API}/passive/{ST['pid']}/bem/{ST['bem1']}")
        assert r.status_code == 200
        d = r.json()
        assert d["collegate"] == [] and ST["bem1"] in [b["id"] for b in d["candidate"]] and d["confronto"] is None
        b = next(x for x in sess().get(f"{API}/bem").json() if x["id"] == ST["bem1"])
        assert not b.get("passive_id")

    def test_28_delete_passive_unlinks_bem(self):
        """After deleting a passive invoice, linked BEM should not stay orphan-linked (else it can't be annulled)."""
        assert sess().post(f"{API}/passive/{ST['pid2']}/bem", json={"bem_id": ST["bem1"]}).status_code == 200
        r = sess().delete(f"{API}/passive/{ST['pid2']}")
        if r.status_code != 200:
            pytest.skip(f"delete passive not allowed: {r.text}")
        b = next(x for x in sess().get(f"{API}/bem").json() if x["id"] == ST["bem1"])
        assert not b.get("passive_id"), f"BEM still linked to deleted invoice {b.get('passive_numero')}"

    def test_29_isolation_other_company(self):
        r = sess("nonexistent-company").get(f"{API}/passive/{ST['pid']}/bem")
        assert r.status_code in (403, 404)

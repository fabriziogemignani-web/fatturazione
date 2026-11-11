# Iteration 45: line discounts (sconto cascade), customer price list (listino), GET /parties/{pid}/prezzo,
# DDT "Fattura subito" (POST /ddt/{id}/fattura) and fattura accompagnatoria (POST /ddt/{id}/accompagnatoria, DatiTrasporto).
# Run with: REACT_APP_BACKEND_URL=... pytest tests/test_iteration45_sconti_listino_fattura.py -n 0
import io
import os
import subprocess
import sys
from datetime import date

import pytest
import requests
from pypdf import PdfReader

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
PA = "01234567897"
TODAY = date.today().isoformat()
U = ("test-user-t45-admin", "test_session_t45_admin")
S = {}


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


def sess():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {U[1]}"
    if S.get("A"):
        s.headers["X-Company-Id"] = S["A"]
    return s


def clean():
    mongo(f'db.companies.find({{partita_iva:"{PA}", denominazione:/^TEST_T45/}}).forEach(c=>{{["invoices","parties","articles","stock_moves","ddts","payments","coa_entries","coa_accounts","coa_causali","coa_iva","audit","sdi_events"].forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{U[0]}"}}); db.user_sessions.deleteMany({{user_id:"{U[0]}"}});')


def party(s, name, piva, **kw):
    r = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "codice_destinatario": "ABC1234",
                                       "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT", **kw})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{U[0]}", email:"test.user.t45@example.com", name:"TEST_admin45", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{U[0]}", session_token:"{U[1]}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": "TEST_T45 Alfa Srl", "partita_iva": PA, "codice_fiscale": PA, "regime_fiscale": "RF01",
                                              "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    S["A"] = r.json()["id"]
    s = sess()
    for k, mag, prezzo in (("MAG", True, 10), ("NOMAG", False, 7)):
        r = s.post(f"{API}/articles", json={"codice": f"T45{k}", "descrizione": f"TEST art {k}", "unita_misura": "PZ", "prezzo": prezzo, "aliquota": 22, "gestione_magazzino": mag})
        assert r.status_code == 200, r.text
        S[k] = r.json()["id"]
    r = s.post(f"{API}/magazzino/movimenti", json={"article_id": S["MAG"], "tipo": "carico", "data": f"{date.today().year}-01-01", "quantita": 10, "costo_unitario": 5, "causale": "Acquisto"})
    assert r.status_code == 200, r.text
    S["cli"] = party(s, "TEST_T45 Cliente Spa", "02345670481")["id"]
    S["cli2"] = party(s, "TEST_T45 Secondo Srl", "00743110157")["id"]
    yield
    clean()


def giac(aid):
    return next(a for a in sess().get(f"{API}/magazzino/articoli").json()["articoli"] if a["id"] == aid)["giacenza"]


def inv_body(lines, **kw):
    return {"tipo_documento": "TD01", "data": TODAY, "party_id": S["cli"], "lines": lines, **kw}


def ln(sconto="", q=10, p=2, **kw):
    return {"descrizione": "TEST riga", "quantita": q, "prezzo_unitario": p, "aliquota": 22, "sconto": sconto, **kw}


def ddt_body(qty=2, pid=None, causale="Vendita", sconto="10+5", **kw):
    return {"data": TODAY, "party_id": pid or S["cli"], "causale": causale, "porto": "assegnato", "trasporto_a_cura": "vettore",
            "vettore": {"denominazione": "TEST Vettore", "partita_iva": "IT11111111111", "indirizzo": "Via C 9"},
            "destinazione": {"denominazione": "Mag", "indirizzo": "Via Dest 5", "cap": "10100", "comune": "Torino", "provincia": "to"},
            "colli": 3, "peso_kg": 12.5, "aspetto_beni": "Scatole", "inizio_trasporto": f"{TODAY}T10:30",
            "lines": [{"article_id": S["MAG"], "descrizione": "TEST art MAG", "quantita": qty, "unita_misura": "PZ", "prezzo_unitario": 10, "aliquota": 22, "sconto": sconto},
                      {"article_id": S["NOMAG"], "descrizione": "TEST art NOMAG", "quantita": 1, "prezzo_unitario": 5, "aliquota": 22}], **kw}


class TestSconto:
    # parse/normalize + totals
    @pytest.mark.parametrize("raw,norm", [("10", "10"), ("10+5", "10+5"), ("10,5", "10.5"), ("10 + 5%", "10+5"), ("", "")])
    def test_norm_valid(self, raw, norm):
        r = sess().post(f"{API}/invoices", json=inv_body([ln(raw)]))
        assert r.status_code == 200, r.text
        inv = r.json()
        assert inv["lines"][0]["sconto"] == norm
        sess().delete(f"{API}/invoices/{inv['id']}")

    @pytest.mark.parametrize("raw", ["abc", "0", "100", "1+2+3+4+5", "-5", "10++5"])
    def test_invalid(self, raw):
        r = sess().post(f"{API}/invoices", json=inv_body([ln(raw)]))
        assert r.status_code == 422, f"{raw}: {r.status_code} {r.text[:200]}"

    def test_totals_xml(self):
        s = sess()
        r = s.post(f"{API}/invoices", json=inv_body([ln("10+5"), ln("", q=1, p=100)]))
        assert r.status_code == 200, r.text
        inv = r.json()
        S["inv_sc"] = inv["id"]
        assert inv["lines"][0]["prezzo_totale"] == 17.10
        assert inv["imponibile"] == 117.10 and inv["iva"] == round(117.10 * 0.22, 2) and inv["totale"] == round(117.10 + inv["iva"], 2)
        assert inv["riepilogo"][0]["imponibile"] == 117.10
        x = s.get(f"{API}/invoices/{inv['id']}/xml").text
        seg = x[x.index("<NumeroLinea>1</NumeroLinea>"):x.index("<NumeroLinea>2</NumeroLinea>")]
        assert seg.count("<ScontoMaggiorazione>") == 2
        assert "<Percentuale>10.00</Percentuale>" in seg and "<Percentuale>5.00</Percentuale>" in seg
        assert seg.index("<PrezzoUnitario>") < seg.index("<ScontoMaggiorazione>") < seg.index("<PrezzoTotale>")
        assert "<PrezzoTotale>17.10000000</PrezzoTotale>" in seg
        seg2 = x[x.index("<NumeroLinea>2</NumeroLinea>"):]
        assert "<ScontoMaggiorazione>" not in seg2.split("</DettaglioLinee>")[0]

    def test_courtesy_pdf(self):
        from export_comm import courtesy_pdf
        inv = sess().get(f"{API}/invoices/{S['inv_sc']}").json()
        comp = sess().get(f"{API}/company").json()
        t = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(courtesy_pdf(comp, inv["cliente"], inv))).pages)
        assert "sc. 10+5%" in t, t[:500]

    def test_storno_copies_sconto(self):
        s = sess()
        mongo(f'db.invoices.updateOne({{id:"{S["inv_sc"]}"}}, {{$set:{{status:"consegnata"}}}})')
        r = s.post(f"{API}/invoices/{S['inv_sc']}/storno-totale", json={})
        assert r.status_code == 200, r.text
        nc = r.json()
        assert nc["lines"][0]["sconto"] == "10+5" and nc["lines"][0]["prezzo_totale"] == 17.10
        assert s.delete(f"{API}/invoices/{nc['id']}").status_code == 200
        mongo(f'db.invoices.updateOne({{id:"{S["inv_sc"]}"}}, {{$set:{{status:"bozza"}}}})')
        assert s.delete(f"{API}/invoices/{S['inv_sc']}").status_code == 200

    def test_ddt_sconto(self):
        s = sess()
        b = ddt_body(sconto="10 + 5%")
        r = s.post(f"{API}/ddt", json=b)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["lines"][0]["sconto"] == "10+5" and d["imponibile"] == 17.10 + 5
        s.delete(f"{API}/ddt/{d['id']}")
        assert s.post(f"{API}/ddt", json=ddt_body(sconto="abc")).status_code == 422


class TestListino:
    def test_listino_crud_and_prezzo(self):
        s = sess()
        p = s.get(f"{API}/parties").json()
        p = next(x for x in p if x["id"] == S["cli"])
        # article source with no history
        r = s.get(f"{API}/parties/{S['cli']}/prezzo", params={"article_id": S["MAG"]})
        assert r.status_code == 200 and r.json() == {"prezzo": 10, "sconto": "", "fonte": "articolo"}, r.text
        body = {k: v for k, v in p.items() if k not in ("id", "company_id", "created_at")}
        body["listino"] = [{"article_id": S["MAG"], "prezzo": 8.5, "sconto": "10 + 5"}]
        r = s.put(f"{API}/parties/{S['cli']}", json=body)
        assert r.status_code == 200, r.text
        got = next(x for x in s.get(f"{API}/parties").json() if x["id"] == S["cli"])
        assert got["listino"] == [{"article_id": S["MAG"], "prezzo": 8.5, "sconto": "10+5"}]
        r = s.get(f"{API}/parties/{S['cli']}/prezzo", params={"article_id": S["MAG"]}).json()
        assert r == {"prezzo": 8.5, "sconto": "10+5", "fonte": "listino"}
        body["listino"] = [{"article_id": S["MAG"], "prezzo": 8.5, "sconto": "abc"}]
        assert s.put(f"{API}/parties/{S['cli']}", json=body).status_code == 422
        body["listino"] = [{"article_id": S["MAG"], "prezzo": -1, "sconto": ""}]
        assert s.put(f"{API}/parties/{S['cli']}", json=body).status_code == 422
        # POST with listino
        np_ = party(s, "TEST_T45 Terzo Srl", "03456780156", listino=[{"article_id": S["NOMAG"], "prezzo": 3, "sconto": "5"}])
        assert np_["listino"][0]["sconto"] == "5"
        S["cli3"] = np_["id"]
        assert s.get(f"{API}/parties/nonexistent/prezzo", params={"article_id": S["MAG"]}).status_code == 404

    def test_ultima_vendita(self):
        s = sess()
        # invoice with article for cli2
        r = s.post(f"{API}/invoices", json=inv_body([ln("7", q=1, p=9.9, article_id=S["NOMAG"], descrizione="TEST art NOMAG")], party_id=S["cli2"]))
        assert r.status_code == 200, r.text
        S["inv_uv"] = r.json()
        r = s.get(f"{API}/parties/{S['cli2']}/prezzo", params={"article_id": S["NOMAG"]}).json()
        assert r["fonte"] == "ultima_vendita" and r["prezzo"] == 9.9 and r["sconto"] == "7", r
        S["rif_inv"] = r["riferimento"]
        # TD04 excluded
        nc = s.post(f"{API}/invoices", json=inv_body([ln("", q=1, p=1.0, article_id=S["MAG"], descrizione="x")], party_id=S["cli2"], tipo_documento="TD04"))
        if nc.status_code == 200:
            r = s.get(f"{API}/parties/{S['cli2']}/prezzo", params={"article_id": S["MAG"]}).json()
            assert r["fonte"] == "articolo", r
            s.delete(f"{API}/invoices/{nc.json()['id']}")
        s.delete(f"{API}/invoices/{S['inv_uv']['id']}")
        # bozza DDT excluded, confirmed DDT included
        d = s.post(f"{API}/ddt", json=ddt_body(qty=1, pid=S["cli2"], sconto="3")).json()
        assert s.get(f"{API}/parties/{S['cli2']}/prezzo", params={"article_id": S["MAG"]}).json()["fonte"] == "articolo"
        assert s.post(f"{API}/ddt/{d['id']}/conferma", json={}).status_code == 200
        r = s.get(f"{API}/parties/{S['cli2']}/prezzo", params={"article_id": S["MAG"]}).json()
        assert r["fonte"] == "ultima_vendita" and r["sconto"] == "3" and r["riferimento"].startswith("DDT "), r
        S["ddt_conf"] = d["id"]


    def test_riferimento_label_invoice(self):
        # BUG check: riferimento from an invoice must say 'Fattura' (server uses `coll is db.invoices`, Motor returns new objects)
        assert S["rif_inv"].startswith("Fattura "), S["rif_inv"]


class TestFatturaSubito:
    def test_fattura_subito(self):
        s = sess()
        did = S["ddt_conf"]
        r = s.post(f"{API}/ddt/{did}/fattura")
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["ddt"]["status"] == "fatturato" and out["ddt"]["invoice_id"] == out["invoice"]["id"]
        inv = s.get(f"{API}/invoices/{out['invoice']['id']}").json()
        assert inv["tipo_documento"] == "TD01" and inv["data"] == TODAY and len(inv["lines"]) == 2
        assert inv["lines"][0]["note"].startswith("Rif. DDT n. ") and inv["lines"][0]["sconto"] == "3"
        assert inv["ddt_rif"][0]["id"] == did and inv["ddt_rif"][0]["linee"] == [1, 2]
        x = s.get(f"{API}/invoices/{inv['id']}/xml").text
        assert "<DatiDDT>" in x and "<DatiTrasporto>" not in x
        assert s.post(f"{API}/ddt/{did}/fattura").status_code == 400
        assert s.post(f"{API}/ddt/{did}/annulla").status_code == 400
        S["inv_subito"] = inv["id"]

    def test_fattura_subito_requires_confirmed(self):
        s = sess()
        d = s.post(f"{API}/ddt", json=ddt_body(qty=1, pid=S["cli2"])).json()
        assert s.post(f"{API}/ddt/{d['id']}/fattura").status_code == 400
        s.delete(f"{API}/ddt/{d['id']}")

    def test_fattura_subito_non_vendita(self):
        # Spec: only causale Vendita. Check backend enforces it.
        s = sess()
        d = s.post(f"{API}/ddt", json=ddt_body(qty=1, pid=S["cli2"], causale="Omaggio")).json()
        assert s.post(f"{API}/ddt/{d['id']}/conferma", json={}).status_code == 200
        r = s.post(f"{API}/ddt/{d['id']}/fattura")
        S["omaggio"] = d["id"]
        if r.status_code == 200:
            S["omaggio_inv"] = r.json()["invoice"]["id"]
        assert r.status_code == 400, f"Fattura subito accepted on causale Omaggio: {r.status_code}"

    def test_delete_subito_reverts(self):
        s = sess()
        if S.get("omaggio_inv"):
            assert s.delete(f"{API}/invoices/{S['omaggio_inv']}").status_code == 200
        assert s.delete(f"{API}/invoices/{S['inv_subito']}").status_code == 200, "delete invoice"
        dd = s.get(f"{API}/ddt/{S['ddt_conf']}").json()
        assert dd["status"] == "confermato" and not dd.get("invoice_id")
        s.post(f"{API}/ddt/{S['omaggio']}/annulla")
        s.post(f"{API}/ddt/{S['ddt_conf']}/annulla")


class TestAccompagnatoria:
    def test_accompagnatoria(self):
        s = sess()
        g0 = giac(S["MAG"])
        d = s.post(f"{API}/ddt", json=ddt_body(qty=2)).json()
        r = s.post(f"{API}/ddt/{d['id']}/accompagnatoria", json={})
        assert r.status_code == 200, r.text
        out = r.json()
        dd = out["ddt"]
        assert dd["status"] == "fatturato" and dd["tipo"] == "accompagnatoria" and dd["numero"] is None and dd["numero_display"] is None
        assert giac(S["MAG"]) == g0 - 2
        mv = [m for m in s.get(f"{API}/magazzino/movimenti", params={"article_id": S["MAG"]}).json() if m.get("ddt_id") == d["id"]]
        assert len(mv) == 1 and mv[0]["documento"] == f"Fattura accompagnatoria {out['invoice']['numero_display']}"
        inv = s.get(f"{API}/invoices/{out['invoice']['id']}").json()
        assert inv["tipo_documento"] == "TD01" and inv["data"] == d["data"] and inv["trasporto"]["colli"] == 3
        assert inv["lines"][0]["prezzo_totale"] == 17.10
        x = s.get(f"{API}/invoices/{inv['id']}/xml").text
        assert "<DatiTrasporto>" in x and "<DatiDDT>" not in x
        tr = x[x.index("<DatiTrasporto>"):x.index("</DatiTrasporto>")]
        for tag in ("<DatiAnagraficiVettore>", "<IdCodice>11111111111</IdCodice>", "<MezzoTrasporto>Vettore</MezzoTrasporto>", "<CausaleTrasporto>Vendita</CausaleTrasporto>",
                    "<NumeroColli>3</NumeroColli>", "<Descrizione>Scatole</Descrizione>", "<UnitaMisuraPeso>KG</UnitaMisuraPeso>", "<PesoLordo>12.50</PesoLordo>",
                    f"<DataInizioTrasporto>{TODAY}</DataInizioTrasporto>", "<IndirizzoResa>", "<Provincia>TO</Provincia>"):
            assert tag in tr, tag
        assert x.index("</DatiGeneraliDocumento>") < x.index("<DatiTrasporto>") < x.index("</DatiGenerali>")
        # XSD order inside DatiTrasporto
        order = ["DatiAnagraficiVettore", "MezzoTrasporto", "CausaleTrasporto", "NumeroColli", "Descrizione", "UnitaMisuraPeso", "PesoLordo", "DataInizioTrasporto", "IndirizzoResa"]
        idx = [tr.index(f"<{t}>") for t in order]
        assert idx == sorted(idx)
        # repeated calls refused
        assert s.post(f"{API}/ddt/{d['id']}/accompagnatoria", json={}).status_code == 400
        assert s.post(f"{API}/ddt/{d['id']}/conferma", json={}).status_code == 400
        S["acc_ddt"], S["acc_inv"], S["g0"] = d["id"], inv["id"], g0

    def test_delete_accompagnatoria_restores(self):
        s = sess()
        assert s.delete(f"{API}/invoices/{S['acc_inv']}").status_code == 200
        assert giac(S["MAG"]) == S["g0"]
        dd = s.get(f"{API}/ddt/{S['acc_ddt']}").json()
        assert dd["status"] == "bozza" and not dd.get("tipo") and not dd.get("invoice_id") and dd["stock_move_ids"] == []
        assert not [m for m in s.get(f"{API}/magazzino/movimenti", params={"article_id": S["MAG"]}).json() if m.get("ddt_id") == S["acc_ddt"]]
        s.delete(f"{API}/ddt/{S['acc_ddt']}")

    def test_accompagnatoria_non_vendita(self):
        s = sess()
        d = s.post(f"{API}/ddt", json=ddt_body(qty=1, causale="Omaggio")).json()
        assert s.post(f"{API}/ddt/{d['id']}/accompagnatoria", json={}).status_code == 400
        s.delete(f"{API}/ddt/{d['id']}")

    def test_accompagnatoria_carenze(self):
        s = sess()
        g0 = giac(S["MAG"])
        d = s.post(f"{API}/ddt", json=ddt_body(qty=100)).json()
        r = s.post(f"{API}/ddt/{d['id']}/accompagnatoria", json={})
        assert r.status_code == 409 and r.json()["detail"]["carenze"], r.text
        assert s.get(f"{API}/ddt/{d['id']}").json()["status"] == "bozza"
        comp = s.get(f"{API}/company").json()
        comp["ddt_giacenza"] = "blocca"
        assert s.put(f"{API}/company", json=comp).status_code == 200
        assert s.post(f"{API}/ddt/{d['id']}/accompagnatoria", json={"forza": True}).status_code == 400
        comp["ddt_giacenza"] = "avviso"
        assert s.put(f"{API}/company", json=comp).status_code == 200
        r = s.post(f"{API}/ddt/{d['id']}/accompagnatoria", json={"forza": True})
        assert r.status_code == 200, r.text
        assert r.json()["carenze"] and giac(S["MAG"]) == g0 - 100
        assert s.delete(f"{API}/invoices/{r.json()['invoice']['id']}").status_code == 200
        assert giac(S["MAG"]) == g0
        s.delete(f"{API}/ddt/{d['id']}")

    def test_vettore_without_piva(self):
        s = sess()
        b = ddt_body(qty=1)
        b["vettore"]["partita_iva"] = ""
        d = s.post(f"{API}/ddt", json=b).json()
        r = s.post(f"{API}/ddt/{d['id']}/accompagnatoria", json={})
        assert r.status_code == 200, r.text
        x = s.get(f"{API}/invoices/{r.json()['invoice']['id']}/xml").text
        assert "<DatiTrasporto>" in x and "<DatiAnagraficiVettore>" not in x
        assert s.delete(f"{API}/invoices/{r.json()['invoice']['id']}").status_code == 200
        s.delete(f"{API}/ddt/{d['id']}")

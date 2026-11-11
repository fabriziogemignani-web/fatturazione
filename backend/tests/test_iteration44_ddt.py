# Iteration 44: DDT (documenti di trasporto) + stock unload + fatturazione differita (TD24 with DatiDDT).
# Covers CRUD/validation, conferma numbering + date coherence, stock moves scarico, carenze avviso(409/forza)/blocca(400),
# annulla (stock restored), DDT move delete guard, PDF content, fatturazione GET/POST, XML DatiDDT, invoice delete reverts,
# tenant isolation, module/menu gating.
# Run with: REACT_APP_BACKEND_URL=... pytest tests/test_iteration44_ddt.py -n 0
import io
import os
import subprocess
from datetime import date, timedelta

import pytest
import requests
from pypdf import PdfReader

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
PA, PB = "01234567897", "12345678903"
PY = date.today().year - 1
U = {k: (f"test-user-t44-{k}", f"test_session_t44_{k}") for k in ("admin", "op")}
ROLE = {"admin": "admin", "op": "operatore"}
S = {}


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


def sess(k="admin", cid="A"):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {U[k][1]}"
    if cid and S.get(cid):
        s.headers["X-Company-Id"] = S[cid]
    return s


def clean():
    ids = "[" + ",".join(f'"{u}"' for u, _ in U.values()) + "]"
    mongo(f'db.companies.find({{partita_iva:{{$in:["{PA}","{PB}"]}}, denominazione:/^TEST_T44/}}).forEach(c=>{{["invoices","parties","articles","stock_moves","ddts","payments","coa_entries","coa_accounts","coa_causali","coa_iva","audit","sdi_events"].forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:{ids}}}}}); db.user_sessions.deleteMany({{user_id:{{$in:{ids}}}}});')


def mk_company(name, piva):
    r = sess("admin", None).post(f"{API}/companies", json={"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01",
                                                          "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT",
                                                          "banche": [{"nome": "Banca A", "iban": "IT60X0542811101000000123456", "predefinita": True}]})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def party(s, tipo, name, piva):
    r = s.post(f"{API}/parties", json={"tipo": tipo, "denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "codice_destinatario": "ABC1234",
                                       "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def do_setup():
    clean()
    for k, (uid, tok) in U.items():
        mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.{uid}@example.com", name:"TEST_{k}", picture:"", role:"{ROLE[k]}", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
              f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    S["A"] = mk_company("TEST_T44 Alfa Srl", PA)
    S["B"] = mk_company("TEST_T44 Beta Srl", PB)
    mongo(f'db.users.updateMany({{user_id:"{U["op"][0]}"}}, {{$set:{{company_ids:["{S["A"]}"]}}}});')
    s = sess()
    S["cli"] = party(s, "cliente", "TEST_T44 Cliente Spa", "02345670481")
    S["cli2"] = party(s, "cliente", "TEST_T44 Secondo Srl", "00743110157")
    S["forn"] = party(s, "fornitore", "TEST_T44 Fornitore Srl", "03456780156")
    for k, mag in (("MAG1", True), ("NOMAG", False)):
        r = s.post(f"{API}/articles", json={"codice": f"T44{k}", "descrizione": f"TEST articolo {k}", "unita_misura": "PZ", "prezzo": 10, "aliquota": 22, "gestione_magazzino": mag})
        assert r.status_code == 200, r.text
        S[k] = r.json()["id"]
    r = s.post(f"{API}/magazzino/movimenti", json={"article_id": S["MAG1"], "tipo": "carico", "data": f"{PY}-10-01", "quantita": 10, "costo_unitario": 5, "causale": "Acquisto"})
    assert r.status_code == 200, r.text
    S["carico"] = r.json()["id"]


def ddt_body(data, qty=4, causale="Vendita", pid=None, **kw):
    return {"data": data, "party_id": pid or S["cli"], "causale": causale, "porto": "assegnato", "trasporto_a_cura": "vettore",
            "vettore": {"denominazione": "TEST Vettore Express", "partita_iva": "11111111111", "indirizzo": "Via Corriere 9"},
            "destinazione": {"denominazione": "Magazzino Cliente", "indirizzo": "Via Dest 5", "cap": "10100", "comune": "Torino", "provincia": "TO"},
            "colli": 3, "peso_kg": 12.5, "aspetto_beni": "Scatole", "prezzi_in_stampa": True,
            "lines": [{"article_id": S["MAG1"], "descrizione": "TEST articolo MAG1", "quantita": qty, "unita_misura": "PZ", "prezzo_unitario": 10, "aliquota": 22},
                      {"article_id": S["NOMAG"], "descrizione": "TEST articolo NOMAG", "quantita": 1, "prezzo_unitario": 5, "aliquota": 22, "note": "nota riga"}], **kw}


def giac(aid):
    return next(a for a in sess().get(f"{API}/magazzino/articoli").json()["articoli"] if a["id"] == aid)["giacenza"]


def pdf_text(content):
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(content)).pages)


@pytest.fixture(scope="module", autouse=True)
def setup():
    do_setup()
    yield
    clean()


class TestDdt:
    # Validation
    def test_validation(self):
        s = sess()
        assert s.post(f"{API}/ddt", json=ddt_body(f"{PY}-11-05", pid=S["forn"])).status_code == 400
        fut = (date.today() + timedelta(days=2)).isoformat()
        assert s.post(f"{API}/ddt", json=ddt_body(fut)).status_code == 422
        b = ddt_body(f"{PY}-11-05"); b["lines"][0]["aliquota"] = 0
        r = s.post(f"{API}/ddt", json=b); assert r.status_code == 422, r.text
        b["lines"][0]["aliquota"] = 7
        assert s.post(f"{API}/ddt", json=b).status_code == 422
        b = ddt_body(f"{PY}-11-05"); b["lines"] = []
        assert s.post(f"{API}/ddt", json=b).status_code == 422

    # CRUD bozza
    def test_crud_bozza(self):
        s = sess()
        r = s.post(f"{API}/ddt", json=ddt_body(f"{PY}-11-05"))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "bozza" and d["numero"] is None and d["numero_display"] is None
        assert d["lines"][0]["codice"] == "T44MAG1" and d["imponibile"] == 45.0
        S["d1"] = d["id"]
        b = ddt_body(f"{PY}-11-05", qty=4, note="TEST nota ddt")
        r = s.put(f"{API}/ddt/{d['id']}", json=b); assert r.status_code == 200 and r.json()["note"] == "TEST nota ddt"
        assert s.get(f"{API}/ddt/{d['id']}").json()["note"] == "TEST nota ddt"
        assert any(x["id"] == d["id"] for x in s.get(f"{API}/ddt", params={"stato": "bozza"}).json())
        assert not any(x["id"] == d["id"] for x in s.get(f"{API}/ddt", params={"stato": "confermato"}).json())
        r = s.post(f"{API}/ddt", json=ddt_body(f"{PY}-11-05"))
        tmp = r.json()["id"]
        assert s.delete(f"{API}/ddt/{tmp}").status_code == 200
        assert s.get(f"{API}/ddt/{tmp}").status_code == 404

    # PDF bozza
    def test_pdf_bozza(self):
        r = sess().get(f"{API}/ddt/{S['d1']}/pdf")
        assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
        t = pdf_text(r.content)
        assert "BOZZA" in t and "Prezzo" in t and "TEST Vettore Express" in t and "Torino" in t and "Scatole" in t
        assert "FIRMA CONDUCENTE" in t and "Assegnato" in t

    # Conferma: numbering + stock scarico
    def test_conferma(self):
        s = sess()
        r = s.post(f"{API}/ddt/{S['d1']}/conferma", json={})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["numero_display"] == f"1/{PY}" and d["status"] == "confermato" and len(d["stock_move_ids"]) == 1
        mv = s.get(f"{API}/magazzino/movimenti", params={"article_id": S["MAG1"]}).json()
        sm = next(m for m in mv if m.get("ddt_id") == S["d1"])
        assert sm["tipo"] == "scarico" and sm["causale"] == "Vendita" and sm["documento"] == f"DDT 1/{PY}" and sm["quantita"] == 4
        assert giac(S["MAG1"]) == 6
        assert not s.get(f"{API}/magazzino/movimenti", params={"article_id": S["NOMAG"]}).json()
        S["mv1"] = sm["id"]
        assert s.post(f"{API}/ddt/{S['d1']}/conferma", json={}).status_code == 400
        assert s.put(f"{API}/ddt/{S['d1']}", json=ddt_body(f"{PY}-11-05")).status_code == 400
        assert s.delete(f"{API}/ddt/{S['d1']}").status_code == 400

    def test_move_delete_guard(self):
        r = sess().delete(f"{API}/magazzino/movimenti/{S['mv1']}")
        assert r.status_code == 400, r.text

    def test_date_before_last(self):
        s = sess()
        d = s.post(f"{API}/ddt", json=ddt_body(f"{PY}-11-01", qty=1)).json()
        r = s.post(f"{API}/ddt/{d['id']}/conferma", json={})
        assert r.status_code == 400, r.text
        assert s.get(f"{API}/ddt/{d['id']}").json()["status"] == "bozza"
        s.delete(f"{API}/ddt/{d['id']}")

    # Carenze avviso -> 409 then forza
    def test_carenze_avviso_forza(self):
        s = sess()
        d = s.post(f"{API}/ddt", json=ddt_body(f"{PY}-11-10", qty=10)).json()
        r = s.post(f"{API}/ddt/{d['id']}/conferma", json={})
        assert r.status_code == 409, r.text
        car = r.json()["detail"]["carenze"]
        assert car[0]["article_id"] == S["MAG1"] and car[0]["richiesta"] == 10 and car[0]["disponibile"] == 6
        assert s.get(f"{API}/ddt/{d['id']}").json()["numero"] is None
        r = s.post(f"{API}/ddt/{d['id']}/conferma", json={"forza": True})
        assert r.status_code == 200 and r.json()["numero_display"] == f"2/{PY}"
        assert giac(S["MAG1"]) == -4
        S["d2"] = d["id"]

    # Annulla restores stock
    def test_annulla(self):
        s = sess()
        r = s.post(f"{API}/ddt/{S['d2']}/annulla")
        assert r.status_code == 200 and r.json()["status"] == "annullato"
        assert giac(S["MAG1"]) == 6
        assert not [m for m in s.get(f"{API}/magazzino/movimenti", params={"article_id": S["MAG1"]}).json() if m.get("ddt_id") == S["d2"]]
        assert s.post(f"{API}/ddt/{S['d2']}/annulla").status_code == 400
        assert "ANNULLATO" in pdf_text(s.get(f"{API}/ddt/{S['d2']}/pdf").content)
        # bozza cannot be annulled
        d = s.post(f"{API}/ddt", json=ddt_body(f"{PY}-11-10", qty=1)).json()
        assert s.post(f"{API}/ddt/{d['id']}/annulla").status_code == 400
        s.delete(f"{API}/ddt/{d['id']}")

    # Blocca: 400 even with forza
    def test_blocca(self):
        s = sess()
        comp = s.get(f"{API}/company").json()
        assert comp.get("ddt_giacenza", "avviso") == "avviso"
        comp["ddt_giacenza"] = "blocca"
        r = s.put(f"{API}/company", json=comp); assert r.status_code == 200, r.text
        assert s.get(f"{API}/company").json()["ddt_giacenza"] == "blocca"
        d = s.post(f"{API}/ddt", json=ddt_body(f"{PY}-11-12", qty=100)).json()
        r = s.post(f"{API}/ddt/{d['id']}/conferma", json={})
        assert r.status_code == 400 and r.json()["detail"]["carenze"]
        assert s.post(f"{API}/ddt/{d['id']}/conferma", json={"forza": True}).status_code == 400
        assert giac(S["MAG1"]) == 6
        s.delete(f"{API}/ddt/{d['id']}")
        comp["ddt_giacenza"] = "avviso"
        assert s.put(f"{API}/company", json=comp).status_code == 200

    # Other causali -> stock causale mapping; not in fatturazione
    def test_causali_mapping(self):
        s = sess()
        for caus, exp, day in (("Reso a fornitore", "Reso a fornitore", 13), ("Omaggio", "Altro", 14)):
            d = s.post(f"{API}/ddt", json=ddt_body(f"{PY}-11-{day}", qty=1, causale=caus)).json()
            r = s.post(f"{API}/ddt/{d['id']}/conferma", json={}); assert r.status_code == 200, r.text
            sm = next(m for m in s.get(f"{API}/magazzino/movimenti", params={"article_id": S["MAG1"]}).json() if m.get("ddt_id") == d["id"])
            assert sm["causale"] == exp
            S[f"oth_{day}"] = d["id"]
        assert giac(S["MAG1"]) == 4

    # Fatturazione differita
    def test_fatturazione_flow(self):
        s = sess()
        b = ddt_body(f"{PY}-11-20", qty=2, prezzi_in_stampa=False)
        d3 = s.post(f"{API}/ddt", json=b).json()
        assert s.post(f"{API}/ddt/{d3['id']}/conferma", json={}).status_code == 200
        t = pdf_text(s.get(f"{API}/ddt/{d3['id']}/pdf").content)
        assert "Prezzo" not in t and f"5/{PY}" in t
        d4 = s.post(f"{API}/ddt", json=ddt_body(f"{PY}-11-21", qty=1, pid=S["cli2"])).json()
        assert s.post(f"{API}/ddt/{d4['id']}/conferma", json={}).status_code == 200
        S["d3"], S["d4"] = d3["id"], d4["id"]
        g = s.get(f"{API}/ddt/fatturazione", params={"dal": f"{PY}-11-01", "al": f"{PY}-11-30"}).json()
        by = {x["party_id"]: x for x in g}
        assert set(by) == {S["cli"], S["cli2"]}
        assert [x["id"] for x in by[S["cli"]]["ddt"]] == [S["d1"], S["d3"]]
        assert by[S["cli"]]["imponibile"] == 45 + 25
        # date before last DDT -> error per client
        r = s.post(f"{API}/ddt/fatturazione", json={"dal": f"{PY}-11-01", "al": f"{PY}-11-30", "data_fattura": f"{PY}-11-20", "party_ids": [S["cli"], S["cli2"]]})
        assert r.status_code == 200, r.text
        out = r.json()
        assert len(out["fatture"]) == 1 and len(out["errori"]) == 1 and "TEST_T44 Secondo" in out["errori"][0]["cliente"]
        inv = out["fatture"][0]
        assert inv["ddt"] == 2
        S["inv"] = inv["id"]
        full = s.get(f"{API}/invoices/{inv['id']}").json()
        assert full["tipo_documento"] == "TD24" and full["status"] == "bozza" and len(full["lines"]) == 4
        assert full["lines"][0]["note"].startswith(f"Rif. DDT n. 1/{PY} del 05/11/{PY}")
        assert full["lines"][2]["note"].startswith(f"Rif. DDT n. 5/{PY} del 20/11/{PY}")
        assert "nota riga" in full["lines"][1]["note"]
        assert [x["linee"] for x in full["ddt_rif"]] == [[1, 2], [3, 4]]
        for did in (S["d1"], S["d3"]):
            dd = s.get(f"{API}/ddt/{did}").json()
            assert dd["status"] == "fatturato" and dd["invoice_numero"] == inv["numero_display"]
        assert s.post(f"{API}/ddt/{S['d1']}/annulla").status_code == 400
        x = s.get(f"{API}/invoices/{inv['id']}/xml")
        assert x.status_code == 200, x.text
        xml = x.text
        assert "<TipoDocumento>TD24</TipoDocumento>" in xml and xml.count("<DatiDDT>") == 2
        assert f"<NumeroDDT>1/{PY}</NumeroDDT>" in xml and f"<DataDDT>{PY}-11-05</DataDDT>" in xml
        assert xml.index("</DatiGeneraliDocumento>") < xml.index("<DatiDDT>") < xml.index("</DatiGenerali>")
        assert "<RiferimentoNumeroLinea>3</RiferimentoNumeroLinea>" in xml
        # list for the period now excludes invoiced
        g = s.get(f"{API}/ddt/fatturazione", params={"dal": f"{PY}-11-01", "al": f"{PY}-11-30"}).json()
        assert [x["party_id"] for x in g] == [S["cli2"]]

    def test_delete_invoice_reverts(self):
        s = sess()
        r = s.delete(f"{API}/invoices/{S['inv']}")
        assert r.status_code == 200, r.text
        for did in (S["d1"], S["d3"]):
            dd = s.get(f"{API}/ddt/{did}").json()
            assert dd["status"] == "confermato" and not dd.get("invoice_id")

    # Tenant isolation
    def test_tenant_isolation(self):
        b = sess("admin", "B")
        assert b.get(f"{API}/ddt").json() == []
        assert b.get(f"{API}/ddt/{S['d1']}").status_code == 404
        assert b.get(f"{API}/ddt/{S['d1']}/pdf").status_code == 404
        assert b.post(f"{API}/ddt/{S['d1']}/annulla").status_code == 404
        assert b.get(f"{API}/ddt/fatturazione", params={"dal": f"{PY}-01-01", "al": f"{PY}-12-31"}).json() == []
        # client of A not usable in B
        assert b.post(f"{API}/ddt", json=ddt_body(f"{PY}-11-05")).status_code == 400
        # operatore not assigned to B
        assert sess("op", "B").get(f"{API}/ddt").status_code in (403, 404)
        assert sess("op", "A").get(f"{API}/ddt").status_code == 200

    # Module and menu gating
    def test_module_menu_gating(self):
        a = sess("admin", None)
        r = a.put(f"{API}/companies/{S['B']}/moduli", json={"fatture_attive": False})
        assert r.status_code == 200, r.text
        assert sess("admin", "B").get(f"{API}/ddt").status_code == 403
        a.put(f"{API}/companies/{S['B']}/moduli", json={})
        assert sess("admin", "B").get(f"{API}/ddt").status_code == 200
        a.put(f"{API}/companies/{S['B']}/menu", json={"off": ["fatturazione-differita"]})
        assert sess("admin", "B").get(f"{API}/ddt/fatturazione", params={"dal": f"{PY}-01-01", "al": f"{PY}-12-31"}).status_code == 403
        assert sess("admin", "B").get(f"{API}/ddt").status_code == 200
        a.put(f"{API}/companies/{S['B']}/menu", json={"off": ["ddt"]})
        assert sess("admin", "B").get(f"{API}/ddt").status_code == 403
        a.put(f"{API}/companies/{S['B']}/menu", json={"off": []})
        assert sess("admin", "B").get(f"{API}/ddt").status_code == 200

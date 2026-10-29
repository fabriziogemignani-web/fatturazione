# Iteration 5: credit notes (TD04) - separate numbering, linked invoice validation, residual, XML, SDI, dashboard
import os
import subprocess
from datetime import date
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"
TOK = "test_session_a"
TODAY = date.today().isoformat()
YEAR = date.today().year


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


def company(piva, name):
    return {"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01",
            "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"}


def party(name, piva="01234567890"):
    return {"tipo": "cliente", "denominazione": name, "partita_iva": piva, "codice_destinatario": "ABC1234",
            "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"}


def doc(pid, tipo="TD01", price=100, link=None):
    d = {"tipo_documento": tipo, "data": TODAY, "party_id": pid, "modalita_pagamento": "MP05",
         "lines": [{"descrizione": "Consulenza", "quantita": 1, "prezzo_unitario": price, "aliquota": 22}]}
    if link:
        d["fattura_collegata_id"] = link
    return d


@pytest.fixture(scope="module")
def ctx():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    ids = {}
    for k, piva, name in (("A", "55555555551", "TEST_T5 Alfa"), ("B", "55555555552", "TEST_T5 Beta")):
        mongo(f'db.companies.deleteMany({{partita_iva:"{piva}"}})')
        r = s.post(f"{API}/companies", json=company(piva, name))
        assert r.status_code == 200, r.text
        ids[k] = r.json()["id"]
    hA = {"X-Company-Id": ids["A"]}
    hB = {"X-Company-Id": ids["B"]}
    c1 = s.post(f"{API}/parties", json=party("TEST_T5 Cliente1"), headers=hA).json()["id"]
    c2 = s.post(f"{API}/parties", json=party("TEST_T5 Cliente2", "09876543210"), headers=hA).json()["id"]
    cb = s.post(f"{API}/parties", json=party("TEST_T5 ClienteB"), headers=hB).json()["id"]
    yield {"s": s, "A": ids["A"], "B": ids["B"], "hA": hA, "hB": hB, "c1": c1, "c2": c2, "cb": cb, "st": {}}
    js_ids = str(list(ids.values())).replace("'", '"')
    mongo(f'db.invoices.deleteMany({{company_id: {{$in: {js_ids}}}}}); db.parties.deleteMany({{company_id: {{$in: {js_ids}}}}});'
          f'db.counters.deleteMany({{key: {{$in: {str(["progressivo_" + i for i in ids.values()]).replace(chr(39), chr(34))}}}}});'
          f'db.companies.deleteMany({{id: {{$in: {js_ids}}}}}); db.users.updateMany({{}}, {{$pull: {{company_ids: {{$in: {js_ids}}}}}}});')


class TestCreditNotes:
    def test_01_invoice_and_draft_numbering(self, ctx):
        s, h = ctx["s"], ctx["hA"]
        inv = s.post(f"{API}/invoices", json=doc(ctx["c1"]), headers=h)
        assert inv.status_code == 200, inv.text
        assert inv.json()["numero_display"] == f"1/{YEAR}"
        ctx["st"]["inv1"] = inv.json()["id"]

    def test_02_link_draft_rejected(self, ctx):
        s, h = ctx["s"], ctx["hA"]
        r = s.post(f"{API}/invoices", json=doc(ctx["c1"], "TD04", 50, ctx["st"]["inv1"]), headers=h)
        assert r.status_code == 400
        assert "inviate" in r.json()["detail"]

    def test_03_send_original(self, ctx):
        s, h = ctx["s"], ctx["hA"]
        r = s.post(f"{API}/invoices/{ctx['st']['inv1']}/send", headers=h)
        assert r.status_code == 200 and r.json()["status"] == "inviata"
        g = s.get(f"{API}/invoices/{ctx['st']['inv1']}", headers=h).json()
        assert g["residuo_stornabile"] == 122.0
        assert g["note_credito"] == []

    def test_04_nc_separate_register(self, ctx):
        s, h = ctx["s"], ctx["hA"]
        r = s.post(f"{API}/invoices", json=doc(ctx["c1"], "TD04", 50, ctx["st"]["inv1"]), headers=h)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["numero_display"] == f"1/NC/{YEAR}" and d["sezionale"] == "NC" and d["numero"] == 1
        assert d["fattura_collegata"]["id"] == ctx["st"]["inv1"]
        assert d["fattura_collegata"]["numero_display"] == f"1/{YEAR}"
        ctx["st"]["nc1"] = d["id"]
        # next invoice continues invoice register
        i2 = s.post(f"{API}/invoices", json=doc(ctx["c1"]), headers=h).json()
        assert i2["numero_display"] == f"2/{YEAR}"
        ctx["st"]["inv2"] = i2["id"]

    def test_05_other_company_independent_register(self, ctx):
        s, h = ctx["s"], ctx["hB"]
        r = s.post(f"{API}/invoices", json=doc(ctx["cb"], "TD04", 10), headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["numero_display"] == f"1/NC/{YEAR}"
        assert r.json()["fattura_collegata"] is None
        # linking to company A invoice from B -> 400
        r2 = s.post(f"{API}/invoices", json=doc(ctx["cb"], "TD04", 10, ctx["st"]["inv1"]), headers=h)
        assert r2.status_code == 400

    def test_06_different_client_rejected(self, ctx):
        r = ctx["s"].post(f"{API}/invoices", json=doc(ctx["c2"], "TD04", 10, ctx["st"]["inv1"]), headers=ctx["hA"])
        assert r.status_code == 400
        assert "stesso cliente" in r.json()["detail"]

    def test_07_residual_exceeded(self, ctx):
        # residual = 122 - 61 = 61 ; 60 net -> 73.2 > 61
        r = ctx["s"].post(f"{API}/invoices", json=doc(ctx["c1"], "TD04", 60, ctx["st"]["inv1"]), headers=ctx["hA"])
        assert r.status_code == 400
        assert "61.00" in r.json()["detail"]

    def test_08_link_to_td04_rejected(self, ctx):
        r = ctx["s"].post(f"{API}/invoices", json=doc(ctx["c1"], "TD04", 1, ctx["st"]["nc1"]), headers=ctx["hA"])
        assert r.status_code == 400

    def test_09_update_nc_residual_excludes_self(self, ctx):
        s, h = ctx["s"], ctx["hA"]
        r = s.put(f"{API}/invoices/{ctx['st']['nc1']}", json=doc(ctx["c1"], "TD04", 100, ctx["st"]["inv1"]), headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["totale"] == 122.0
        r = s.put(f"{API}/invoices/{ctx['st']['nc1']}", json=doc(ctx["c1"], "TD04", 101, ctx["st"]["inv1"]), headers=h)
        assert r.status_code == 400
        r = s.put(f"{API}/invoices/{ctx['st']['nc1']}", json=doc(ctx["c1"], "TD04", 50, ctx["st"]["inv1"]), headers=h)
        assert r.status_code == 200

    def test_10_tipo_change_rejected(self, ctx):
        s, h = ctx["s"], ctx["hA"]
        r = s.put(f"{API}/invoices/{ctx['st']['nc1']}", json=doc(ctx["c1"], "TD01", 50), headers=h)
        assert r.status_code == 400
        r = s.put(f"{API}/invoices/{ctx['st']['inv2']}", json=doc(ctx["c1"], "TD04", 50), headers=h)
        assert r.status_code == 400

    def test_11_original_shows_linked(self, ctx):
        g = ctx["s"].get(f"{API}/invoices/{ctx['st']['inv1']}", headers=ctx["hA"]).json()
        assert [n["id"] for n in g["note_credito"]] == [ctx["st"]["nc1"]]
        assert g["residuo_stornabile"] == 61.0

    def test_12_xml(self, ctx):
        r = ctx["s"].get(f"{API}/invoices/{ctx['st']['nc1']}/xml", headers=ctx["hA"])
        assert r.status_code == 200
        x = r.text
        assert "<TipoDocumento>TD04</TipoDocumento>" in x
        assert f"<Numero>1/NC/{YEAR}</Numero>" in x
        assert "<DatiFattureCollegate>" in x and f"<IdDocumento>1/{YEAR}</IdDocumento>" in x
        dg = x[x.index("<DatiGenerali>"):x.index("</DatiGenerali>")]
        assert "DatiFattureCollegate" in dg
        assert x.index("</DatiGeneraliDocumento>") < x.index("<DatiFattureCollegate>")

    def test_13_send_refresh_nc_and_dashboard(self, ctx):
        s, h = ctx["s"], ctx["hA"]
        r = s.post(f"{API}/invoices/{ctx['st']['nc1']}/send", headers=h)
        assert r.status_code == 200 and r.json()["status"] == "inviata"
        r = s.post(f"{API}/invoices/{ctx['st']['nc1']}/refresh", headers=h)
        assert r.status_code == 200 and r.json()["status"] == "consegnata"
        d = s.get(f"{API}/dashboard", headers=h).json()
        assert d["fatturato"] == 61.0  # 122 - 61
        assert d["note_credito"] == {"count": 1, "totale": 61.0}
        assert d["imponibile"] == 50.0

    def test_14_delete_rules(self, ctx):
        s, h = ctx["s"], ctx["hA"]
        # inv2 is last draft of invoice register -> deletable
        r = s.delete(f"{API}/invoices/{ctx['st']['inv2']}", headers=h)
        assert r.status_code == 200
        assert s.get(f"{API}/invoices/{ctx['st']['inv2']}", headers=h).status_code == 404
        # new NC draft deletable (last of NC register), invoices register unaffected
        nc2 = s.post(f"{API}/invoices", json=doc(ctx["c1"], "TD04", 10, ctx["st"]["inv1"]), headers=h).json()
        assert nc2["numero_display"] == f"2/NC/{YEAR}"
        assert s.delete(f"{API}/invoices/{nc2['id']}", headers=h).status_code == 200

    def test_15_list_contains_both(self, ctx):
        items = ctx["s"].get(f"{API}/invoices", headers=ctx["hA"]).json()
        tipi = sorted(i["tipo_documento"] for i in items)
        assert tipi == ["TD01", "TD04"]
        assert all("_id" not in i for i in items)

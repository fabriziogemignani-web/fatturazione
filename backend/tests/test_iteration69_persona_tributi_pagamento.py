# Iteration 69: PartyIn persona fisica/giuridica + ritenuta_codice_tributo + pagamento predefinito, /api/codici-tributo,
# ritenute per codice (1038 + 1040) in /ritenute/mese + F24 PDFs + versato, import massivo (modello columns + anteprima/conferma).
# Run: pytest tests/test_iteration69_persona_tributi_pagamento.py -v -n 0   (T69_KEEP=1 keeps data; `python tests/test_iteration69_persona_tributi_pagamento.py clean`)
import io
import os
import subprocess
import sys
from datetime import date

import pytest
import requests
from openpyxl import load_workbook

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
FIX = open(os.path.join(os.path.dirname(__file__), "fixtures", "sample_fattura.xml")).read()
UID, TOK = "test-user-t69-admin", "test_session_t69_admin"
S = {}
today = date.today()
PM = date(today.year - (today.month == 1), 12 if today.month == 1 else today.month - 1, 1)
YM = PM.isoformat()[:7]
COLLS = ["invoices", "passive_invoices", "parties", "payments", "passive_payments", "coa_entries", "coa_accounts", "coa_causali", "coa_iva", "articles",
         "stock_moves", "f24_versamenti", "sdi_events", "audit", "com_log", "import_batches", "partite_aperte", "export_log"]


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


def piva(b):
    s = 0
    for i, ch in enumerate(b):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            d = d - 9 if d > 9 else d
        s += d
    return b + str((10 - s % 10) % 10)


CO, F1, F2, CLI = piva("0987123469"), piva("0234567069"), piva("0234567169"), piva("0123456969")


def sess():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    if S.get("cid"):
        s.headers["X-Company-Id"] = S["cid"]
    return s


def clean():
    colls = "[" + ",".join(f'"{c}"' for c in COLLS) + "]"
    mongo(f'db.companies.find({{denominazione:/^TEST_T69/}}).forEach(c=>{{{colls}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def pdf_text(b):
    from pypdf import PdfReader
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(b)).pages)


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t69@example.com", name:"TEST_t69", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": "TEST_T69 Srl", "partita_iva": CO, "codice_fiscale": CO, "regime_fiscale": "RF01",
                                              "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT",
                                              "iban": "IT60X0542811101000000123456"})
    assert r.status_code == 200, r.text
    S["cid"] = r.json()["id"]
    yield
    if not os.environ.get("T69_KEEP"):
        clean()
    else:
        print("\nKEEP", S)


def forn(**kw):
    b = {"tipo": "fornitore", "denominazione": "TEST_T69 Forn", "partita_iva": "", "codice_fiscale": "RSSMRA80A01H501U", "indirizzo": "Via Y 1", "cap": "50100",
         "comune": "Firenze", "provincia": "FI", "nazione": "IT"}
    b.update(kw)
    return b


def loc(r):
    return [tuple(x.get("loc", [])) for x in (r.json().get("detail") or [])] if isinstance(r.json().get("detail"), list) else r.text


# --- PartyIn persona / codice tributo / pagamento
class TestPartyIn:
    def test_fisica_requires_nome(self):
        r = sess().post(f"{API}/parties", json=forn(persona="fisica", cognome="Rossi"))
        assert r.status_code == 422 and "nome" in str(loc(r)), r.text

    def test_fisica_requires_cognome(self):
        r = sess().post(f"{API}/parties", json=forn(persona="fisica", nome="Mario"))
        assert r.status_code == 422 and "cognome" in str(loc(r)), r.text

    def test_fisica_create_persist(self):
        r = sess().post(f"{API}/parties", json=forn(persona="fisica", nome=" Mario ", cognome="Rossi", data_nascita="1980-01-01", comune_nascita="Roma",
                                                    provincia_nascita="rm", soggetto_ritenuta=True, ritenuta_codice_tributo="1038",
                                                    pagamento_modalita="MP05", pagamento_rate=2, pagamento_giorni=60, pagamento_fine_mese=True))
        assert r.status_code == 200, r.text
        d = r.json()
        S["pf"] = d["id"]
        assert d["denominazione"] == "Rossi Mario" and d["provincia_nascita"] == "RM" and d["persona"] == "fisica"
        g = next(x for x in sess().get(f"{API}/parties", params={"tipo": "fornitore"}).json() if x["id"] == d["id"])
        assert g["ritenuta_codice_tributo"] == "1038" and g["data_nascita"] == "1980-01-01" and g["pagamento_rate"] == 2 and g["pagamento_fine_mese"] is True

    def test_giuridica_clears_personal_and_defaults(self):
        r = sess().post(f"{API}/parties", json=forn(partita_iva=F1, codice_fiscale=F1, denominazione="TEST_T69 Giur Srl", nome="X", cognome="Y", data_nascita="1990-02-02"))
        assert r.status_code == 200, r.text
        d = r.json()
        S["pg"] = d["id"]
        assert d["persona"] == "giuridica" and d["nome"] == "" and d["cognome"] == "" and d["data_nascita"] == ""
        assert d["denominazione"] == "TEST_T69 Giur Srl" and d["ritenuta_codice_tributo"] == "1040"
        assert d["pagamento_modalita"] == "" and d["pagamento_rate"] == 1 and d["pagamento_giorni"] == 30 and d["pagamento_fine_mese"] is False

    def test_update_fisica_to_giuridica(self):
        r = sess().put(f"{API}/parties/{S['pf']}", json=forn(persona="giuridica", denominazione="TEST_T69 Ora Srl", nome="Mario", cognome="Rossi"))
        assert r.status_code == 200, r.text
        assert r.json()["nome"] == "" and r.json()["denominazione"] == "TEST_T69 Ora Srl"
        r = sess().put(f"{API}/parties/{S['pf']}", json=forn(persona="fisica", nome="Mario", cognome="Rossi", ritenuta_codice_tributo="1038"))
        assert r.status_code == 200 and r.json()["denominazione"] == "Rossi Mario"

    @pytest.mark.parametrize("kw", [{"data_nascita": "01/01/1980"}, {"ritenuta_codice_tributo": "10400"}, {"ritenuta_codice_tributo": "1a"},
                                    {"pagamento_modalita": "MP99"}, {"pagamento_rate": 0}, {"pagamento_rate": 13}, {"pagamento_giorni": 366},
                                    {"pagamento_giorni": -1}, {"persona": "altro"}, {"provincia_nascita": "ROM"}])
    def test_invalid_422(self, kw):
        r = sess().post(f"{API}/parties", json=forn(**{"persona": "fisica", "nome": "A", "cognome": "B", **kw}))
        assert r.status_code == 422, (kw, r.text)

    @pytest.mark.parametrize("m", ["", "MP01", "MP02", "MP05", "MP08", "MP12"])
    def test_modalita_ok_client(self, m):
        pv = piva("0123456" + str(100 + ["", "MP01", "MP02", "MP05", "MP08", "MP12"].index(m)))
        r = sess().post(f"{API}/parties", json={"tipo": "cliente", "denominazione": f"TEST_T69 Cli {m}", "partita_iva": pv, "codice_fiscale": pv, "codice_destinatario": "ABC1234",
                                                "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT",
                                                "pagamento_modalita": m, "pagamento_rate": 3, "pagamento_giorni": 30, "pagamento_fine_mese": True})
        assert r.status_code == 200, r.text
        assert r.json()["pagamento_modalita"] == m and r.json()["pagamento_rate"] == 3


# --- /api/codici-tributo
class TestCodiciTributo:
    def test_all(self):
        d = sess().get(f"{API}/codici-tributo").json()
        cods = {x["codice"] for x in d["codici"]}
        assert isinstance(d["categorie"], dict) and len(d["codici"]) >= 55, len(d["codici"])
        for c in ("1001", "1004", "1038", "1040", "6001", "6012", "6031", "6035", "6099", "2521", "2526", "4001", "2003", "3800"):
            assert c in cods, c
        S["n_all"] = len(d["codici"])

    def test_categoria_and_q(self):
        d = sess().get(f"{API}/codici-tributo", params={"categoria": "ritenute"}).json()
        assert d["codici"] and all(x["categoria"] == "ritenute" for x in d["codici"]) and "1040" in {x["codice"] for x in d["codici"]}
        assert "6001" not in {x["codice"] for x in d["codici"]}
        q = sess().get(f"{API}/codici-tributo", params={"q": "provvigioni"}).json()["codici"]
        assert "1038" in {x["codice"] for x in q}
        q = sess().get(f"{API}/codici-tributo", params={"q": "1040"}).json()["codici"]
        assert [x["codice"] for x in q] == ["1040"]

    def test_requires_auth(self):
        assert requests.get(f"{API}/codici-tributo").status_code in (401, 403)


# --- Ritenute per codice tributo
def _upload(piva_forn, numero, rag):
    d1 = PM.replace(day=5).isoformat()
    xml = FIX.replace("02345670481", piva_forn).replace("<IdCodice>01234567890</IdCodice>", f"<IdCodice>{CO}</IdCodice>") \
        .replace("<Numero>5674/2026</Numero>", f"<Numero>{numero}</Numero>").replace("<Data>2026-10-30</Data>", f"<Data>{d1}</Data>") \
        .replace("DEMO Energia Toscana SpA", rag)
    up = sess().post(f"{API}/passive/upload", files=[("files", ("p.xml", xml, "text/xml"))])
    assert up.status_code == 200 and up.json()[0]["ok"], up.text
    return up.json()[0]["documenti"][0]["id"]


class TestRitenuteCodici:
    def test_setup_suppliers_invoices(self):
        s = sess()
        for k, pv, cod in (("a", F2, "1038"), ("b", piva("0234567269"), "1040")):
            r = s.post(f"{API}/parties", json=forn(partita_iva=pv, codice_fiscale=pv, denominazione=f"TEST_T69 Rit {cod}", soggetto_ritenuta=True,
                                                   ritenuta_tipo="RT01", ritenuta_aliquota=20, ritenuta_base=100, ritenuta_causale="A", ritenuta_codice_tributo=cod))
            assert r.status_code == 200, r.text
            pid = _upload(pv, f"TEST69-{k}", f"TEST_T69 Rit {cod}")
            d = s.get(f"{API}/passive/{pid}").json()
            assert d["ritenuta_importo"] > 0, d
            p = s.post(f"{API}/passive/{pid}/pagamenti", json={"data": PM.replace(day=20).isoformat(), "importo": d["netto"]})
            assert p.status_code == 200, p.text
            S[f"rit_{k}"] = d["ritenuta_importo"]

    def test_mese_righe_per_codice(self):
        m = sess().get(f"{API}/ritenute/mese", params={"mese": YM}).json()
        assert m["codice"] == "1038 + 1040", m["codice"]
        righe = {r["codice"]: r for r in m["righe"]}
        assert set(righe) == {"1038", "1040"} and righe["1038"]["importo"] == S["rit_a"] and righe["1040"]["importo"] == S["rit_b"]
        assert m["totale"] == round(S["rit_a"] + S["rit_b"], 2)
        assert all(r["anno_riferimento"] == PM.year and r["descrizione"] for r in m["righe"])
        assert {i["codice"] for f in m["fornitori"] for i in f["righe"]} == {"1038", "1040"}

    def test_f24_pdf_two_rows(self):
        r = sess().get(f"{API}/ritenute/{YM}/f24")
        assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
        t = pdf_text(r.content)
        assert "1038" in t and "1040" in t, t[:1500]
        S["pdf1"] = t

    def test_scadenza_f24_pdf(self):
        r = sess().get(f"{API}/scadenze-fiscali/RIT-{YM}/f24")
        assert r.status_code == 200, r.text
        t = pdf_text(r.content)
        assert "1038" in t and "1040" in t

    def test_scadenze_list(self):
        r = sess().get(f"{API}/scadenze-fiscali")
        if r.status_code != 200:
            pytest.skip(r.text)
        items = r.json() if isinstance(r.json(), list) else r.json().get("scadenze", [])
        x = next((i for i in items if i.get("key") == f"RIT-{YM}"), None)
        assert x and x["codice"] == "1038 + 1040" and len(x["righe"]) == 2, x

    def test_versato_stores_codice(self):
        v = sess().post(f"{API}/ritenute/{YM}/versato", json={"data": today.isoformat()})
        assert v.status_code == 200, v.text
        assert v.json()["versato"]["codice"] == "1038 + 1040" and v.json()["versato"]["importo"] == round(S["rit_a"] + S["rit_b"], 2)
        assert sess().delete(f"{API}/scadenze-fiscali/versato/RIT-{YM}").status_code == 200

    def test_single_codice_month_unchanged(self):
        m = sess().get(f"{API}/ritenute/mese", params={"mese": today.isoformat()[:7]}).json()
        assert m["codice"] == "1040" and m["righe"] == [] and m["totale"] == 0


# --- Import massivo
def _xlsx(wb):
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


class TestImport:
    def test_modello_columns_prefilled(self):
        r = sess().get(f"{API}/importazione/modello")
        assert r.status_code == 200, r.text
        wb = load_workbook(io.BytesIO(r.content))
        cli = [c.value.replace(" *", "") for c in wb["Clienti"][1]]
        fo = [c.value.replace(" *", "") for c in wb["Fornitori"][1]]
        pag = ["pagamento_modalita", "pagamento_rate", "pagamento_giorni", "pagamento_fine_mese"]
        assert cli[-4:] == pag and "persona" not in cli
        extra = ["detraibilita_iva", "iban", "persona", "nome", "cognome", "data_nascita", "comune_nascita", "provincia_nascita", "soggetto_ritenuta",
                 "ritenuta_codice_tributo", "ritenuta_tipo", "ritenuta_aliquota", "ritenuta_base", "ritenuta_causale", "cassa_tipo", "cassa_aliquota", "cassa_ritenuta"]
        assert fo == cli + extra, fo
        rows = [dict(zip(fo, [c.value for c in row])) for row in wb["Fornitori"].iter_rows(min_row=2)]
        pf = next(x for x in rows if x["denominazione"] == "Rossi Mario")
        assert pf["persona"] == "FISICA" and pf["nome"] == "Mario" and pf["ritenuta_codice_tributo"] == "1038" and pf["soggetto_ritenuta"] in ("SI", "NO")
        assert pf["pagamento_fine_mese"] in ("SI", "NO") and pf["cassa_ritenuta"] in ("SI", "NO")
        crow = [dict(zip(cli, [c.value for c in row])) for row in wb["Clienti"].iter_rows(min_row=2)]
        c = next(x for x in crow if x["denominazione"] == "TEST_T69 Cli MP12")
        assert c["pagamento_modalita"] == "MP12" and c["pagamento_rate"] == 3 and c["pagamento_fine_mese"] == "SI"
        S["wb"] = r.content

    def test_upload_fill(self):
        wb = load_workbook(io.BytesIO(S["wb"]))
        fo = [c.value.replace(" *", "") for c in wb["Fornitori"][1]]
        cli = [c.value.replace(" *", "") for c in wb["Clienti"][1]]
        new_cf = "VRDGPP75B02F205X"
        S["new_cf"] = new_cf
        rowf = {"denominazione": "x", "codice_fiscale": new_cf, "indirizzo": "Via Z 3", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT",
                "pagamento_modalita": "mp05", "pagamento_rate": 2, "pagamento_giorni": 45, "pagamento_fine_mese": "SI",
                "persona": "FISICA", "nome": "Giuseppe", "cognome": "Verdi", "data_nascita": "02/02/1975", "comune_nascita": "Milano", "provincia_nascita": "mi",
                "soggetto_ritenuta": "SI", "ritenuta_codice_tributo": "1038", "ritenuta_tipo": "RT01", "ritenuta_aliquota": 23, "ritenuta_base": 50,
                "ritenuta_causale": "R", "cassa_ritenuta": "NO"}
        wb["Fornitori"].append([rowf.get(c) for c in fo])
        cv = piva("0123456869")
        S["new_cli"] = cv
        rowc = {"denominazione": "TEST_T69 Import Cli", "partita_iva": cv, "codice_fiscale": cv, "codice_destinatario": "ABC1234", "indirizzo": "Via Q", "cap": "10100",
                "comune": "Torino", "provincia": "TO", "nazione": "IT", "pagamento_modalita": "MP12", "pagamento_rate": 4, "pagamento_giorni": 30, "pagamento_fine_mese": "NO"}
        wb["Clienti"].append([rowc.get(c) for c in cli])
        # update existing giuridica supplier: change pagamento
        for row in wb["Fornitori"].iter_rows(min_row=2):
            if row[0].value == "TEST_T69 Giur Srl":
                row[fo.index("pagamento_modalita")].value = "MP08"
                row[fo.index("ritenuta_codice_tributo")].value = "1038"
        r = sess().post(f"{API}/importazione/anteprima", files={"file": ("imp.xlsx", _xlsx(wb), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert r.status_code == 200, r.text
        rp = r.json()["riepilogo"]
        assert not rp["Fornitori"]["errori"] and not rp["Clienti"]["errori"], rp
        assert rp["Fornitori"]["nuovi"] == 1 and rp["Clienti"]["nuovi"] == 1, rp
        c = sess().post(f"{API}/importazione/{r.json()['id']}/conferma")
        assert c.status_code == 200, c.text

    def test_imported_values(self):
        ps = sess().get(f"{API}/parties").json()
        f = next(x for x in ps if x.get("codice_fiscale") == S["new_cf"])
        assert f["denominazione"] == "Verdi Giuseppe" and f["persona"] == "fisica" and f["data_nascita"] == "1975-02-02" and f["provincia_nascita"] == "MI"
        assert f["soggetto_ritenuta"] is True and f["ritenuta_codice_tributo"] == "1038" and f["ritenuta_aliquota"] == 23 and f["cassa_ritenuta"] is False
        assert f["pagamento_modalita"] == "MP05" and f["pagamento_rate"] == 2 and f["pagamento_giorni"] == 45 and f["pagamento_fine_mese"] is True
        c = next(x for x in ps if x.get("partita_iva") == S["new_cli"])
        assert c["pagamento_modalita"] == "MP12" and c["pagamento_rate"] == 4 and c["pagamento_fine_mese"] is False
        g = next(x for x in ps if x["id"] == S["pg"])
        assert g["pagamento_modalita"] == "MP08" and g["ritenuta_codice_tributo"] == "1038"

    def test_import_fisica_missing_nome_error(self):
        wb = load_workbook(io.BytesIO(S["wb"]))
        fo = [c.value.replace(" *", "") for c in wb["Fornitori"][1]]
        row = {"denominazione": "x", "codice_fiscale": "BNCLRA80A41H501X", "indirizzo": "V", "cap": "00100", "comune": "Roma", "persona": "FISICA", "cognome": "Bianchi"}
        wb["Fornitori"].append([row.get(c) for c in fo])
        r = sess().post(f"{API}/importazione/anteprima", files={"file": ("imp.xlsx", _xlsx(wb), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert r.status_code == 200
        e = r.json()["riepilogo"]["Fornitori"]["errori"]
        assert e and "nome" in e[0]["errore"].lower(), e


if __name__ == "__main__" and sys.argv[-1] == "clean":
    clean()

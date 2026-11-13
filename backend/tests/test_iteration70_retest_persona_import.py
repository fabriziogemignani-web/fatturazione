# Iteration 70: retest of iteration 69 fixes - persona fisica without denominazione, giuridica w/o ragione sociale 422,
# codice tributo validation vs table, import FISICA row with blank denominazione, import update path normalised values.
# Run: pytest tests/test_iteration70_retest_persona_import.py -v -n 0   (T70_KEEP=1 keeps data; `python tests/test_iteration70_retest_persona_import.py clean`)
import io
import os
import subprocess
import sys

import pytest
import requests
from openpyxl import load_workbook

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
UID, TOK = "test-user-t70-admin", "test_session_t70_admin"
S = {}
COLLS = ["invoices", "passive_invoices", "parties", "payments", "passive_payments", "coa_entries", "coa_accounts", "coa_causali", "coa_iva", "articles",
         "stock_moves", "f24_versamenti", "sdi_events", "audit", "com_log", "import_batches", "partite_aperte", "export_log"]
XL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


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


CO, F1, CLI = piva("0987123470"), piva("0234567070"), piva("0123456970")


def sess():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    if S.get("cid"):
        s.headers["X-Company-Id"] = S["cid"]
    return s


def clean():
    colls = "[" + ",".join(f'"{c}"' for c in COLLS) + "]"
    mongo(f'db.companies.find({{denominazione:/^TEST_T70/}}).forEach(c=>{{{colls}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t70@example.com", name:"TEST_t70", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": "TEST_T70 Srl", "partita_iva": CO, "codice_fiscale": CO, "regime_fiscale": "RF01",
                                              "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT",
                                              "iban": "IT60X0542811101000000123456"})
    assert r.status_code == 200, r.text
    S["cid"] = r.json()["id"]
    yield
    if not os.environ.get("T70_KEEP"):
        clean()
    else:
        print("\nKEEP", S)


def forn(**kw):
    b = {"tipo": "fornitore", "partita_iva": "", "codice_fiscale": "RSSMRA80A01H501U", "indirizzo": "Via Y 1", "cap": "50100",
         "comune": "Firenze", "provincia": "FI", "nazione": "IT"}
    b.update(kw)
    return b


def detail(r):
    d = r.json().get("detail")
    return d if isinstance(d, list) else [{"loc": [], "msg": str(d)}]


# --- HIGH 1: persona fisica w/o denominazione, giuridica w/o ragione sociale
class TestPersona:
    def test_fisica_no_denominazione_key(self):
        r = sess().post(f"{API}/parties", json=forn(persona="fisica", nome="Mario", cognome="Rossi"))
        assert r.status_code == 200, r.text
        d = r.json()
        S["pf"] = d["id"]
        assert d["denominazione"] == "Rossi Mario" and d["persona"] == "fisica"

    def test_fisica_empty_denominazione(self):
        r = sess().post(f"{API}/parties", json=forn(persona="fisica", nome=" Anna ", cognome=" Bianchi ", denominazione="", codice_fiscale="BNCNNA80A41H501X"))
        assert r.status_code == 200, r.text
        S["pf2"] = r.json()["id"]
        g = next(x for x in sess().get(f"{API}/parties", params={"tipo": "fornitore"}).json() if x["id"] == S["pf2"])
        assert g["denominazione"] == "Bianchi Anna" and g["nome"] == "Anna" and g["cognome"] == "Bianchi"

    def test_fisica_ignores_given_denominazione(self):
        r = sess().put(f"{API}/parties/{S['pf']}", json=forn(persona="fisica", nome="Mario", cognome="Verdi", denominazione="Altro"))
        assert r.status_code == 200, r.text
        g = next(x for x in sess().get(f"{API}/parties").json() if x["id"] == S["pf"])
        assert g["denominazione"] == "Verdi Mario"

    @pytest.mark.parametrize("den", [None, "", "   "])
    def test_giuridica_no_ragione_sociale_422(self, den):
        body = forn(partita_iva=F1, codice_fiscale=F1)
        if den is not None:
            body["denominazione"] = den
        r = sess().post(f"{API}/parties", json=body)
        assert r.status_code == 422, r.text
        d = detail(r)
        assert any(tuple(x["loc"])[-1:] == ("denominazione",) and "ragione sociale" in x["msg"].lower() for x in d), d

    def test_put_giuridica_empty_denominazione_422(self):
        r = sess().put(f"{API}/parties/{S['pf']}", json=forn(persona="giuridica", denominazione=""))
        assert r.status_code == 422, r.text


# --- New validation: codice tributo must exist in table
class TestCodiceTributo:
    def test_unknown_codice_422(self):
        r = sess().post(f"{API}/parties", json=forn(persona="fisica", nome="X", cognome="Y", ritenuta_codice_tributo="9999"))
        assert r.status_code == 422, r.text
        d = detail(r)
        assert any(tuple(x["loc"])[-1:] == ("ritenuta_codice_tributo",) and "Codice tributo non presente" in x["msg"] for x in d), d

    def test_known_codici_ok(self):
        for c in ("1038", "1040", ""):
            r = sess().put(f"{API}/parties/{S['pf2']}", json=forn(persona="fisica", nome="Anna", cognome="Bianchi", codice_fiscale="BNCNNA80A41H501X", ritenuta_codice_tributo=c))
            assert r.status_code == 200, (c, r.text)

    def test_codice_bad_pattern_422(self):
        r = sess().put(f"{API}/parties/{S['pf2']}", json=forn(persona="fisica", nome="Anna", cognome="Bianchi", ritenuta_codice_tributo="10a"))
        assert r.status_code == 422


# --- Import: FISICA blank denominazione accepted, update path normalised, unknown codice tributo flagged
class TestImport:
    def test_setup_giur(self):
        r = sess().post(f"{API}/parties", json=forn(partita_iva=F1, codice_fiscale=F1, denominazione="TEST_T70 Giur Srl"))
        assert r.status_code == 200, r.text
        S["pg"] = r.json()["id"]
        r = sess().get(f"{API}/importazione/modello")
        assert r.status_code == 200
        S["wb"] = r.content

    def _wb(self):
        wb = load_workbook(io.BytesIO(S["wb"]))
        fo = [c.value.replace(" *", "") for c in wb["Fornitori"][1]]
        return wb, fo

    def _send(self, wb):
        b = io.BytesIO()
        wb.save(b)
        return sess().post(f"{API}/importazione/anteprima", files={"file": ("imp.xlsx", b.getvalue(), XL)})

    def test_fisica_blank_den_and_update_normalised(self):
        wb, fo = self._wb()
        new = {"codice_fiscale": "VRDGPP75B02F205X", "indirizzo": "Via Z 3", "cap": "20100", "comune": "Milano", "nazione": "IT", "persona": "FISICA",
               "nome": "Giuseppe", "cognome": "Verdi", "provincia_nascita": "mi"}
        wb["Fornitori"].append([new.get(c) for c in fo])
        for row in wb["Fornitori"].iter_rows(min_row=2):
            if row[0].value == "TEST_T70 Giur Srl":
                row[fo.index("persona")].value = "GIURIDICA"
                row[fo.index("nome")].value = "Zzz"
                row[fo.index("cognome")].value = "Qqq"
                row[fo.index("provincia_nascita")].value = "fi"
            if row[0].value == "Bianchi Anna":
                row[fo.index("provincia_nascita")].value = "to"
                row[fo.index("nome")].value = "Annalisa"
        r = self._send(wb)
        assert r.status_code == 200, r.text
        rp = r.json()["riepilogo"]["Fornitori"]
        assert not rp["errori"] and rp["nuovi"] == 1, rp
        c = sess().post(f"{API}/importazione/{r.json()['id']}/conferma")
        assert c.status_code == 200, c.text
        ps = sess().get(f"{API}/parties").json()
        n = next(x for x in ps if x.get("codice_fiscale") == "VRDGPP75B02F205X")
        S["imp"] = n["id"]
        assert n["denominazione"] == "Verdi Giuseppe" and n["provincia_nascita"] == "MI"
        g = next(x for x in ps if x["id"] == S["pg"])
        assert g["nome"] == "" and g["cognome"] == "" and g["provincia_nascita"] == "" and g["denominazione"] == "TEST_T70 Giur Srl", g
        a = next(x for x in ps if x["id"] == S["pf2"])
        assert a["provincia_nascita"] == "TO" and a["nome"] == "Annalisa" and a["denominazione"] == "Bianchi Annalisa", a

    def test_import_unknown_codice_error(self):
        wb, fo = self._wb()
        row = {"codice_fiscale": "NRELCU80A01H501X", "indirizzo": "V", "cap": "00100", "comune": "Roma", "persona": "FISICA", "nome": "Luca", "cognome": "Neri",
               "ritenuta_codice_tributo": "9999"}
        wb["Fornitori"].append([row.get(c) for c in fo])
        r = self._send(wb)
        assert r.status_code == 200
        e = r.json()["riepilogo"]["Fornitori"]["errori"]
        assert e and "codice tributo" in str(e).lower(), e

    def test_import_giuridica_blank_den_error(self):
        wb, fo = self._wb()
        row = {"partita_iva": piva("0234567170"), "codice_fiscale": piva("0234567170"), "indirizzo": "V", "cap": "00100", "comune": "Roma", "persona": "GIURIDICA"}
        wb["Fornitori"].append([row.get(c) for c in fo])
        r = self._send(wb)
        assert r.status_code == 200
        e = r.json()["riepilogo"]["Fornitori"]["errori"]
        assert e and "denominazione" in str(e).lower(), e


if __name__ == "__main__" and sys.argv[-1] == "clean":
    clean()

# Iteration 71: supplier multiple banks (banche_fornitore), IBAN entered at distinta time saved in anagrafica,
# choice of non-default supplier bank in distinta (PDF/CBI), Excel import iban -> default bank, Liquidazione IVA PDF, menu voci.
# Run: pytest tests/test_iteration71_banche_fornitore_liqpdf.py -v -n 0   (T71_KEEP=1 keeps data; `python tests/test_iteration71_banche_fornitore_liqpdf.py clean`)
import io
import json
import os
import random
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import date, timedelta

import fitz
import pytest
import requests
from openpyxl import load_workbook

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
RUN = os.environ.get("T71_RUN") or str(random.randint(100000, 999999))
UID, TOK = "test-user-t71-admin", "test_session_t71_admin"
PIVA = "77" + RUN + "711"
SUP_A, SUP_B, SUP_C = "07" + RUN + "712", "07" + RUN + "713", "07" + RUN + "714"
CO_IBAN1, CO_IBAN2 = "IT60X0542811101000000123456", "IT40S0542811101000000123456"
IBAN_A = "IT02A0306902887100000001234"   # in XML
IBAN_B1 = "IT07X0542811101000000654321"
IBAN_B2 = "GB82WEST12345698765432"
IBAN_C = "DE89370400440532013000"
IBAN_LEG = "IT60X0542811101000000123456"
T = date.today()
d = lambda n: (T + timedelta(days=n)).isoformat()  # noqa: E731
ST = {}
COLLS = ["invoices", "passive_invoices", "parties", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "partite_aperte", "pag_distinte", "import_batches", "f24_versamenti", "articles"]
NSX = {"c": "urn:CBI:xsd:CBIPaymentRequest.00.04.00"}
XL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


def sess(cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    if cid or ST.get("cid"):
        s.headers["X-Company-Id"] = cid or ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{denominazione:/^TEST_T71/}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def xml(numero, piva_sup, nome, iban=True):
    x = open(os.path.join(os.path.dirname(__file__), "fixtures/sample_fattura.xml")).read()
    x = x.replace("<IdCodice>01234567890</IdCodice>", f"<IdCodice>{PIVA}</IdCodice>").replace("02345670481", piva_sup)
    x = x.replace("<Numero>5674/2026</Numero>", f"<Numero>{numero}</Numero>").replace("<Data>2026-10-30</Data>", f"<Data>{d(-3)}</Data>")
    x = x.replace("DEMO Energia Toscana SpA", nome).replace("<DataScadenzaPagamento>2026-11-29</DataScadenzaPagamento>", f"<DataScadenzaPagamento>{d(20)}</DataScadenzaPagamento>")
    if not iban:
        x = x.replace(f"<IBAN>{IBAN_A}</IBAN>", "")
    return x


def up(name, x):
    r = sess().post(f"{API}/passive/upload", files=[("files", (name, x, "text/xml"))])
    assert r.status_code == 200, r.text
    assert r.json()[0]["ok"], r.text
    return r.json()[0]["documenti"][0]


def getp(pid):
    return next(x for x in sess().get(f"{API}/parties").json() if x["id"] == pid)


def scad():
    r = sess().get(f"{API}/pagamenti-fornitori/scadenze")
    assert r.status_code == 200, r.text
    return {x["key"]: x for x in r.json()}


def post_dist(voci, iban=CO_IBAN1):
    return sess().post(f"{API}/pagamenti-fornitori/distinte", json={"banca_iban": iban, "data": T.isoformat(),
                                                                    "voci": [{"key": k, "importo": v, **({"iban": ib} if ib is not None else {})} for k, v, ib in voci]})


def pdf_text(content):
    doc = fitz.open(stream=content, filetype="pdf")
    return [p.get_text() for p in doc]


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t71@example.com", name:"TEST_T71", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess(cid="").post(f"{API}/companies", json={"denominazione": f"TEST_T71 Banche {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                                   "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    sess().put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True, "corrispettivi": True, "contabilita": True})
    c = sess().get(f"{API}/company").json()
    c["banche"] = [{"nome": "TEST Banca Uno", "iban": CO_IBAN1, "predefinita": True, "cuc": "AB12CD34"}, {"nome": "TEST Banca Due", "iban": CO_IBAN2, "predefinita": False}]
    assert sess().put(f"{API}/company", json=c).status_code == 200
    a = up("a.xml", xml("T71-A1", SUP_A, "TEST_T71 Forn A SpA"))
    b = up("b.xml", xml("T71-B1", SUP_B, "TEST_T71 Forn B Srl", iban=False))
    cc = up("c.xml", xml("T71-C1", SUP_C, "TEST_T71 Forn C Srl", iban=False))
    ST.update(A=a["id"], fa=a["nuovo_fornitore_id"], B=b["id"], fb=b["nuovo_fornitore_id"], C=cc["id"], fc=cc["nuovo_fornitore_id"])
    yield
    if os.environ.get("T71_KEEP"):
        print("\nKEEP", RUN, ST)
    else:
        clean()


# Supplier banks in anagrafica
class TestBancheFornitore:
    def test_01_multi_banks_default(self):
        p = getp(ST["fb"])
        body = {**p, "iban": "", "banche_fornitore": [{"nome": "TEST Banca B1", "iban": "it07 x054 2811 1010 0000 0654 321", "predefinita": False},
                                                       {"nome": "TEST Banca B2", "iban": IBAN_B2, "predefinita": True}]}
        r = sess().put(f"{API}/parties/{ST['fb']}", json=body)
        assert r.status_code == 200, r.text
        g = getp(ST["fb"])
        assert g["iban"] == IBAN_B2, g["iban"]
        assert [(b["iban"], b["predefinita"], b["nome"]) for b in g["banche_fornitore"]] == [(IBAN_B1, False, "TEST Banca B1"), (IBAN_B2, True, "TEST Banca B2")]

    def test_02_invalid_iban_422(self):
        p = getp(ST["fb"])
        r = sess().put(f"{API}/parties/{ST['fb']}", json={**p, "banche_fornitore": p["banche_fornitore"] + [{"nome": "x", "iban": "IT00X123", "predefinita": False}]})
        assert r.status_code == 422, r.text

    def test_03_duplicate_iban_422(self):
        p = getp(ST["fb"])
        r = sess().put(f"{API}/parties/{ST['fb']}", json={**p, "banche_fornitore": p["banche_fornitore"] + [{"nome": "dup", "iban": IBAN_B1, "predefinita": False}]})
        assert r.status_code == 422 and "banche_fornitore" in r.text, r.text

    def test_04_remove_default_with_stale_iban(self):
        # client sends only the non-default bank but keeps the old iban field -> what happens?
        p = getp(ST["fb"])
        r = sess().put(f"{API}/parties/{ST['fb']}", json={**p, "banche_fornitore": [{"nome": "TEST Banca B1", "iban": IBAN_B1, "predefinita": True}]})
        assert r.status_code == 200, r.text
        g = getp(ST["fb"])
        ST["stale_iban_readded"] = any(b["iban"] == IBAN_B2 for b in g["banche_fornitore"])
        # restore
        r = sess().put(f"{API}/parties/{ST['fb']}", json={**g, "iban": IBAN_B2, "banche_fornitore": [{"nome": "TEST Banca B1", "iban": IBAN_B1}, {"nome": "TEST Banca B2", "iban": IBAN_B2, "predefinita": True}]})
        assert r.status_code == 200 and getp(ST["fb"])["iban"] == IBAN_B2
        print("stale iban re-added:", ST["stale_iban_readded"])

    def test_05_legacy_iban_only(self):
        mongo(f'db.parties.updateOne({{id:"{ST["fa"]}"}}, {{$unset:{{banche_fornitore:""}}, $set:{{iban:"{IBAN_A}"}}}})')
        s = scad()
        row = s[f"{ST['A']}:1"]
        assert row["iban"] == IBAN_A and row["banche"] == [{"nome": "", "iban": IBAN_A, "predefinita": True}], row


# Scadenze listing with banks
class TestScadenze:
    def test_01_fields(self):
        s = scad()
        b = s[f"{ST['B']}:1"]
        assert b["iban"] == IBAN_B2 and len(b["banche"]) == 2, b
        c = s[f"{ST['C']}:1"]
        assert c["iban"] == "" and c["banche"] == [], c


# Distinta with IBAN entered / chosen per voce
class TestDistinta:
    def test_01_missing_iban_400(self):
        r = post_dist([(f"{ST['C']}:1", 10, None)])
        assert r.status_code == 400 and "IBAN" in r.text, r.text

    def test_02_invalid_iban_400(self):
        r = post_dist([(f"{ST['C']}:1", 10, "IT00X0000000000000000000000")])
        assert r.status_code == 400 and "non valido" in r.text, r.text
        assert getp(ST["fc"]).get("banche_fornitore") in (None, [])

    def test_03_new_iban_saved_and_non_default_bank(self):
        r = post_dist([(f"{ST['C']}:1", 100, "de89 3704 0044 0532 0130 00"), (f"{ST['B']}:1", 50, IBAN_B1)])
        assert r.status_code == 200, r.text
        dd = r.json()
        ST["D1"] = dd["id"]
        assert dd["iban_salvati"] == 1, dd
        by = {x["party_id"]: x["iban"] for x in dd["disposizioni"]}
        assert by == {ST["fc"]: IBAN_C, ST["fb"]: IBAN_B1}, by
        pc = getp(ST["fc"])
        assert pc["iban"] == IBAN_C and pc["banche_fornitore"] == [{"nome": "", "iban": IBAN_C, "predefinita": True}], pc
        pb = getp(ST["fb"])
        assert pb["iban"] == IBAN_B2 and len(pb["banche_fornitore"]) == 2, pb  # existing bank chosen -> nothing changed

    def test_04_cbi_pdf_use_chosen_iban(self):
        x = sess().get(f"{API}/pagamenti-fornitori/distinte/{ST['D1']}/cbi")
        assert x.status_code == 200, x.text
        root = ET.fromstring(x.content)
        ibans = {t.find("c:CdtrAcct/c:Id/c:IBAN", NSX).text for t in root.findall("c:PmtInf/c:CdtTrfTxInf", NSX)}
        assert ibans == {IBAN_C, IBAN_B1}, ibans
        p = sess().get(f"{API}/pagamenti-fornitori/distinte/{ST['D1']}/pdf")
        assert p.status_code == 200 and p.headers["content-type"].startswith("application/pdf")
        txt = "".join(pdf_text(p.content)).replace(" ", "").replace("\n", "")
        assert IBAN_B1 in txt and IBAN_C in txt and IBAN_B2 not in txt

    def test_05_second_new_iban_not_default(self):
        # supplier C already has a bank -> another new IBAN is appended, not default
        r = post_dist([(f"{ST['C']}:1", 10, "IT60X0542811101000000123456")])
        assert r.status_code == 200, r.text
        ST["D2"] = r.json()["id"]
        assert r.json()["iban_salvati"] == 1
        pc = getp(ST["fc"])
        assert pc["iban"] == IBAN_C and [(b["iban"], b["predefinita"]) for b in pc["banche_fornitore"]] == [(IBAN_C, True), ("IT60X0542811101000000123456", False)], pc

    def test_06_party_save_regression(self):
        pc = getp(ST["fc"])
        r = sess().put(f"{API}/parties/{ST['fc']}", json=pc)
        assert r.status_code == 200, r.text
        assert len(getp(ST["fc"])["banche_fornitore"]) == 2

    def test_07_annulla(self):
        for k in ("D1", "D2"):
            assert sess().delete(f"{API}/pagamenti-fornitori/distinte/{ST[k]}").status_code == 200


# Excel import keeps other banks, imported IBAN becomes default
class TestImport:
    def test_01_import_iban_default(self):
        # sample XML IBAN of supplier A has a wrong checksum: replace it so the template round-trip is clean
        mongo(f'db.parties.updateOne({{id:"{ST["fa"]}"}}, {{$set:{{iban:"{IBAN_LEG}", banche_fornitore:[{{nome:"", iban:"{IBAN_LEG}", predefinita:true}}]}}}})')
        r = sess().get(f"{API}/importazione/modello")
        assert r.status_code == 200
        wb = load_workbook(io.BytesIO(r.content))
        fo = [c.value.replace(" *", "") for c in wb["Fornitori"][1]]
        found = False
        for row in wb["Fornitori"].iter_rows(min_row=2):
            if row[fo.index("partita_iva")].value == SUP_B:
                row[fo.index("iban")].value = IBAN_B1
                found = True
        assert found
        b = io.BytesIO()
        wb.save(b)
        r = sess().post(f"{API}/importazione/anteprima", files={"file": ("imp.xlsx", b.getvalue(), XL)})
        assert r.status_code == 200, r.text
        assert not r.json()["riepilogo"]["Fornitori"]["errori"], r.json()["riepilogo"]
        c = sess().post(f"{API}/importazione/{r.json()['id']}/conferma")
        assert c.status_code == 200, c.text
        pb = getp(ST["fb"])
        assert pb["iban"] == IBAN_B1
        assert sorted((b["iban"], b["predefinita"]) for b in pb["banche_fornitore"]) == sorted([(IBAN_B1, True), (IBAN_B2, False)]), pb["banche_fornitore"]
        assert {b["nome"] for b in pb["banche_fornitore"]} == {"TEST Banca B1", "TEST Banca B2"}
        pc = getp(ST["fc"])
        assert len(pc["banche_fornitore"]) == 2 and pc["iban"] == IBAN_C  # unchanged supplier untouched

    def test_02_import_legacy_supplier(self):
        # legacy supplier with only iban (no banche_fornitore) imported with a new iban: is the old iban kept as a bank?
        mongo(f'db.parties.updateOne({{id:"{ST["fa"]}"}}, {{$unset:{{banche_fornitore:""}}, $set:{{iban:"{IBAN_LEG}"}}}})')
        r = sess().get(f"{API}/importazione/modello")
        wb = load_workbook(io.BytesIO(r.content))
        fo = [c.value.replace(" *", "") for c in wb["Fornitori"][1]]
        for row in wb["Fornitori"].iter_rows(min_row=2):
            if row[fo.index("partita_iva")].value == SUP_A:
                row[fo.index("iban")].value = IBAN_B1
        b = io.BytesIO()
        wb.save(b)
        r = sess().post(f"{API}/importazione/anteprima", files={"file": ("imp.xlsx", b.getvalue(), XL)})
        assert r.status_code == 200, r.text
        assert sess().post(f"{API}/importazione/{r.json()['id']}/conferma").status_code == 200
        pa = getp(ST["fa"])
        print("legacy after import:", pa["iban"], pa.get("banche_fornitore"))
        assert pa["iban"] == IBAN_B1
        assert any(b["iban"] == IBAN_LEG for b in pa["banche_fornitore"]), "legacy IBAN lost after import"


# Liquidazione IVA PDF
class TestLiquidazionePdf:
    @pytest.fixture(autouse=True, scope="class")
    def registra(self):
        ids = json.dumps([ST["A"], ST["B"], ST["C"]])
        mongo(f'db.passive_invoices.updateMany({{company_id:"{ST["cid"]}", id:{{$in:{ids}}}, stato_reg:{{$ne:"registrata"}}}}, '
              f'{{$set:{{stato_reg:"registrata", data_registrazione:"{T.isoformat()}", anno_registrazione:{T.year}}}}})')

    def test_01_json_vs_pdf_mensile_all(self):
        j = sess().get(f"{API}/liquidazione-iva", params={"anno": T.year, "periodicita": "mensile"}).json()
        p = next(x for x in j["periodi"] if x["periodo"] == T.month)
        assert p["iva_credito"] > 0, p
        r = sess().get(f"{API}/liquidazione-iva/pdf", params={"anno": T.year, "periodicita": "mensile"})
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/pdf"), r.text[:200]
        pages = pdf_text(r.content)
        assert len(pages) >= 13, len(pages)
        from estratto import eur  # noqa
        pg = pages[T.month - 1]
        assert p["label"] in pg and "Dettaglio IVA per aliquota" in pg
        assert eur(-p["iva_credito"]) in pg, (eur(-p["iva_credito"]), pg)
        assert "22%" in pg and eur(p["acquisti"]["imponibile"]) in pg, pg
        assert "Riepilogo annuale" in "".join(pages[12:])

    def test_02_single_period_and_trimestrale(self):
        r = sess().get(f"{API}/liquidazione-iva/pdf", params={"anno": T.year, "periodicita": "mensile", "periodo": T.month})
        assert r.status_code == 200 and len(pdf_text(r.content)) == 1
        assert f"_{T.month:02d}.pdf" in r.headers.get("content-disposition", "")
        r = sess().get(f"{API}/liquidazione-iva/pdf", params={"anno": T.year, "periodicita": "trimestrale"})
        assert r.status_code == 200 and len(pdf_text(r.content)) >= 5
        r = sess().get(f"{API}/liquidazione-iva/pdf", params={"anno": T.year, "periodicita": "trimestrale", "periodo": (T.month - 1) // 3 + 1})
        assert r.status_code == 200 and "Interessi" in pdf_text(r.content)[0]

    def test_03_invalid_periodo(self):
        r = sess().get(f"{API}/liquidazione-iva/pdf", params={"anno": T.year, "periodicita": "trimestrale", "periodo": 5})
        assert r.status_code == 400, r.text
        r = sess().get(f"{API}/liquidazione-iva/pdf", params={"anno": T.year, "periodicita": "mensile", "periodo": 13})
        assert r.status_code in (400, 422), r.text
        assert sess().get(f"{API}/liquidazione-iva/pdf", params={"periodicita": "mensile"}).status_code == 422  # anno required


# Menu voci
class TestMenuVoci:
    def test_01_menu_groups(self):
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from menu_voci import MENU
        g = {m[0]: m[1] for m in MENU}
        assert g["scadenzario"] == g["scadenzario-fornitori"] == g["riba"] == "Contabilità generale"


if __name__ == "__main__" and sys.argv[-1] == "clean":
    clean()

# Iteration 74: Certificazione compensi annuale (GET /ritenute/certificazione, /ritenute/certificazione/pdf) + regression /ritenute/mese, scadenze-fiscali RIT.
# Run: pytest tests/test_iteration74_certificazione_compensi.py -v -n 0   (T74_KEEP=1 keeps data for UI; `python tests/<file> clean`)
import json
import os
import random
import sys

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

RUN = os.environ.get("T74_RUN") or str(random.randint(100000, 999999))
TOK, UID = "test_session_t74_admin", "test-user-t74-admin"
PIVA = "74" + RUN + "741"
IBAN = "IT60X0542811101000000123456"
ST = {}
COLLS = ["invoices", "passive_invoices", "parties", "articles", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "partite_aperte", "f24_versamenti", "distinte_pagamento", "pagamenti_distinte", "counters"]


def sess(cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    c = cid or ST.get("cid")
    if c:
        s.headers["X-Company-Id"] = c
    return s


def clean():
    mongo(f'db.companies.find({{denominazione:/^TEST_T74/}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.getCollectionNames().forEach(n=>{{ if(n.indexOf("distint")>=0) db[n].deleteMany({{company_id:c.id}}); }});'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def company(name, piva=PIVA):
    r = sess("x").post(f"{API}/companies", json={"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01",
                                                 "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    sess(cid).put(f"{API}/companies/{cid}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                         "corrispettivi": True, "contabilita": True})
    s = sess(cid)
    c = s.get(f"{API}/company").json()
    c["banche"] = [{"nome": "TEST Banca", "iban": IBAN, "abi": "05428", "cab": "11101", "sia": "A1B2C", "predefinita": True}]
    assert s.put(f"{API}/company", json=c).status_code == 200
    s.get(f"{API}/contabilita/conti")
    return cid


def party(name, piva, **kw):
    r = sess().post(f"{API}/parties", json={"tipo": "fornitore", "denominazione": name, "partita_iva": piva, "codice_fiscale": "RSSMRA80A01H501U",
                                           "codice_destinatario": "ABC1234", "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI",
                                           "nazione": "IT", "soggetto_ritenuta": True, **kw})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def rv(party_id, data, imp):
    b = {"tipo": "acquisto", "party_id": party_id, "numero": f"T74-{random.randint(1000, 99999)}", "data_documento": data, "data_registrazione": data,
         "scadenza": data, "righe": [{"aliquota": 22, "totale": round(imp * 1.22, 2)}]}
    r = sess().post(f"{API}/reg-veloce", json=b)
    assert r.status_code == 200, r.text
    return r.json()


def pay(pid, data, imp):
    r = sess().post(f"{API}/passive/{pid}/pagamenti", json={"data": data, "importo": imp, "metodo": "bonifico"})
    assert r.status_code == 200, r.text
    return r.json()


def cert(anno=2026, cid=None):
    r = sess(cid).get(f"{API}/ritenute/certificazione", params={"anno": anno})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t74.admin@example.com", name:"TEST_T74 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    ST["cid"] = company(f"TEST_T74 Cert {RUN} Srl")
    ST["cid2"] = company(f"TEST_T74 Altra {RUN} Srl", "75" + RUN + "751")
    ST["A"] = party("TEST_T74 Avv. Rossi", "01234567890", ritenuta_aliquota=20, ritenuta_base=100, ritenuta_causale="A")
    ST["B"] = party("TEST_T74 Agente Bianchi", "09876543217", ritenuta_aliquota=23, ritenuta_base=50, ritenuta_causale="Q")
    # A3: 2025 invoice, half paid 2025-12-20, half 2026-01-10 -> only Jan counts in 2026
    a3 = rv(ST["A"], "2025-12-10", 500)
    pay(a3["id"], "2025-12-20", 255)
    pay(a3["id"], "2026-01-10", 255)
    # A1: fully paid March, March versato
    a1 = rv(ST["A"], "2026-03-05", 1000)
    pay(a1["id"], "2026-03-20", 1020)
    # A2: partial (half) in September
    a2 = rv(ST["A"], "2026-09-01", 2000)
    pay(a2["id"], "2026-09-15", 1020)
    # B1: base 50% paid April
    b1 = rv(ST["B"], "2026-04-05", 1000)
    pay(b1["id"], "2026-04-20", 1105)
    # B2: paid only by compensazione -> excluded
    b2 = rv(ST["B"], "2026-05-05", 1000)
    mongo(f'db.passive_payments.insertOne({{id:"t74-comp-{RUN}", company_id:"{ST["cid"]}", invoice_id:"{b2["id"]}", party_id:"{ST["B"]}", importo:1105, data:"2026-05-10", metodo:"compensazione", created_at:new Date().toISOString()}})')
    ST.update(a1=a1, a2=a2, a3=a3, b1=b1, b2=b2)
    r = sess().post(f"{API}/ritenute/2026-03/versato", json={"data": "2026-04-16"})
    assert r.status_code == 200, r.text
    yield
    if os.environ.get("T74_KEEP"):
        print("\nKEEP", RUN, ST["cid"])
    else:
        clean()


class TestCertificazione:
    def test_01_structure_and_supplier_a(self):
        j = cert()
        assert j["anno"] == 2026
        keys = [f["key"] for f in j["fornitori"]]
        assert keys == [ST["B"], ST["A"]], keys  # sorted by name: Agente < Avv.
        a = next(f for f in j["fornitori"] if f["key"] == ST["A"])
        assert [m["mese"] for m in a["mesi"]] == ["2026-01", "2026-03", "2026-09"], a["mesi"]
        jan, mar, sep = a["mesi"]
        assert (jan["compenso"], jan["imponibile_ritenuta"], jan["ritenuta"]) == (250, 250, 50), jan
        assert (mar["compenso"], mar["ritenuta"], mar["versato_il"]) == (1000, 200, "2026-04-16"), mar
        assert (sep["compenso"], sep["ritenuta"], sep["versato_il"]) == (1000, 200, None), sep
        assert mar["label"] == "marzo 2026" or mar["label"].lower().startswith("marzo"), mar["label"]
        assert mar["documenti"] and isinstance(mar["documenti"][0], str)
        assert (a["compenso"], a["imponibile_ritenuta"], a["ritenuta"], a["versata"], a["da_versare"]) == (2250, 2250, 450, 200, 250), a
        assert a["causale"] == "A" and a["codice"] == "1040" and a["descrizione_codice"]
        assert a["codice_fiscale"] == "RSSMRA80A01H501U" and "Milano" in a["indirizzo"]

    def test_02_supplier_b_base50_and_compensazione_excluded(self):
        b = next(f for f in cert()["fornitori"] if f["key"] == ST["B"])
        assert [m["mese"] for m in b["mesi"]] == ["2026-04"], b["mesi"]
        assert (b["compenso"], b["imponibile_ritenuta"], b["ritenuta"], b["non_soggette"], b["versata"], b["da_versare"]) == (1000, 500, 115, 500, 0, 115), b
        assert b["causale"] == "Q"

    def test_03_totals(self):
        assert cert()["totali"] == {"compenso": 3250, "imponibile_ritenuta": 2750, "ritenuta": 565, "versata": 200, "da_versare": 365}

    def test_04_previous_year_only_dec(self):
        j = cert(2025)
        assert len(j["fornitori"]) == 1
        a = j["fornitori"][0]
        assert [m["mese"] for m in a["mesi"]] == ["2025-12"] and a["compenso"] == 250 and a["ritenuta"] == 50

    def test_05_empty_year_and_isolation(self):
        assert cert(2024)["fornitori"] == []
        j2 = cert(2026, ST["cid2"])
        assert j2["fornitori"] == [] and j2["totali"]["ritenuta"] == 0

    def test_06_anno_validation(self):
        assert sess().get(f"{API}/ritenute/certificazione", params={"anno": 1999}).status_code == 422
        assert sess().get(f"{API}/ritenute/certificazione").status_code == 422

    def test_07_no_auth(self):
        assert requests.get(f"{API}/ritenute/certificazione", params={"anno": 2026}).status_code == 401


class TestPdf:
    def test_01_pdf_party(self):
        r = sess().get(f"{API}/ritenute/certificazione/pdf", params={"anno": 2026, "party": ST["A"]})
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/pdf" and r.content[:4] == b"%PDF"
        assert "Certificazione_compensi_2026_TEST_T74_Avv_Rossi" in r.headers.get("content-disposition", "")
        assert r.content.count(b"/Type /Page\n") + r.content.count(b"/Type /Page ") + r.content.count(b"/Type /Page>") >= 1

    def test_02_pdf_all_pages(self):
        r = sess().get(f"{API}/ritenute/certificazione/pdf", params={"anno": 2026})
        assert r.status_code == 200 and r.content[:4] == b"%PDF"
        assert "tutti" in r.headers.get("content-disposition", "")
        import re
        m = re.search(rb"/Count (\d+)", r.content)
        assert m and int(m.group(1)) == 2, m and m.group(1)

    def test_03_pdf_unknown_party_404(self):
        r = sess().get(f"{API}/ritenute/certificazione/pdf", params={"anno": 2026, "party": "nope"})
        assert r.status_code == 404 and "a questo fornitore" in r.json()["detail"], r.text

    def test_04_pdf_no_data_404(self):
        r = sess().get(f"{API}/ritenute/certificazione/pdf", params={"anno": 2024})
        assert r.status_code == 404 and r.json()["detail"] == "Nessun compenso con ritenuta pagato nel 2024"

    def test_05_pdf_isolation(self):
        r = sess(ST["cid2"]).get(f"{API}/ritenute/certificazione/pdf", params={"anno": 2026, "party": ST["A"]})
        assert r.status_code == 404


class TestRegression:
    def test_01_mese(self):
        j = sess().get(f"{API}/ritenute/mese", params={"mese": "2026-09"}).json()
        assert j["totale"] == 200 and j["pagato"] == 1020 and j["versato"] is None
        r = j["fornitori"][0]["righe"][0]
        assert r["compenso"] == 1000 and r["imponibile_ritenuta"] == 1000 and r["ritenuta"] == 200
        jm = sess().get(f"{API}/ritenute/mese", params={"mese": "2026-03"}).json()
        assert jm["versato"]["data"] == "2026-04-16" and jm["totale"] == 200
        assert sess().get(f"{API}/ritenute/mese", params={"mese": "2026-05"}).json()["totale"] == 0  # compensazione only

    def test_02_scadenze_rit(self):
        j = sess().get(f"{API}/scadenze-fiscali").json()
        x = next((x for x in j["scadenze"] if x["key"] == "RIT-2026-09"), None)
        assert x, [s["key"] for s in j["scadenze"]]
        assert x["importo"] == 200 and x["codice"] == "1040" and x["scadenza"] == "2026-10-16"
        assert x["dettaglio"][0]["compenso"] == 1000 and x["dettaglio"][0]["imponibile_ritenuta"] == 1000

    def test_03_versato_then_cert_updates(self):
        r = sess().post(f"{API}/ritenute/2026-09/versato", json={"data": "2026-10-16"})
        assert r.status_code == 200, r.text
        a = next(f for f in cert()["fornitori"] if f["key"] == ST["A"])
        assert a["versata"] == 400 and a["da_versare"] == 50
        assert sess().delete(f"{API}/scadenze-fiscali/versato/RIT-2026-09").status_code == 200
        a = next(f for f in cert()["fornitori"] if f["key"] == ST["A"])
        assert a["versata"] == 200 and a["da_versare"] == 250

    def test_04_f24_pdf(self):
        r = sess().get(f"{API}/ritenute/2026-09/f24")
        assert r.status_code == 200 and r.content[:4] == b"%PDF"


if __name__ == "__main__" and sys.argv[-1] == "clean":
    clean()

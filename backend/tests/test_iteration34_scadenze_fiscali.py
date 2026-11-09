# Iteration 34: Scadenzario fiscale F24 - GET /api/scadenze-fiscali (IVA mensile/trimestrale + ritenute 1040),
# stato (scaduta/in_scadenza/prossima/versato), POST/DELETE versato, GET {key}/f24 PDF, periodicita_iva on company,
# module gating (fatture_passive hides ritenute), roles. Also an in-process unit test with a patched "today" for in_scadenza.
# Run with: pytest test_iteration34_scadenze_fiscali.py -n 0   (date-dependent: written for today = 2026-11-09)
import asyncio
import io
import random
import sys
import uuid
from datetime import date, timedelta

import pytest
import requests
from pypdf import PdfReader

from test_iteration7_pa_scartate_registro import API, mongo
from test_iteration11_passive import variant

sys.path.insert(0, "/app/backend")

RUN = str(random.randint(100000, 999999))
TOK, UID = f"test_session_t34_admin_{RUN}", f"test-user-t34-admin-{RUN}"
OTOK, OUID = f"test_session_t34_oper_{RUN}", f"test-user-t34-oper-{RUN}"
PIVA = "01234567890"  # cessionario of the passive XML fixture
TODAY = date.today()
ST = {}


def sess(tok=TOK):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    if ST.get("cid"):
        c = ST["cid"]
        mongo(f'["invoices","parties","counters","passive_invoices","passive_payments","f24_versamenti","journal","coge_entries","prima_nota"].forEach(k=>db[k].deleteMany({{company_id:"{c}"}})); db.companies.deleteOne({{id:"{c}"}});')
    mongo(f'db.users.deleteMany({{user_id:{{$in:["{UID}","{OUID}"]}}}}); db.user_sessions.deleteMany({{user_id:{{$in:["{UID}","{OUID}"]}}}});')


def user(uid, tok, role, cids):
    mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.{uid}@example.com", name:"TEST_T34 {role}", picture:"", role:"{role}", status:"approved", company_ids:{cids}, created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')


def inv(cid, data, iva, n):
    mongo(f'db.invoices.insertOne({{id:"{uuid.uuid4()}", company_id:"{cid}", status:"inviata", anno:{int(data[:4])}, data:"{data}", tipo_documento:"TD01", numero:{n}, sezionale:"", '
          f'numero_display:"{n}/{data[:4]}", split_payment:false, riepilogo:[{{aliquota:22, natura:null, imponibile:{iva / 0.22:.2f}, imposta:{iva}}}], totale:{iva / 0.22 + iva:.2f}, '
          f'cliente:{{denominazione:"TEST_Cli", partita_iva:"09876543210"}}}});')


def get():
    r = sess().get(f"{API}/scadenze-fiscali")
    assert r.status_code == 200, r.text
    return r.json()


def by_key(d):
    return {x["key"]: x for x in d["scadenze"]}


@pytest.fixture(scope="module", autouse=True)
def setup():
    assert TODAY.isoformat() == "2026-11-09", "Expected values are computed for 2026-11-09"
    existing = mongo(f'print(db.companies.countDocuments({{partita_iva:"{PIVA}"}}))')
    if existing != "0":
        pytest.skip("Another company already uses P.IVA 01234567890")
    user(UID, TOK, "admin", "[]")
    r = sess().post(f"{API}/companies", json={"denominazione": f"TEST_T34 Fisco {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                              "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT",
                                              "banche": [{"nome": "Banca T34", "iban": "IT60X0542811101000000123456", "abi": "05428", "cab": "11101", "predefinita": True}]})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    ST["company"] = r.json()
    user(OUID, OTOK, "operatore", f'["{ST["cid"]}"]')
    c = ST["cid"]
    inv(c, "2026-06-10", 300, 1)   # 6006 due 16/07 -> outside window (lo = 11/08)
    inv(c, "2026-07-10", 440, 2)   # 6007 due 17/08 (16/08 Sunday) -> scaduta
    inv(c, "2026-09-10", 220, 3)   # 6009 due 16/10 -> scaduta
    inv(c, "2026-10-10", 1100, 4)  # 6010 due 16/11 -> prossima (7 days)
    inv(c, "2026-11-05", 55, 5)    # 6011 due 16/12 -> prossima, provvisorio
    yield
    clean()


# ---- IVA mensile
class TestIvaMensile:
    def test_01_default_mensile_and_items(self):
        d = get()
        assert d["periodicita_iva"] == "mensile" and d["giorni_avviso"] == 5
        k = by_key(d)
        assert "IVA-2026-m-6" not in k, "June IVA (due 16/07) should be outside the 90-day window"
        oct_ = k["IVA-2026-m-10"]
        assert oct_["codice"] == "6010" and oct_["importo"] == 1100 and oct_["scadenza"] == "2026-11-16"
        assert oct_["giorni"] == 7 and oct_["stato"] == "prossima" and oct_["provvisorio"] is False and oct_["tipo"] == "iva"
        assert oct_["f24"] == {"anno": 2026, "periodicita": "mensile", "periodo": 10}
        jul = k["IVA-2026-m-7"]
        assert jul["scadenza"] == "2026-08-17" and jul["stato"] == "scaduta" and jul["codice"] == "6007"
        sep = k["IVA-2026-m-9"]
        assert sep["codice"] == "6009" and sep["importo"] == 220 and sep["stato"] == "scaduta" and sep["giorni"] == -24
        nov = k["IVA-2026-m-11"]
        assert nov["provvisorio"] is True and nov["scadenza"] == "2026-12-16" and nov["importo"] == 55
        assert [x["key"] for x in d["avvisi"]] == ["IVA-2026-m-7", "IVA-2026-m-9"]
        assert [x["scadenza"] for x in d["scadenze"]] == sorted(x["scadenza"] for x in d["scadenze"])
        assert all("_id" not in x for x in d["scadenze"])


# ---- Versato
class TestVersato:
    def test_02_bad_key_422_unknown_404(self):
        assert sess().post(f"{API}/scadenze-fiscali/versato", json={"key": "FOO"}).status_code == 422
        assert sess().post(f"{API}/scadenze-fiscali/versato", json={"key": "IVA-2026-m-6"}).status_code == 404
        assert sess().post(f"{API}/scadenze-fiscali/versato", json={"key": "IVA-2026-m-9", "data": "2026-13-45"}).status_code == 422
        assert sess().delete(f"{API}/scadenze-fiscali/versato/IVA-2026-m-9").status_code == 404

    def test_03_operatore_forbidden(self):
        o = sess(OTOK)
        assert o.get(f"{API}/scadenze-fiscali").status_code == 200
        assert o.post(f"{API}/scadenze-fiscali/versato", json={"key": "IVA-2026-m-10"}).status_code == 403
        assert o.delete(f"{API}/scadenze-fiscali/versato/IVA-2026-m-10").status_code == 403

    def test_04_versato_future_and_past(self):
        r = sess().post(f"{API}/scadenze-fiscali/versato", json={"key": "IVA-2026-m-10", "data": "2026-11-09"})
        assert r.status_code == 200 and r.json()["ok"] is True
        r = sess().post(f"{API}/scadenze-fiscali/versato", json={"key": "IVA-2026-m-9"})
        assert r.status_code == 200
        k = by_key(get())
        assert k["IVA-2026-m-10"]["stato"] == "versato" and k["IVA-2026-m-10"]["versato"]["data"] == "2026-11-09"
        assert k["IVA-2026-m-10"]["versato"]["importo"] == 1100
        assert "IVA-2026-m-9" not in k, "past paid items must be hidden"
        d = get()
        assert [x["key"] for x in d["avvisi"]] == ["IVA-2026-m-7"]

    def test_05_annulla(self):
        assert sess().delete(f"{API}/scadenze-fiscali/versato/IVA-2026-m-9").status_code == 200
        assert sess().delete(f"{API}/scadenze-fiscali/versato/IVA-2026-m-10").status_code == 200
        k = by_key(get())
        assert k["IVA-2026-m-9"]["stato"] == "scaduta" and k["IVA-2026-m-10"]["stato"] == "prossima" and k["IVA-2026-m-10"]["versato"] is None


# ---- Ritenute 1040
class TestRitenute:
    def test_06_upload_passive_and_pay(self):
        s = sess()
        r = s.post(f"{API}/passive/upload", files=[("files", ("rit.xml", variant(f"T34-{RUN}", ritenuta=94.25, data="2026-09-30"), "application/octet-stream"))])
        assert r.status_code == 200 and r.json()[0]["ok"], r.text
        pid = r.json()[0]["documenti"][0]["id"]
        ST["pid"] = pid
        d = s.get(f"{API}/passive/{pid}").json()
        assert d["ritenuta_importo"] == 94.25
        netto = d["netto"]
        ST["netto"] = netto
        half = round(netto / 2, 2)
        r = s.post(f"{API}/passive/{pid}/pagamenti", json={"data": "2026-10-20", "importo": half, "metodo": "bonifico"})
        assert r.status_code == 200, r.text
        r = s.post(f"{API}/passive/{pid}/pagamenti", json={"data": "2026-11-02", "importo": round(netto - half, 2), "metodo": "bonifico"})
        assert r.status_code == 200, r.text
        # a compensazione payment must be ignored
        mongo(f'db.passive_payments.insertOne({{id:"{uuid.uuid4()}", company_id:"{ST["cid"]}", invoice_id:"{pid}", importo:{half}, data:"2026-10-25", metodo:"compensazione"}})')

    def test_07_ritenute_items(self):
        k = by_key(get())
        half_q = round(94.25 * min(round(ST["netto"] / 2, 2) / ST["netto"], 1), 2)
        o = k["RIT-2026-10"]
        assert o["codice"] == "1040" and o["tipo"] == "ritenute" and o["scadenza"] == "2026-11-16" and o["stato"] == "prossima"
        assert o["importo"] == half_q, o
        assert len(o["dettaglio"]) == 1 and o["dettaglio"][0]["pagato_il"] == "2026-10-20"
        assert o["provvisorio"] is False and "ottobre 2026" in o["periodo_label"]
        n = k["RIT-2026-11"]
        assert n["scadenza"] == "2026-12-16" and n["provvisorio"] is True
        assert abs(o["importo"] + n["importo"] - 94.25) <= 0.01

    def test_08_f24_pdf_ritenute(self):
        r = sess().get(f"{API}/scadenze-fiscali/RIT-2026-10/f24")
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/pdf")
        assert "F24_ritenute_RIT-2026-10.pdf" in r.headers.get("content-disposition", "")
        txt = "".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
        assert "1040" in txt and PIVA in txt
        assert sess().get(f"{API}/scadenze-fiscali/IVA-2026-m-10/f24").status_code == 404
        assert sess().get(f"{API}/scadenze-fiscali/RIT-2020-01/f24").status_code == 404

    def test_09_versato_ritenute(self):
        assert sess().post(f"{API}/scadenze-fiscali/versato", json={"key": "RIT-2026-10"}).status_code == 200
        assert by_key(get())["RIT-2026-10"]["stato"] == "versato"
        assert sess().delete(f"{API}/scadenze-fiscali/versato/RIT-2026-10").status_code == 200

    def test_10_module_off_hides_ritenute(self):
        c = ST["cid"]
        mongo(f'db.companies.updateOne({{id:"{c}"}}, {{$set:{{"moduli.fatture_passive":false}}}})')
        try:
            k = by_key(get())
            assert not any(x.startswith("RIT-") for x in k) and "IVA-2026-m-10" in k
        finally:
            mongo(f'db.companies.updateOne({{id:"{c}"}}, {{$unset:{{"moduli.fatture_passive":""}}}})')

    def test_11_fatturazione_off_403(self):
        c = ST["cid"]
        mongo(f'db.companies.updateOne({{id:"{c}"}}, {{$set:{{"moduli.fatturazione":false}}}})')
        try:
            assert sess().get(f"{API}/scadenze-fiscali").status_code == 403
        finally:
            mongo(f'db.companies.updateOne({{id:"{c}"}}, {{$unset:{{"moduli.fatturazione":""}}}})')

    def test_12_no_auth_401(self):
        assert requests.get(f"{API}/scadenze-fiscali", headers={"X-Company-Id": ST["cid"]}).status_code == 401


# ---- Trimestrale via PUT /api/company
class TestTrimestrale:
    def test_13_put_company_trimestrale(self):
        s = sess()
        comp = s.get(f"{API}/company").json()
        comp["periodicita_iva"] = "trimestrale"
        r = s.put(f"{API}/company", json={k: v for k, v in comp.items() if k != "id"})
        assert r.status_code == 200, r.text
        assert r.json()["periodicita_iva"] == "trimestrale"
        assert s.get(f"{API}/company").json()["periodicita_iva"] == "trimestrale"
        bad = dict(comp, periodicita_iva="annuale")
        assert s.put(f"{API}/company", json={k: v for k, v in bad.items() if k != "id"}).status_code == 422

    def test_14_trimestrale_items(self):
        d = get()
        assert d["periodicita_iva"] == "trimestrale"
        k = by_key(d)
        assert not any(x.startswith("IVA-") and "-m-" in x for x in k)
        q3 = k["IVA-2026-t-3"]
        # Q3 = Jul 440 + Sep 220 = 660 + 1% interessi
        assert q3["codice"] == "6033" and q3["scadenza"] == "2026-11-16" and q3["importo"] == 666.6 and q3["stato"] == "prossima"
        q2 = k["IVA-2026-t-2"]
        assert q2["codice"] == "6032" and q2["scadenza"] == "2026-08-20" and q2["stato"] == "scaduta"
        assert "IVA-2026-t-4" not in k  # due 16/03/2027 outside +75 days
        assert "RIT-2026-10" in k  # ritenute independent of periodicita


# ---- Unit (in-process) with patched today -> in_scadenza within 5 days
class TestPatchedToday:
    def test_15_in_scadenza(self):
        import server

        class FakeDate(date):
            @classmethod
            def today(cls):
                return date(2026, 11, 12)

        async def run():
            comp = await server.db.companies.find_one({"id": ST["cid"]}, server.COMPANY_PROJ)
            t = {"cid": ST["cid"], "company": comp, "user": {"role": "admin", "email": "x"}}
            return await server._scadenze(t)

        orig = server.date
        server.date = FakeDate
        try:
            items = asyncio.run(run())
        finally:
            server.date = orig
        k = {x["key"]: x for x in items}
        assert k["IVA-2026-t-3"]["giorni"] == 4 and k["IVA-2026-t-3"]["stato"] == "in_scadenza"
        assert k["RIT-2026-10"]["stato"] == "in_scadenza"

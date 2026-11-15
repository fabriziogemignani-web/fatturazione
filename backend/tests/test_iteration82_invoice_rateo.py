# Iteration 82: rateo/risconto dates in the issued-invoice editor -> invoice.rateo stored (POST/PUT), 422 on inconsistent tipo,
# auto ratei_risconti record (origine vendita) on SDI consegnata / mancata_consegna, quota by days.
# Run: pytest tests/test_iteration82_invoice_rateo.py -v -n 0   (T82_KEEP=1 keeps data; `python tests/<file> clean`)
import json
import os
import random
import sys

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

RUN = os.environ.get("T82_RUN") or str(random.randint(100000, 999999))
TOK, UID = "test_session_t82_admin", "test-user-t82-admin"
PIVA = "82" + RUN + "821"
ST = {}
COLLS = ["invoices", "passive_invoices", "parties", "articles", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "partite_aperte", "ratei_risconti", "coa_chiusure", "counters"]
RR = {"competenza_dal": "2026-12-01", "competenza_al": "2027-05-31", "tipo": "risconto", "note": "TEST canone"}


def sess():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{denominazione:/^TEST_T82/}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:["{UID}","test-user-t82-op"]}}}}); db.user_sessions.deleteMany({{user_id:{{$in:["{UID}","test-user-t82-op"]}}}});')


def party(name, piva, **kw):
    r = sess().post(f"{API}/parties", json={"tipo": "cliente", "denominazione": name, "partita_iva": piva, "codice_fiscale": kw.pop("codice_fiscale", piva), "codice_destinatario": "ABC1234",
                                           "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT", **kw})
    assert r.status_code == 200, r.text
    return r.json()


def inv(pid, data="2026-11-15", price=1000, **kw):
    return {"tipo_documento": "TD01", "data": data, "party_id": pid, "modalita_pagamento": "MP05",
            "lines": [{"descrizione": "TEST canone semestrale", "quantita": 1, "prezzo_unitario": price, "aliquota": 22}], **kw}


def lista(anno):
    r = sess().get(f"{API}/contabilita/ratei", params={"anno": anno})
    assert r.status_code == 200, r.text
    return r.json()


def consegna(iid):
    r = sess().post(f"{API}/invoices/{iid}/send")
    assert r.status_code == 200, r.text
    r = sess().post(f"{API}/invoices/{iid}/refresh")
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t82.admin@example.com", name:"TEST_T82 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": f"TEST_T82 Fatture {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    sess().put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                            "corrispettivi": True, "contabilita": True})
    sess().get(f"{API}/contabilita/conti")
    ST["C"] = party("TEST_T82 Cliente Canoni", "02345670481", ratei_risconti=True)["id"]
    ST["CMC"] = party("TEST_T82 Cliente MC", "", ratei_risconti=True, codice_destinatario="0000000", codice_fiscale="RSSMRA80A01H501U")["id"]
    ST["N"] = party("TEST_T82 Cliente Normale", "09876543217")["id"]
    yield
    if os.environ.get("T82_KEEP"):
        print("\nKEEP", RUN, ST["cid"], ST)
    else:
        clean()


class TestSalvataggio:
    def test_01_create_with_rateo(self):
        r = sess().post(f"{API}/invoices", json=inv(ST["C"], rateo=RR))
        assert r.status_code == 200, r.text
        ST["I1"] = r.json()["id"]
        g = sess().get(f"{API}/invoices/{ST['I1']}").json()
        assert g["rateo"] == RR
        assert [x for x in lista(2026) if x["doc_id"] == ST["I1"]] == []  # not yet in archive while draft

    def test_02_update_rateo_and_clear(self):
        b = inv(ST["C"], rateo=RR | {"competenza_al": "2027-04-30", "note": "x"})
        r = sess().put(f"{API}/invoices/{ST['I1']}", json=b)
        assert r.status_code == 200, r.text
        assert sess().get(f"{API}/invoices/{ST['I1']}").json()["rateo"]["competenza_al"] == "2027-04-30"
        r = sess().put(f"{API}/invoices/{ST['I1']}", json=inv(ST["C"], rateo=None))
        assert r.status_code == 200, r.text
        assert sess().get(f"{API}/invoices/{ST['I1']}").json()["rateo"] is None
        r = sess().put(f"{API}/invoices/{ST['I1']}", json=inv(ST["C"], rateo=RR))
        assert r.status_code == 200 and sess().get(f"{API}/invoices/{ST['I1']}").json()["rateo"] == RR

    @pytest.mark.parametrize("rr", [RR | {"tipo": "rateo"}, RR | {"competenza_dal": "2026-03-01", "competenza_al": "2026-10-31"},
                                    RR | {"competenza_al": "2026-11-01"}, RR | {"competenza_dal": "2026-13-01"}])
    def test_03_invalid_422(self, rr):
        r = sess().post(f"{API}/invoices", json=inv(ST["C"], rateo=rr))
        assert r.status_code == 422, r.text
        r = sess().put(f"{API}/invoices/{ST['I1']}", json=inv(ST["C"], rateo=rr))
        assert r.status_code == 422, r.text

    def test_04_tipo_message(self):
        r = sess().post(f"{API}/invoices", json=inv(ST["C"], rateo=RR | {"tipo": "rateo"}))
        assert "risconto" in r.text, r.text

    def test_05_no_flag_client(self):
        r = sess().post(f"{API}/invoices", json=inv(ST["N"]))
        assert r.status_code == 200 and r.json().get("rateo") is None
        ST["I_N"] = r.json()["id"]
        # observational: backend accepts rateo also for a client without the flag?
        r2 = sess().post(f"{API}/invoices", json=inv(ST["N"], rateo=RR))
        print("NOFLAG_WITH_RATEO", r2.status_code, (r2.json() or {}).get("rateo") if r2.status_code == 200 else r2.text)
        if r2.status_code == 200:
            ST["I_N2"] = r2.json()["id"]


class TestConsegna:
    def test_06_consegnata_creates_risconto(self):
        d = consegna(ST["I1"])
        assert d["status"] == "consegnata", d.get("sdi_message")
        rows = [x for x in lista(2026) if x["doc_id"] == ST["I1"]]
        assert len(rows) == 1, rows
        x = rows[0]
        ST["R1"] = x["id"]
        assert x["origine"] == "vendita" and x["tipo"] == "risconto" and x["nome_tipo"] == "Risconto passivo"
        assert x["importo"] == 1000 and len(x["righe"]) == 1 and x["righe"][0]["conto"]
        assert x["quota"]["giorni"] == 151 and x["quota"]["giorni_totali"] == 182
        assert x["quota"]["importo"] == round(1000 * 151 / 182, 2)
        assert x["stato"] == "da_contabilizzare" and x["anni"] == [2026]
        assert x["competenza_dal"] == RR["competenza_dal"] and x["note"] == RR["note"]
        assert x["party_id"] == ST["C"] and x["data_documento"] == "2026-11-15"
        e = json.loads(mongo(f'print(JSON.stringify(db.coa_entries.find({{company_id:"{ST["cid"]}", origine:"vendita", ref_id:"{ST["I1"]}"}},{{_id:0}}).toArray()))') or "[]")
        assert len(e) == 1 and x["data_registrazione"] == e[0]["data"]

    def test_07_locked_put_rejected(self):
        r = sess().put(f"{API}/invoices/{ST['I1']}", json=inv(ST["C"], rateo=None))
        assert r.status_code == 400

    def test_08_mancata_consegna(self):
        r = sess().post(f"{API}/invoices", json=inv(ST["CMC"], price=600, rateo={"competenza_dal": "2026-07-01", "competenza_al": "2027-06-30", "tipo": "risconto"}))
        assert r.status_code == 200, r.text
        ST["I2"] = r.json()["id"]
        d = consegna(ST["I2"])
        assert d["status"] == "mancata_consegna", d.get("sdi_message")
        x = [v for v in lista(2026) if v["doc_id"] == ST["I2"]]
        assert len(x) == 1 and x[0]["importo"] == 600
        assert x[0]["quota"]["giorni"] == 181 and x[0]["quota"]["giorni_totali"] == 365
        assert x[0]["quota"]["importo"] == round(600 * 181 / 365, 2)

    def test_09_no_rateo_no_record(self):
        d = consegna(ST["I_N"])
        assert d["status"] == "consegnata"
        assert [v for v in lista(2026) if v["doc_id"] == ST["I_N"]] == []

    def test_10_contabilizza_simulazione(self):
        r = sess().post(f"{API}/contabilita/ratei/contabilizza", json={"anno": 2026, "definitiva": False, "ids": [ST["R1"]]})
        assert r.status_code == 200 and r.json()["contabilizzati"] == 1, r.text
        assert [v for v in lista(2026) if v["id"] == ST["R1"]][0]["stato"] == "simulata"


if __name__ == "__main__" and sys.argv[-1] == "clean":
    clean()

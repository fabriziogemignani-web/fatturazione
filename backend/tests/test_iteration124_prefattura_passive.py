# Iteration 124: scadenzario passivo "prefattura" - unregistered passive invoices flagged da_registrare, payable with contabilita active
# (prefattura=true, prima nota Dare fornitori/Avere banca), XML rate kept, registration afterwards still works.
# Run: pytest tests/test_iteration124_prefattura_passive.py -v -n 0   (T124_KEEP=1 keeps data for UI testing)
import json
import os
import random
import sys
from datetime import date, timedelta

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo, party, inv  # noqa: E402
import test_iteration89_rigenera_passive as t89  # noqa: E402

RUN = str(random.randint(100000, 999999))
TOK, UID = "test_session_t124_admin", "test-user-t124-admin"
PIVA = "14" + RUN + "141"
ST = {}
COLLS = ["invoices", "passive_invoices", "parties", "articles", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "partite_aperte", "counters", "bank_tx", "bank_accounts", "ratei_risconti", "iva_registri"]
T = date.today()
D = lambda n: (T - timedelta(days=n)).isoformat()  # noqa: E731
F = lambda n: (T + timedelta(days=n)).isoformat()  # noqa: E731
IBAN1 = "IT60X0542811101000000123456"
IBAN2 = "IT42L1234512345123456789012"


def sess(cid=None):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {TOK}", "X-Requested-With": "invoix"})
    c = cid if cid is not None else ST.get("cid")
    if c:
        s.headers["X-Company-Id"] = c
    return s


def clean():
    mongo(f'db.companies.find({{denominazione:/^TEST_T124/}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def mk_company(name, piva, contab):
    r = sess("").post(f"{API}/companies", json={"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01",
                                               "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    s = sess(cid)
    s.put(f"{API}/companies/{cid}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                 "corrispettivi": True, "contabilita": contab})
    c = s.get(f"{API}/company").json()
    c["banche"] = [{"nome": "TEST_Banca Uno", "iban": IBAN1, "predefinita": True},
                   {"nome": "TEST_Banca Due", "iban": IBAN2, "predefinita": False}]
    assert s.put(f"{API}/company", json=c).status_code == 200
    return cid


def pxml(num, data, ced, imp=1000.0, rate=None):
    x = t89.xml(num, data, ced, imp).replace(t89.PIVA.encode(), PIVA.encode()).replace(b"TEST_T89", b"TEST_T124")
    if rate:
        dp = "<DatiPagamento><CondizioniPagamento>TP01</CondizioniPagamento>" + "".join(
            f"<DettaglioPagamento><ModalitaPagamento>MP05</ModalitaPagamento><DataScadenzaPagamento>{s}</DataScadenzaPagamento>"
            f"<ImportoPagamento>{v:.2f}</ImportoPagamento></DettaglioPagamento>" for s, v in rate) + "</DatiPagamento>"
        x = x.replace(b"</FatturaElettronicaBody>", dp.encode() + b"</FatturaElettronicaBody>")
    return x


def upload(x):
    r = sess().post(f"{API}/passive/upload", files=[("files", (f"t124_{RUN}_{random.randint(1, 10**6)}.xml", x, "application/octet-stream"))])
    assert r.status_code == 200, r.text
    j = r.json()[0]
    assert j["ok"], j
    return j["documenti"][0]["id"]


def scad_rows(pid, cid=None):
    r = sess(cid).get(f"{API}/scadenzario-passivo")
    assert r.status_code == 200, r.text
    return sorted([x for x in r.json()["rate"] if x["invoice_id"] == pid], key=lambda x: x["n"])


def entry(rid):
    out = mongo(f'print(JSON.stringify(db.coa_entries.findOne({{id:"{rid}"}}, {{_id:0}})))')
    return json.loads(out) if out and out != "null" else None


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t124.admin@example.com", name:"TEST_T124 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    ST["cid"] = mk_company("TEST_T124 Contab Srl", PIVA, True)
    sess().get(f"{API}/contabilita/conti")
    yield
    if os.environ.get("T124_KEEP"):
        json.dump({**ST, "tok": TOK}, open("/tmp/t124.json", "w"))
        print("\nKEEP", ST)
    else:
        clean()


class TestPrefattura:
    # scadenzario flag
    def test_01_flags(self):
        ST["A"] = upload(pxml(f"T124A{RUN}", D(30), "01111111111"))  # no rate -> single rata full netto
        ST["B"] = upload(pxml(f"T124B{RUN}", D(30), "01111111111", rate=[(F(10), 610.0), (F(40), 610.0)]))
        ST["R"] = upload(pxml(f"T124R{RUN}", D(30), "01111111111"))
        r = sess().patch(f"{API}/passive/{ST['R']}", json={"stato_reg": "registrata", "data_registrazione": D(10)})
        assert r.status_code == 200, r.text
        a, b, rr = scad_rows(ST["A"]), scad_rows(ST["B"]), scad_rows(ST["R"])
        assert len(a) == 1 and a[0]["da_registrare"] is True and a[0]["importo"] == 1220.0, a
        assert len(b) == 2 and all(x["da_registrare"] for x in b) and [x["importo"] for x in b] == [610.0, 610.0], b
        assert [x["scadenza"] for x in b] == [F(10), F(40)]
        assert rr and all(x["da_registrare"] is False for x in rr), rr

    # pay unregistered invoice with contabilita active
    def test_02_pay_unregistered_requires_bank(self):
        r = sess().post(f"{API}/passive/{ST['A']}/pagamenti", json={"data": D(5), "importo": 500, "metodo": "bonifico"})
        assert r.status_code == 400 and "banca_iban" in r.text, r.text

    def test_03_pay_unregistered_ok(self):
        r = sess().post(f"{API}/passive/{ST['A']}/pagamenti", json={"data": D(29), "importo": 500, "metodo": "bonifico", "banca_iban": IBAN2})
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["prefattura"] is True and p["banca_iban"] == IBAN2, p
        assert p.get("coge_entry_id"), p
        ST["PA"] = p
        e = entry(p["coge_entry_id"])
        assert e, "prima nota entry missing"
        print("entry", e["righe"], e.get("causale"))
        dare = [x for x in e["righe"] if x.get("dare")]
        avere = [x for x in e["righe"] if x.get("avere")]
        assert len(dare) == 1 and dare[0]["dare"] == 500 and dare[0].get("party_id"), e["righe"]
        assert len(avere) == 1 and avere[0]["avere"] == 500 and avere[0]["conto"] == p["conto"], e["righe"]
        rows = scad_rows(ST["A"])
        assert rows[0]["residuo"] == 720.0 and rows[0]["da_registrare"] is True, rows
        g = sess().get(f"{API}/passive/{ST['A']}/pagamenti").json()
        assert any(x["id"] == p["id"] and x["prefattura"] for x in g["pagamenti"])

    def test_04_pay_unregistered_validations(self):
        r = sess().post(f"{API}/passive/{ST['A']}/pagamenti", json={"data": D(5), "importo": 721, "metodo": "contanti"})
        assert r.status_code == 400 and "residuo" in r.text, r.text
        r = sess().post(f"{API}/passive/{ST['A']}/pagamenti", json={"data": D(31), "importo": 10, "metodo": "contanti"})
        assert r.status_code == 400 and "data della fattura" in r.text, r.text

    def test_05_pay_rate_invoice_first_rata(self):
        r = sess().post(f"{API}/passive/{ST['B']}/pagamenti", json={"data": D(2), "importo": 610, "metodo": "bonifico", "banca_iban": IBAN1})
        assert r.status_code == 200 and r.json()["prefattura"] is True, r.text
        b = scad_rows(ST["B"])
        assert b[0]["stato"] == "pagata" and b[1]["residuo"] == 610.0, b

    # registration afterwards
    def test_06_register_after_prepayment(self):
        d = sess().get(f"{API}/passive/{ST['A']}").json()
        body = {"data_registrazione": D(3), "numero": d["numero"], "data": d["data"],
                "riepilogo": [{"aliquota": x["aliquota"], "natura": x.get("natura"), "imponibile": x["imponibile"], "imposta": x["imposta"]} for x in d["riepilogo"]]}
        pv = sess().post(f"{API}/passive/{ST['A']}/registrazione/anteprima", json=body)
        assert pv.status_code == 200, pv.text
        r = sess().post(f"{API}/passive/{ST['A']}/registrazione", json=body)
        assert r.status_code == 200, r.text
        assert r.json()["stato_reg"] == "registrata"
        rows = scad_rows(ST["A"])
        assert rows[0]["da_registrare"] is False and rows[0]["residuo"] == 720.0, rows
        # prefattura payment still present and its entry intact
        assert entry(ST["PA"]["coge_entry_id"])
        part = sess().get(f"{API}/contabilita/saldaconto/partite", params={"party_id": d["party_id"], "tipo": "fornitore"}).json()
        pa = next(x for x in part["aperte"] if x["invoice_id"] == ST["A"])
        assert pa["pagato"] == 500.0 and pa["residuo"] == 720.0, pa

    def test_07_registered_enforces_data_registrazione(self):
        r = sess().post(f"{API}/passive/{ST['A']}/pagamenti", json={"data": D(10), "importo": 10, "metodo": "contanti"})
        assert r.status_code == 400 and "registrazione" in r.text, r.text
        r = sess().post(f"{API}/passive/{ST['A']}/pagamenti", json={"data": D(1), "importo": 720, "metodo": "bonifico", "banca_iban": IBAN1})
        assert r.status_code == 200 and r.json()["prefattura"] is False, r.text
        rows = scad_rows(ST["A"])
        assert rows[0]["residuo"] == 0 and rows[0]["stato"] == "pagata", rows

    def test_08_delete_prefattura_payment(self):
        r = sess().post(f"{API}/passive/{ST['B']}/pagamenti", json={"data": D(2), "importo": 100, "metodo": "contanti"})
        assert r.status_code == 200, r.text
        p = r.json()
        d = sess().delete(f"{API}/passive-pagamenti/{p['id']}")
        assert d.status_code == 200, d.text
        assert entry(p["coge_entry_id"]) is None if p.get("coge_entry_id") else True
        assert scad_rows(ST["B"])[1]["residuo"] == 610.0

    # regression: clienti scadenzario
    def test_09_scadenzario_clienti(self):
        s = sess()
        pid = s.post(f"{API}/parties", json=party("TEST_T124 Cliente", piva="01234567892", cf="01234567892")).json()["id"]
        r = s.post(f"{API}/invoices", json=inv(pid, data=D(20), price=1000))
        assert r.status_code == 200, r.text
        iid = r.json()["id"]
        assert s.post(f"{API}/invoices/{iid}/send").status_code == 200
        s.post(f"{API}/invoices/{iid}/refresh")
        ST["I"] = iid
        j = s.get(f"{API}/scadenzario")
        assert j.status_code == 200, j.text
        rows = [x for x in j.json()["rate"] if x["invoice_id"] == iid]
        assert rows and all(x.get("da_registrare") is False for x in rows), rows
        r = s.post(f"{API}/invoices/{iid}/pagamenti", json={"data": D(3), "importo": 100, "metodo": "contanti"})
        assert r.status_code == 200, r.text

    def test_10_keep_ui_fixture(self):
        # fresh unregistered invoice for UI test
        ST["U"] = upload(pxml(f"T124U{RUN}", D(15), "01111111111", imp=500))
        assert scad_rows(ST["U"])[0]["da_registrare"] is True

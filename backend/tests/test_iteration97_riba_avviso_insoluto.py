# Iteration 97: Ri.Ba. avviso insoluto al cliente (email with importo, spese addebitate, nuova scadenza).
# POST /riba/insoluti avvisa=true, GET /riba/insoluti-registrati, POST /riba/effetti/{eid}/avviso.
# Needs the SMTP sink: python3 tests/t97_smtp_sink.py &   then: pytest tests/test_iteration97_riba_avviso_insoluto.py -v -n 0
import glob
import json
import os
import random
import sys
import time
from datetime import date, timedelta
from email import message_from_bytes, policy

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

RUN = str(random.randint(100000, 999999))
TOK, UID = f"test_session_t97_{RUN}", f"test-user-t97-{RUN}"
PIVA = "97" + RUN + "971"
IBAN = "IT60X0542811101000000123456"
T = date.today()
d = lambda n: (T + timedelta(days=n)).isoformat()  # noqa: E731
itd = lambda s: "/".join(reversed(s.split("-")))  # noqa: E731
ST = {}
COLLS = ["invoices", "passive_invoices", "parties", "articles", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "riba_distinte", "riba_effetti", "partite_aperte", "solleciti"]
NAME = f"TEST_T97 Riba {RUN} Srl"
MAILDIR = "/tmp/t97_mail"


def sess():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{denominazione:"{NAME}"}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def client(name, piva, flag, email="", pec=""):
    r = sess().post(f"{API}/parties", json={"tipo": "cliente", "denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "codice_destinatario": "ABC1234",
                                           "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT", "email": email, "pec": pec,
                                           "appoggio_banca": "TEST Intesa", "appoggio_abi": "03069", "appoggio_cab": "09606", "riba_spese_addebito": flag})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def inv(pid, data, rate):
    s = sess()
    r = s.post(f"{API}/invoices", json={"tipo_documento": "TD01", "data": data, "party_id": pid, "modalita_pagamento": "MP12", "scadenza": rate[-1][0],
                                        "rate": [{"scadenza": a, "importo": b} for a, b in rate],
                                        "lines": [{"descrizione": "TEST_riga", "quantita": 1, "prezzo_unitario": 100, "aliquota": 22}]})
    assert r.status_code == 200, r.text
    iid = r.json()["id"]
    assert s.post(f"{API}/invoices/{iid}/send").status_code == 200
    assert s.post(f"{API}/invoices/{iid}/refresh").status_code == 200
    return iid


def mails_since(ts):
    out = []
    for f in sorted(glob.glob(f"{MAILDIR}/*.eml")):
        if float(os.path.basename(f)[:-4]) >= ts:
            m = message_from_bytes(open(f, "rb").read(), policy=policy.default)
            html = next((p.get_content() for p in m.walk() if p.get_content_type() == "text/html"), "")
            out.append({"to": m["To"], "subject": str(m["Subject"]), "html": html, "reply_to": m["Reply-To"]})
    return out


def effetto(eid):
    return next(x for x in sess().get(f"{API}/riba/distinte/{ST['D']}").json()["effetti"] if x["id"] == eid)


BANKS = [{"nome": "TEST Banca Uno", "iban": IBAN, "abi": "05428", "cab": "11101", "sia": "A1B2C", "predefinita": True, "spese_emissione": 0, "spese_insoluto": 7}]


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t97.{RUN}@example.com", name:"TEST_T97 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": NAME, "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    s = sess()
    s.put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                      "corrispettivi": True, "contabilita": True})
    c = s.get(f"{API}/company").json()
    c["banche"], c["iban"] = BANKS, IBAN
    r = s.put(f"{API}/company", json=c)
    assert r.status_code == 200, r.text
    ST["A"] = client("TEST_T97 Cliente A Srl", "01234567890", True, email="test.a.t97@example.com")
    ST["B"] = client("TEST_T97 Cliente B Srl", "09876543217", False, pec="test.b.t97@pec.example.com")
    ST["C"] = client("TEST_T97 Cliente C Srl", "12345678903", True)
    ST["Q"] = inv(ST["A"], d(-60), [(d(-30), 122)])
    ST["R"] = inv(ST["B"], d(-45), [(d(-15), 122)])
    ST["S"] = inv(ST["C"], d(-45), [(d(-12), 122)])
    ST["U"] = inv(ST["A"], d(-45), [(d(-11), 122)])
    ST["V"] = inv(ST["A"], d(-45), [(d(-10), 122)])
    ST["F"] = inv(ST["A"], d(-45), [(d(30), 122)])
    keys = [f"{ST[k]}:1" for k in ("Q", "R", "S", "U", "V", "F")]
    r = s.post(f"{API}/riba/distinte", json={"banca_iban": IBAN, "data": d(-40), "effetti": keys})
    assert r.status_code == 200, r.text
    ST["D"] = r.json()["id"]
    ST["E"] = {e["invoice_id"]: e["id"] for e in s.get(f"{API}/riba/distinte/{ST['D']}").json()["effetti"]}
    yield
    if os.environ.get("T97_KEEP"):
        print("\nKEEP", RUN, ST["cid"], TOK)
    else:
        clean()


class TestAvvisoInsoluti:
    def test_01_no_smtp_insoluto_still_registered(self):
        eid = ST["E"][ST["U"]]
        r = sess().post(f"{API}/riba/insoluti", json={"effetti": [eid], "data": d(-5), "giorni": 30, "avvisa": True})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["registrati"] == 1 and j["avvisi"] == 0, j
        assert len(j["errori"]) == 1 and j["errori"][0]["errore"].startswith("Avvisi email non inviati: "), j
        assert "SMTP" in j["errori"][0]["errore"], j
        e = effetto(eid)
        assert e["stato"] == "insoluto" and not e.get("avviso"), e

    def test_02_configure_smtp(self):
        r = sess().put(f"{API}/company/smtp", json={"host": "127.0.0.1", "port": 1025, "security": "none", "username": "",
                                                   "from_email": "test.t97@example.com", "from_name": "TEST T97"})
        assert r.status_code == 200, r.text

    def test_03_blocco_avvisa(self):
        ts = time.time()
        ids = [ST["E"][ST[k]] for k in ("Q", "R", "S")]
        r = sess().post(f"{API}/riba/insoluti", json={"effetti": ids, "data": d(-5), "giorni": 30, "avvisa": True})
        assert r.status_code == 200, r.text
        j = r.json()
        print(j)
        assert j["registrati"] == 3 and j["avvisi"] == 2 and j["nuova_scadenza"] == d(25), j
        assert len(j["errori"]) == 1 and j["errori"][0]["id"] == ids[2], j
        assert j["errori"][0]["errore"].startswith("Insoluto registrato, avviso non inviato: ") and "email" in j["errori"][0]["errore"].lower(), j
        time.sleep(1)
        ST["mails"] = {m["to"]: m for m in mails_since(ts)}
        assert set(ST["mails"]) == {"test.a.t97@example.com", "test.b.t97@pec.example.com"}, list(ST["mails"])

    def test_04_avviso_field(self):
        a = effetto(ST["E"][ST["Q"]])["avviso"]
        assert a["to"] == "test.a.t97@example.com" and a["totale"] == 129 and a["email_id"] and a["inviato_il"] and a["inviato_da"] == "TEST_T97 admin", a
        b = effetto(ST["E"][ST["R"]])["avviso"]
        assert b["to"] == "test.b.t97@pec.example.com" and b["totale"] == 122, b
        assert not effetto(ST["E"][ST["S"]]).get("avviso")

    def test_05_email_content_with_spese(self):
        m = ST["mails"]["test.a.t97@example.com"]
        num = effetto(ST["E"][ST["Q"]])["numero_display"]
        assert m["subject"] == f"Avviso di insoluto - fattura {num} - {NAME}", m["subject"]
        h = m["html"]
        for s in (num, itd(d(-30)), itd(d(-5)), "Importo effetto insoluto", "122,00 €", "Spese di insoluto addebitate", "7,00 €",
                  "Totale da pagare", "129,00 €", "Nuova scadenza", itd(d(25)), IBAN):
            assert s in h, (s, h)

    def test_06_email_content_no_spese(self):
        h = ST["mails"]["test.b.t97@pec.example.com"]["html"]
        assert "Spese di insoluto addebitate" not in h, h
        assert "Totale da pagare" in h and "122,00 €" in h and itd(d(25)) in h

    def test_07_avvisa_false_default(self):
        eid = ST["E"][ST["V"]]
        ts = time.time()
        r = sess().post(f"{API}/riba/insoluti", json={"effetti": [eid], "data": d(-5)})
        assert r.status_code == 200 and r.json()["registrati"] == 1 and r.json()["avvisi"] == 0 and not r.json()["errori"], r.text
        time.sleep(0.5)
        assert not mails_since(ts) and not effetto(eid).get("avviso")

    def test_08_insoluti_registrati(self):
        r = sess().get(f"{API}/riba/insoluti-registrati")
        assert r.status_code == 200, r.text
        ids = {x["id"] for x in r.json()}
        assert ids == {ST["E"][ST[k]] for k in ("Q", "R", "S", "U", "V")}, ids
        assert all(x["stato"] == "insoluto" and "_id" not in x for x in r.json())

    def test_09_resend(self):
        eid = ST["E"][ST["Q"]]
        old = effetto(eid)["avviso"]
        ts = time.time()
        r = sess().post(f"{API}/riba/effetti/{eid}/avviso")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["to"] == "test.a.t97@example.com" and j["totale"] == 129 and j["inviato_il"] > old["inviato_il"] and j["email_id"] != old["email_id"], (old, j)
        time.sleep(0.5)
        assert len(mails_since(ts)) == 1
        assert effetto(eid)["avviso"]["email_id"] == j["email_id"]

    def test_10_send_after_no_smtp(self):
        eid = ST["E"][ST["U"]]
        r = sess().post(f"{API}/riba/effetti/{eid}/avviso")
        assert r.status_code == 200, r.text
        assert effetto(eid)["avviso"]["to"] == "test.a.t97@example.com"

    def test_11_errors(self):
        s = sess()
        r = s.post(f"{API}/riba/effetti/{ST['E'][ST['S']]}/avviso")
        assert r.status_code == 400 and "email" in r.text.lower(), r.text
        r = s.post(f"{API}/riba/effetti/{ST['E'][ST['F']]}/avviso")
        assert r.status_code == 400 and "insoluto" in r.text.lower(), r.text
        r = s.post(f"{API}/riba/effetti/nonexistent-{RUN}/avviso")
        assert r.status_code == 404, r.text

    def test_12_unauth(self):
        r = requests.post(f"{API}/riba/effetti/{ST['E'][ST['Q']]}/avviso")
        assert r.status_code == 401, r.status_code

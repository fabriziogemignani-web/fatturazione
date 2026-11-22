# Iteration 117: GET /api/dashboard iva_liquidazione {importo, periodo, debito, credito, credito_precedente} for the current
# liquidation period (mensile / trimestrale), same numbers as GET /api/liquidazione-iva. positive = da versare, negative = credito.
# Run: pytest tests/test_iteration117_dashboard_iva_liq.py -v -n 0 -s   (T117_KEEP=1 keeps data for UI tests)
import json
import os
import random
import sys
from datetime import date

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

RUN = os.environ.get("T117_RUN", str(random.randint(100000, 999999)))
TOK, UID = f"test_session_t117_admin_{RUN}", f"test-user-t117-admin-{RUN}"
PIVA = "17" + RUN + "117"
ST = {}
TODAY = date.today()
Y = TODAY.year
NOW = TODAY.isoformat()
Q = (TODAY.month - 1) // 3 + 1
MESI = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
# another month of the same quarter (before today if possible)
OTHER_M = TODAY.month - 1 if TODAY.month % 3 != 1 else TODAY.month + 1
OTHER = f"{Y}-{OTHER_M:02d}-05"
COLLS = ["invoices", "passive_invoices", "parties", "articles", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "audit_log", "partite_aperte", "f24_versamenti", "pag_distinte", "ratei_risconti", "counters", "corrispettivi"]


def sess():
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {TOK}", "X-Requested-With": "invoix"})
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{partita_iva:"{PIVA}"}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def party(tipo, name):
    pi = "".join(str(random.randint(0, 9)) for _ in range(11))
    r = sess().post(f"{API}/parties", json={"tipo": tipo, "denominazione": name, "partita_iva": pi, "codice_fiscale": pi, "indirizzo": "Via Verdi 1",
                                            "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT", "codice_destinatario": "0000000"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def rv(tipo, pid, data, righe):
    r = sess().post(f"{API}/reg-veloce", json={"tipo": tipo, "party_id": pid, "numero": f"T117-{random.randint(1000, 9999)}", "data_documento": data,
                                               "data_registrazione": data, "scadenza": f"{Y}-12-31", "righe": righe})
    assert r.status_code == 200, r.text
    return r.json()


def set_per(per):
    c = sess().get(f"{API}/company").json()
    c["periodicita_iva"] = per
    r = sess().put(f"{API}/company", json=c)
    assert r.status_code == 200, r.text
    assert sess().get(f"{API}/company").json()["periodicita_iva"] == per


def dash():
    r = sess().get(f"{API}/dashboard")
    assert r.status_code == 200, r.text
    return r.json()["iva_liquidazione"]


def liq_period(per):
    r = sess().get(f"{API}/liquidazione-iva", params={"anno": Y, "periodicita": per})
    assert r.status_code == 200, r.text
    k = TODAY.month if per == "mensile" else Q
    return next(p for p in r.json()["periodi"] if p["periodo"] == k)


def consistent(iv, per):
    p = liq_period(per)
    print(per, "dash:", iv, "liq:", {k: p[k] for k in ("iva_debito", "iva_credito", "credito_precedente", "saldo", "da_versare", "credito_riporto")})
    assert iv["debito"] == p["iva_debito"] and iv["credito"] == p["iva_credito"] and iv["credito_precedente"] == p["credito_precedente"]
    if iv["importo"] > 0 and not p["sotto_soglia"]:
        assert iv["importo"] == p["da_versare"]
    if iv["importo"] < 0:
        assert -iv["importo"] == p["credito_riporto"]


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t117.admin.{RUN}@example.com", name:"TEST_T117 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": "TEST_T117 Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    assert sess().put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                                   "corrispettivi": True, "contabilita": True}).status_code == 200
    sess().get(f"{API}/contabilita/conti")
    ST["cli"] = party("cliente", "TEST_T117 Cliente")
    ST["for"] = party("fornitore", "TEST_T117 Fornitore")
    yield
    if os.environ.get("T117_KEEP"):
        print("\nKEEP", RUN, ST["cid"], TOK)
    else:
        clean()


class TestDashboardIva:
    def test_01_empty_company(self):
        iv = dash()
        print("empty:", iv)
        assert iv is not None and iv["importo"] == 0 and iv["periodo"] == f"{MESI[TODAY.month - 1]} {Y}"
        assert set(iv) >= {"importo", "periodo", "debito", "credito", "credito_precedente"}

    def test_02_sale_220_da_versare(self):
        d = rv("vendita", ST["cli"], NOW, [{"aliquota": 22, "totale": 1220}])
        assert d["iva"] == 220
        iv = dash()
        assert iv["importo"] == 220 and iv["debito"] == 220 and iv["credito"] == 0
        consistent(iv, "mensile")

    def test_03_purchase_500_credito(self):
        rv("acquisto", ST["for"], NOW, [{"aliquota": 22, "totale": 2440}, {"aliquota": 10, "totale": 660}])
        iv = dash()
        assert iv["importo"] == -280 and iv["debito"] == 220 and iv["credito"] == 500
        consistent(iv, "mensile")

    def test_04_trimestrale(self):
        set_per("trimestrale")
        iv = dash()
        assert iv["periodo"] == f"{Q}° trimestre {Y}" and iv["importo"] == -280
        consistent(iv, "trimestrale")

    def test_05_trimestrale_other_month_sale(self):
        # sale IVA 330 in another month of the same quarter: quarter = 550 - 500 = +50 (+1% interest if not Q4)
        rv("vendita", ST["cli"], OTHER, [{"aliquota": 22, "totale": 1830}])
        iv = dash()
        exp = 50.0 if Q == 4 else 50.5
        assert iv["debito"] == 550 and iv["credito"] == 500 and iv["importo"] == exp, iv
        consistent(iv, "trimestrale")

    def test_06_back_to_mensile(self):
        set_per("mensile")
        iv = dash()
        assert iv["periodo"] == f"{MESI[TODAY.month - 1]} {Y}"
        consistent(iv, "mensile")
        # previous month in debit -> current month unaffected (credit 280); next month case -> still -280 now
        assert iv["importo"] == -280

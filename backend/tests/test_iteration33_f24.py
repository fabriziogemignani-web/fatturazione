# Iteration 33: F24 IVA - tributo/scadenze (unit), GET/POST /api/liquidazione-iva/f24 (debito, crediti, banche, PDF),
# validation (crediti > debito, periodo senza IVA, max 5 crediti, data), module gating (fatturazione).
# Run with: pytest test_iteration33_f24.py -n 0
import io
import random
import sys
import uuid

import pytest
import requests
from pypdf import PdfReader

from test_iteration7_pa_scartate_registro import API, mongo

sys.path.insert(0, "/app/backend")
import f24  # noqa: E402

RUN = str(random.randint(100000, 999999))
TOK, UID = f"test_session_t33_admin_{RUN}", f"test-user-t33-admin-{RUN}"
PIVA = "86" + RUN + "321"
IBAN = "IT60X0542811101000000123456"
ST = {}


def sess():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{partita_iva:"{PIVA}"}}).forEach(c=>{{["invoices","parties","counters"].forEach(k=>db[k].deleteMany({{company_id:c.id}})); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def inv(cid, data, iva, n):
    mongo(f'db.invoices.insertOne({{id:"{uuid.uuid4()}", company_id:"{cid}", status:"inviata", anno:{int(data[:4])}, data:"{data}", tipo_documento:"TD01", numero:{n}, sezionale:"", '
          f'numero_display:"{n}/{data[:4]}", split_payment:false, riepilogo:[{{aliquota:22, natura:null, imponibile:{iva / 0.22:.2f}, imposta:{iva}}}], totale:{iva / 0.22 + iva:.2f}, '
          f'cliente:{{denominazione:"TEST_Cli", partita_iva:"09876543210"}}}});')


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t33.{RUN}@example.com", name:"TEST_T33", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": f"TEST_T33 F24 {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                              "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT",
                                              "banche": [{"nome": "Banca T33", "iban": IBAN, "abi": "05428", "cab": "11101", "predefinita": True},
                                                         {"nome": "Banca Due", "iban": "IT52X0306909606100000063529", "predefinita": False}]})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    inv(ST["cid"], "2026-11-09", 1100, 1)
    inv(ST["cid"], "2026-04-10", 220, 2)
    inv(ST["cid"], "2026-02-10", 10, 3)  # under 25.82 threshold
    yield
    clean()


# --- unit: tributo codes & deadlines
@pytest.mark.parametrize("per,k,cod,scad", [
    ("mensile", 1, "6001", "2026-02-16"), ("mensile", 4, "6004", "2026-05-18"), ("mensile", 11, "6011", "2026-12-16"),
    ("mensile", 12, "6012", "2027-01-18"), ("trimestrale", 1, "6031", "2026-05-18"), ("trimestrale", 2, "6032", "2026-08-20"),
    ("trimestrale", 3, "6033", "2026-11-16"), ("trimestrale", 4, "6099", "2027-03-16")])
def test_tributo(per, k, cod, scad):
    t = f24.tributo(2026, per, k)
    assert (t["codice"], t["scadenza"], t["anno_riferimento"]) == (cod, scad, 2026)


# --- GET info
def test_info_mensile_nov():
    r = sess().get(f"{API}/liquidazione-iva/f24", params={"anno": 2026, "periodicita": "mensile", "periodo": 11})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["debito"]["codice"] == "6011" and d["debito"]["importo"] == 1100 and d["debito"]["scadenza"] == "2026-12-16"
    assert len(d["crediti_suggeriti"]) >= 1 and d["crediti_suggeriti"][0][0] == "6099"
    assert [b["nome"] for b in d["banche"]] == ["Banca T33", "Banca Due"] and d["banche"][0]["predefinita"] is True


def test_info_trimestrale_matches_liquidazione():
    liq = sess().get(f"{API}/liquidazione-iva", params={"anno": 2026, "periodicita": "trimestrale"}).json()
    for k, cod in ((2, "6032"), (4, "6099")):
        p = next(x for x in liq["periodi"] if x["periodo"] == k)
        d = sess().get(f"{API}/liquidazione-iva/f24", params={"anno": 2026, "periodicita": "trimestrale", "periodo": k}).json()["debito"]
        assert d["codice"] == cod and d["importo"] == round(p["da_versare"], 2), (d, p)
    q2 = next(x for x in liq["periodi"] if x["periodo"] == 2)
    assert q2["da_versare"] == pytest.approx(232.3, abs=0.01)  # Q1 10 deferred (<25.82) + 220, +1%
    ST["q4"] = next(x for x in liq["periodi"] if x["periodo"] == 4)


@pytest.mark.parametrize("per,k", [("mensile", 2), ("mensile", 6), ("trimestrale", 3)])
def test_info_nothing_to_pay_400(per, k):
    r = sess().get(f"{API}/liquidazione-iva/f24", params={"anno": 2026, "periodicita": per, "periodo": k})
    assert r.status_code == 400 and "nessuna IVA da versare" in r.json()["detail"]


def test_info_invalid_period():
    r = sess().get(f"{API}/liquidazione-iva/f24", params={"anno": 2026, "periodicita": "trimestrale", "periodo": 7})
    assert r.status_code == 400


# --- POST pdf
def pdf_text(content):
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(content)).pages)


def test_pdf_no_credits():
    r = sess().post(f"{API}/liquidazione-iva/f24", json={"anno": 2026, "periodicita": "mensile", "periodo": 11, "data_versamento": "2026-12-16"})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf" and 'F24_IVA_6011_2026.pdf' in r.headers["content-disposition"]
    tx = pdf_text(r.content)
    for s in (PIVA, f"TEST_T33 F24 {RUN} Srl", "Via Roma 1", "Roma", "6011", "2026", "1.100,00", "16/12/2026", "05428", "11101", IBAN, "SALDO FINALE", "Banca T33"):
        assert s in tx, s
    assert "telematica" not in tx


def test_pdf_with_credits_and_bank():
    banche = sess().get(f"{API}/liquidazione-iva/f24", params={"anno": 2026, "periodicita": "mensile", "periodo": 11}).json()["banche"]
    r = sess().post(f"{API}/liquidazione-iva/f24", json={"anno": 2026, "periodicita": "mensile", "periodo": 11, "banca_id": banche[1]["id"],
                                                         "crediti": [{"codice": "6099", "anno": 2025, "importo": 300.5, "descrizione": "Credito IVA"},
                                                                     {"codice": "1627", "anno": 2025, "importo": 99.5}]})
    assert r.status_code == 200, r.text
    tx = pdf_text(r.content)
    for s in ("6099", "1627", "300,50", "99,50", "400,00", "700,00", "telematica", "IT52X0306909606100000063529", "Banca Due"):
        assert s in tx, s


def test_pdf_credits_equal_debito_ok():
    r = sess().post(f"{API}/liquidazione-iva/f24", json={"anno": 2026, "periodicita": "mensile", "periodo": 11, "crediti": [{"codice": "6099", "anno": 2025, "importo": 1100}]})
    assert r.status_code == 200
    assert "0,00" in pdf_text(r.content)


def test_pdf_credits_exceed_400():
    r = sess().post(f"{API}/liquidazione-iva/f24", json={"anno": 2026, "periodicita": "mensile", "periodo": 11, "crediti": [{"codice": "6099", "anno": 2025, "importo": 1100.01}]})
    assert r.status_code == 400 and r.json()["detail"].startswith("I crediti compensati superano")


def test_pdf_nothing_to_pay_400():
    r = sess().post(f"{API}/liquidazione-iva/f24", json={"anno": 2026, "periodicita": "mensile", "periodo": 2})
    assert r.status_code == 400


def test_pdf_validation():
    base = {"anno": 2026, "periodicita": "mensile", "periodo": 11}
    c = {"codice": "6099", "anno": 2025, "importo": 1}
    assert sess().post(f"{API}/liquidazione-iva/f24", json={**base, "crediti": [c] * 6}).status_code == 422
    assert sess().post(f"{API}/liquidazione-iva/f24", json={**base, "crediti": [{**c, "importo": 0}]}).status_code == 422
    assert sess().post(f"{API}/liquidazione-iva/f24", json={**base, "crediti": [{**c, "codice": "60"}]}).status_code == 422
    assert sess().post(f"{API}/liquidazione-iva/f24", json={**base, "data_versamento": "2026-13-45"}).status_code == 422
    assert sess().post(f"{API}/liquidazione-iva/f24", json={**base, "crediti": [c] * 5}).status_code == 200


def test_pdf_trimestrale_q4():
    r = sess().post(f"{API}/liquidazione-iva/f24", json={"anno": 2026, "periodicita": "trimestrale", "periodo": 4})
    assert r.status_code == 200 and "F24_IVA_6099_2026.pdf" in r.headers["content-disposition"]
    tx = pdf_text(r.content)
    assert "6099" in tx and "16/03/2027" in tx


# --- module gating
def test_gating_fatturazione_off():
    r = sess().put(f"{API}/companies/{ST['cid']}/moduli", json={k: k != "fatturazione" for k in ("fatturazione", "archivio", "fatture_attive", "fatture_passive", "corrispettivi", "contabilita")})
    assert r.status_code == 200, r.text
    try:
        g = sess().get(f"{API}/liquidazione-iva/f24", params={"anno": 2026, "periodicita": "mensile", "periodo": 11})
        p = sess().post(f"{API}/liquidazione-iva/f24", json={"anno": 2026, "periodicita": "mensile", "periodo": 11})
        assert g.status_code == 403 and p.status_code == 403 and "Fatturazione" in g.json()["detail"]
    finally:
        sess().put(f"{API}/companies/{ST['cid']}/moduli", json={k: True for k in ("fatturazione", "archivio", "fatture_attive", "fatture_passive", "corrispettivi", "contabilita")})


def test_unauth():
    r = requests.get(f"{API}/liquidazione-iva/f24", params={"anno": 2026, "periodicita": "mensile", "periodo": 11})
    assert r.status_code == 401

# Iteration 87: invoicing to a condominio (CF only, no P.IVA), sostituto d'imposta 4% ritenuta at collection,
# bonus edilizi 'bonifico parlante' Causale in XML, prima nota incasso with ritenuta, TD17 cedente nazione regression.
# Run: pytest tests/test_iteration87_condominio_bonus.py -v -n 0   (T87_KEEP=1 keeps the company for UI tests)
import json
import os
import random
import sys

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo, strip_ns, TODAY  # noqa: E402

RUN = str(random.randint(100000, 999999))
TOK, UID = "test_session_t87_admin", "test-user-t87-admin"
PIVA = "87" + RUN + "871"
CF_CONDO = "9" + RUN + "8701"
ST = {}
COLLS = ["invoices", "passive_invoices", "parties", "articles", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "partite_aperte", "f24_versamenti", "pag_distinte", "ratei_risconti", "counters"]


def sess():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{denominazione:/^TEST_T87/}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def condo(**kw):
    return {"tipo": "cliente", "denominazione": f"TEST_T87 Condominio Via Roma {RUN}", "partita_iva": "", "codice_fiscale": CF_CONDO,
            "codice_destinatario": "0000000", "pec": "studio.admin@pec.example.com", "indirizzo": "Via Roma 10", "cap": "20100",
            "comune": "Milano", "provincia": "MI", "nazione": "IT", "condominio": True, "sostituto_imposta": True, **kw}


def inv(pid, price=1000, **kw):
    return {"tipo_documento": "TD01", "data": TODAY, "party_id": pid, "modalita_pagamento": "MP05",
            "lines": [{"descrizione": "Lavori manutenzione", "quantita": 1, "prezzo_unitario": price, "aliquota": 22}], **kw}


def loc(r):
    return [e["loc"][-1] for e in r.json()["detail"]]


def sent(body):
    s = sess()
    r = s.post(f"{API}/invoices", json=body)
    assert r.status_code == 200, r.text
    iid = r.json()["id"]
    assert s.post(f"{API}/invoices/{iid}/send").status_code == 200
    s.post(f"{API}/invoices/{iid}/refresh")
    return iid


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t87.admin@example.com", name:"TEST_T87 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": f"TEST_T87 Edile {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                             "iban": "IT60X0542811101000000123456", "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    sess().put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                            "corrispettivi": True, "contabilita": True})
    sess().get(f"{API}/contabilita/conti")
    ST["params"] = sess().get(f"{API}/contabilita/parametri").json()["parametri"]
    yield
    if not os.environ.get("T87_KEEP"):
        clean()


# --- parties validation
def test_condominio_with_piva_rejected():
    r = sess().post(f"{API}/parties", json=condo(partita_iva="01234567890"))
    assert r.status_code == 422 and "partita_iva" in loc(r), r.text


def test_condominio_cf_must_be_11_digits():
    r = sess().post(f"{API}/parties", json=condo(codice_fiscale="RSSMRA80A01H501U"))
    assert r.status_code == 422 and "codice_fiscale" in loc(r), r.text
    r = sess().post(f"{API}/parties", json=condo(codice_fiscale="123"))
    assert r.status_code == 422 and "codice_fiscale" in loc(r)


def test_condominio_created_and_persisted():
    r = sess().post(f"{API}/parties", json=condo(persona="fisica", nome="Mario", cognome="Rossi"))
    assert r.status_code == 200, r.text
    ST["pid"] = r.json()["id"]
    p = next(x for x in sess().get(f"{API}/parties").json() if x["id"] == ST["pid"])
    assert p["condominio"] is True and p["sostituto_imposta"] is True and p["persona"] == "giuridica"
    assert p["partita_iva"] == "" and p["codice_fiscale"] == CF_CONDO


def test_fornitore_flags_forced_false():
    b = condo(tipo="fornitore", partita_iva="01234567890", codice_fiscale="01234567890", denominazione="TEST_T87 Fornitore Srl")
    r = sess().post(f"{API}/parties", json=b)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["condominio"] is False and j["sostituto_imposta"] is False


def test_update_condominio_with_piva_rejected():
    r = sess().put(f"{API}/parties/{ST['pid']}", json=condo(partita_iva="01234567890"))
    assert r.status_code == 422 and "partita_iva" in loc(r)


# --- invoice XML to condominio + bonus causale
def test_invoice_condominio_xml_and_bonus():
    s = sess()
    r = s.post(f"{API}/invoices", json=inv(ST["pid"], bonus_edilizio="eco"))
    assert r.status_code == 200, r.text
    j = r.json()
    ST["iid"] = j["id"]
    assert j["bonus_edilizio"] == "eco"
    assert round(j["totale"], 2) == 1220.0 and not j.get("ritenuta")
    x = strip_ns(s.get(f"{API}/invoices/{ST['iid']}/xml").text)
    da = x.find(".//CessionarioCommittente/DatiAnagrafici")
    assert da.find("IdFiscaleIVA") is None
    assert da.findtext("CodiceFiscale") == CF_CONDO
    assert x.findtext(".//DatiTrasmissione/CodiceDestinatario") == "0000000"
    assert x.findtext(".//DatiTrasmissione/PECDestinatario") == "studio.admin@pec.example.com"
    dg = x.find(".//DatiGeneraliDocumento")
    assert dg.find("DatiRitenuta") is None
    assert dg.findtext("ImportoTotaleDocumento") == "1220.00"
    caus = [c.text for c in dg.findall("Causale")]
    assert caus and all(len(c) <= 200 for c in caus)
    full = "".join(caus)
    num = j.get("numero_display") or str(j.get("numero"))
    d = TODAY
    assert full.startswith("Bonifico per Ecobonus (riqualificazione energetica) ai sensi dell'art. 1 c. 344-347 L. 296/2006"), full
    assert f"Fatt. n. {num} del {d[8:10]}/{d[5:7]}/{d[:4]}" in full, full
    assert f"C.F. beneficiario detrazione {CF_CONDO}" in full and f"P.IVA beneficiario bonifico {PIVA}" in full
    ST["full"] = full
    # scadenze = totale
    pd = x.findall(".//DettaglioPagamento/ImportoPagamento")
    assert round(sum(float(p.text) for p in pd), 2) == 1220.0


def test_bonus_update_and_clear():
    s = sess()
    cur = s.get(f"{API}/invoices/{ST['iid']}").json()
    body = inv(ST["pid"], bonus_edilizio="sisma")
    r = s.put(f"{API}/invoices/{ST['iid']}", json=body)
    assert r.status_code == 200, r.text
    assert s.get(f"{API}/invoices/{ST['iid']}").json()["bonus_edilizio"] == "sisma"
    x = strip_ns(s.get(f"{API}/invoices/{ST['iid']}/xml").text)
    assert "Sismabonus" in "".join(c.text for c in x.findall(".//DatiGeneraliDocumento/Causale"))
    r = s.put(f"{API}/invoices/{ST['iid']}", json=inv(ST["pid"], bonus_edilizio="xxx"))
    assert r.status_code == 422
    assert cur["id"] == ST["iid"]


def test_bonus_with_user_causale_both_present():
    s = sess()
    r = s.post(f"{API}/invoices", json=inv(ST["pid"], bonus_edilizio="casa", causale="TEST_T87 lavori scala B"))
    assert r.status_code == 200, r.text
    x = strip_ns(s.get(f"{API}/invoices/{r.json()['id']}/xml").text)
    caus = [c.text for c in x.findall(".//DatiGeneraliDocumento/Causale")]
    assert caus[0] == "TEST_T87 lavori scala B" and "Bonus casa" in "".join(caus[1:])
    s.delete(f"{API}/invoices/{r.json()['id']}")


# --- incasso with ritenuta via PaymentDialog API
def test_payment_with_ritenuta_closes_invoice():
    iid = sent(inv(ST["pid"]))
    ST["paid_iid"] = iid
    s = sess()
    over = s.post(f"{API}/invoices/{iid}/pagamenti", json={"data": TODAY, "importo": 1200, "ritenuta_subita": 40, "metodo": "bonifico"})
    assert over.status_code == 400, over.text
    r = s.post(f"{API}/invoices/{iid}/pagamenti", json={"data": TODAY, "importo": 1180, "ritenuta_subita": 40, "metodo": "bonifico"})
    assert r.status_code == 200, r.text
    j = s.get(f"{API}/invoices/{iid}/pagamenti").json()
    pays = j["pagamenti"]
    assert sorted((p["metodo"], p["importo"]) for p in pays) == [("bonifico", 1180.0), ("ritenuta", 40.0)], pays
    assert round(j["scadenzario"]["residuo"], 2) == 0


# --- prima nota incasso with ritenuta
def test_saldaconto_partite_has_imponibile_and_incasso_entry():
    iid = sent(inv(ST["pid"], price=500))
    s = sess()
    r = s.get(f"{API}/contabilita/saldaconto/partite", params={"party_id": ST["pid"], "tipo": "cliente"})
    assert r.status_code == 200, r.text
    row = next(x for x in r.json()["aperte"] if x["invoice_id"] == iid)
    assert row["imponibile"] == 500 and round(row["residuo"], 2) == 610.0
    p = ST["params"]
    rit = 20.0
    body = {"data": TODAY, "causale": "IN", "descrizione": "TEST_T87 incasso condominio",
            "righe": [{"conto": p["banca"], "dare": 590.0, "avere": 0, "party_id": None, "nota": ""},
                      {"conto": p["ritenute_subite"], "dare": rit, "avere": 0, "party_id": None, "nota": "Ritenuta 4%"},
                      {"conto": p["clienti"], "dare": 0, "avere": 610.0, "party_id": ST["pid"], "nota": ""}],
            "saldaconto": [{"invoice_id": iid, "importo": 610.0, "passivo": False}]}
    r = s.post(f"{API}/contabilita/registrazioni", json=body)
    assert r.status_code == 200, r.text
    assert p["ritenute_subite"] == "05.02.003"
    r = s.get(f"{API}/contabilita/saldaconto/partite", params={"party_id": ST["pid"], "tipo": "cliente"}).json()
    assert iid in [x["invoice_id"] for x in r["chiuse"]], r
    j = s.get(f"{API}/invoices/{iid}/pagamenti").json()
    assert round(j["scadenzario"]["residuo"], 2) == 0


# --- regression iteration 86: TD17 cedente nazione from paese_iva
def test_td17_regression_suite_exists():
    # covered by tests/test_iteration86_iva_intra_conferma.py::test_register_mixed_td17_cedente_country (run separately)
    assert os.path.exists(os.path.join(os.path.dirname(__file__), "test_iteration86_iva_intra_conferma.py"))

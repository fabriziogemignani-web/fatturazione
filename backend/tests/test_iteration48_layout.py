# Iteration 48: Layout documenti (logo, colore, dati extra, piede fattura/NC, campi toggles) - GET/PUT /api/company/layout,
# admin-only PUT, validation, PUT /api/company preserves layout, courtesy PDF (unit + cortesia endpoint + export ZIP).
# Run: REACT_APP_BACKEND_URL=... pytest tests/test_iteration48_layout.py -v -n 0  (SMTP sink on 127.0.0.1:1025)
import base64
import io
import os
import subprocess
import sys
import zipfile
from datetime import date, timedelta

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
TODAY = date.today()
U = {"admin": ("test-user-t48-admin", "test_session_t48_admin", "admin"),
     "op": ("test-user-t48-op", "test_session_t48_op", "operatore"),
     "cont": ("test-user-t48-cont", "test_session_t48_cont", "contabile")}
S = {}
# 1x1 red PNG
PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
LOGO = f"data:image/png;base64,{PNG}"
CAMPI = ("cliente_codice_fiscale", "cliente_codice_destinatario", "cliente_pec", "cliente_email", "cliente_telefono",
         "causale", "note_righe", "riepilogo_iva", "scadenza", "coordinate_bancarie")
COLLS = ["invoices", "parties", "payments", "coa_entries", "coa_accounts", "coa_causali", "coa_iva", "sdi_events", "audit", "com_log", "export_log"]


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


def piva(base10):
    s = 0
    for i, ch in enumerate(base10):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            d = d - 9 if d > 9 else d
        s += d
    return base10 + str((10 - s % 10) % 10)


def sess(k="admin"):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {U[k][1]}"
    if S.get("cid"):
        s.headers["X-Company-Id"] = S["cid"]
    return s


def clean():
    ids = "[" + ",".join(f'"{u}"' for u, _, _ in U.values()) + "]"
    colls = "[" + ",".join(f'"{c}"' for c in COLLS) + "]"
    mongo(f'db.companies.find({{denominazione:/^TEST_T48/}}).forEach(c=>{{{colls}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:{ids}}}}}); db.user_sessions.deleteMany({{user_id:{{$in:{ids}}}}});')


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    for k, (uid, tok, role) in U.items():
        mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.{uid}@example.com", name:"TEST_{k}", picture:"", role:"{role}", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
              f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    co = piva("0987123481")
    r = sess().post(f"{API}/companies", json={"denominazione": "TEST_T48 Grafica Srl", "partita_iva": co, "codice_fiscale": co, "regime_fiscale": "RF01",
                                              "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT",
                                              "iban": "IT60X0542811101000000123456"})
    assert r.status_code == 200, r.text
    S["cid"] = r.json()["id"]
    mongo(f'db.users.updateMany({{user_id:{{$in:["{U["op"][0]}","{U["cont"][0]}"]}}}}, {{$set:{{company_ids:["{S["cid"]}"]}}}});')
    yield
    clean()


def test_get_defaults():
    for k in ("admin", "op", "cont"):
        r = sess(k).get(f"{API}/company/layout")
        assert r.status_code == 200, (k, r.text)
        d = r.json()
        assert d["colore"] == "#0f172a" and d["logo"] is None and d["piede_fattura"] == "" and d["piede_nc"] == ""
        print(k, "default campi:", d["campi"])


def test_get_defaults_campi_all_true():
    d = sess().get(f"{API}/company/layout").json()
    assert d["campi"] == {k: True for k in CAMPI}, f"default campi not all true: {d['campi']}"


def test_get_requires_company_header():
    s = sess()
    s.headers.pop("X-Company-Id")
    assert s.get(f"{API}/company/layout").status_code == 400


def full_payload(**kw):
    p = {"logo": LOGO, "colore": "#1e40af", "telefono": "+39 06 1234567", "email": "info@t48.example.com", "pec": "t48@pec.example.com",
         "sito": "www.t48.example.com", "rea": "RM-123456", "capitale_sociale": "10.000,00 i.v.",
         "piede_fattura": "TEST_T48 PIEDE FATTURA condizioni", "piede_nc": "TEST_T48 PIEDE NOTA CREDITO",
         "campi": {k: True for k in CAMPI}}
    p.update(kw)
    return p


@pytest.mark.parametrize("k", ["op", "cont"])
def test_put_non_admin_403(k):
    r = sess(k).put(f"{API}/company/layout", json=full_payload())
    assert r.status_code == 403, r.text


@pytest.mark.parametrize("bad", [{"logo": "data:image/gif;base64,R0lGOD"}, {"logo": "http://x/logo.png"}, {"logo": "data:image/svg+xml;base64,PHN2Zz4="},
                                 {"logo": "data:image/png;base64,<script>"}, {"colore": "red"}, {"colore": "#12345"}, {"colore": "#GGGGGG"},
                                 {"telefono": "1" * 41}, {"piede_fattura": "x" * 2001}])
def test_put_invalid_422(bad):
    r = sess().put(f"{API}/company/layout", json=full_payload(**bad))
    assert r.status_code == 422, (bad, r.status_code, r.text[:200])


def test_put_admin_and_persist():
    campi = {k: True for k in CAMPI}
    campi.update({"cliente_pec": False, "causale": False, "note_righe": False, "scadenza": False, "coordinate_bancarie": False, "riepilogo_iva": False})
    p = full_payload(campi={**campi, "bogus_key": True})
    r = sess().put(f"{API}/company/layout", json=p)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "bogus_key" not in d["campi"] and d["campi"] == campi
    g = sess("op").get(f"{API}/company/layout").json()
    for k in ("logo", "colore", "telefono", "email", "pec", "sito", "rea", "capitale_sociale", "piede_fattura", "piede_nc"):
        assert g[k] == p[k], k
    assert g["campi"] == campi


def test_put_company_preserves_layout():
    s = sess()
    c = s.get(f"{API}/company").json()
    c.pop("id", None)
    c["indirizzo"] = "Via Roma 2"
    r = s.put(f"{API}/company", json=c)
    assert r.status_code == 200, r.text[:300]
    assert s.get(f"{API}/company").json()["indirizzo"] == "Via Roma 2"
    g = s.get(f"{API}/company/layout").json()
    assert g["logo"] == LOGO and g["piede_nc"] == "TEST_T48 PIEDE NOTA CREDITO" and g["campi"]["causale"] is False


def _pdf_text(b):
    from pypdf import PdfReader
    rd = PdfReader(io.BytesIO(b))
    txt = "\n".join(p.extract_text() or "" for p in rd.pages)
    imgs = sum(len(p.images) for p in rd.pages)
    return txt, imgs


def test_courtesy_pdf_unit():
    from export_comm import courtesy_pdf
    comp = sess().get(f"{API}/company").json()
    comp["layout"] = sess().get(f"{API}/company/layout").json()
    ces = {"denominazione": "TEST Cliente", "partita_iva": "01234567897", "codice_fiscale": "RSSMRA80A01H501U", "pec": "cli@pec.it", "email": "cli@x.it",
           "telefono": "333", "codice_destinatario": "ABC1234", "indirizzo": "Via X", "cap": "20100", "comune": "Milano", "provincia": "MI"}
    d = {"tipo_documento": "TD01", "numero_display": "1/2026", "data": TODAY.isoformat(), "causale": "CAUSALE_T48", "scadenza": TODAY.isoformat(),
         "banca": {"iban": "IT60X0542811101000000123456"},
         "lines": [{"descrizione": "Riga", "note": "NOTA_RIGA_T48", "quantita": 1, "prezzo_unitario": 100, "prezzo_totale": 100, "aliquota": 22}],
         "riepilogo": [{"aliquota": 22, "imponibile": 100, "imposta": 22}], "imponibile": 100, "iva": 22, "totale": 122}
    txt, imgs = _pdf_text(courtesy_pdf(comp, ces, d))
    assert imgs >= 1, "logo missing"
    for s in ("TEST_T48 PIEDE FATTURA", "REA RM-123456", "PEC t48@pec.example.com", "Tel. +39 06 1234567", "Capitale sociale 10.000,00", "www.t48.example.com"):
        assert s in txt, s
    for s in ("CAUSALE_T48", "NOTA_RIGA_T48", "PEC cli@pec.it", "Scadenza pagamento", "IBAN", "Aliquota", "PIEDE NOTA CREDITO"):
        assert s not in txt, s
    assert "C.F. RSSMRA80A01H501U" in txt  # still on
    txt, _ = _pdf_text(courtesy_pdf(comp, ces, {**d, "tipo_documento": "TD04"}))
    assert "TEST_T48 PIEDE NOTA CREDITO" in txt and "PIEDE FATTURA" not in txt
    # ricevuta (passive) ignores layout
    txt, imgs = _pdf_text(courtesy_pdf(ces, comp, d, ricevuta=True))
    assert imgs == 0 and "PIEDE" not in txt


def test_invoices_cortesia_and_export_zip():
    s = sess()
    assert s.put(f"{API}/company/smtp", json={"host": "127.0.0.1", "port": 1025, "security": "none", "username": "", "password": "",
                                              "from_email": "noreply@example.com", "from_name": "TEST_T48"}).status_code == 200
    pv = piva("0123456781")
    r = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": "TEST_T48 Cliente Srl", "partita_iva": pv, "codice_fiscale": pv, "codice_destinatario": "ABC1234",
                                       "email": "cli48@example.com", "pec": "cli48@pec.example.com", "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"})
    assert r.status_code == 200, r.text
    S["party"] = r.json()["id"]
    base = {"data": (TODAY - timedelta(days=1)).isoformat(), "party_id": S["party"], "modalita_pagamento": "MP05", "causale": "CAUSALE_T48",
            "scadenza": (TODAY + timedelta(days=30)).isoformat(),
            "lines": [{"descrizione": "TEST riga", "note": "NOTA_RIGA_T48", "quantita": 1, "prezzo_unitario": 100, "aliquota": 22}]}
    r = s.post(f"{API}/invoices", json={**base, "tipo_documento": "TD01"})
    assert r.status_code == 200, r.text
    S["inv"] = r.json()["id"]
    assert s.post(f"{API}/invoices/{S['inv']}/send").status_code == 200
    assert s.post(f"{API}/invoices/{S['inv']}/refresh").json()["status"] == "consegnata"
    r = s.post(f"{API}/invoices", json={**base, "tipo_documento": "TD04", "fattura_collegata_id": S["inv"],
                                        "lines": [{"descrizione": "TEST storno", "quantita": 1, "prezzo_unitario": 50, "aliquota": 22}]})
    assert r.status_code == 200, r.text
    S["nc"] = r.json()["id"]
    assert s.post(f"{API}/invoices/{S['nc']}/send").status_code == 200
    s.post(f"{API}/invoices/{S['nc']}/refresh")
    for iid in (S["inv"], S["nc"]):
        r = s.post(f"{API}/comunicazioni/cortesia/{iid}", json={})
        assert r.status_code == 200, r.text
    r = s.get(f"{API}/export/commercialista.zip", params={"dal": (TODAY - timedelta(days=5)).isoformat(), "al": TODAY.isoformat()})
    assert r.status_code == 200, r.text[:300]
    z = zipfile.ZipFile(io.BytesIO(r.content))
    pdfs = [n for n in z.namelist() if n.endswith(".pdf")]
    assert len(pdfs) >= 2, z.namelist()
    found = {"fatt": False, "nc": False}
    for n in pdfs:
        txt, imgs = _pdf_text(z.read(n))
        assert imgs >= 1, n
        found["fatt"] |= "TEST_T48 PIEDE FATTURA" in txt
        found["nc"] |= "TEST_T48 PIEDE NOTA CREDITO" in txt
        assert "CAUSALE_T48" not in txt and "NOTA_RIGA_T48" not in txt
    assert found == {"fatt": True, "nc": True}, found


def test_logo_removal():
    r = sess().put(f"{API}/company/layout", json=full_payload(logo=None))
    assert r.status_code == 200 and r.json()["logo"] is None
    assert sess().get(f"{API}/company/layout").json()["logo"] is None
    # restore for UI tests
    assert sess().put(f"{API}/company/layout", json=full_payload()).status_code == 200

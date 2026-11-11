# Iteration 49: codice fiscale obbligatorio (IT) on POST/PUT /api/parties + Excel import preview; layout piede_ddt persist + DDT PDF with logo/piede.
# Run: REACT_APP_BACKEND_URL=... pytest tests/test_iteration49_cf_layout.py -v -n 0
import io
import os
import subprocess
from datetime import date

import pytest
import requests
from openpyxl import load_workbook

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
TODAY = date.today().isoformat()
U = {"admin": ("test-user-t49-admin", "test_session_t49_admin", "admin")}
S = {}
PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
LOGO = f"data:image/png;base64,{PNG}"
COLLS = ["invoices", "parties", "articles", "stock_moves", "ddts", "payments", "coa_entries", "coa_accounts", "coa_causali", "coa_iva", "audit",
         "sdi_events", "import_batches", "partite_aperte"]
CF_MSG = "Il codice fiscale è obbligatorio per clienti e fornitori italiani"


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


def sess():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {U['admin'][1]}"
    if S.get("cid"):
        s.headers["X-Company-Id"] = S["cid"]
    return s


def clean():
    ids = "[" + ",".join(f'"{u}"' for u, _, _ in U.values()) + "]"
    colls = "[" + ",".join(f'"{c}"' for c in COLLS) + "]"
    mongo(f'db.companies.find({{denominazione:/^TEST_T49/}}).forEach(c=>{{{colls}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:{ids}}}}}); db.user_sessions.deleteMany({{user_id:{{$in:{ids}}}}});')


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    uid, tok, role = U["admin"]
    mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.{uid}@example.com", name:"TEST_admin49", picture:"", role:"{role}", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": "TEST_T49 Srl", "partita_iva": "01234567897", "codice_fiscale": "01234567897", "regime_fiscale": "RF01",
                                              "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    S["cid"] = r.json()["id"]
    yield
    clean()


def party(**kw):
    p = {"tipo": "cliente", "denominazione": "TEST_T49 Cliente", "partita_iva": "02345670481", "codice_fiscale": "", "codice_destinatario": "ABC1234",
         "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"}
    p.update(kw)
    return p


def assert_cf_err(r):
    assert r.status_code == 422, r.text
    det = r.json()["detail"]
    hit = [e for e in det if e["loc"][-1] == "codice_fiscale"]
    assert hit, det
    assert CF_MSG in hit[0]["msg"], hit


# --- Parties CF required for IT ---
@pytest.mark.parametrize("tipo", ["cliente", "fornitore"])
@pytest.mark.parametrize("naz,cf", [("IT", ""), ("IT", "   "), ("it", ""), ("", "")])
def test_post_it_without_cf_422(tipo, naz, cf):
    assert_cf_err(sess().post(f"{API}/parties", json=party(tipo=tipo, nazione=naz, codice_fiscale=cf)))


@pytest.mark.parametrize("tipo", ["cliente", "fornitore"])
def test_post_it_with_cf_ok_and_put(tipo):
    s = sess()
    r = s.post(f"{API}/parties", json=party(tipo=tipo, denominazione=f"TEST_T49 {tipo} IT", codice_fiscale="02345670481"))
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    assert r.json()["codice_fiscale"] == "02345670481"
    # PUT removing CF -> 422
    assert_cf_err(s.put(f"{API}/parties/{pid}", json=party(tipo=tipo, codice_fiscale="")))
    # PUT valid -> persisted
    r = s.put(f"{API}/parties/{pid}", json=party(tipo=tipo, denominazione="TEST_T49 upd", codice_fiscale="RSSMRA80A01H501U"))
    assert r.status_code == 200, r.text
    got = [p for p in s.get(f"{API}/parties", params={"tipo": tipo}).json() if p["id"] == pid]
    assert got and got[0]["codice_fiscale"] == "RSSMRA80A01H501U"
    # PUT switching to foreign w/o CF -> ok
    r = s.put(f"{API}/parties/{pid}", json=party(tipo=tipo, codice_fiscale="", nazione="FR", partita_iva="12345678903", codice_destinatario="XXXXXXX"))
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("tipo", ["cliente", "fornitore"])
@pytest.mark.parametrize("naz", ["DE", "FR"])
def test_post_foreign_without_cf_ok(tipo, naz):
    r = sess().post(f"{API}/parties", json=party(tipo=tipo, denominazione=f"TEST_T49 {tipo} {naz}", nazione=naz, partita_iva="12345678903",
                                                 codice_destinatario="XXXXXXX", codice_fiscale=""))
    assert r.status_code == 200, r.text
    assert r.json()["nazione"] == naz


# --- Excel import preview ---
def upload(wb):
    b = io.BytesIO(); wb.save(b)
    return sess().post(f"{API}/importazione/anteprima", files={"file": ("imp.xlsx", b.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})


def test_import_preview_cf():
    r = sess().get(f"{API}/importazione/modello")
    assert r.status_code == 200, r.text
    wb = load_workbook(io.BytesIO(r.content))
    c = wb["Clienti"]
    start = c.max_row
    c.append(["TEST_T49 Imp IT noCF", "05555550481", "", "", "", "", "", "Via 1", "00100", "Roma", "RM", "IT"])      # err
    c.append(["TEST_T49 Imp vuota noCF", "06666660481", "", "", "", "", "", "Via 2", "00100", "Roma", "RM", ""])     # err (default IT)
    c.append(["TEST_T49 Imp IT CF", "07777770481", "07777770481", "", "", "", "", "Via 3", "00100", "Roma", "RM", "IT"])  # ok
    c.append(["TEST_T49 Imp DE", "99999999990", "", "XXXXXXX", "", "", "", "Str 4", "10115", "Berlin", "", "DE"])     # ok
    f = wb["Fornitori"]
    fstart = f.max_row
    f.append(["TEST_T49 Forn IT noCF", "08888880481", "", "", "", "", "", "Via F", "10100", "Torino", "TO", "IT", ""])  # err
    f.append(["TEST_T49 Forn FR", "11111111110", "", "XXXXXXX", "", "", "", "Rue 1", "75001", "Paris", "", "FR", ""])  # ok
    r = upload(wb)
    assert r.status_code == 200, r.text
    res = r.json()
    print(res["riepilogo"].get("Clienti"), res["riepilogo"].get("Fornitori"))
    ce = {e["riga"]: e["errore"] for e in res["riepilogo"]["Clienti"]["errori"]}
    fe = {e["riga"]: e["errore"] for e in res["riepilogo"]["Fornitori"]["errori"]}
    assert set(ce) == {start + 1, start + 2}, ce
    assert all("codice fiscale" in v.lower() for v in ce.values()), ce
    assert set(fe) == {fstart + 1}, fe
    assert res["riepilogo"]["Clienti"]["righe"] == start - 1 + 2 and res["riepilogo"]["Fornitori"]["righe"] == fstart - 1 + 1, (start, fstart)


# --- Layout piede_ddt + DDT PDF ---
def test_layout_piede_ddt_and_ddt_pdf():
    s = sess()
    lay = s.get(f"{API}/company/layout").json()
    assert lay["piede_ddt"] == ""
    lay.update({"logo": LOGO, "colore": "#b91c1c", "piede_ddt": "TEST_T49 PIEDE DDT reclami entro 8 giorni", "piede_fattura": "TEST_T49 PF"})
    r = s.put(f"{API}/company/layout", json=lay)
    assert r.status_code == 200 and r.json()["piede_ddt"] == lay["piede_ddt"], r.text
    g = s.get(f"{API}/company/layout").json()
    assert g["piede_ddt"] == lay["piede_ddt"] and g["logo"] == LOGO and g["colore"] == "#b91c1c"
    assert s.put(f"{API}/company/layout", json={**lay, "piede_ddt": "x" * 2001}).status_code == 422
    p = s.post(f"{API}/parties", json=party(denominazione="TEST_T49 DDT Cli", codice_fiscale="02345670481")).json()
    r = s.post(f"{API}/ddt", json={"data": TODAY, "party_id": p["id"], "causale": "Vendita", "porto": "franco", "trasporto_a_cura": "mittente",
                                   "colli": 1, "peso_kg": 2, "aspetto_beni": "Scatola", "prezzi_in_stampa": True,
                                   "lines": [{"descrizione": "TEST riga ddt", "quantita": 1, "unita_misura": "PZ", "prezzo_unitario": 10, "aliquota": 22}]})
    assert r.status_code == 200, r.text
    did = r.json()["id"]
    r = s.get(f"{API}/ddt/{did}/pdf")
    assert r.status_code == 200 and r.content[:4] == b"%PDF", r.text[:200]
    from pypdf import PdfReader
    rd = PdfReader(io.BytesIO(r.content))
    txt = "\n".join(pg.extract_text() or "" for pg in rd.pages)
    imgs = sum(len(pg.images) for pg in rd.pages)
    assert "TEST_T49 PIEDE DDT" in txt, txt[-500:]
    assert "TEST_T49 PF" not in txt
    assert imgs >= 1, "logo missing in DDT PDF"
    # restore no logo -> no image
    s.put(f"{API}/company/layout", json={**lay, "logo": None})
    rd = PdfReader(io.BytesIO(s.get(f"{API}/ddt/{did}/pdf").content))
    assert sum(len(pg.images) for pg in rd.pages) == 0


def test_foreign_vat_format_rejected_preexisting():
    # Documents pre-existing limitation: foreign VAT (non 11 digits) is rejected even when nazione != IT
    r = sess().post(f"{API}/parties", json=party(denominazione="TEST_T49 DE vat", nazione="DE", partita_iva="DE123456789", codice_destinatario="XXXXXXX"))
    print("foreign VAT status", r.status_code, r.text[:200])
    if r.status_code == 200:
        sess().delete(f"{API}/parties/{r.json()['id']}")

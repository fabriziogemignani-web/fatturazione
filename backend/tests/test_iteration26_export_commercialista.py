# Iteration 26: Export commercialista - GET /api/export/commercialista (counts/totals/log), .zip structure & filtering,
# POST /send (no SMTP 400, invalid email 422, success with local debug SMTP), role & module gating, emailer mime regression.
# Needs local debug SMTP: python3 -m smtpd -n -c DebuggingServer 127.0.0.1:1025 > /tmp/smtp_t26.log
# Run with: pytest test_iteration26_export_commercialista.py -n 0
import io
import os
import random
import sys
import time
import zipfile
from datetime import date

import pytest
import requests
from openpyxl import load_workbook

from test_iteration7_pa_scartate_registro import API, mongo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RUN = str(random.randint(100000, 999999))
TOK, UID = f"test_session_t26_admin_{RUN}", f"test-user-t26-admin-{RUN}"
CTOK, CUID = f"test_session_t26_cont_{RUN}", f"test-user-t26-cont-{RUN}"
OTOK, OUID = f"test_session_t26_oper_{RUN}", f"test-user-t26-oper-{RUN}"
PIVA = "86" + RUN + "261"
TODAY = date.today().isoformat()
DAL, AL = "2026-10-01", TODAY
SMTP_LOG = "/tmp/smtp_t26.log"
SMTP_OK = {"host": "127.0.0.1", "port": 1025, "security": "none", "username": "", "password": "",
           "from_email": "noreply@test-t26.it", "from_name": "TEST T26"}
FIX = open(os.path.join(os.path.dirname(__file__), "fixtures", "sample_fattura.xml")).read()
ST = {}


def sess(tok, cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    if cid:
        s.headers["X-Company-Id"] = cid
    return s


def user(uid, tok, role, cids):
    mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.t26.{uid}@example.com", name:"TEST_T26 {role}", picture:"", role:"{role}", status:"approved", company_ids:{cids}, created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')


def clean():
    ids = f'["{UID}","{CUID}","{OUID}"]'
    mongo(f'db.companies.find({{partita_iva:"{PIVA}"}}).forEach(c=>{{["invoices","passive_invoices","parties","export_log","counters","payments","passive_payments"].forEach(k=>db[k].deleteMany({{company_id:c.id}})); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:{ids}}}}}); db.user_sessions.deleteMany({{user_id:{{$in:{ids}}}}});')


def pxml(numero, data, tipo="TD01", tot="574.93"):
    return (FIX.replace("<IdCodice>01234567890</IdCodice>", f"<IdCodice>{PIVA}</IdCodice>")
            .replace("<Numero>5674/2026</Numero>", f"<Numero>{numero}</Numero>")
            .replace("<Data>2026-10-30</Data>", f"<Data>{data}</Data>")
            .replace("<TipoDocumento>TD01</TipoDocumento>", f"<TipoDocumento>{tipo}</TipoDocumento>"))


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    user(UID, TOK, "admin", "[]")
    s = sess(TOK)
    r = s.post(f"{API}/companies", json={"denominazione": f"TEST_T26 Export {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                         "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    cid = ST["cid"] = r.json()["id"]
    user(CUID, CTOK, "contabile", f'["{cid}"]')
    user(OUID, OTOK, "operatore", f'["{cid}"]')
    s.headers["X-Company-Id"] = cid
    p = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": "TEST_T26 Cliente", "partita_iva": "01234567890", "codice_fiscale": "",
                                       "codice_destinatario": "ABC1234", "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"})
    assert p.status_code == 200, p.text
    pid = p.json()["id"]

    def inv(data, price, send=True):
        r = s.post(f"{API}/invoices", json={"tipo_documento": "TD01", "data": data, "party_id": pid, "modalita_pagamento": "MP05",
                                           "lines": [{"descrizione": "TEST_T26 servizio", "quantita": 1, "prezzo_unitario": price, "aliquota": 22}]})
        assert r.status_code == 200, r.text
        iid = r.json()["id"]
        if send:
            assert s.post(f"{API}/invoices/{iid}/send").status_code == 200
        return iid
    ST["sept"] = inv("2026-09-15", 300)            # out of period
    ST["a1"] = inv("2026-10-05", 1000)             # inviata -> refresh -> consegnata
    s.post(f"{API}/invoices/{ST['a1']}/refresh")
    ST["a2"] = inv("2026-10-10", 500)              # inviata, then stornata with TD04 (today)
    ST["scart"] = inv("2026-10-12", 200)           # forced scartata
    mongo(f'db.invoices.updateOne({{id:"{ST["scart"]}"}}, {{$set:{{status:"scartata"}}}})')
    ST["bozza"] = inv("2026-10-15", 700, send=False)
    nc = s.post(f"{API}/invoices/{ST['a2']}/storno-totale", json={"invia": True})
    assert nc.status_code == 200, nc.text
    ST["nc"] = nc.json()["id"]
    up = s.post(f"{API}/passive/upload", files=[("files", ("p1.xml", pxml("TEST26-1", "2026-10-20"), "text/xml")),
                                                 ("files", ("p2.xml", pxml("TEST26-2", "2026-10-22", "TD04"), "text/xml")),
                                                 ("files", ("p3.xml", pxml("TEST26-3", "2026-09-20"), "text/xml"))])
    assert up.status_code == 200 and all(x["ok"] for x in up.json()), up.text
    yield
    clean()


class TestInfo:
    def test_counts_totals(self):
        r = sess(TOK, ST["cid"]).get(f"{API}/export/commercialista", params={"dal": DAL, "al": AL})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["attive"] == 3, d              # a1 consegnata, a2 inviata, nc inviata
        assert d["passive"] == 2, d
        assert d["totale_attive"] == pytest.approx(1220.0), d   # 1220 + 610 - 610
        assert d["totale_passive"] == pytest.approx(0.0), d     # 574.93 - 574.93
        assert d["email"] == "" and d["log"] == []

    @pytest.mark.parametrize("dal,al", [("2026-10-31", "2026-10-01"), ("2026-13-01", "2026-14-01"), ("x", "2026-10-01"), ("2026-02-30", "2026-03-01")])
    def test_invalid_period_400(self, dal, al):
        r = sess(TOK, ST["cid"]).get(f"{API}/export/commercialista", params={"dal": dal, "al": al})
        assert r.status_code == 400, f"{dal}..{al} -> {r.status_code} {r.text}"

    def test_roles(self):
        assert sess(CTOK, ST["cid"]).get(f"{API}/export/commercialista", params={"dal": DAL, "al": AL}).status_code == 200
        for path in ("/export/commercialista", "/export/commercialista.zip"):
            r = sess(OTOK, ST["cid"]).get(f"{API}{path}", params={"dal": DAL, "al": AL})
            assert r.status_code == 403, r.text
        r = sess(OTOK, ST["cid"]).post(f"{API}/export/commercialista/send", json={"dal": DAL, "al": AL, "to": "a@example.com"})
        assert r.status_code == 403


class TestZip:
    def test_zip_structure(self):
        r = sess(TOK, ST["cid"]).get(f"{API}/export/commercialista.zip", params={"dal": DAL, "al": AL})
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/zip")
        assert "attachment" in r.headers["content-disposition"] and r.headers.get("x-filename", "").endswith(".zip")
        z = zipfile.ZipFile(io.BytesIO(r.content))
        names = z.namelist()
        root = names[0].split("/")[0]
        ax = [n for n in names if n.startswith(f"{root}/Fatture_emesse/XML/") and n.endswith(".xml")]
        ap = [n for n in names if n.startswith(f"{root}/Fatture_emesse/PDF/") and n.endswith(".pdf")]
        px = [n for n in names if n.startswith(f"{root}/Fatture_ricevute/XML/") and n.endswith(".xml")]
        pp = [n for n in names if n.startswith(f"{root}/Fatture_ricevute/PDF/") and n.endswith(".pdf")]
        assert (len(ax), len(ap), len(px), len(pp)) == (3, 3, 2, 2), names
        assert f"{root}/Riepilogo.xlsx" in names
        for n in ap + pp:
            assert z.read(n)[:4] == b"%PDF"
        # passive XML is the original file
        originals = {pxml("TEST26-1", "2026-10-20"), pxml("TEST26-2", "2026-10-22", "TD04")}
        assert {z.read(n).decode() for n in px} == originals
        # active XMLs: TD04 present, scartata/bozza/out-of-period absent
        body = "".join(z.read(n).decode("utf-8", "ignore") for n in ax)
        assert body.count("<TipoDocumento>TD04</TipoDocumento>") == 1
        assert "2026-09-15" not in body and "2026-10-12" not in body and "2026-10-15" not in body
        wb = load_workbook(io.BytesIO(z.read(f"{root}/Riepilogo.xlsx")))
        assert wb.sheetnames == ["Fatture emesse", "Fatture ricevute"]
        em = list(wb["Fatture emesse"].iter_rows(min_row=2, values_only=True))
        ri = list(wb["Fatture ricevute"].iter_rows(min_row=2, values_only=True))
        assert len(em) == 3 and len(ri) == 2
        assert round(sum(x[7] for x in em), 2) == 1220.0
        assert any(x[0] == "Nota di credito" and x[7] < 0 for x in em)
        assert {x[9] for x in em} == {n.rsplit("/", 1)[1] for n in ax}

    def test_empty_period_400(self):
        r = sess(TOK, ST["cid"]).get(f"{API}/export/commercialista.zip", params={"dal": "2020-01-01", "al": "2020-01-31"})
        assert r.status_code == 400 and "Nessuna fattura da esportare" in r.json()["detail"]


class TestSend:
    def test_send_no_smtp_400(self):
        r = sess(TOK, ST["cid"]).post(f"{API}/export/commercialista/send", json={"dal": DAL, "al": AL, "to": "studio@example.com"})
        assert r.status_code == 400 and "SMTP" in r.json()["detail"], r.text

    def test_send_invalid_email_422(self):
        r = sess(TOK, ST["cid"]).post(f"{API}/export/commercialista/send", json={"dal": DAL, "al": AL, "to": "not-an-email"})
        assert r.status_code == 422

    def test_send_bad_date_422(self):
        r = sess(TOK, ST["cid"]).post(f"{API}/export/commercialista/send", json={"dal": "01/10/2026", "al": AL, "to": "studio@example.com"})
        assert r.status_code == 422

    def test_send_success(self):
        s = sess(TOK, ST["cid"])
        r = s.put(f"{API}/company/smtp", json=SMTP_OK)
        assert r.status_code == 200, r.text
        size0 = os.path.getsize(SMTP_LOG)
        r = s.post(f"{API}/export/commercialista/send", json={"dal": DAL, "al": AL, "to": "TEST_studio.t26@example.com", "note": "TEST_nota <b>x</b>"})
        assert r.status_code == 200, r.text
        e = r.json()
        assert e["to"].lower() == "test_studio.t26@example.com" and e["attive"] == 3 and e["passive"] == 2 and e["size_kb"] >= 1
        assert "_id" not in e
        time.sleep(1.5)
        with open(SMTP_LOG) as f:
            f.seek(size0)
            log = f.read()
        assert "application/zip" in log, log[:2000]
        assert "TEST_nota &lt;b&gt;x&lt;/b&gt;" in log or "TEST_nota" in log
        d = s.get(f"{API}/export/commercialista", params={"dal": DAL, "al": AL}).json()
        assert d["email"].lower() == "test_studio.t26@example.com"
        assert d["log"][0]["id"] == e["id"]
        ST["log_id"] = e["id"]


class TestModules:
    def test_passive_off(self):
        s = sess(TOK)
        assert s.put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": False, "corrispettivi": True}).status_code == 200
        s.headers["X-Company-Id"] = ST["cid"]
        d = s.get(f"{API}/export/commercialista", params={"dal": DAL, "al": AL}).json()
        assert d["passive"] is None and d["attive"] == 3
        z = zipfile.ZipFile(io.BytesIO(s.get(f"{API}/export/commercialista.zip", params={"dal": DAL, "al": AL}).content))
        assert not any("Fatture_ricevute" in n for n in z.namelist())
        root = z.namelist()[0].split("/")[0]
        assert load_workbook(io.BytesIO(z.read(f"{root}/Riepilogo.xlsx"))).sheetnames == ["Fatture emesse"]

    def test_fatturazione_off_403(self):
        s = sess(TOK)
        assert s.put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": False, "archivio": True, "fatture_attive": True, "fatture_passive": True, "corrispettivi": True}).status_code == 200
        s.headers["X-Company-Id"] = ST["cid"]
        assert s.get(f"{API}/export/commercialista", params={"dal": DAL, "al": AL}).status_code == 403
        assert s.get(f"{API}/export/commercialista.zip", params={"dal": DAL, "al": AL}).status_code == 403
        assert s.post(f"{API}/export/commercialista/send", json={"dal": DAL, "al": AL, "to": "a@example.com"}).status_code == 403
        sess(TOK).put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True, "corrispettivi": True})


class TestEmailerMime:
    def test_default_pdf_and_zip(self):
        import base64
        import emailer
        smtp = {"host": "h", "port": 25, "security": "none", "username": "", "password": "", "from_email": "a@test.it", "from_name": "A"}
        c = base64.b64encode(b"x").decode()
        m = emailer._build(smtp, "b@test.it", "s", "<p>x</p>", None, [{"filename": "a.pdf", "content": c}, {"filename": "b.zip", "content": c, "mime": "application/zip"}])
        types = [p.get_content_type() for p in m.iter_attachments()]
        assert types == ["application/pdf", "application/zip"]

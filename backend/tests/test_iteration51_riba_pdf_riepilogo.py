# Iteration 51: Ri.Ba. distinta PDF (GET /api/riba/distinte/{id}/pdf) and dashboard riepilogo (GET /api/riba/riepilogo)
# Run: pytest tests/test_iteration51_riba_pdf_riepilogo.py -v -n 0
import base64
import io
import json
import os
import random
import struct
import zlib
from datetime import date, timedelta

import pytest
import requests
from pypdf import PdfReader

from test_iteration7_pa_scartate_registro import API, mongo

RUN = str(random.randint(100000, 999999))
TOK, UID = f"test_session_t51_admin_{RUN}", f"test-user-t51-admin-{RUN}"
PIVA = "87" + RUN + "511"
IBAN = "IT60X0542811101000000123456"
T = date.today()
d = lambda n: (T + timedelta(days=n)).isoformat()  # noqa: E731
ST = {}
COLLS = ["invoices", "parties", "payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries", "sdi_events", "audit", "riba_distinte", "riba_effetti", "partite_aperte"]


def sess():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{partita_iva:"{PIVA}"}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def png():
    raw = b"".join(b"\x00" + b"\xaa\x33\x00" * 8 for _ in range(4))
    ch = lambda t, b: struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xffffffff)  # noqa: E731
    data = b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", 8, 4, 8, 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b"")
    return "data:image/png;base64," + base64.b64encode(data).decode()


def inv(pid, data, rate, mp="MP12", price=100):
    s = sess()
    r = s.post(f"{API}/invoices", json={"tipo_documento": "TD01", "data": data, "party_id": pid, "modalita_pagamento": mp, "scadenza": rate[-1][0],
                                        "rate": [{"scadenza": a, "importo": b} for a, b in rate],
                                        "lines": [{"descrizione": "TEST_riga", "quantita": 1, "prezzo_unitario": price, "aliquota": 22}]})
    assert r.status_code == 200, r.text
    iid = r.json()["id"]
    assert s.post(f"{API}/invoices/{iid}/send").status_code == 200
    assert s.post(f"{API}/invoices/{iid}/refresh").status_code == 200
    return iid


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    try:
        yield from _setup()
    finally:
        if not os.environ.get("T51_KEEP"):
            clean()


def _setup():
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t51.{UID}@example.com", name:"TEST_T51 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": f"TEST_T51 Riba {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT", "iban": IBAN})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    s = sess()
    s.put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                       "corrispettivi": True, "contabilita": True})
    c = s.get(f"{API}/company").json()
    c["banche"] = [{**(c.get("banche") or [{}])[0], "nome": "TEST Banca PDF", "iban": IBAN, "abi": "05428", "cab": "11101", "sia": "A1B2C", "predefinita": True}]
    assert s.put(f"{API}/company", json=c).status_code == 200
    r = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": "TEST_T51 Cliente A Srl", "partita_iva": "01234567890", "codice_fiscale": "RSSMRA80A01H501U",
                                       "codice_destinatario": "ABC1234", "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT",
                                       "appoggio_banca": "TEST Intesa", "appoggio_abi": "03069", "appoggio_cab": "09606"})
    assert r.status_code == 200, r.text
    A = r.json()["id"]
    ST.update(P=inv(A, d(-40), [(d(-10), 122)]), O=inv(A, d(-20), [(d(-3), 122)]))
    ST.update(N=inv(A, d(-5), [(d(5), 122)]), Z=inv(A, d(-5), [(d(0), 61)], price=50),
              L=inv(A, d(-5), [(d(15), 122)]), E=inv(A, d(-5), [(d(8), 122)]),
              X=inv(A, d(-5), [(d(20), 122)]), M=inv(A, d(-5), [(d(5), 122)], mp="MP05"))
    yield
    print("KEEP", ST["cid"], TOK) if os.environ.get("T51_KEEP") else None


def riep():
    r = sess().get(f"{API}/riba/riepilogo")
    assert r.status_code == 200, r.text
    return r.json()


class TestRiepilogoEmpty:
    def test_01_before_distinta(self):
        r = riep()
        assert r["mese"] == T.isoformat()[:7] and r["fino_al"] == d(10)
        assert r["insoluti"] == [] and r["in_scadenza"] == [] and r["insoluti_totale"] == 0
        nums = {x["key"].split(":")[0] for x in r["da_presentare"]}
        # P(-10), N(5), Z(0), O(-3), E(8) are within 10 days; L(15), X(20), MP05 M excluded
        assert nums == {ST["P"], ST["N"], ST["Z"], ST["O"], ST["E"]}, nums
        assert r["da_presentare_totale"] == 122 * 4 + 61


class TestDistintaPdf:
    def test_01_create_distinta(self):
        keys = [f"{ST[k]}:1" for k in ("P", "N", "Z", "L")]
        r = sess().post(f"{API}/riba/distinte", json={"banca_iban": IBAN, "data": T.isoformat(), "effetti": keys})
        assert r.status_code == 200, r.text
        ST["D"] = r.json()
        assert ST["D"]["totale"] == 427

    def test_02_pdf_default(self):
        r = sess().get(f"{API}/riba/distinte/{ST['D']['id']}/pdf")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/pdf")
        assert "inline" in r.headers["content-disposition"] and f"Distinta_RIBA_{T.year}_" in r.headers["content-disposition"]
        assert r.content[:4] == b"%PDF"
        txt = " ".join(" ".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages).split())
        ST["txt"] = txt
        for s in (f"TEST_T51 Riba {RUN} Srl", PIVA, "TEST Banca PDF", IBAN, "ABI 05428", "CAB 11101", "SIA A1B2C", ST["D"]["numero_display"],
                  "TEST_T51 Cliente A Srl", "RSSMRA80A01H501U", "TEST Intesa", "03069", "09606", "Totale 4 effetti", "427,00",
                  f"{T.year % 100:02d}{ST['D']['numero']:04d}0001"):
            assert s in txt, (s, txt)

    def test_03_pdf_layout_logo_colore(self):
        s = sess()
        lay = s.get(f"{API}/company/layout").json()
        r = s.put(f"{API}/company/layout", json={**lay, "logo": png(), "colore": "#aa3300"})
        assert r.status_code == 200, r.text
        r = s.get(f"{API}/riba/distinte/{ST['D']['id']}/pdf")
        assert r.status_code == 200
        reader = PdfReader(io.BytesIO(r.content))
        assert len(reader.pages[0].images) >= 1
        assert b"/Image" in r.content or b"/XObject" in r.content

    def test_04_pdf_404(self):
        assert sess().get(f"{API}/riba/distinte/nope/pdf").status_code == 404

    def test_05_pdf_unauth(self):
        assert requests.get(f"{API}/riba/distinte/{ST['D']['id']}/pdf", headers={"X-Company-Id": ST["cid"]}).status_code == 401


class TestRiepilogoAfter:
    def test_01_insoluto_and_summary(self):
        s = sess()
        eff = {e["invoice_id"]: e for e in s.get(f"{API}/riba/distinte/{ST['D']['id']}").json()["effetti"]}
        ST["eff"] = eff
        assert eff[ST["P"]]["stato"] == "maturato"
        r = s.post(f"{API}/riba/effetti/{eff[ST['P']]['id']}/insoluto", json={"data": T.isoformat(), "spese_banca": 3, "spese_cliente": 5, "nuova_scadenza": d(40)})
        assert r.status_code == 200, r.text
        r = riep()
        ST["riep"] = r
        assert [x["id"] for x in r["insoluti"]] == [eff[ST["P"]]["id"]]
        assert r["insoluti_totale"] == 122 and r["insoluti"][0]["insoluto"]["data"] == T.isoformat()
        assert r["insoluti"][0]["cliente"] == "TEST_T51 Cliente A Srl" and r["insoluti"][0]["distinta_numero"] == ST["D"]["numero_display"]

    def test_02_in_scadenza(self):
        r = ST["riep"]
        ids = [x["id"] for x in r["in_scadenza"]]
        assert ST["eff"][ST["N"]]["id"] in ids
        assert ST["eff"][ST["L"]]["id"] not in ids  # scadenza +15
        assert r["in_scadenza_totale"] == round(sum(x["importo"] for x in r["in_scadenza"]), 2)

    def test_03_in_scadenza_today(self):
        # effetto due today: spec "between today and today+10"; matura() turns it maturato -> excluded
        ids = [x["id"] for x in ST["riep"]["in_scadenza"]]
        ST["today_included"] = ST["eff"][ST["Z"]]["id"] in ids
        print("effetto scadenza oggi incluso in in_scadenza:", ST["today_included"])

    def test_04_da_presentare(self):
        r = ST["riep"]
        nums = {x["key"].split(":")[0] for x in r["da_presentare"]}
        assert nums == {ST["O"], ST["E"]}, r["da_presentare"]
        assert r["da_presentare_totale"] == 244
        assert all(x["scadenza"] <= d(10) for x in r["da_presentare"])
        assert any(x["scadenza"] < T.isoformat() for x in r["da_presentare"])  # overdue included

    def test_05_menu_off_forbidden(self):
        s = sess()
        assert s.put(f"{API}/companies/{ST['cid']}/menu", json={"off": ["riba"]}).status_code == 200
        try:
            r = s.get(f"{API}/riba/riepilogo")
            assert r.status_code == 403, r.text
            comps = s.get(f"{API}/companies").json()
            c = next(x for x in comps if x["id"] == ST["cid"])
            assert "riba" in c["menu_off"]
        finally:
            assert s.put(f"{API}/companies/{ST['cid']}/menu", json={"off": []}).status_code == 200
        assert s.get(f"{API}/riba/riepilogo").status_code == 200

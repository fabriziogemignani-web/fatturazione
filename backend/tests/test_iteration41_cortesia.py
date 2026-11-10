# Iteration 41: courtesy invoice manual send (single + bulk), cortesia-inviate, roles, log
# Run: pytest tests/test_iteration41_cortesia.py -v -n 0  (needs local SMTP sink on 127.0.0.1:1025)
import os
import subprocess
import uuid
from datetime import date, timedelta

import pytest
import requests

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ADMIN = {"email": "fabrizio.gemignani@gmail.com", "password": "Fe-Admin-2aOBey8irzL8"}
TODAY = date.today()


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


@pytest.fixture(scope="module")
def ctx():
    s = requests.Session()
    assert s.post(f"{API}/auth/login", json=ADMIN).status_code == 200
    co = piva("0987123461")
    r = s.post(f"{API}/companies", json={"denominazione": "TEST_T41 Cortesia Srl", "partita_iva": co, "codice_fiscale": co, "regime_fiscale": "RF01",
                                         "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    s.headers["X-Company-Id"] = cid
    out = {"s": s, "cid": cid, "users": []}
    try:
        assert s.put(f"{API}/company/smtp", json={"host": "127.0.0.1", "port": 1025, "security": "none", "username": "", "password": "",
                                                  "from_email": "noreply@example.com", "from_name": "TEST_T41"}).status_code == 200
        for key, name, pv, email in [("c1", "TEST_T41 Alfa Srl", piva("0123456780"), "alfa41@example.com"),
                                     ("c3", "TEST_T41 NoMail Srl", piva("0888999110"), "")]:
            r = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": name, "partita_iva": pv, "codice_fiscale": pv, "codice_destinatario": "ABC1234",
                                               "email": email, "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"})
            assert r.status_code == 200, r.text
            out[key] = r.json()["id"]

        def mk(pid, send=True):
            r = s.post(f"{API}/invoices", json={"tipo_documento": "TD01", "data": (TODAY - timedelta(days=2)).isoformat(), "party_id": pid, "modalita_pagamento": "MP05",
                                                "scadenza": (TODAY + timedelta(days=30)).isoformat(),
                                                "lines": [{"descrizione": "TEST riga", "quantita": 1, "prezzo_unitario": 100, "aliquota": 22}]})
            assert r.status_code == 200, r.text
            iid = r.json()["id"]
            if send:
                assert s.post(f"{API}/invoices/{iid}/send").status_code == 200
                assert s.post(f"{API}/invoices/{iid}/refresh").json()["status"] == "consegnata"
            return iid
        out["i1"], out["i2"], out["i3"] = mk(out["c1"]), mk(out["c1"]), mk(out["c3"])
        out["draft"] = mk(out["c1"], send=False)
        yield out
    finally:
        mongo(f'["invoices","parties","payments","coa_entries","coa_accounts","coa_causali","coa_iva","sdi_events","audit","com_log"].forEach(k=>db[k].deleteMany({{company_id:"{cid}"}})); '
              f'db.counters.deleteMany({{key:{{$regex:"{cid}"}}}}); db.users.updateMany({{}},{{$pull:{{company_ids:"{cid}"}}}}); db.companies.deleteOne({{id:"{cid}"}});')
        for uid in out["users"]:
            mongo(f'db.users.deleteOne({{user_id:"{uid}"}}); db.user_sessions.deleteMany({{user_id:"{uid}"}});')


def cortesia_logs(ctx):
    return ctx["s"].get(f"{API}/comunicazioni/log", params={"tipo": "cortesia", "limit": 100}).json()["log"]


def test_inviate_initially_empty(ctx):
    r = ctx["s"].get(f"{API}/comunicazioni/cortesia-inviate")
    assert r.status_code == 200 and r.json() == []


def test_single_default_recipient(ctx):
    r = ctx["s"].post(f"{API}/comunicazioni/cortesia/{ctx['i1']}", json={})
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}
    lg = cortesia_logs(ctx)
    assert lg[0]["to"] == "alfa41@example.com" and lg[0]["esito"] == "ok" and lg[0]["tipo"] == "cortesia" and lg[0]["auto"] is False
    assert ctx["i1"] in ctx["s"].get(f"{API}/comunicazioni/cortesia-inviate").json()


def test_single_no_body(ctx):
    r = ctx["s"].post(f"{API}/comunicazioni/cortesia/{ctx['i1']}")
    assert r.status_code == 200, r.text


def test_single_override_recipient(ctx):
    r = ctx["s"].post(f"{API}/comunicazioni/cortesia/{ctx['i2']}", json={"to": "  altro41@example.com "})
    assert r.status_code == 200, r.text
    assert cortesia_logs(ctx)[0]["to"] == "altro41@example.com"


@pytest.mark.parametrize("bad", ["nope", "a@b", "a@b.it,c@d.it", "a b@c.it"])
def test_single_invalid_email(ctx, bad):
    r = ctx["s"].post(f"{API}/comunicazioni/cortesia/{ctx['i1']}", json={"to": bad})
    assert r.status_code in (400, 422), r.text
    print(bad, r.status_code, r.text[:200])


def test_single_draft_and_missing(ctx):
    r = ctx["s"].post(f"{API}/comunicazioni/cortesia/{ctx['draft']}", json={})
    assert r.status_code == 400 and "trasmessa" in r.json()["detail"]
    assert ctx["s"].post(f"{API}/comunicazioni/cortesia/{uuid.uuid4()}", json={}).status_code == 404


def test_single_no_email_client(ctx):
    r = ctx["s"].post(f"{API}/comunicazioni/cortesia/{ctx['i3']}", json={})
    assert r.status_code == 400 and "Cliente senza email o PEC" in r.json()["detail"]
    assert ctx["i3"] not in ctx["s"].get(f"{API}/comunicazioni/cortesia-inviate").json()


def test_bulk_escludi(ctx):
    ids = [ctx["i1"], ctx["i2"], ctx["i3"], ctx["draft"]]
    r = ctx["s"].post(f"{API}/comunicazioni/cortesia-massiva", json={"ids": ids, "escludi_inviate": True})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["inviate"] == 0
    motivi = sorted(x["motivo"] for x in d["saltate"])
    assert motivi == ["già inviata", "già inviata", "non trasmessa allo SDI"], d
    assert len(d["errori"]) == 1 and d["errori"][0]["errore"] == "Cliente senza email o PEC in anagrafica"
    assert d["errori"][0]["cliente"] == "TEST_T41 NoMail Srl"


def test_bulk_no_escludi(ctx):
    r = ctx["s"].post(f"{API}/comunicazioni/cortesia-massiva", json={"ids": [ctx["i1"], ctx["i2"]], "escludi_inviate": False})
    assert r.status_code == 200 and r.json()["inviate"] == 2 and r.json()["saltate"] == [] and r.json()["errori"] == []


def test_bulk_validation(ctx):
    assert ctx["s"].post(f"{API}/comunicazioni/cortesia-massiva", json={"ids": []}).status_code == 422
    r = ctx["s"].post(f"{API}/comunicazioni/cortesia-massiva", json={"ids": [str(uuid.uuid4())]})
    assert r.status_code == 200 and r.json() == {"inviate": 0, "saltate": [], "errori": []}


def test_cross_tenant_ids_ignored(ctx):
    # invoice of another company (seed test data company) must not be sent from this tenant
    other = "4c1ebc47-788b-4fdf-bc18-84b6adbc75af"
    r = ctx["s"].post(f"{API}/comunicazioni/cortesia-massiva", json={"ids": [other]})
    assert r.status_code == 200 and r.json()["inviate"] == 0
    assert ctx["s"].post(f"{API}/comunicazioni/cortesia/{other}", json={}).status_code == 404


def test_operatore_403(ctx):
    s = ctx["s"]
    email = f"test.user.t41{uuid.uuid4().hex[:6]}@example.com"
    requests.post(f"{API}/auth/register", json={"name": "TEST_T41 Operatore", "email": email, "password": "TestPass-123456"})
    uid = next(u["user_id"] for u in s.get(f"{API}/users").json() if u["email"] == email)
    ctx["users"].append(uid)
    assert s.patch(f"{API}/users/{uid}", json={"status": "approved", "role": "operatore", "company_ids": [ctx["cid"]]}).status_code == 200
    o = requests.Session()
    assert o.post(f"{API}/auth/login", json={"email": email, "password": "TestPass-123456"}).status_code == 200
    o.headers["X-Company-Id"] = ctx["cid"]
    assert o.post(f"{API}/comunicazioni/cortesia/{ctx['i1']}", json={}).status_code == 403
    assert o.post(f"{API}/comunicazioni/cortesia-massiva", json={"ids": [ctx["i1"]]}).status_code == 403
    r = o.get(f"{API}/comunicazioni/cortesia-inviate")
    print("operatore cortesia-inviate:", r.status_code)
    assert r.status_code == 200


def test_unauth(ctx):
    assert requests.get(f"{API}/comunicazioni/cortesia-inviate").status_code == 401
    assert requests.post(f"{API}/comunicazioni/cortesia-massiva", json={"ids": ["x"]}).status_code == 401

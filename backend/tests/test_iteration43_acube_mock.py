# Iteration 43: Conservazione -> A-Cube Preservation API flow with a MOCKED A-Cube (local HTTP server), app run in-process (ASGI).
# Covers: invia (login, legal entity GET/POST, multipart upload, /send with metadata), skip of internal-only types, error storage,
# aggiorna (status + receipt PDF), GET /ricevuta, config/test, usa_sdi credentials from an A-Cube SDI connection.
# Run with: REACT_APP_BACKEND_URL=... pytest tests/test_iteration43_acube_mock.py -n 0
import asyncio
import json
import os
import subprocess
import sys
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import httpx  # noqa: E402
import server  # noqa: E402
import conservazione as cons  # noqa: E402
import sdi_providers as sdip  # noqa: E402

PA = "01234567897"
PY = date.today().year - 1
UID, TOK = "test-user-t43m-admin", "test_session_t43m_admin"
CALLS = []
STATE = {"fail_send_slug": None, "le": []}
PDF = b"%PDF-1.4 TEST RECEIPT"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _reply(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _do(self, m):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        CALLS.append({"m": m, "p": self.path, "h": dict(self.headers), "b": body})
        p = self.path.split("?")[0]
        if p == "/login":
            return self._reply(200, {"token": "MOCKTOKEN"})
        if p == "/legal-entities/it":
            if m == "GET":
                return self._reply(200, {"hydra:member": STATE["le"]})
            STATE["le"].append(json.loads(body))
            return self._reply(201, json.loads(body))
        parts = p.strip("/").split("/")  # preserved-documents it slug [uuid] [send|receipt]
        if parts[:2] == ["preserved-documents", "it"]:
            slug = parts[2]
            if len(parts) == 3 and m == "POST":
                return self._reply(201, {"uuid": f"uuid-{slug}-{len(CALLS)}"})
            if len(parts) == 5 and parts[4] == "send":
                if STATE["fail_send_slug"] == slug:
                    return self._reply(422, {"message": "metadata non validi TEST"})
                return self._reply(200, {"status": "sent_metadata", "status_history": [{"status": "sent_metadata"}], "preserved_object_id": "po-1"})
            if len(parts) == 4 and m == "GET":
                return self._reply(200, {"status": "stored", "status_history": [{"status": "stored"}]})
            if len(parts) == 5 and parts[4] == "receipt":
                return self._reply(200, PDF, "application/pdf")
        return self._reply(404, {"message": "not found"})

    def do_GET(self):
        self._do("GET")

    def do_POST(self):
        self._do("POST")


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


def clean():
    mongo(f'db.companies.find({{partita_iva:"{PA}", denominazione:/^TEST_T43M/}}).forEach(c=>{{["invoices","passive_invoices","parties","payments","coa_entries","f24_versamenti","corrispettivi","sdi_events","audit","cons_docs"].forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


S = {}


@pytest.fixture(scope="module")
def env():
    clean()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    old = (dict(cons.BASE), sdip.ACUBE_LOGIN)
    cons.BASE.update({"sandbox": base, "production": base})
    sdip.ACUBE_LOGIN = base + "/login"
    sdip._tokens.clear()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.{UID}@example.com", name:"TEST_t43m", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    loop = asyncio.new_event_loop()
    cl = httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://t", headers={"Authorization": f"Bearer {TOK}"}, timeout=60)

    def call(m, url, **kw):
        if S.get("cid"):
            kw.setdefault("headers", {})["X-Company-Id"] = S["cid"]
        return loop.run_until_complete(cl.request(m, "/api" + url, **kw))
    r = call("POST", "/companies", json={"denominazione": "TEST_T43M Srl", "partita_iva": PA, "codice_fiscale": PA, "regime_fiscale": "RF01",
                                         "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    S["cid"] = r.json()["id"]
    p = call("POST", "/parties", json={"tipo": "cliente", "denominazione": "TEST_T43M Cliente", "partita_iva": "02345670481", "codice_fiscale": "02345670481",
                                       "codice_destinatario": "ABC1234", "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"}).json()
    inv = call("POST", "/invoices", json={"data": f"{PY}-02-10", "party_id": p["id"], "lines": [{"descrizione": "TEST", "quantita": 1, "prezzo_unitario": 100, "aliquota": 22}]}).json()
    assert call("POST", f"/invoices/{inv['id']}/send").status_code == 200
    mongo(f'db.f24_versamenti.insertOne({{company_id:"{S["cid"]}", key:"IVA-{PY}-05", codice:"6005", importo:50, data:"{PY}-06-16"}});')
    for tipo, rif in (("fattura_emessa", inv["id"]), ("registro_iva_vendite", str(PY)), ("libro_giornale", str(PY)), ("corrispettivi", str(PY)), ("f24", f"IVA-{PY}-05")):
        r = call("POST", "/conservazione/archivia", json={"tipo": tipo, "anno": PY, "rif": [rif]})
        assert r.status_code == 200 and r.json()["archiviati"] == 1, r.text
    S["docs"] = {d["tipo"]: d for d in call("GET", "/conservazione", params={"anno": PY}).json()["documenti"]}
    yield call
    loop.run_until_complete(cl.aclose())
    loop.close()
    srv.shutdown()
    cons.BASE.clear()
    cons.BASE.update(old[0])
    sdip.ACUBE_LOGIN = old[1]
    clean()


def test_config_and_test(env):
    r = env("PUT", "/conservazione/config", json={"usa_sdi": False, "ambiente": "sandbox", "email": "test_acube@example.com", "password": "Pw-TEST-1"})
    assert r.status_code == 200, r.text
    CALLS.clear()
    r = env("POST", "/conservazione/config/test")
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    login = next(c for c in CALLS if c["p"] == "/login")
    assert json.loads(login["b"]) == {"email": "test_acube@example.com", "password": "Pw-TEST-1", "environment": "sandbox"}
    assert any(c["m"] == "POST" and c["p"] == "/legal-entities/it" for c in CALLS)
    assert json.loads(next(c for c in CALLS if c["m"] == "POST" and c["p"] == "/legal-entities/it")["b"])["fiscal_id"] == PA
    assert env("GET", "/conservazione/config").json()["legal_entity"] == PA


def test_invia(env):
    CALLS.clear()
    STATE["fail_send_slug"] = "libro-giornale"
    ids = [d["id"] for d in S["docs"].values()]
    r = env("POST", "/conservazione/invia", json={"ids": ids})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["inviati"] == 2 and j["saltati"] == 2 and len(j["errori"]) == 1, j  # corrispettivi + f24 skipped; libro giornale fails
    assert "metadata non validi TEST" in j["errori"][0]["errore"]
    # legal entity already registered -> no GET/POST legal-entities this time
    assert not any(c["p"].startswith("/legal-entities") for c in CALLS)
    up = [c for c in CALLS if c["m"] == "POST" and c["p"].count("/") == 3]
    assert sorted(c["p"] for c in up) == ["/preserved-documents/it/fatture", "/preserved-documents/it/libro-giornale", "/preserved-documents/it/registro-iva-vendite"]
    assert all(c["h"]["Content-Type"].startswith("multipart/form-data") and c["h"]["Authorization"] == "Bearer MOCKTOKEN" for c in up)
    sends = {c["p"].split("/")[3]: json.loads(c["b"]) for c in CALLS if c["p"].endswith("/send")}
    f = sends["fatture"]
    assert f["tipologia_di_flusso"] == "U" and f["numero_fattura"] and f["data_fattura"] == f"{PY}-02-10"
    assert f["mittente"]["codice_fiscale_partita_iva"] == PA and f["destinatario"]["codice_fiscale_partita_iva"] == "02345670481"
    assert f["versione_del_documento"] == "1" and f["soggetto_che_effettua_la_registrazione"]["codice_fiscale_partita_iva"] == PA and f["oggetto"]
    rv = sends["registro-iva-vendite"]
    assert rv["numero_registrazione_documento"] == f"registro_iva_vendite-{PY}" and rv["data_registrazione_documento"]
    docs = {d["tipo"]: d for d in env("GET", "/conservazione", params={"anno": PY}).json()["documenti"]}
    assert docs["fattura_emessa"]["acube"]["status"] == "sent_metadata" and docs["fattura_emessa"]["acube"]["sent_metadata_at"]
    assert docs["libro_giornale"]["acube"]["error"] and docs["libro_giornale"]["acube"]["uuid"]
    assert docs["corrispettivi"]["acube"] is None and docs["f24"]["acube"] is None
    # retry: libro giornale re-sends metadata without re-upload; already sent ones skipped
    STATE["fail_send_slug"] = None
    CALLS.clear()
    j = env("POST", "/conservazione/invia", json={"ids": ids}).json()
    assert j["inviati"] == 1 and j["saltati"] == 4, j
    assert not any(c["m"] == "POST" and c["p"].count("/") == 3 for c in CALLS)


def test_aggiorna_and_ricevuta(env):
    did = S["docs"]["fattura_emessa"]["id"]
    assert env("GET", f"/conservazione/{did}/ricevuta").status_code == 404
    CALLS.clear()
    j = env("POST", "/conservazione/aggiorna", json={"ids": []}).json()
    assert j["aggiornati"] == 3 and j["conservati"] == 3 and j["errori"] == [], j
    rc = [c for c in CALLS if c["p"].endswith("/receipt")]
    assert len(rc) == 3 and all(c["h"]["Accept"] == "application/pdf" for c in rc)
    r = env("GET", f"/conservazione/{did}/ricevuta")
    assert r.status_code == 200 and r.content == PDF and r.headers["content-type"] == "application/pdf"
    lst = env("GET", "/conservazione", params={"anno": PY}).json()["documenti"]
    assert all("receipt_b64" not in (d.get("acube") or {}) for d in lst)
    # already stored docs not polled again
    CALLS.clear()
    assert env("POST", "/conservazione/aggiorna", json={"ids": []}).json()["aggiornati"] == 0


def test_usa_sdi(env):
    assert env("PUT", "/conservazione/config", json={"usa_sdi": True, "ambiente": "sandbox", "email": ""}).status_code == 422
    enc = server.FERNET.encrypt(b"Sdi-Pw-TEST").decode()
    mongo(f'db.companies.updateOne({{id:"{S["cid"]}"}}, {{$set:{{sdi:{{provider:"acube", ambiente:"sandbox", email:"sdi_test@example.com", password_enc:"{enc}"}}}}}});')
    r = env("PUT", "/conservazione/config", json={"usa_sdi": True, "ambiente": "sandbox", "email": ""})
    assert r.status_code == 200 and r.json()["usa_sdi"] is True and r.json()["sdi_acube"] is True, r.text
    sdip._tokens.clear()
    CALLS.clear()
    assert env("POST", "/conservazione/config/test").status_code == 200
    assert json.loads(next(c for c in CALLS if c["p"] == "/login")["b"])["email"] == "sdi_test@example.com"

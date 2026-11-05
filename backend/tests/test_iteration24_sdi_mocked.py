# Iteration 24 (in-process, mocked provider): monkeypatch sdi_providers.send/notifications/received and drive the
# FastAPI app via httpx ASGITransport. Verifies send stores sdi_provider/sdi_id, refresh maps RC/NS/MC, seen
# notifications ignored, received XML imported as origine 'sdi' with duplicates skipped, background sync.
# Run with: pytest test_iteration24_sdi_mocked.py -n 0
import asyncio
import os
import sys
import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server  # noqa: E402
import sdi_providers as sdip  # noqa: E402
from passive import demo_xmls  # noqa: E402
from test_iteration7_pa_scartate_registro import mongo, party, inv  # noqa: E402

PA = "86999999242"
UID, TOK = "test-user-t24m-admin", "test_session_t24m_admin"
LOOP = asyncio.new_event_loop()
ST = {"notes": {}, "sent": [], "received": []}


def run(coro):
    return LOOP.run_until_complete(coro)


def clean():
    mongo(f'db.companies.find({{partita_iva:"{PA}"}}).forEach(c=>{{db.invoices.deleteMany({{company_id:c.id}}); db.passive_invoices.deleteMany({{company_id:c.id}});'
          f'db.parties.deleteMany({{company_id:c.id}}); db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


async def req(method, path, **kw):
    h = {"Authorization": f"Bearer {TOK}", **({"X-Company-Id": ST["cid"]} if ST.get("cid") else {})}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://t") as c:
        return await c.request(method, f"/api{path}", headers=h, **kw)


def call(method, path, **kw):
    return run(req(method, path, **kw))


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t24m@example.com", name:"TEST_t24m", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = call("POST", "/companies", json={"denominazione": "TEST_T24M Srl", "partita_iva": PA, "codice_fiscale": PA, "regime_fiscale": "RF01",
                                         "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    ST["company"] = r.json()
    r = call("POST", "/parties", json=party("TEST_T24M Cliente"))
    ST["pid"] = r.json()["id"]
    r = call("PUT", "/company/sdi", json={"provider": "acube", "ambiente": "sandbox", "email": "t24m@example.com", "password": "TEST_pw"})
    assert r.status_code == 200, r.text
    yield
    clean()


@pytest.fixture(autouse=True)
def mocks(monkeypatch):
    async def send(cfg, xml):
        assert cfg["provider"] == "acube" and cfg["password"] == "TEST_pw" and "<FatturaElettronica" in xml or "FatturaElettronica" in xml
        rid = f"uuid-{len(ST['sent']) + 1}"
        ST["sent"].append(rid)
        return rid

    async def notifications(cfg, rid):
        return ST["notes"].get(rid, [])

    async def received(cfg, piva):
        assert piva == PA
        return ST["received"]

    monkeypatch.setattr(sdip, "send", send)
    monkeypatch.setattr(sdip, "notifications", notifications)
    monkeypatch.setattr(sdip, "received", received)


def new_sent():
    r = call("POST", "/invoices", json=inv(ST["pid"]))
    assert r.status_code == 200, r.text
    iid = r.json()["id"]
    r = call("POST", f"/invoices/{iid}/send")
    assert r.status_code == 200, r.text
    return r.json()


def note(t, u, at="2026-01-10T10:00:00"):
    return {"type": t, "message": f"msg {t}", "at": at, "uuid": u}


class TestMocked:
    def test_01_send_stores_provider(self):
        d = new_sent()
        assert d["status"] == "inviata" and d["sdi_provider"] == "acube" and d["sdi_id"] == ST["sent"][-1]
        assert d["sdi_ambiente"] == "sandbox" and "A-Cube" in d["sdi_message"]
        ST["inv_rc"] = d

    def test_02_refresh_no_notes_400(self):
        r = call("POST", f"/invoices/{ST['inv_rc']['id']}/refresh")
        assert r.status_code == 400 and "Nessuna nuova notifica" in r.text

    def test_03_refresh_rc_consegnata_then_seen(self):
        ST["notes"][ST["inv_rc"]["sdi_id"]] = [note("RC", "n-rc-1")]
        r = call("POST", f"/invoices/{ST['inv_rc']['id']}/refresh")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "consegnata" and r.json()["sdi_notifica"] == "RC"
        r = call("POST", f"/invoices/{ST['inv_rc']['id']}/refresh")
        assert r.status_code == 400 and "Nessuna nuova notifica" in r.text

    def test_04_ns_scartata_and_resend(self):
        d = new_sent()
        ST["notes"][d["sdi_id"]] = [note("NS", "n-ns-1")]
        r = call("POST", f"/invoices/{d['id']}/refresh")
        assert r.status_code == 200 and r.json()["status"] == "scartata"
        r = call("POST", f"/invoices/{d['id']}/send")
        assert r.status_code == 200 and r.json()["status"] == "inviata" and r.json()["sdi_id"] != d["sdi_id"]
        assert r.json()["sdi_seen"] == []

    def test_05_mc_mancata_consegna(self):
        d = new_sent()
        ST["notes"][d["sdi_id"]] = [note("MC", "n-mc-1")]
        r = call("POST", f"/invoices/{d['id']}/refresh")
        assert r.status_code == 200 and r.json()["status"] == "mancata_consegna"

    def test_06_received_imported_as_sdi_dupes_skipped(self):
        xmls = demo_xmls(ST["company"], 2)
        ST["received"] = [("rid-1", xmls[0]), ("rid-2", xmls[1])]
        r = call("POST", "/passive/sdi-sync")
        assert r.status_code == 200, r.text
        assert len(r.json()["ricevute"]) >= 2
        r2 = call("POST", "/passive/sdi-sync")
        assert r2.status_code == 200 and r2.json()["ricevute"] == []
        p = call("GET", "/passive").json()
        items = p if isinstance(p, list) else p.get("items", [])
        sdi = [x for x in items if x["origine"] == "sdi"]
        assert len(sdi) == len(r.json()["ricevute"]) and all(x["file_name"].startswith("SDI_rid-") for x in sdi)

    def test_07_background_sync_company(self):
        d = new_sent()
        ST["notes"][d["sdi_id"]] = [note("RC", "n-bg-1")]
        comp = run(server.db.companies.find_one({"id": ST["cid"]}, server.COMPANY_PROJ))
        run(server._sdi_sync_company(comp))
        assert call("GET", f"/invoices/{d['id']}").json()["status"] == "consegnata"
        s = call("GET", "/company/sdi").json()
        assert s["last_sync_at"] and s["last_sync_error"] is None

    def test_08_refresh_after_provider_switch(self):
        d = new_sent()
        assert call("PUT", "/company/sdi", json={"provider": "simulato"}).status_code == 200
        r = call("POST", f"/invoices/{d['id']}/refresh")
        assert r.status_code == 400 and "A-Cube" in r.text

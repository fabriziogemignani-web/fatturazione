# Iteration 25: scheduled SDI reception (GET/PUT /api/company/sdi-schedule, POST /run), validation, RBAC,
# next_run_at in Europe/Rome, simulated outcomes on run, real-provider error, background loop claim.
# Run with: pytest test_iteration25_sdi_schedule.py -n 0
import json
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
import requests
from test_iteration7_pa_scartate_registro import API, mongo, party, inv

ROME = ZoneInfo("Europe/Rome")
PA = "86999999251"
USERS = (("test-user-t25-admin", "test_session_t25_admin", "admin"), ("test-user-t25-co", "test_session_t25_co", "contabile"),
         ("test-user-t25-op", "test_session_t25_op", "operatore"))
ST = {}
BASE = {"enabled": True, "modo": "intervallo", "ogni_minuti": 30, "dalle": "07:00", "alle": "20:00",
        "orari": ["08:00"], "giorni": [0, 1, 2, 3, 4, 5, 6], "passive": True, "notifiche": True}


def sess(tok):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


ADM = lambda: sess(USERS[0][1])  # noqa: E731
CO = lambda: sess(USERS[1][1])  # noqa: E731
OP = lambda: sess(USERS[2][1])  # noqa: E731


def clean():
    ids = json.dumps([u[0] for u in USERS])
    mongo(f'db.companies.find({{partita_iva:"{PA}"}}).forEach(c=>{{db.invoices.deleteMany({{company_id:c.id}}); db.passive_invoices.deleteMany({{company_id:c.id}});'
          f'db.parties.deleteMany({{company_id:c.id}}); db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:{ids}}}}}); db.user_sessions.deleteMany({{user_id:{{$in:{ids}}}}});')


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    for uid, tok, role in USERS:
        mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.{uid}@example.com", name:"TEST_{uid}", picture:"", role:"{role}", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
              f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = ADM().post(f"{API}/companies", json={"denominazione": "TEST_T25 Sched Srl", "partita_iva": PA, "codice_fiscale": PA, "regime_fiscale": "RF01",
                                            "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    mongo(f'db.users.updateMany({{user_id:{{$in:["{USERS[1][0]}","{USERS[2][0]}"]}}}}, {{$set:{{company_ids:["{ST["cid"]}"]}}}});')
    r = ADM().post(f"{API}/parties", json=party("TEST_T25 Cliente"))
    assert r.status_code == 200, r.text
    ST["pid"] = r.json()["id"]
    yield
    clean()


def sent_inv():
    r = ADM().post(f"{API}/invoices", json=inv(ST["pid"]))
    assert r.status_code == 200, r.text
    iid = r.json()["id"]
    r = CO().post(f"{API}/invoices/{iid}/send")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "inviata", r.json()["status"]
    return iid


def parse(s):
    return datetime.fromisoformat(s).astimezone(ROME)


class TestSchedule:
    def test_01_default_get_any_role(self):
        for s in (ADM(), CO(), OP()):
            r = s.get(f"{API}/company/sdi-schedule")
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["enabled"] is False and d["provider"] == "simulato"
            assert d["descrizione"] == "Ricezione automatica disattivata"
            assert d.get("next_run_at") is None

    @pytest.mark.parametrize("patch", [
        {"modo": "orari", "orari": ["25:00"]}, {"giorni": []}, {"dalle": "20:00", "alle": "07:00"},
        {"dalle": "10:00", "alle": "10:00"}, {"passive": False, "notifiche": False}, {"ogni_minuti": 4},
        {"modo": "orari", "orari": []}, {"giorni": [7]}, {"dalle": "7:00"}])
    def test_02_validation_422(self, patch):
        r = ADM().put(f"{API}/company/sdi-schedule", json=BASE | patch)
        assert r.status_code == 422, (patch, r.status_code, r.text)

    def test_03_rbac_put(self):
        for s in (CO(), OP()):
            assert s.put(f"{API}/company/sdi-schedule", json=BASE).status_code == 403

    def test_04_orari_monday_only(self):
        r = ADM().put(f"{API}/company/sdi-schedule", json=BASE | {"modo": "orari", "orari": ["08:00"], "giorni": [0]})
        assert r.status_code == 200, r.text
        d = r.json()
        n = parse(d["next_run_at"])
        now = datetime.now(ROME)
        assert n.weekday() == 0 and (n.hour, n.minute) == (8, 0) and n > now and n - now <= timedelta(days=7), n
        assert "08:00" in d["descrizione"] and "lun" in d["descrizione"]
        g = CO().get(f"{API}/company/sdi-schedule").json()
        assert g["next_run_at"] == d["next_run_at"] and g["modo"] == "orari" and g["giorni"] == [0]

    def test_05_intervallo_30(self):
        r = ADM().put(f"{API}/company/sdi-schedule", json=BASE)
        assert r.status_code == 200, r.text
        d = r.json()
        n = parse(d["next_run_at"])
        now = datetime.now(ROME)
        assert n > now and n.minute in (0, 30) and (7, 0) <= (n.hour, n.minute) <= (20, 0), n
        if (7, 0) <= (now.hour, now.minute) < (19, 30):
            assert n - now <= timedelta(minutes=30), (n, now)
        assert d["descrizione"].startswith("Ogni 30 minuti dalle 07:00 alle 20:00")

    def test_06_disabled_null(self):
        r = ADM().put(f"{API}/company/sdi-schedule", json=BASE | {"enabled": False})
        assert r.status_code == 200 and r.json()["next_run_at"] is None
        assert ADM().get(f"{API}/company/sdi-schedule").json()["enabled"] is False

    def test_07_run_rbac(self):
        assert OP().post(f"{API}/company/sdi-schedule/run").status_code == 403

    def test_08_run_simulato_outcome(self):
        iid = sent_inv()
        r = CO().post(f"{API}/company/sdi-schedule/run")
        assert r.status_code == 200, r.text
        run = r.json()["run"]
        assert run["simulato"] is True and run["error"] is None and run["notifiche"] >= 1 and run["fatture"] == 0
        assert run["manual_by"] == "TEST_test-user-t25-co"
        assert r.json()["schedule"]["last_run"]["at"] == run["at"]
        st = ADM().get(f"{API}/invoices/{iid}").json()["status"]
        assert st in ("consegnata", "mancata_consegna", "scartata"), st
        # second run: nothing left in 'inviata'
        r = ADM().post(f"{API}/company/sdi-schedule/run")
        assert r.json()["run"]["notifiche"] == 0

    def test_09_put_preserves_last_run(self):
        last = ADM().get(f"{API}/company/sdi-schedule").json()["last_run"]
        assert last
        r = ADM().put(f"{API}/company/sdi-schedule", json=BASE)
        assert r.json()["last_run"] == last

    def test_10_background_loop(self):
        ADM().put(f"{API}/company/sdi-schedule", json=BASE)
        iid = sent_inv()
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}}, {{$set:{{"sdi_schedule.next_run_at":"{past}"}}}});')
        deadline = time.time() + 140
        d = None
        while time.time() < deadline:
            time.sleep(10)
            d = ADM().get(f"{API}/company/sdi-schedule").json()
            if d["next_run_at"] != past and d["last_run"] and d["last_run"]["manual_by"] is None:
                break
        assert d["next_run_at"] != past and d["next_run_at"] > datetime.now(timezone.utc).isoformat(), d
        assert d["last_run"]["manual_by"] is None and d["last_run"]["notifiche"] >= 1, d["last_run"]
        assert ADM().get(f"{API}/invoices/{iid}").json()["status"] != "inviata"

    def test_11_real_provider_fake_creds_error(self):
        r = ADM().put(f"{API}/company/sdi", json={"provider": "openapi", "ambiente": "sandbox", "token": "TEST_fake_token"})
        assert r.status_code == 200, r.text
        r = ADM().post(f"{API}/company/sdi-schedule/run", timeout=90)
        assert r.status_code == 200, r.text
        run = r.json()["run"]
        print("REAL RUN", run)
        assert run["simulato"] is False
        assert run["error"] and "imprevisto" not in run["error"], run
        assert r.json()["schedule"]["provider"] == "openapi"
        ADM().put(f"{API}/company/sdi", json={"provider": "simulato"})

    def test_12_moduli_off_run(self):
        r = ADM().put(f"{API}/company/sdi-schedule", json=BASE | {"enabled": False})
        assert r.status_code == 200

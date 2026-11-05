# Iteration 24: SDI provider config (Openapi.it / A-Cube) - GET/PUT /api/company/sdi, POST /api/company/sdi/test,
# secret never returned, RBAC (admin only for PUT/test), real-provider errors on send / passive sdi-sync,
# simulato regression (send/refresh/sdi-sync). Run with: pytest test_iteration24_sdi_providers.py -n 0
import json
import pytest
import requests
from test_iteration7_pa_scartate_registro import API, mongo, party, inv

PA = "86999999241"
USERS = (("test-user-t24-admin", "test_session_t24_admin", "admin"), ("test-user-t24-co", "test_session_t24_co", "contabile"),
         ("test-user-t24-op", "test_session_t24_op", "operatore"))
ST = {}
SECRET = "TEST_SECRET_TOKEN_abc123"


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
    r = ADM().post(f"{API}/companies", json={"denominazione": "TEST_T24 Sdi Srl", "partita_iva": PA, "codice_fiscale": PA, "regime_fiscale": "RF01",
                                            "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    mongo(f'db.users.updateMany({{user_id:{{$in:["{USERS[1][0]}","{USERS[2][0]}"]}}}}, {{$set:{{company_ids:["{ST["cid"]}"]}}}});')
    r = ADM().post(f"{API}/parties", json=party("TEST_T24 Cliente"))
    assert r.status_code == 200, r.text
    ST["pid"] = r.json()["id"]
    yield
    clean()


def new_inv():
    r = ADM().post(f"{API}/invoices", json=inv(ST["pid"]))
    assert r.status_code == 200, r.text
    return r.json()["id"]


class TestSdiConfig:
    def test_01_default_simulato(self):
        r = CO().get(f"{API}/company/sdi")
        assert r.status_code == 200
        d = r.json()
        assert d["provider"] == "simulato" and d["ambiente"] == "sandbox" and d["has_token"] is False

    def test_02_test_when_simulato_400(self):
        r = ADM().post(f"{API}/company/sdi/test")
        assert r.status_code == 400 and "simulato" in r.json()["detail"]

    def test_03_rbac(self):
        for s in (CO(), OP()):
            assert s.put(f"{API}/company/sdi", json={"provider": "openapi", "token": "x"}).status_code == 403
            assert s.post(f"{API}/company/sdi/test").status_code == 403
        assert OP().get(f"{API}/company/sdi").status_code == 200

    def test_04_openapi_without_token_field_error(self):
        r = ADM().put(f"{API}/company/sdi", json={"provider": "openapi", "ambiente": "sandbox"})
        assert r.status_code == 400, r.text
        assert "token" in r.text.lower()

    def test_05_invalid_provider_422(self):
        assert ADM().put(f"{API}/company/sdi", json={"provider": "aruba"}).status_code == 422
        assert ADM().put(f"{API}/company/sdi", json={"provider": "openapi", "ambiente": "live", "token": "x"}).status_code == 422

    def test_06_openapi_save_token_not_leaked(self):
        r = ADM().put(f"{API}/company/sdi", json={"provider": "openapi", "ambiente": "sandbox", "token": SECRET})
        assert r.status_code == 200, r.text
        assert r.json()["has_token"] is True and r.json()["label"] == "Openapi.it" and SECRET not in r.text
        for p in ("/company/sdi", "/company", "/companies"):
            g = ADM().get(f"{API}{p}")
            assert g.status_code == 200, p
            assert SECRET not in g.text and "token_enc" not in g.text and "password_enc" not in g.text, p
        assert ADM().get(f"{API}/company/sdi").json()["provider"] == "openapi"

    def test_07_keep_token_when_blank(self):
        r = ADM().put(f"{API}/company/sdi", json={"provider": "openapi", "ambiente": "sandbox", "token": None})
        assert r.status_code == 200 and r.json()["has_token"] is True

    def test_08_openapi_test_fake_400(self):
        r = ADM().post(f"{API}/company/sdi/test", timeout=90)
        assert r.status_code == 400, r.text
        assert "Collegamento a Openapi.it non riuscito" in r.json()["detail"], r.text
        print("openapi test:", r.json()["detail"])

    def test_09_openapi_send_fails_stays_bozza(self):
        iid = new_inv()
        r = CO().post(f"{API}/invoices/{iid}/send", timeout=90)
        assert r.status_code == 400, r.text
        assert "Openapi.it ha rifiutato l'invio" in r.json()["detail"]
        print("openapi send:", r.json()["detail"])
        assert ADM().get(f"{API}/invoices/{iid}").json()["status"] == "bozza"

    def test_10_openapi_sdi_sync_fails(self):
        r = CO().post(f"{API}/passive/sdi-sync", timeout=90)
        assert r.status_code == 400, r.text
        assert "Impossibile scaricare le fatture da Openapi.it" in r.json()["detail"]

    def test_11_acube_missing_password(self):
        r = ADM().put(f"{API}/company/sdi", json={"provider": "acube", "email": "test.t24@example.com"})
        assert r.status_code == 400 and "A-Cube" in r.text

    def test_12_acube_save_and_test_fake(self):
        r = ADM().put(f"{API}/company/sdi", json={"provider": "acube", "ambiente": "sandbox", "email": "TEST.T24@example.com", "password": "TEST_pw_xyz"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["has_password"] is True and d["has_token"] is False and d["email"] == "test.t24@example.com"
        assert "TEST_pw_xyz" not in ADM().get(f"{API}/companies").text
        r = ADM().post(f"{API}/company/sdi/test", timeout=90)
        assert r.status_code == 400 and "Collegamento a A-Cube non riuscito" in r.json()["detail"], r.text
        print("acube test:", r.json()["detail"])

    def test_13_acube_send_fails(self):
        iid = new_inv()
        r = CO().post(f"{API}/invoices/{iid}/send", timeout=90)
        assert r.status_code == 400 and "A-Cube ha rifiutato l'invio" in r.json()["detail"], r.text
        assert ADM().get(f"{API}/invoices/{iid}").json()["status"] == "bozza"
        r = CO().post(f"{API}/passive/sdi-sync", timeout=90)
        assert r.status_code == 400 and "A-Cube" in r.json()["detail"]

    def test_14_back_to_simulato_regression(self):
        r = ADM().put(f"{API}/company/sdi", json={"provider": "simulato"})
        assert r.status_code == 200 and r.json()["provider"] == "simulato" and r.json()["has_password"] is False
        iid = new_inv()
        r = CO().post(f"{API}/invoices/{iid}/send")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "inviata" and d.get("sdi_provider") is None and "SIMULATO" in d["sdi_message"]
        r = CO().post(f"{API}/invoices/{iid}/refresh")
        assert r.status_code == 200 and r.json()["status"] in ("consegnata", "mancata_consegna", "scartata")
        r = CO().post(f"{API}/passive/sdi-sync")
        assert r.status_code == 200, r.text
        assert len(r.json()["ricevute"]) >= 1
        p = ADM().get(f"{API}/passive").json()
        items = p if isinstance(p, list) else p.get("items", [])
        assert all(x["origine"] == "sdi_simulato" for x in items)

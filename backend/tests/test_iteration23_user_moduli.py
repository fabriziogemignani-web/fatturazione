# Iteration 23: Per-user modules - PUT /api/users/{id}/moduli (admin-only, validation, self/owner protection),
# effective modules = company AND user (admins ignore user restriction), GET /api/companies merged moduli,
# backend enforcement in tenant() for restricted contabile. Run with: pytest test_iteration23_user_moduli.py -n 0
import pytest
import requests
from test_iteration7_pa_scartate_registro import API, mongo

TOK, UID = "test_session_t23_admin", "test-user-t23-admin"
TOK_CO, UID_CO = "test_session_t23_co", "test-user-t23-co"
TOK_A2, UID_A2 = "test_session_t23_a2", "test-user-t23-a2"
PA = "86999999231"
ALL = {"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True, "corrispettivi": True}
ONLY_PASS = {**ALL, "fatture_attive": False, "corrispettivi": False, "archivio": False}
STATE = {}

ARCH = [("GET", "/archivio/invoices"), ("GET", "/archivio/stats")]
CORR = [("GET", "/corrispettivi"), ("GET", "/corrispettivi/riepilogo")]
PASS = [("GET", "/passive"), ("GET", "/scadenzario-passivo"), ("GET", "/registro-iva-acquisti")]
ATT = [("GET", "/invoices"), ("GET", "/scadenzario"), ("GET", "/registro-iva-vendite"), ("GET", "/registro")]
FATT = [("GET", "/dashboard"), ("GET", "/parties"), ("GET", "/articles")]


def sess(tok, cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    if cid:
        s.headers["X-Company-Id"] = cid
    return s


def clean():
    ids = f'["{UID}","{UID_CO}","{UID_A2}"]'
    mongo(f'db.companies.find({{partita_iva:"{PA}"}}).forEach(c=>{{db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:{ids}}}}}); db.user_sessions.deleteMany({{user_id:{{$in:{ids}}}}});')


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    for uid, tok, role in ((UID, TOK, "admin"), (UID_CO, TOK_CO, "contabile"), (UID_A2, TOK_A2, "admin")):
        mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.{uid}@example.com", name:"TEST_{uid}", picture:"", role:"{role}", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
              f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess(TOK).post(f"{API}/companies", json={"denominazione": "TEST_T23 Srl", "partita_iva": PA, "codice_fiscale": PA, "regime_fiscale": "RF01",
                                                  "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    STATE["a"] = r.json()["id"]
    mongo(f'db.users.updateOne({{user_id:"{UID_CO}"}}, {{$set:{{company_ids:["{STATE["a"]}"]}}}});')
    yield
    clean()


def put_user(uid, mods, tok=TOK):
    return sess(tok).put(f"{API}/users/{uid}/moduli", json=mods)


def put_comp(mods):
    return sess(TOK).put(f"{API}/companies/{STATE['a']}/moduli", json=mods)


def call(tok, m, p):
    return sess(tok, STATE["a"]).request(m, f"{API}{p}")


def blocked(eps, tok=TOK_CO):
    for m, p in eps:
        r = call(tok, m, p)
        assert r.status_code == 403 and "Modulo non attivo" in r.text, f"{p} -> {r.status_code} {r.text[:150]}"


def opened(eps, tok=TOK_CO):
    for m, p in eps:
        r = call(tok, m, p)
        assert r.status_code < 400 or (r.status_code != 403 and r.status_code < 500), f"{p} -> {r.status_code} {r.text[:150]}"
        assert not (r.status_code == 403 and "Modulo" in r.text), p


def my_company(tok=TOK_CO):
    return next(c for c in sess(tok).get(f"{API}/companies").json() if c["id"] == STATE["a"])


def test_default_user_has_no_moduli_all_open():
    users = sess(TOK).get(f"{API}/users").json()
    u = next(x for x in users if x["user_id"] == UID_CO)
    assert not u.get("moduli")
    assert my_company()["moduli"] == ALL
    opened(ARCH + CORR + PASS + ATT + FATT)


def test_put_user_moduli_persists_and_listed():
    r = put_user(UID_CO, ONLY_PASS)
    assert r.status_code == 200 and r.json() == ONLY_PASS, r.text
    u = next(x for x in sess(TOK).get(f"{API}/users").json() if x["user_id"] == UID_CO)
    assert u["moduli"] == ONLY_PASS


def test_restricted_user_enforcement():
    put_user(UID_CO, ONLY_PASS)
    assert my_company()["moduli"] == ONLY_PASS
    blocked(ARCH + CORR + ATT)
    opened(PASS + FATT)
    r = sess(TOK_CO, STATE["a"]).post(f"{API}/invoices", json={})
    assert r.status_code == 403


def test_403_message_mentions_user():
    put_user(UID_CO, ONLY_PASS)
    r = call(TOK_CO, "GET", "/invoices")
    assert "Fatture attive" in r.json()["detail"]


def test_admin_ignores_own_user_restriction():
    # admin2 with user moduli set in DB directly -> still sees all
    mongo(f'db.users.updateOne({{user_id:"{UID_A2}"}}, {{$set:{{moduli:{{fatturazione:true, archivio:false, fatture_attive:false, fatture_passive:true, corrispettivi:false}}}}}});')
    assert my_company(TOK_A2).get("moduli") in (None, {}, ALL)
    opened(ARCH + CORR + ATT + PASS, tok=TOK_A2)


def test_company_and_user_intersection():
    put_user(UID_CO, {**ALL, "archivio": False})
    put_comp({**ALL, "fatture_passive": False})
    m = my_company()["moduli"]
    assert m["archivio"] is False and m["fatture_passive"] is False and m["fatture_attive"] is True
    blocked(ARCH + PASS)
    opened(ATT + CORR)
    put_comp(ALL)
    put_user(UID_CO, ALL)
    opened(ARCH + PASS + ATT + CORR)


def test_validation():
    r = put_user(UID_CO, {**ALL, "fatturazione": False, "archivio": False})
    assert r.status_code == 422 and "almeno un'area" in r.text
    r = put_user(UID_CO, {**ALL, "fatture_attive": False, "fatture_passive": False, "corrispettivi": False})
    assert r.status_code == 422 and "almeno una funzione" in r.text
    assert put_user(UID_CO, {**ALL, "archivio": "x"}).status_code == 422


def test_non_admin_forbidden():
    put_user(UID_CO, ALL)
    r = put_user(UID_CO, ONLY_PASS, tok=TOK_CO)
    assert r.status_code == 403
    assert put_user(UID_A2, ONLY_PASS, tok=TOK_CO).status_code == 403
    u = next(x for x in sess(TOK).get(f"{API}/users").json() if x["user_id"] == UID_CO)
    assert u["moduli"] == ALL


def test_cannot_edit_self_owner_or_missing():
    assert put_user(UID, ONLY_PASS).status_code == 400
    owner = next(x for x in sess(TOK).get(f"{API}/users").json() if x.get("is_owner"))
    r = put_user(owner["user_id"], ONLY_PASS)
    assert r.status_code == 400, r.text
    assert put_user("nope-user", ONLY_PASS).status_code == 404


def test_unauthenticated():
    assert requests.put(f"{API}/users/{UID_CO}/moduli", json=ALL).status_code == 401


def test_archivio_only_user():
    put_user(UID_CO, {"fatturazione": False, "archivio": True, "fatture_attive": False, "fatture_passive": False, "corrispettivi": False})
    blocked(PASS + ATT + CORR + FATT)
    opened(ARCH)
    put_user(UID_CO, ALL)

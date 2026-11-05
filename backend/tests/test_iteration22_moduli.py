# Iteration 22: Company modules (moduli) - PUT /api/companies/{id}/moduli, GET /api/companies moduli,
# validation, role checks, backend enforcement in tenant() per URL segment, re-enable restores access.
# Run with: pytest test_iteration22_moduli.py -n 0
import pytest
import requests
from test_iteration7_pa_scartate_registro import API, mongo

TOK, UID = "test_session_t22_admin", "test-user-t22-admin"
TOK_CO, UID_CO = "test_session_t22_co", "test-user-t22-co"
TOK_OP, UID_OP = "test_session_t22_op", "test-user-t22-op"
PA, PB = "86999999221", "86999999222"
ALL = {"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True, "corrispettivi": True}
STATE = {}

ARCH = [("GET", "/archivio/invoices"), ("GET", "/archivio/stats"), ("GET", "/archivio/years"), ("GET", "/archivio/anagrafiche")]
CORR = [("GET", "/corrispettivi"), ("GET", "/corrispettivi/riepilogo")]
PASS = [("GET", "/passive"), ("GET", "/scadenzario-passivo"), ("GET", "/registro-iva-acquisti"), ("DELETE", "/passive-pagamenti/nope"), ("GET", "/passive/nope")]
ATT = [("GET", "/invoices"), ("GET", "/scadenzario"), ("GET", "/registro-iva-vendite"), ("GET", "/registro"),
       ("DELETE", "/pagamenti/nope"), ("GET", "/clienti/nope/estratto-conto.pdf"), ("GET", "/invoices/nope")]
FATT = [("GET", "/dashboard"), ("GET", "/liquidazione-iva"), ("GET", "/parties"), ("GET", "/articles")]
ALWAYS = [("GET", "/company"), ("GET", "/company/smtp")]


def sess(tok, cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    if cid:
        s.headers["X-Company-Id"] = cid
    return s


def clean():
    ids = f'["{UID}","{UID_CO}","{UID_OP}"]'
    mongo(f'db.companies.find({{partita_iva:{{$in:["{PA}","{PB}"]}}}}).forEach(c=>{{db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:{ids}}}}}); db.user_sessions.deleteMany({{user_id:{{$in:{ids}}}}});')


def comp(name, piva):
    return {"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01",
            "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"}


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    for uid, tok, role in ((UID, TOK, "admin"), (UID_CO, TOK_CO, "contabile"), (UID_OP, TOK_OP, "operatore")):
        mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.{uid}@example.com", name:"TEST_{uid}", picture:"", role:"{role}", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
              f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    s = sess(TOK)
    a = s.post(f"{API}/companies", json=comp("TEST_T22 A Srl", PA)); assert a.status_code == 200, a.text
    b = s.post(f"{API}/companies", json=comp("TEST_T22 B Srl", PB)); assert b.status_code == 200, b.text
    STATE["a"], STATE["b"] = a.json()["id"], b.json()["id"]
    mongo(f'db.users.updateMany({{user_id:{{$in:["{UID_CO}","{UID_OP}"]}}}}, {{$set:{{company_ids:["{STATE["a"]}","{STATE["b"]}"]}}}});')
    yield
    clean()


def put(mods, tok=TOK, cid=None):
    return sess(tok).put(f"{API}/companies/{cid or STATE['a']}/moduli", json=mods)


def call(tok, cid, method, path):
    return sess(tok, cid).request(method, f"{API}{path}")


def assert_blocked(eps, tok=TOK, cid=None, label=None):
    for m, p in eps:
        r = call(tok, cid or STATE["a"], m, p)
        assert r.status_code == 403, f"{m} {p} -> {r.status_code} {r.text[:200]}"
        assert "Modulo non attivo per questa azienda" in r.json()["detail"], p
        if label:
            assert label in r.json()["detail"], f"{p}: {r.json()['detail']}"


def assert_open(eps, tok=TOK, cid=None):
    for m, p in eps:
        r = call(tok, cid or STATE["a"], m, p)
        assert not (r.status_code == 403 and "Modulo" in r.text), f"{m} {p} blocked: {r.text[:200]}"
        assert r.status_code < 500, f"{m} {p} -> {r.status_code}"


# --- defaults / list ---
def test_default_all_enabled_and_list_has_moduli():
    rows = sess(TOK).get(f"{API}/companies").json()
    a = next(c for c in rows if c["id"] == STATE["a"])
    assert "moduli" not in a or a["moduli"] in (None, {})
    assert_open(ARCH + CORR + PASS + ATT + FATT + ALWAYS)


# --- put & validation ---
def test_put_moduli_persists():
    body = {**ALL, "corrispettivi": False}
    r = put(body); assert r.status_code == 200 and r.json() == body
    a = next(c for c in sess(TOK).get(f"{API}/companies").json() if c["id"] == STATE["a"])
    assert a["moduli"] == body
    assert put(ALL).status_code == 200


def test_put_validation_both_areas_off():
    r = put({**ALL, "fatturazione": False, "archivio": False})
    assert r.status_code == 422, r.text
    assert "almeno un'area" in str(r.json())


def test_put_validation_no_subfunctions():
    r = put({**ALL, "fatture_attive": False, "fatture_passive": False, "corrispettivi": False})
    assert r.status_code == 422, r.text
    assert "almeno una funzione" in str(r.json())


def test_put_archivio_only_with_subs_off_ok():
    r = put({"fatturazione": False, "archivio": True, "fatture_attive": False, "fatture_passive": False, "corrispettivi": False})
    assert r.status_code == 200, r.text
    assert put(ALL).status_code == 200


def test_put_invalid_type_and_404():
    assert put({**ALL, "archivio": "maybe"}).status_code == 422
    assert put(ALL, cid="does-not-exist").status_code == 404


def test_put_roles_forbidden():
    for tok in (TOK_CO, TOK_OP):
        r = put({**ALL, "archivio": False}, tok=tok)
        assert r.status_code == 403, r.text
    a = next(c for c in sess(TOK).get(f"{API}/companies").json() if c["id"] == STATE["a"])
    assert (a.get("moduli") or ALL)["archivio"] is True


def test_non_admin_list_sees_moduli():
    put({**ALL, "corrispettivi": False})
    rows = sess(TOK_CO).get(f"{API}/companies").json()
    a = next(c for c in rows if c["id"] == STATE["a"])
    assert a["moduli"]["corrispettivi"] is False
    put(ALL)


# --- enforcement ---
def test_archivio_off():
    put({**ALL, "archivio": False})
    assert_blocked(ARCH, label="Archivio fatture")
    assert_open(CORR + PASS + ATT + FATT + ALWAYS)
    assert_open(ARCH, cid=STATE["b"])  # other company unaffected
    put(ALL); assert_open(ARCH)


def test_corrispettivi_off():
    put({**ALL, "corrispettivi": False})
    assert_blocked(CORR, label="Corrispettivi")
    assert_blocked(CORR, tok=TOK_CO)
    assert_open(ARCH + PASS + ATT + FATT + ALWAYS)
    put(ALL); assert_open(CORR)


def test_passive_off():
    put({**ALL, "fatture_passive": False})
    assert_blocked(PASS, label="Fatture passive")
    assert_blocked(PASS, tok=TOK_OP)
    assert_open(ARCH + CORR + ATT + FATT + ALWAYS)
    put(ALL); assert_open(PASS)


def test_attive_off():
    put({**ALL, "fatture_attive": False})
    assert_blocked(ATT, label="Fatture attive")
    assert_open(ARCH + CORR + PASS + FATT + ALWAYS)
    put(ALL); assert_open(ATT)


def test_fatturazione_off():
    put({"fatturazione": False, "archivio": True, "fatture_attive": True, "fatture_passive": True, "corrispettivi": True})
    assert_blocked(CORR + PASS + ATT + FATT, label="Fatturazione")
    assert_blocked(FATT, tok=TOK_CO)
    assert_open(ARCH + ALWAYS)
    put(ALL); assert_open(CORR + PASS + ATT + FATT)


def test_post_write_endpoints_blocked():
    put({**ALL, "fatture_attive": False, "fatture_passive": True})
    r = sess(TOK, STATE["a"]).post(f"{API}/invoices", json={})
    assert r.status_code == 403, r.text
    put({**ALL, "fatturazione": False})
    r = sess(TOK, STATE["a"]).post(f"{API}/parties", json={})
    assert r.status_code == 403, r.text
    put({**ALL, "archivio": False})
    r = sess(TOK, STATE["a"]).post(f"{API}/archivio/upload", files=[("files", ("a.xml", b"<x/>"))])
    assert r.status_code == 403, r.text
    put(ALL)


def test_ipa_search_blocked_when_fatturazione_off():
    put({**ALL, "fatturazione": False})
    r = sess(TOK, STATE["a"]).get(f"{API}/ipa/search", params={"q": "comune"})
    put(ALL)
    assert r.status_code == 403, f"/api/ipa/search not module-gated: {r.status_code}"

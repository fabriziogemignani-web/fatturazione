# Iteration 122: GET /api/sistema/avviso (system update banner) - null / doc from sistema_avvisi tipo 'aggiornamento', auth required.
# Run: pytest tests/test_iteration122_avviso_sistema.py -v -n 0
import os
import random
import sys

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

RUN = str(random.randint(100000, 999999))
TOK, UID = "test_session_t122_admin", "test-user-t122-admin"
TOKP, UIDP = "test_session_t122_pending", "test-user-t122-pending"


def s(tok=TOK):
    x = requests.Session()
    x.headers.update({"Authorization": f"Bearer {tok}"})
    return x


def clean():
    mongo(f'db.sistema_avvisi.deleteMany({{test_run:"{RUN}"}}); db.users.deleteMany({{user_id:{{$in:["{UID}","{UIDP}"]}}}});'
          f'db.user_sessions.deleteMany({{user_id:{{$in:["{UID}","{UIDP}"]}}}});')


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    for uid, tok, st in ((UID, TOK, "approved"), (UIDP, TOKP, "pending")):
        mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.{uid}@example.com", name:"TEST_T122", picture:"", role:"admin", status:"{st}", company_ids:[], created_at:new Date().toISOString()}});'
              f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    yield
    clean()


class TestAvviso:
    def test_01_unauth_401(self):
        r = requests.get(f"{API}/sistema/avviso")
        assert r.status_code == 401, r.text

    def test_02_pending_forbidden(self):
        r = s(TOKP).get(f"{API}/sistema/avviso")
        assert r.status_code in (401, 403), r.text

    def test_03_null_when_none(self):
        r = s().get(f"{API}/sistema/avviso")
        assert r.status_code == 200, r.text
        assert r.json() == {"avviso": None}

    def test_04_present_then_removed(self):
        mongo(f'db.sistema_avvisi.insertOne({{tipo:"aggiornamento", test_run:"{RUN}", messaggio:"TEST avviso {RUN}", creato_il:new Date().toISOString(), spegnimento_at:new Date(Date.now()+60000).toISOString()}});')
        a = s().get(f"{API}/sistema/avviso").json()["avviso"]
        assert a["messaggio"] == f"TEST avviso {RUN}"
        assert set(a.keys()) == {"messaggio", "spegnimento_at"}, a
        mongo(f'db.sistema_avvisi.deleteMany({{test_run:"{RUN}"}});')
        assert s().get(f"{API}/sistema/avviso").json() == {"avviso": None}

    def test_05_other_tipo_ignored(self):
        mongo(f'db.sistema_avvisi.insertOne({{tipo:"altro", test_run:"{RUN}", messaggio:"x", spegnimento_at:new Date().toISOString()}});')
        assert s().get(f"{API}/sistema/avviso").json() == {"avviso": None}

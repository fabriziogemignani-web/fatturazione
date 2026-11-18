# Iteration 102: AI credits per company (ai_crediti/ai_attiva), parent company (societa_padre + packs), Stripe checkout + status polling
# (idempotent credit), AI on/off (400) and exhausted credits (402), token consumption (ai_consumi) for analizza + consulente chat.
# Run: pytest tests/test_iteration102_ai_crediti.py -v -n 0   (T102_KEEP=1 keeps data for UI tests)
import json
import os
import random
import sys
import uuid
from datetime import date

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402
import test_iteration101_ai_registrazione_consulente as t101  # noqa: E402

RUN = str(random.randint(100000, 999999))
TOK, UID = "test_session_t102_admin", "test-user-t102-admin"
TOK_OP, UID_OP = "test_session_t102_oper", "test-user-t102-oper"
ST = {}
Y = date.today().year
PACKS = [{"id": "base", "nome": "Base", "crediti": 500, "prezzo": 10.0}, {"id": "pro", "nome": "Pro", "crediti": 2000, "prezzo": 35.0}]


def sess(tok=TOK, cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    c = cid or ST.get("cid")
    if c:
        s.headers["X-Company-Id"] = c
    return s


def comp(cid):
    return json.loads(mongo(f'print(JSON.stringify(db.companies.findOne({{id:"{cid}"}},{{_id:0,id:1,ai_crediti:1,ai_attiva:1,societa_padre:1,ai_pacchetti:1}})))') or "null")


def clean():
    mongo(f'db.companies.find({{denominazione:/^TEST_T102/}}).forEach(c=>{{{json.dumps(t101.COLLS + ["ai_consumi", "payment_transactions"])}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:["{UID}","{UID_OP}"]}}}}); db.user_sessions.deleteMany({{user_id:{{$in:["{UID}","{UID_OP}"]}}}});')


def mk_company(name, piva):
    r = sess(cid="").post(f"{API}/companies", json={"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01",
                                                   "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t102.admin@example.com", name:"TEST_T102 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    t101.PIVA = "10" + RUN + "102"
    ST["cid"] = mk_company(f"TEST_T102 Cliente {RUN} Srl", t101.PIVA)
    ST["padre"] = mk_company(f"TEST_T102 Padre {RUN} Srl", "20" + RUN + "102")
    ST["altro"] = mk_company(f"TEST_T102 Altro {RUN} Srl", "30" + RUN + "102")
    mongo(f'db.users.insertOne({{user_id:"{UID_OP}", email:"test.user.t102.oper@example.com", name:"TEST_T102 oper", picture:"", role:"operatore", status:"approved", company_ids:["{ST["cid"]}"], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID_OP}", session_token:"{TOK_OP}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    t101.ST["cid"] = ST["cid"]
    t101.TOK = TOK
    t101.sess = sess
    yield
    if os.environ.get("T102_KEEP"):
        print("\nKEEP", json.dumps(ST))
    else:
        clean()


class TestCrediti:
    def test_01_new_company_defaults(self):
        c = comp(ST["cid"])
        assert c["ai_crediti"] == 100 and c["ai_attiva"] is True, c

    def test_02_crediti_no_padre(self):
        r = sess().get(f"{API}/ai/crediti")
        assert r.status_code == 200, r.text
        j = r.json()
        print("CREDITI", j)
        assert j["attiva"] is True and j["crediti"] == 100 and j["token_per_credito"] == 1000
        assert j["pacchetti"] == [] and j["venditore"] is None and j["acquisti"] == []

    def test_03_checkout_no_padre_400(self):
        r = sess().post(f"{API}/ai/crediti/checkout", json={"pacchetto_id": "base", "origin_url": "https://x.example.com"})
        assert r.status_code == 400, r.text

    def test_04_padre_admin_only(self):
        assert sess(TOK_OP).get(f"{API}/ai/padre").status_code == 403
        assert sess(TOK_OP).put(f"{API}/companies/{ST['padre']}/padre", json={"pacchetti": PACKS}).status_code == 403
        assert sess(TOK_OP).delete(f"{API}/companies/{ST['padre']}/padre").status_code == 403

    def test_05_padre_validation(self):
        dup = [PACKS[0], {**PACKS[1], "id": "base"}]
        assert sess().put(f"{API}/companies/{ST['padre']}/padre", json={"pacchetti": dup}).status_code == 422
        assert sess().put(f"{API}/companies/{ST['padre']}/padre", json={"pacchetti": []}).status_code == 422
        assert sess().put(f"{API}/companies/nonexistent/padre", json={"pacchetti": PACKS}).status_code == 404

    def test_06_padre_unique(self):
        assert sess().put(f"{API}/companies/{ST['altro']}/padre", json={"pacchetti": PACKS}).status_code == 200
        assert comp(ST["altro"])["societa_padre"] is True
        r = sess().put(f"{API}/companies/{ST['padre']}/padre", json={"pacchetti": PACKS})
        assert r.status_code == 200, r.text
        assert comp(ST["padre"])["societa_padre"] is True and comp(ST["altro"])["societa_padre"] is False
        g = sess().get(f"{API}/ai/padre").json()
        assert g["id"] == ST["padre"] and g["pacchetti"] == PACKS, g
        lst = sess(cid="").get(f"{API}/companies").json()
        row = next(x for x in lst if x["id"] == ST["padre"])
        assert row.get("societa_padre") is True

    def test_07_crediti_with_padre(self):
        j = sess().get(f"{API}/ai/crediti").json()
        assert j["venditore"].startswith("TEST_T102 Padre") and j["pacchetti"] == PACKS, j

    def test_08_checkout(self):
        assert sess().post(f"{API}/ai/crediti/checkout", json={"pacchetto_id": "nope", "origin_url": "https://x.example.com"}).status_code == 404
        assert sess(TOK_OP).post(f"{API}/ai/crediti/checkout", json={"pacchetto_id": "base", "origin_url": "https://x.example.com"}).status_code == 403
        r = sess().post(f"{API}/ai/crediti/checkout", json={"pacchetto_id": "base", "origin_url": "https://x.example.com"}, timeout=60)
        print("CHECKOUT", r.status_code, r.text[:300])
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["checkout_url"].startswith("https://") and j["session_id"].startswith("cs_")
        ST["sid"] = j["session_id"]
        tx = json.loads(mongo(f'print(JSON.stringify(db.payment_transactions.findOne({{session_id:"{ST["sid"]}"}},{{_id:0}})))'))
        print("TX", tx)
        assert tx["payment_status"] == "pending" and tx["crediti"] == 500 and tx["amount"] == 10.0 and tx["company_id"] == ST["cid"]

    def test_09_status_pending(self):
        r = sess().get(f"{API}/payments/status/{ST['sid']}", timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert set(j) == {"session_id", "status", "payment_status"} and j["payment_status"] != "paid", j
        assert comp(ST["cid"])["ai_crediti"] == 100
        assert sess().get(f"{API}/payments/status/cs_test_nonexistent").status_code == 404

    def test_10_status_paid_idempotent(self):
        mongo(f'db.payment_transactions.updateOne({{session_id:"{ST["sid"]}"}}, {{$set:{{payment_status:"paid", status:"completed"}}}})')
        for _ in range(3):
            j = sess().get(f"{API}/payments/status/{ST['sid']}").json()
            assert j["payment_status"] == "paid", j
        assert comp(ST["cid"])["ai_crediti"] == 600, comp(ST["cid"])
        acq = sess().get(f"{API}/ai/crediti").json()
        assert acq["crediti"] == 600 and len(acq["acquisti"]) == 1 and acq["acquisti"][0]["crediti"] == 500, acq

    def test_11_webhook_bad_signature(self):
        assert requests.post(f"{API}/stripe/webhook", data="{}", headers={"stripe-signature": "x"}).status_code == 400


class TestAttivaEConsumo:
    def test_20_attiva_permissions(self):
        assert sess(TOK_OP).put(f"{API}/ai/attiva", json={"attiva": False}).status_code == 403

    def test_21_off_blocks_ai(self):
        assert sess().put(f"{API}/ai/attiva", json={"attiva": False}).json() == {"attiva": False}
        assert sess().get(f"{API}/ai/crediti").json()["attiva"] is False
        assert sess().post(f"{API}/ai/passive/analizza").status_code == 400
        r = sess().post(f"{API}/ai/consulente/chat", json={"session_id": "x1", "message": "ciao"})
        assert r.status_code == 400, r.text

    def test_22_zero_credits_402(self):
        sess().put(f"{API}/ai/attiva", json={"attiva": True})
        mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}}, {{$set:{{ai_crediti:0}}}})')
        assert sess().post(f"{API}/ai/passive/analizza").status_code == 402
        assert sess().post(f"{API}/ai/consulente/chat", json={"session_id": "x1", "message": "ciao"}).status_code == 402
        mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}}, {{$set:{{ai_crediti:100}}}})')

    def test_23_consumo_analizza(self):
        t101.TestAiRegistrazione().test_01_enable_coge_and_upload()
        before = comp(ST["cid"])["ai_crediti"]
        r = sess().post(f"{API}/ai/passive/analizza", timeout=300)
        assert r.status_code == 200, r.text
        print("ANALIZZA", r.json())
        assert r.json()["analizzate"] == 3
        after = comp(ST["cid"])["ai_crediti"]
        cons = json.loads(mongo(f'print(JSON.stringify(db.ai_consumi.find({{company_id:"{ST["cid"]}", tipo:"registrazione"}},{{_id:0}}).toArray()))'))
        print("CONSUMI", before, after, cons)
        assert len(cons) == 3 and all(c["token"] > 0 and abs(c["crediti"] - c["token"] / 1000) < 0.001 for c in cons)
        assert abs((before - after) - sum(c["crediti"] for c in cons)) < 0.01

    def test_24_consumo_chat(self):
        before = comp(ST["cid"])["ai_crediti"]
        chunks, done, err = t101.sse("t102" + uuid.uuid4().hex[:6], "In una frase: chi è il fornitore principale?")
        assert done and not err and "".join(chunks).strip()
        after = comp(ST["cid"])["ai_crediti"]
        cons = json.loads(mongo(f'print(JSON.stringify(db.ai_consumi.find({{company_id:"{ST["cid"]}", tipo:"consulente"}},{{_id:0}}).toArray()))'))
        print("CHAT CONSUMI", before, after, cons)
        assert len(cons) == 1 and cons[0]["token"] > 0
        assert abs((before - after) - cons[0]["crediti"]) < 0.01

    def test_25_ai_off_rigenera_normal(self):
        sess().put(f"{API}/ai/attiva", json={"attiva": False})
        pid = t101.upload(t101.xml("CA-9", f"{Y}-01-15", "01234567897", "TEST_T102 Cancelleria Srl", [("Carta A4", 50.0)]))
        r = sess().post(f"{API}/contabilita/rigenera", json={"ricrea": False}, timeout=120)
        print("RIGENERA", r.status_code, r.text[:300])
        assert r.status_code == 200 and r.json()["acquisti"] >= 1
        assert t101.pdoc(pid)["stato_reg"] == "registrata"
        sess().put(f"{API}/ai/attiva", json={"attiva": True})

    def test_26_del_padre(self):
        if os.environ.get("T102_KEEP"):
            pytest.skip("keep padre for UI")
        assert sess().delete(f"{API}/companies/{ST['padre']}/padre").status_code == 200
        assert comp(ST["padre"])["societa_padre"] is False
        assert sess().get(f"{API}/ai/padre").json()["id"] is None
        assert sess().get(f"{API}/ai/crediti").json()["pacchetti"] == []

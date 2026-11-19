# Iteration 108: data integrity - audit log (registro attività), optimistic concurrency (If-Match / version), controllo di coerenza,
# JSON schema validators on accounting collections, regression of payments / prima nota wrapped by @atomico.
# Run: pytest tests/test_iteration108_integrita.py -v -n 0
import json
import os
import random
import sys
import uuid
from datetime import date, timedelta

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo, party, inv  # noqa: E402

RUN = str(random.randint(100000, 999999))
TOK, UID = f"test_session_t108_admin_{RUN}", f"test-user-t108-admin-{RUN}"
TOK2, UID2 = f"test_session_t108_op_{RUN}", f"test-user-t108-op-{RUN}"
PIVA = "18" + RUN + "108"
ST = {}
COLLS = ["invoices", "passive_invoices", "parties", "articles", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "audit_log", "partite_aperte", "f24_versamenti", "pag_distinte", "ratei_risconti", "bank_tx", "bank_accounts"]
T = date.today()
D = lambda n: (T - timedelta(days=n)).isoformat()  # noqa: E731
CONFL = "modificato da un altro utente"


def sess(tok=TOK):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "X-Requested-With": "invoix"})
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{partita_iva:"{PIVA}"}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.audit_log.deleteMany({{user_id:{{$in:["{UID}","{UID2}"]}}}}); db.users.deleteMany({{user_id:{{$in:["{UID}","{UID2}"]}}}}); db.user_sessions.deleteMany({{user_id:{{$in:["{UID}","{UID2}"]}}}});')


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t108.admin.{RUN}@example.com", name:"TEST_T108 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": "TEST_T108 Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    sess().put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                            "corrispettivi": True, "contabilita": True})
    conti = sess().get(f"{API}/contabilita/conti").json()
    leaves = [c["codice"] for c in (conti if isinstance(conti, list) else conti.get("conti", [])) if c.get("livello") == 3]
    ST["c1"], ST["c2"] = leaves[0], leaves[1]
    caus = sess().get(f"{API}/contabilita/causali").json()
    caus = caus if isinstance(caus, list) else caus.get("causali", [])
    ST["causale"] = next((c["codice"] for c in caus if c["codice"] in ("GC", "GEN", "VAR")), caus[0]["codice"])
    mongo(f'db.users.insertOne({{user_id:"{UID2}", email:"test.user.t108.op.{RUN}@example.com", name:"TEST_T108 operatore", picture:"", role:"operatore", status:"approved", company_ids:["{ST["cid"]}"], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID2}", session_token:"{TOK2}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    yield
    if os.environ.get("T108_KEEP"):
        print("\nKEEP", RUN, ST["cid"], TOK)
    else:
        clean()


def reg_body(data, imp=100, descr="TEST_T108 manuale"):
    return {"data": data, "causale": ST["causale"], "descrizione": descr,
            "righe": [{"conto": ST["c1"], "dare": imp}, {"conto": ST["c2"], "avere": imp}]}


class TestAuditLog:
    def test_01_party_create_logged(self):
        s = sess()
        r = s.post(f"{API}/parties", json=party("TEST_T108 Cliente", piva="01234567892", cf="01234567892"))
        assert r.status_code == 200, r.text
        ST["pid"] = r.json()["id"]
        j = s.get(f"{API}/registro-attivita").json()
        assert j["totale"] >= 1
        row = next(x for x in j["righe"] if x["path"] == "/api/parties" and x["method"] == "POST")
        assert row["company_id"] == ST["cid"] and row["user_id"] == UID and row["area"] == "parties" and row["esito"] == 200
        assert row["dati"]["denominazione"] == "TEST_T108 Cliente"
        assert "_id" not in row

    def test_02_secrets_masked(self):
        # SMTP config contains a password field -> must be masked
        s = sess()
        r = s.put(f"{API}/company/smtp", json={"host": "127.0.0.1", "port": 1025, "security": "none", "username": "u", "password": "SuperSecret1",
                                               "from_email": "test@example.com", "from_name": "TEST"})
        rows = s.get(f"{API}/registro-attivita", params={"q": "smtp"}).json()["righe"]
        if r.status_code >= 400:
            assert not rows
            pytest.skip(f"smtp put failed {r.status_code}: {r.text[:200]}")
        assert rows, "smtp PUT not logged"
        assert rows[0]["dati"]["password"] == "***", rows[0]["dati"]
        assert "SuperSecret1" not in json.dumps(rows)

    def test_03_failed_and_get_not_logged(self):
        s = sess()
        before = s.get(f"{API}/registro-attivita").json()["totale"]
        assert s.put(f"{API}/parties/nonexistent-xyz", json=party("TEST_T108 X", piva="01234567892", cf="01234567892")).status_code == 404
        s.get(f"{API}/parties")
        assert s.get(f"{API}/registro-attivita").json()["totale"] == before

    def test_04_filters_order(self):
        s = sess()
        s.put(f"{API}/parties/{ST['pid']}", json=party("TEST_T108 Cliente", piva="01234567892", cf="01234567892", comune="Roma"))
        j = s.get(f"{API}/registro-attivita").json()
        ats = [x["at"] for x in j["righe"]]
        assert ats == sorted(ats, reverse=True)
        assert any(u["id"] == UID for u in j["utenti"]) and "parties" in j["aree"]
        assert all(x["area"] == "parties" for x in s.get(f"{API}/registro-attivita", params={"area": "parties"}).json()["righe"])
        assert s.get(f"{API}/registro-attivita", params={"utente": "nobody"}).json()["totale"] == 0
        assert s.get(f"{API}/registro-attivita", params={"dal": "2099-01-01"}).json()["totale"] == 0
        assert s.get(f"{API}/registro-attivita", params={"al": "2000-01-01"}).json()["totale"] == 0
        assert s.get(f"{API}/registro-attivita", params={"dal": T.isoformat(), "al": T.isoformat()}).json()["totale"] >= 2
        q = s.get(f"{API}/registro-attivita", params={"q": ST["pid"]}).json()
        assert q["totale"] >= 1 and all(ST["pid"] in x["path"] for x in q["righe"])
        assert s.get(f"{API}/registro-attivita", params={"pagina": 2}).json()["righe"] == []

    def test_05_non_admin_forbidden(self):
        r = sess(TOK2).get(f"{API}/registro-attivita")
        assert r.status_code == 403, r.text

    def test_06_auth_excluded(self):
        n = mongo(f'print(db.audit_log.countDocuments({{path:/^\\/api\\/auth\\//}}))')
        assert n == "0", n


class TestConcurrency:
    def test_10_party_versioning(self):
        s = sess()
        cur = s.get(f"{API}/parties").json()
        cur = next(p for p in (cur if isinstance(cur, list) else cur.get("items", cur.get("parties", []))) if p["id"] == ST["pid"])
        v = int(cur.get("version") or 0)
        r = s.put(f"{API}/parties/{ST['pid']}", json=party("TEST_T108 Cliente A", piva="01234567892", cf="01234567892"), headers={"If-Match": str(v)})
        assert r.status_code == 200, r.text
        assert r.json()["version"] == v + 1 and r.json()["denominazione"] == "TEST_T108 Cliente A"
        r = s.put(f"{API}/parties/{ST['pid']}", json=party("TEST_T108 Cliente B", piva="01234567892", cf="01234567892"), headers={"If-Match": str(v)})
        assert r.status_code == 409 and CONFL in r.text, r.text
        # backward compat: no header
        r = s.put(f"{API}/parties/{ST['pid']}", json=party("TEST_T108 Cliente C", piva="01234567892", cf="01234567892"))
        assert r.status_code == 200 and r.json()["version"] == v + 2
        r = s.put(f"{API}/parties/{ST['pid']}", json=party("TEST_T108 Cliente", piva="01234567892", cf="01234567892"), headers={"If-Match": "abc"})
        assert r.status_code == 400

    def test_11_party_version_zero_missing(self):
        s = sess()
        r = s.post(f"{API}/parties", json=party("TEST_T108 Cliente V0", piva="01234567893", cf="01234567893"))
        p2 = r.json()["id"]
        mongo(f'db.parties.updateOne({{id:"{p2}"}}, {{$unset:{{version:""}}}})')
        r = s.put(f"{API}/parties/{p2}", json=party("TEST_T108 Cliente V0b", piva="01234567893", cf="01234567893"), headers={"If-Match": "0"})
        assert r.status_code == 200 and r.json()["version"] == 1, r.text
        assert s.delete(f"{API}/parties/{p2}").status_code == 200

    def test_12_invoice_versioning(self):
        s = sess()
        r = s.post(f"{API}/invoices", json=inv(ST["pid"], data=D(20)))
        assert r.status_code == 200, r.text
        i = r.json()
        ST["iid_draft"] = i["id"]
        v = int(i.get("version") or 0)
        r = s.put(f"{API}/invoices/{i['id']}", json=inv(ST["pid"], data=D(20), price=1200), headers={"If-Match": str(v)})
        assert r.status_code == 200, r.text
        assert r.json()["version"] == v + 1
        r = s.put(f"{API}/invoices/{i['id']}", json=inv(ST["pid"], data=D(20), price=1300), headers={"If-Match": str(v)})
        assert r.status_code == 409 and CONFL in r.text, r.text
        got = s.get(f"{API}/invoices/{i['id']}").json()
        assert got["version"] == v + 1 and abs(got["totale"] - 1464) < 0.01, got.get("totale")
        r = s.put(f"{API}/invoices/{i['id']}", json=inv(ST["pid"], data=D(20), price=1000))
        assert r.status_code == 200 and r.json()["version"] == v + 2

    def test_13_registrazione_versioning(self):
        s = sess()
        r = s.post(f"{API}/contabilita/registrazioni", json=reg_body(D(5)))
        assert r.status_code == 200, r.text
        e = r.json()
        ST["rid"] = e["id"]
        v = int(e.get("version") or 0)
        r = s.put(f"{API}/contabilita/registrazioni/{e['id']}", json=reg_body(D(5), 150), headers={"If-Match": str(v)})
        assert r.status_code == 200, r.text
        assert r.json()["version"] == v + 1 and r.json()["totale"] == 150
        r = s.put(f"{API}/contabilita/registrazioni/{e['id']}", json=reg_body(D(5), 175), headers={"If-Match": str(v)})
        assert r.status_code == 409 and CONFL in r.text, r.text
        r = s.put(f"{API}/contabilita/registrazioni/{e['id']}", json=reg_body(D(5), 200))
        assert r.status_code == 200 and r.json()["version"] == v + 2
        db = json.loads(mongo(f'print(JSON.stringify(db.coa_entries.findOne({{id:"{e["id"]}"}},{{_id:0,totale:1,version:1}})))'))
        assert db["totale"] == 200 and db["version"] == v + 2


class TestPaymentsRegression:
    def test_20_incasso_add_delete(self):
        s = sess()
        iid = ST["iid_draft"]
        assert s.post(f"{API}/invoices/{iid}/send").status_code == 200
        assert s.post(f"{API}/invoices/{iid}/refresh").json()["status"] == "consegnata"
        ST["iid"] = iid
        r = s.post(f"{API}/invoices/{iid}/pagamenti", json={"data": D(3), "importo": 200, "metodo": "bonifico"})
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["importo"] == 200 and p.get("coge_entry_id")
        n = mongo(f'print(db.payments.countDocuments({{id:"{p["id"]}"}}))')
        assert n == "1"
        r = s.delete(f"{API}/pagamenti/{p['id']}")
        assert r.status_code == 200, r.text
        assert mongo(f'print(db.payments.countDocuments({{id:"{p["id"]}"}}))') == "0"
        assert mongo(f'print(db.coa_entries.countDocuments({{id:"{p["coge_entry_id"]}"}}))') == "0"
        # keep one payment for coherence check
        r = s.post(f"{API}/invoices/{iid}/pagamenti", json={"data": D(3), "importo": 300, "metodo": "bonifico"})
        assert r.status_code == 200, r.text
        ST["pay"] = r.json()["id"]

    def test_21_delete_registrazione(self):
        s = sess()
        r = s.post(f"{API}/contabilita/registrazioni", json=reg_body(D(4), 50, "TEST_T108 da eliminare"))
        assert r.status_code == 200, r.text
        rid = r.json()["id"]
        assert s.delete(f"{API}/contabilita/registrazioni/{rid}").status_code == 200
        assert mongo(f'print(db.coa_entries.countDocuments({{id:"{rid}"}}))') == "0"


class TestCoerenza:
    def test_30_runs_clean(self):
        s = sess()
        r = s.get(f"{API}/controlli/coerenza")
        assert r.status_code == 200, r.text
        j = r.json()
        assert set(j) >= {"problemi", "errori", "avvisi", "contabilita", "controlli"}
        assert j["contabilita"] is True and len(j["controlli"]) >= 5
        errs = [p for p in j["problemi"] if p["gravita"] == "errore"]
        assert not errs, errs
        ST["base_avvisi"] = j["avvisi"]

    def test_31_detects_inconsistency(self):
        s = sess()
        eid, pid = f"TEST_T108_{uuid.uuid4()}", f"TEST_T108_{uuid.uuid4()}"
        y = T.year
        mongo(f'db.coa_entries.insertOne({{id:"{eid}", company_id:"{ST["cid"]}", anno:NumberInt({y}), numero:9999, data:"{T.isoformat()}", origine:"manuale", '
              f'righe:[{{conto:"{ST["c1"]}", dare:10, avere:0}},{{conto:"{ST["c2"]}", dare:0, avere:10}}], totale:99}});'
              f'db.payments.insertOne({{id:"{pid}", company_id:"{ST["cid"]}", invoice_id:"TEST_T108_missing", importo:5, data:"{T.isoformat()}", numero_display:"TEST_X"}});')
        try:
            assert mongo(f'print(db.coa_entries.countDocuments({{id:"{eid}"}}))') == "1"
            j = s.get(f"{API}/controlli/coerenza").json()
            msgs = [p["messaggio"] for p in j["problemi"]]
            assert any("9999" in m and "totale salvato" in m for m in msgs), msgs
            assert any("TEST_X" in m and "non esiste più" in m for m in msgs), msgs
            assert any("contatore" in m.lower() for m in msgs), msgs
            assert j["errori"] >= 3
        finally:
            mongo(f'db.coa_entries.deleteOne({{id:"{eid}"}}); db.payments.deleteOne({{id:"{pid}"}});')
        assert s.get(f"{API}/controlli/coerenza").json()["errori"] == 0

    def test_32_operatore_forbidden(self):
        assert sess(TOK2).get(f"{API}/controlli/coerenza").status_code == 403


class TestSchema:
    def test_40_validators_present(self):
        out = mongo('const n={}; db.getCollectionInfos().forEach(c=>{ if(c.options&&c.options.validator) n[c.name]=c.options.validationLevel }); print(JSON.stringify(n))')
        v = json.loads(out)
        for c in ("invoices", "coa_entries", "payments", "passive_payments", "passive_invoices", "audit_log"):
            assert v.get(c) == "moderate", v

    def test_41_negative_dare_rejected(self):
        eid = f"TEST_T108_{uuid.uuid4()}"
        out = mongo(f'try {{ db.coa_entries.insertOne({{id:"{eid}", company_id:"{ST["cid"]}", anno:NumberInt(2025), numero:1, data:"2025-01-01", '
                    f'righe:[{{conto:"a", dare:-5, avere:0}},{{conto:"b", dare:0, avere:5}}], totale:0}}); print("INSERTED") }} catch(e) {{ print("REJECTED " + e.code) }}')
        mongo(f'db.coa_entries.deleteOne({{id:"{eid}"}})')
        assert out.startswith("REJECTED") and "121" in out, out

    def test_42_payment_zero_rejected(self):
        pid = f"TEST_T108_{uuid.uuid4()}"
        out = mongo(f'try {{ db.payments.insertOne({{id:"{pid}", company_id:"{ST["cid"]}", invoice_id:"x", importo:0, data:"2025-01-01"}}); print("INSERTED") }} catch(e) {{ print("REJECTED") }}')
        mongo(f'db.payments.deleteOne({{id:"{pid}"}})')
        assert out == "REJECTED", out

    def test_43_invoice_bad_status_rejected(self):
        iid = f"TEST_T108_{uuid.uuid4()}"
        out = mongo(f'try {{ db.invoices.insertOne({{id:"{iid}", company_id:"{ST["cid"]}", anno:NumberInt(2025), numero:1, status:"boh"}}); print("INSERTED") }} catch(e) {{ print("REJECTED") }}')
        mongo(f'db.invoices.deleteOne({{id:"{iid}"}})')
        assert out == "REJECTED", out


class TestPassiveRegression:
    def test_50_passive_payment_add_delete(self):
        import test_iteration89_rigenera_passive as t89
        s = sess()
        x = t89.xml("T108-1", D(30), "01111111111", 1000.0).replace(t89.PIVA.encode(), PIVA.encode()).replace(b"TEST_T89", b"TEST_T108")
        r = s.post(f"{API}/passive/upload", files=[("files", (f"t108_{RUN}.xml", x, "application/octet-stream"))])
        assert r.status_code == 200 and r.json()[0]["ok"], r.text
        pid = r.json()[0]["documenti"][0]["id"]
        r = s.patch(f"{API}/passive/{pid}", json={"stato_reg": "registrata", "data_registrazione": D(10)})
        assert r.status_code == 200, r.text
        r = s.post(f"{API}/passive/{pid}/pagamenti", json={"data": D(5), "importo": 100, "metodo": "bonifico"})
        assert r.status_code == 200, r.text
        p = r.json()
        assert p.get("coge_entry_id")
        r = s.delete(f"{API}/passive-pagamenti/{p['id']}")
        assert r.status_code == 200, r.text
        assert mongo(f'print(db.passive_payments.countDocuments({{id:"{p["id"]}"}}))') == "0"
        assert mongo(f'print(db.coa_entries.countDocuments({{id:"{p["coge_entry_id"]}"}}))') == "0"
        j = s.get(f"{API}/controlli/coerenza").json()
        assert j["errori"] == 0, j["problemi"]

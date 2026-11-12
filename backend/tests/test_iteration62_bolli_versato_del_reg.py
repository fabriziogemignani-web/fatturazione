# Iteration 62: bolli versato (GET /api/bolli key/versato/concluso, POST/DELETE /api/scadenze-fiscali/versato BOL-YYYY-Q with prima nota GE
# 30.14.002 / banca), dashboard scadenze bolli items, and DELETE /api/contabilita/registrazioni/{rid} for all origins except SDI-accepted docs and Ri.Ba.
# Run: pytest tests/test_iteration62_bolli_versato_del_reg.py -v -n 0
# UI fixtures: T62_RUN=123456 python tests/test_iteration62_bolli_versato_del_reg.py setup|clean
import json
import os
import random
import sys
import uuid
from datetime import date

import pytest
import requests

from test_iteration7_pa_scartate_registro import API, mongo

sys.path.insert(0, "/app/backend")
from passive import demo_xmls  # noqa: E402

RUN = os.environ.get("T62_RUN") or str(random.randint(100000, 999999))
TOK, UID = f"test_session_t62_admin_{RUN}", f"test-user-t62-admin-{RUN}"
TOK_OP, UID_OP = f"test_session_t62_op_{RUN}", f"test-user-t62-op-{RUN}"
PIVA = "88" + RUN + "621"
T = date.today()
Y = T.year
QC = (T.month - 1) // 3 + 1
COLLS = ["invoices", "passive_invoices", "parties", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "partite_aperte", "comunicazioni", "f24_versamenti", "pag_distinte"]
ST = {}
ON = {"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True, "corrispettivi": True, "contabilita": True}
COMP = {"denominazione": f"TEST_T62 Bolli {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
        "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT",
        "banche": [{"nome": "Banca T62", "iban": "IT60X0542811101000000123456", "predefinita": True}]}


def sess(tok=TOK, cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    if cid or ST.get("cid"):
        s.headers["X-Company-Id"] = cid or ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{partita_iva:"{PIVA}"}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:["{UID}","{UID_OP}"]}}}}); db.user_sessions.deleteMany({{user_id:{{$in:["{UID}","{UID_OP}"]}}}});')


def inv_send(data, prezzo):
    r = sess().post(f"{API}/invoices", json={"tipo_documento": "TD01", "data": data, "party_id": ST["c"],
                                             "lines": [{"descrizione": f"TEST_T62 esente {data}", "quantita": 1, "prezzo_unitario": prezzo, "aliquota": 0, "natura": "N2.1"}]})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["bollo_virtuale"] is True
    assert sess().post(f"{API}/invoices/{j['id']}/send").status_code == 200
    r = sess().post(f"{API}/invoices/{j['id']}/refresh")
    assert r.status_code == 200, r.text
    return r.json()


def setup_data():
    clean()
    for uid, tok, role in ((UID, TOK, "admin"), (UID_OP, TOK_OP, "operatore")):
        mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.t62.{uid}@example.com", name:"TEST_T62 {role}", picture:"", role:"{role}", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
              f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess(cid="").post(f"{API}/companies", json=COMP)
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    assert sess().put(f"{API}/companies/{ST['cid']}/moduli", json=ON).status_code == 200
    mongo(f'db.users.updateOne({{user_id:"{UID_OP}"}}, {{$set:{{company_ids:["{ST["cid"]}"]}}}})')
    r = sess().post(f"{API}/parties", json={"tipo": "cliente", "denominazione": "TEST_T62 Cliente", "partita_iva": "0" + RUN + "6211", "codice_fiscale": "0" + RUN + "6211",
                                           "codice_destinatario": "ABC1234", "indirizzo": "Via Milano 2", "cap": "20100", "comune": "Milano", "provincia": "MI"})
    assert r.status_code == 200, r.text
    ST["c"] = r.json()["id"]
    ST["inv"] = {}
    for q, d in ((1, f"{Y}-02-10"), (2, f"{Y}-05-10"), (3, f"{Y}-08-10"), (QC, T.isoformat())):
        if q < QC or d == T.isoformat():
            ST["inv"][q] = inv_send(d, 100 + q)
    return ST


@pytest.fixture(scope="module", autouse=True)
def setup():
    setup_data()
    yield
    clean()


def entries(origine=None, ref=None):
    rows = sess().get(f"{API}/contabilita/registrazioni", params={"dal": f"{Y - 1}-01-01", "al": f"{Y + 1}-12-31"}).json()["registrazioni"]
    return [e for e in rows if (origine is None or e["origine"] == origine) and (ref is None or e.get("ref_id") == ref)]


def bolli_q(q, anno=Y):
    return sess().get(f"{API}/bolli", params={"anno": anno}).json()["trimestri"][q - 1]


def ins_entry(origine, ref, anno=Y, data=None):
    eid = f"t62-{RUN}-{uuid.uuid4().hex[:8]}"
    mongo(f'db.coa_entries.insertOne({{id:"{eid}", company_id:"{ST["cid"]}", anno:{anno}, numero:{random.randint(5000, 9999)}, data:"{data or f"{anno}-10-01"}", causale:"GE",'
          f'causale_descrizione:"GE", descrizione:"TEST_T62 {origine}", origine:"{origine}", ref_id:"{ref}", totale:10, created_by:"t62", created_at:new Date().toISOString(),'
          f'righe:[{{conto:"30.14.002", dare:10, avere:0, conto_descrizione:"x"}}, {{conto:"06.01.001", dare:0, avere:10, conto_descrizione:"y"}}]}})')
    return eid


def delete(eid):
    return sess().delete(f"{API}/contabilita/registrazioni/{eid}")


def count(coll, flt):
    return int(mongo(f'print(db.{coll}.countDocuments({json.dumps({"company_id": ST["cid"], **flt})}))') or 0)


# Bolli report keys / versato / concluso and dashboard scadenze
class TestBolliScadenze:
    def test_01_report_fields(self):
        tr = sess().get(f"{API}/bolli", params={"anno": Y}).json()["trimestri"]
        for q in tr:
            assert q["key"] == f"BOL-{Y}-{q['trimestre']}" and q["versato"] is None
        assert [q["concluso"] for q in tr] == [q < QC for q in range(1, 5)]
        for q in range(1, QC):
            assert tr[q - 1]["importo"] == 2 and tr[q - 1]["n"] == 1, tr[q - 1]

    def test_02_dashboard_items(self):
        sc = sess().get(f"{API}/scadenze-fiscali").json()["scadenze"]
        bol = {x["key"]: x for x in sc if x["tipo"] == "bolli"}
        ST["dash_keys"] = list(bol)
        lo, hi = date.fromordinal(T.toordinal() - 90).isoformat(), date.fromordinal(T.toordinal() + 75).isoformat()
        for q in range(1, 5):
            tq = bolli_q(q)
            exp = tq["importo"] > 0 and lo <= tq["scadenza"] <= hi
            assert (f"BOL-{Y}-{q}" in bol) is exp, (q, tq, list(bol))
        assert bol, "expected at least one bolli item in dashboard window"
        for k, x in bol.items():
            q = int(k[-1])
            assert x["codice"] == f"252{q}" and x["importo"] == 2 and x["trimestre"] == q and x["anno_riferimento"] == Y
            assert x["stato"] in ("scaduta", "in_scadenza", "prossima") and x["versato"] is None and "scadenza" in x

    def test_03_versato_errors(self):
        r = sess().post(f"{API}/scadenze-fiscali/versato", json={"key": f"BOL-{Y}-{QC}"})
        assert r.status_code == 400 and "provvisorio" in r.json()["detail"], r.text
        r = sess().post(f"{API}/scadenze-fiscali/versato", json={"key": f"BOL-{Y - 1}-1"})
        assert r.status_code == 404, r.text
        assert sess().post(f"{API}/scadenze-fiscali/versato", json={"key": f"BOL-{Y}-5"}).status_code == 422
        assert sess().post(f"{API}/scadenze-fiscali/versato", json={"key": f"BOL-{Y}-1", "data": "2026-13-45"}).status_code == 422
        assert sess(TOK_OP).post(f"{API}/scadenze-fiscali/versato", json={"key": f"BOL-{Y}-1"}).status_code == 403
        assert count("f24_versamenti", {}) == 0

    def test_04_versato_old_quarter_prima_nota(self):
        # Q1 scadenza (31/05 -> 01/06) is outside the dashboard window -> fallback path
        assert f"BOL-{Y}-1" not in ST["dash_keys"]
        r = sess().post(f"{API}/scadenze-fiscali/versato", json={"key": f"BOL-{Y}-1", "data": f"{Y}-06-01"})
        assert r.status_code == 200, r.text
        q = bolli_q(1)
        assert q["versato"]["data"] == f"{Y}-06-01" and q["versato"]["importo"] == 2, q
        es = entries("bolli", f"BOL-{Y}-1")
        assert len(es) == 1, es
        e = es[0]
        assert e["causale"] == "GE" and e["data"] == f"{Y}-06-01" and "2521" in e["descrizione"]
        rg = {x["conto"]: x for x in e["righe"]}
        assert rg["30.14.002"]["dare"] == 2 and rg["06.01.001"]["avere"] == 2, e["righe"]
        ST["e1"] = e["id"]
        # repeat -> still one entry (replace)
        assert sess().post(f"{API}/scadenze-fiscali/versato", json={"key": f"BOL-{Y}-1", "data": f"{Y}-06-02"}).status_code == 200
        es = entries("bolli", f"BOL-{Y}-1")
        assert len(es) == 1 and es[0]["data"] == f"{Y}-06-02"
        ST["e1"] = es[0]["id"]

    def test_05_versato_dashboard_quarter(self):
        k = sorted(ST["dash_keys"])[-1]
        r = sess().post(f"{API}/scadenze-fiscali/versato", json={"key": k})
        assert r.status_code == 200, r.text
        sc = {x["key"]: x for x in sess().get(f"{API}/scadenze-fiscali").json()["scadenze"]}
        tq = bolli_q(int(k[-1]))
        if tq["scadenza"] < T.isoformat():
            assert k not in sc  # paid and past -> hidden
        else:
            assert sc[k]["stato"] == "versato" and sc[k]["versato"]["data"] == T.isoformat()
        assert tq["versato"]["data"] == T.isoformat()
        assert len(entries("bolli", k)) == 1
        # annulla -> removes versamento + entry
        r = sess().delete(f"{API}/scadenze-fiscali/versato/{k}")
        assert r.status_code == 200, r.text
        assert bolli_q(int(k[-1]))["versato"] is None and entries("bolli", k) == []
        assert sess().delete(f"{API}/scadenze-fiscali/versato/{k}").status_code == 404

    def test_06_delete_bolli_entry_removes_versamento(self):
        r = delete(ST["e1"])
        assert r.status_code == 200, r.text
        assert bolli_q(1)["versato"] is None
        assert count("f24_versamenti", {"key": f"BOL-{Y}-1"}) == 0
        assert sess().get(f"{API}/contabilita/registrazioni/{ST['e1']}").status_code == 404

    def test_07_closed_year_blocks_annulla(self):
        assert sess().post(f"{API}/scadenze-fiscali/versato", json={"key": f"BOL-{Y}-1", "data": f"{Y}-06-01"}).status_code == 200
        mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}}, {{$set:{{coge_chiusi:[{Y}]}}}})')
        try:
            r = sess().delete(f"{API}/scadenze-fiscali/versato/BOL-{Y}-1")
            assert r.status_code == 400 and "chiuso" in r.json()["detail"], r.text
            r = delete(entries("bolli", f"BOL-{Y}-1")[0]["id"])
            assert r.status_code == 400 and "chiuso" in r.json()["detail"], r.text
            assert bolli_q(1)["versato"] is not None
        finally:
            mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}}, {{$unset:{{coge_chiusi:1}}}})')
        assert sess().delete(f"{API}/scadenze-fiscali/versato/BOL-{Y}-1").status_code == 200


# DELETE /api/contabilita/registrazioni/{rid}
class TestDeleteRegistrazioni:
    def test_01_vendita_consegnata_blocked(self):
        inv = ST["inv"][1]
        assert inv["status"] == "consegnata", inv["status"]
        es = entries("vendita", inv["id"])
        assert len(es) == 1, es
        r = delete(es[0]["id"])
        assert r.status_code == 400 and "SDI" in r.json()["detail"], r.text
        mongo(f'db.invoices.updateOne({{id:"{inv["id"]}"}}, {{$set:{{status:"mancata_consegna"}}}})')
        assert delete(es[0]["id"]).status_code == 400
        # not (yet) accepted -> deletable
        mongo(f'db.invoices.updateOne({{id:"{inv["id"]}"}}, {{$set:{{status:"inviata"}}}})')
        r = delete(es[0]["id"])
        assert r.status_code == 200, r.text
        assert entries("vendita", inv["id"]) == []
        mongo(f'db.invoices.updateOne({{id:"{inv["id"]}"}}, {{$set:{{status:"consegnata"}}}})')

    def test_02_passive_sdi_blocked_upload_allowed(self):
        r = sess().post(f"{API}/passive/sdi-sync")
        assert r.status_code == 200, r.text
        docs = r.json()["ricevute"]
        assert docs
        pid = docs[0]["id"] if isinstance(docs[0], dict) else docs[0]
        es = entries("acquisto", pid)
        assert len(es) == 1, es
        r = delete(es[0]["id"])
        assert r.status_code == 400 and "SDI" in r.json()["detail"], r.text
        xml = demo_xmls(COMP, 1)[0]
        r = sess().post(f"{API}/passive/upload", files=[("files", ("t62.xml", xml, "text/xml"))])
        assert r.status_code == 200 and r.json()[0]["ok"], r.text
        d = r.json()[0]["documenti"][0]
        pid2 = d["id"] if isinstance(d, dict) else d
        es = entries("acquisto", pid2)
        assert len(es) == 1, es
        r = delete(es[0]["id"])
        assert r.status_code == 200, r.text
        assert entries("acquisto", pid2) == []

    def test_03_riba_blocked(self):
        for o in ("riba", "riba_scadenza", "riba_insoluto"):
            eid = ins_entry(o, f"t62-riba-{o}")
            r = delete(eid)
            assert r.status_code == 400 and "Ri.Ba." in r.json()["detail"], (o, r.text)

    def test_04_other_origins_deletable(self):
        for o in ("banca", "liquidazione", "importazione", "manuale"):
            eid = ins_entry(o, f"t62-ref-{o}")
            r = delete(eid)
            assert r.status_code == 200, (o, r.text)
            assert sess().get(f"{API}/contabilita/registrazioni/{eid}").status_code == 404

    def test_05_manual_api_entry(self):
        r = sess().post(f"{API}/contabilita/registrazioni", json={"data": T.isoformat(), "causale": "GE", "descrizione": "TEST_T62 manuale",
                                                                 "righe": [{"conto": "30.14.002", "dare": 5}, {"conto": "06.01.001", "avere": 5}]})
        assert r.status_code == 200, r.text
        eid = r.json()["id"]
        assert delete(eid).status_code == 200
        assert sess().get(f"{API}/contabilita/registrazioni/{eid}").status_code == 404
        assert delete(eid).status_code == 404

    def test_06_pagamenti_side_effects(self):
        did = f"t62-dist-{RUN}"
        mongo(f'db.pag_distinte.insertOne({{id:"{did}", company_id:"{ST["cid"]}", numero:1, anno:{Y}, numero_display:"1/{Y}", data:"{Y}-10-01", partite:[], totale:10}});'
              f'db.passive_payments.insertMany([{{id:"t62-pp1-{RUN}", company_id:"{ST["cid"]}", invoice_id:"x", importo:5, data:"{Y}-10-01", distinta_pag_id:"{did}"}},'
              f'{{id:"t62-pp2-{RUN}", company_id:"{ST["cid"]}", invoice_id:"x", importo:5, data:"{Y}-10-01", distinta_pag_id:"{did}"}}]);')
        eid = ins_entry("pagamenti", did)
        assert delete(eid).status_code == 200
        assert count("pag_distinte", {"id": did}) == 0 and count("passive_payments", {"distinta_pag_id": did}) == 0

    def test_07_ritenute_side_effects(self):
        key = f"RIT-{Y}-09"
        mongo(f'db.f24_versamenti.insertOne({{company_id:"{ST["cid"]}", key:"{key}", codice:"1040", importo:10, data:"{Y}-10-16"}})')
        eid = ins_entry("ritenute", key)
        assert delete(eid).status_code == 200
        assert count("f24_versamenti", {"key": key}) == 0

    def test_08_saldaconto_payment_removed(self):
        eid = ins_entry("manuale", None)
        inv = ST["inv"][2]
        mongo(f'db.payments.insertOne({{id:"t62-pay-{RUN}", company_id:"{ST["cid"]}", invoice_id:"{inv["id"]}", party_id:"{ST["c"]}", importo:1, data:"{Y}-10-01",'
              f'metodo:"bonifico", coge_entry_id:"{eid}", numero_display:"{inv["numero_display"]}"}})')
        r = delete(eid)
        assert r.status_code == 200, r.text
        assert count("payments", {"coge_entry_id": eid}) == 0

    def test_09_closed_year_blocks(self):
        eid = ins_entry("manuale", "t62-closed")
        mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}}, {{$set:{{coge_chiusi:[{Y}]}}}})')
        try:
            r = delete(eid)
            assert r.status_code == 400 and "chiuso" in r.json()["detail"], r.text
        finally:
            mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}}, {{$unset:{{coge_chiusi:1}}}})')
        assert delete(eid).status_code == 200

    def test_10_operatore_and_isolation(self):
        eid = ins_entry("manuale", "t62-op")
        assert sess(TOK_OP).delete(f"{API}/contabilita/registrazioni/{eid}").status_code == 403
        assert delete("does-not-exist").status_code == 404
        assert delete(eid).status_code == 200


if __name__ == "__main__":
    if sys.argv[1] == "setup":
        print(json.dumps({**setup_data(), "tok": TOK}, default=str)[:3000])
    else:
        clean()

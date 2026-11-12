# Iteration 63: prima nota eliminabile/motivo_blocco (GET /api/contabilita/registrazioni + DELETE same rules)
# and GET /api/f24-storico (IVA / ritenute / bolli versamenti, labels, totals, filters, isolation, menu 403, ristampa endpoints).
# Run: pytest tests/test_iteration63_eliminabile_storico_f24.py -v -n 0
# UI fixtures: T63_RUN=123456 python tests/test_iteration63_eliminabile_storico_f24.py setup|clean
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

RUN = os.environ.get("T63_RUN") or str(random.randint(100000, 999999))
TOK, UID = f"test_session_t63_admin_{RUN}", f"test-user-t63-admin-{RUN}"
PIVA, PIVA2 = "88" + RUN + "631", "88" + RUN + "632"
T = date.today()
Y = T.year
COLLS = ["invoices", "passive_invoices", "parties", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "partite_aperte", "comunicazioni", "f24_versamenti", "pag_distinte"]
ST = {}
ON = {"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True, "corrispettivi": True, "contabilita": True}
COMP = {"denominazione": f"TEST_T63 Storico {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
        "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT",
        "banche": [{"nome": "Banca T63", "iban": "IT60X0542811101000000123456", "predefinita": True}]}


def sess(cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    c = ST.get("cid") if cid is None else cid
    if c:
        s.headers["X-Company-Id"] = c
    return s


def clean():
    for p in (PIVA, PIVA2):
        mongo(f'db.companies.find({{partita_iva:"{p}"}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
              f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});')
    mongo(f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def inv_send(data, prezzo, aliquota=0):
    line = {"descrizione": f"TEST_T63 {data}", "quantita": 1, "prezzo_unitario": prezzo, "aliquota": aliquota, **({"natura": "N2.1"} if not aliquota else {})}
    r = sess().post(f"{API}/invoices", json={"tipo_documento": "TD01", "data": data, "party_id": ST["c"], "lines": [line]})
    assert r.status_code == 200, r.text
    j = r.json()
    assert sess().post(f"{API}/invoices/{j['id']}/send").status_code == 200
    r = sess().post(f"{API}/invoices/{j['id']}/refresh")
    assert r.status_code == 200, r.text
    return r.json()


def setup_data():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t63.{RUN}@example.com", name:"TEST_T63 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess(cid="").post(f"{API}/companies", json=COMP)
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    assert sess().put(f"{API}/companies/{ST['cid']}/moduli", json=ON).status_code == 200
    r = sess().post(f"{API}/parties", json={"tipo": "cliente", "denominazione": "TEST_T63 Cliente", "partita_iva": "0" + RUN + "6311", "codice_fiscale": "0" + RUN + "6311",
                                           "codice_destinatario": "ABC1234", "indirizzo": "Via Milano 2", "cap": "20100", "comune": "Milano", "provincia": "MI"})
    assert r.status_code == 200, r.text
    ST["c"] = r.json()["id"]
    # bolli Q2/Q3 (esente > 77.47) + IVA settembre (22%)
    ST["inv_b2"] = inv_send(f"{Y}-05-10", 200)
    ST["inv_b3"] = inv_send(f"{Y}-08-10", 300)
    ST["inv_iva"] = inv_send(f"{Y}-09-10", 1000, 22)
    # passive: SDI simulated + uploaded
    r = sess().post(f"{API}/passive/sdi-sync")
    assert r.status_code == 200, r.text
    d = r.json()["ricevute"][0]
    ST["pas_sdi"] = d["id"] if isinstance(d, dict) else d
    r = sess().post(f"{API}/passive/upload", files=[("files", ("t63.xml", demo_xmls(COMP, 1)[0], "text/xml"))])
    assert r.status_code == 200 and r.json()[0]["ok"], r.text
    d = r.json()[0]["documenti"][0]
    ST["pas_up"] = d["id"] if isinstance(d, dict) else d
    # ritenute: passive invoice with ritenuta paid in September and October
    pid = f"t63-rit-{RUN}"
    mongo(f'db.passive_invoices.insertOne({{id:"{pid}", company_id:"{ST["cid"]}", numero:"R{RUN}", numero_display:"R{RUN}", data:"{Y}-09-01", ritenuta_importo:200, ritenuta_aliquota:20, totale:1200, imponibile:1000, imposta:0, scadenze:[], tipo_documento:"TD01", stato_pagamento:"pagata",'
          f'netto:1000, fornitore:{{denominazione:"TEST_T63 Professionista", partita_iva:"01234567890"}}, origine:"manuale", lines:[]}});'
          f'db.passive_payments.insertMany([{{id:"t63-pp1-{RUN}", company_id:"{ST["cid"]}", invoice_id:"{pid}", importo:500, data:"{Y}-09-15", metodo:"bonifico", created_at:"{Y}-09-15"}},'
          f'{{id:"t63-pp2-{RUN}", company_id:"{ST["cid"]}", invoice_id:"{pid}", importo:500, data:"{Y}-10-15", metodo:"bonifico", created_at:"{Y}-10-15"}}]);')
    return ST


@pytest.fixture(scope="module", autouse=True)
def setup():
    setup_data()
    yield
    if not os.environ.get("T63_KEEP"):
        clean()


def regs():
    r = sess().get(f"{API}/contabilita/registrazioni", params={"dal": f"{Y - 1}-01-01", "al": f"{Y + 1}-12-31"})
    assert r.status_code == 200, r.text
    return r.json()["registrazioni"]


def by_ref(origine, ref):
    return [e for e in regs() if e["origine"] == origine and e.get("ref_id") == ref]


def ins_entry(origine, ref, anno=Y):
    eid = f"t63-{RUN}-{uuid.uuid4().hex[:8]}"
    mongo(f'db.coa_entries.insertOne({{id:"{eid}", company_id:"{ST["cid"]}", anno:{anno}, numero:{random.randint(5000, 9999)}, data:"{anno}-10-01", causale:"GE",'
          f'causale_descrizione:"GE", descrizione:"TEST_T63 {origine}", origine:"{origine}", ref_id:"{ref}", totale:10, created_by:"t63", created_at:new Date().toISOString(),'
          f'righe:[{{conto:"30.14.002", dare:10, avere:0, conto_descrizione:"x"}}, {{conto:"06.01.001", dare:0, avere:10, conto_descrizione:"y"}}]}})')
    return eid


def storico(**p):
    r = sess().get(f"{API}/f24-storico", params=p)
    assert r.status_code == 200, r.text
    return r.json()


# Prima nota eliminabile / motivo_blocco
class TestEliminabile:
    def test_01_fields_present(self):
        rows = regs()
        assert rows
        for e in rows:
            assert isinstance(e["eliminabile"], bool) and "motivo_blocco" in e
            assert (e["motivo_blocco"] is None) == e["eliminabile"], e

    def test_02_vendita_consegnata_locked_matches_delete(self):
        inv = ST["inv_b2"]
        assert inv["status"] == "consegnata"
        e = by_ref("vendita", inv["id"])[0]
        assert e["eliminabile"] is False and inv["numero_display"] in e["motivo_blocco"]
        r = sess().delete(f"{API}/contabilita/registrazioni/{e['id']}")
        assert r.status_code == 400 and r.json()["detail"] == e["motivo_blocco"]
        mongo(f'db.invoices.updateOne({{id:"{inv["id"]}"}}, {{$set:{{status:"mancata_consegna"}}}})')
        assert by_ref("vendita", inv["id"])[0]["eliminabile"] is False
        mongo(f'db.invoices.updateOne({{id:"{inv["id"]}"}}, {{$set:{{status:"inviata"}}}})')
        e2 = by_ref("vendita", inv["id"])[0]
        assert e2["eliminabile"] is True and e2["motivo_blocco"] is None
        mongo(f'db.invoices.updateOne({{id:"{inv["id"]}"}}, {{$set:{{status:"consegnata"}}}})')

    def test_03_passive_sdi_locked_upload_free(self):
        e = by_ref("acquisto", ST["pas_sdi"])[0]
        assert e["eliminabile"] is False and "SDI" in e["motivo_blocco"]
        r = sess().delete(f"{API}/contabilita/registrazioni/{e['id']}")
        assert r.status_code == 400 and r.json()["detail"] == e["motivo_blocco"]
        e2 = by_ref("acquisto", ST["pas_up"])[0]
        assert e2["eliminabile"] is True and e2["motivo_blocco"] is None

    def test_04_riba_locked_others_free(self):
        ids = {o: ins_entry(o, f"t63-{o}") for o in ("riba", "riba_scadenza", "riba_insoluto", "banca", "manuale", "liquidazione", "pagamenti")}
        m = {e["id"]: e for e in regs()}
        for o, eid in ids.items():
            exp = not o.startswith("riba")
            assert m[eid]["eliminabile"] is exp, (o, m[eid])
            if not exp:
                assert "Ri.Ba." in m[eid]["motivo_blocco"]
                r = sess().delete(f"{API}/contabilita/registrazioni/{eid}")
                assert r.status_code == 400 and r.json()["detail"] == m[eid]["motivo_blocco"]
        for o in ("banca", "manuale", "liquidazione", "pagamenti"):
            assert sess().delete(f"{API}/contabilita/registrazioni/{ids[o]}").status_code == 200
        for o in ("riba", "riba_scadenza", "riba_insoluto"):
            mongo(f'db.coa_entries.deleteOne({{id:"{ids[o]}"}})')

    def test_05_closed_year_locks_all(self):
        mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}}, {{$set:{{coge_chiusi:[{Y}]}}}})')
        try:
            rows = [e for e in regs() if e["anno"] == Y]
            assert rows and all(not e["eliminabile"] and "chiuso" in e["motivo_blocco"] for e in rows)
            up = by_ref("acquisto", ST["pas_up"])[0]
            r = sess().delete(f"{API}/contabilita/registrazioni/{up['id']}")
            assert r.status_code == 400 and r.json()["detail"] == up["motivo_blocco"]
        finally:
            mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}}, {{$unset:{{coge_chiusi:1}}}})')
        assert by_ref("acquisto", ST["pas_up"])[0]["eliminabile"] is True


# F24 versamenti + storico
class TestStoricoF24:
    def test_01_empty(self):
        d = storico()
        assert d["versamenti"] == [] and d["totale"] == 0 and d["totali"] == {"iva": 0, "ritenute": 0, "bolli": 0} and d["anni"] == []

    def test_02_versa_all(self):
        sc = {x["key"]: x for x in sess().get(f"{API}/scadenze-fiscali").json()["scadenze"]}
        ST["sc"] = sc
        for k, dt in ((f"IVA-{Y}-m-9", f"{Y}-10-14"), (f"RIT-{Y}-09", f"{Y}-10-15"), (f"RIT-{Y}-10", f"{Y}-11-10"),
                      (f"BOL-{Y}-2", f"{Y}-09-29"), (f"BOL-{Y}-3", f"{Y}-11-11")):
            assert k in sc or k.startswith("BOL-"), (k, list(sc))
            r = sess().post(f"{API}/scadenze-fiscali/versato", json={"key": k, "data": dt})
            assert r.status_code == 200, (k, r.text)

    def test_03_list_content(self):
        d = storico()
        v = {x["key"]: x for x in d["versamenti"]}
        assert set(v) == {f"IVA-{Y}-m-9", f"RIT-{Y}-09", f"RIT-{Y}-10", f"BOL-{Y}-2", f"BOL-{Y}-3"}
        assert [x["data"] for x in d["versamenti"]] == sorted([x["data"] for x in d["versamenti"]], reverse=True)
        iva = v[f"IVA-{Y}-m-9"]
        assert iva["tipo"] == "iva" and iva["periodo_label"] == f"IVA settembre {Y}" and iva["importo"] == 220 and iva["coge_rif"] is None
        assert iva["f24"] == {"anno": Y, "periodicita": "mensile", "periodo": 9} and iva["codice"] == "6009"
        r9, r10 = v[f"RIT-{Y}-09"], v[f"RIT-{Y}-10"]
        assert r9["periodo_label"] == f"Ritenute d'acconto settembre {Y}" and r9["importo"] == 100 and r9["codice"] == "1040"
        assert r10["periodo_label"] == f"Ritenute d'acconto ottobre {Y}" and r10["importo"] == 100
        assert r9["coge_rif"] and r9["coge_rif"].startswith("prima nota n. ") and r9["coge_rif"].endswith(f"/{Y}")
        b2 = v[f"BOL-{Y}-2"]
        assert b2["tipo"] == "bolli" and b2["periodo_label"] == f"Imposta di bollo 2° trimestre {Y}" and b2["importo"] == 2 and b2["trimestre"] == 2
        assert b2["codice"] == "2522" and b2["coge_rif"].startswith("prima nota n. ")
        assert all(x["by"] == "TEST_T63 admin" for x in d["versamenti"]) and all("company_id" not in x and "_id" not in x for x in d["versamenti"])
        assert d["totali"] == {"iva": 220, "ritenute": 200, "bolli": 4} and d["totale"] == 424 and d["anni"] == [Y]
        # coge_rif number matches the real entry
        e = by_ref("ritenute", f"RIT-{Y}-09")[0]
        assert r9["coge_rif"] == f"prima nota n. {e['numero']}/{e['anno']}"
        assert e["eliminabile"] is True

    def test_04_filters_and_labels(self):
        assert [x["tipo"] for x in storico(tipo="iva")["versamenti"]] == ["iva"]
        d = storico(tipo="bolli")
        assert len(d["versamenti"]) == 2 and d["totali"]["iva"] == 0 and d["totale"] == 4
        assert storico(anno=Y - 1)["versamenti"] == [] and storico(anno=Y - 1)["anni"] == [Y]
        assert sess().get(f"{API}/f24-storico", params={"anno": 1800}).status_code == 422
        # trimestrale label + older year via direct insert
        mongo(f'db.f24_versamenti.insertOne({{company_id:"{ST["cid"]}", key:"IVA-{Y - 1}-t-2", codice:"6032", importo:50, data:"{Y - 1}-08-20", by:"x"}})')
        d = storico()
        t2 = next(x for x in d["versamenti"] if x["key"] == f"IVA-{Y - 1}-t-2")
        assert t2["periodo_label"] == f"IVA 2° trimestre {Y - 1}" and t2["f24"]["periodicita"] == "trimestrale"
        assert d["anni"] == [Y, Y - 1] and d["versamenti"][-1]["key"] == f"IVA-{Y - 1}-t-2"
        assert [x["key"] for x in storico(anno=Y - 1)["versamenti"]] == [f"IVA-{Y - 1}-t-2"]
        mongo(f'db.f24_versamenti.deleteOne({{company_id:"{ST["cid"]}", key:"IVA-{Y - 1}-t-2"}})')

    def test_05_ristampa_iva_bolli(self):
        r = sess().get(f"{API}/liquidazione-iva/f24", params={"anno": Y, "periodicita": "mensile", "periodo": 9})
        assert r.status_code == 200 and r.json()["debito"]["importo"] == 220, r.text
        r = sess().post(f"{API}/liquidazione-iva/f24", json={"anno": Y, "periodicita": "mensile", "periodo": 9, "crediti": []})
        assert r.status_code == 200 and r.content[:4] == b"%PDF", r.text[:200]
        for q in (2, 3):
            r = sess().get(f"{API}/bolli/f24", params={"anno": Y, "trimestre": q})
            assert r.status_code == 200 and r.content[:4] == b"%PDF", (q, r.text[:200])

    def test_06_ristampa_ritenute_current(self):
        r = sess().get(f"{API}/scadenze-fiscali/RIT-{Y}-10/f24")
        assert r.status_code == 200 and r.content[:4] == b"%PDF", r.text[:200]

    def test_07_ristampa_ritenute_past_deadline(self):
        # RIT-Y-09 scadenza 16/10 is past and versato -> hidden from _scadenze
        r = sess().get(f"{API}/scadenze-fiscali/RIT-{Y}-09/f24")
        assert r.status_code == 200 and r.content[:4] == b"%PDF", f"{r.status_code} {r.text[:200]}"

    def test_08_isolation(self):
        r = sess(cid="").post(f"{API}/companies", json={**COMP, "denominazione": f"TEST_T63 Altra {RUN}", "partita_iva": PIVA2, "codice_fiscale": PIVA2})
        assert r.status_code == 200, r.text
        c2 = r.json()["id"]
        r = sess(cid=c2).get(f"{API}/f24-storico")
        assert r.status_code == 200 and r.json()["versamenti"] == [], r.text

    def test_09_menu_disabled_403(self):
        mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}}, {{$set:{{menu_off:["storico-f24"]}}}})')
        try:
            assert sess().get(f"{API}/f24-storico").status_code == 403
        finally:
            mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}}, {{$unset:{{menu_off:1}}}})')
        assert sess().get(f"{API}/f24-storico").status_code == 200

    def test_10_delete_reg_removes_from_storico(self):
        e = by_ref("bolli", f"BOL-{Y}-3")[0]
        assert e["eliminabile"] is True
        assert sess().delete(f"{API}/contabilita/registrazioni/{e['id']}").status_code == 200
        keys = [x["key"] for x in storico()["versamenti"]]
        assert f"BOL-{Y}-3" not in keys and len(keys) == 4
        assert sess().delete(f"{API}/scadenze-fiscali/versato/RIT-{Y}-10").status_code == 200
        assert f"RIT-{Y}-10" not in [x["key"] for x in storico()["versamenti"]]
        assert by_ref("ritenute", f"RIT-{Y}-10") == []


if __name__ == "__main__":
    if sys.argv[1] == "setup":
        print(json.dumps({**setup_data(), "tok": TOK}, default=str)[:3000])
    else:
        clean()

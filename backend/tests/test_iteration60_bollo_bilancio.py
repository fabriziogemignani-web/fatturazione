# Iteration 60: Bollo virtuale (auto/forzato, addebito cliente N1, rate, no duplicazione, XML DatiBollo, PDF cortesia, storno totale),
# report /api/bolli (mesi, trimestri 2521-2524, bozze escluse, isolamento, 403 modulo/menu off) and GET /api/contabilita/registrazioni/{rid}
# (isolamento, 404, modifica -> bilancio/mastrino aggiornati). Run: pytest tests/test_iteration60_bollo_bilancio.py -v -n 0
# UI fixtures: T60_RUN=123456 python tests/test_iteration60_bollo_bilancio.py setup|clean
import json
import os
import random
import sys
import xml.etree.ElementTree as ET
from datetime import date

import pytest
import requests

from test_iteration7_pa_scartate_registro import API, mongo

RUN = os.environ.get("T60_RUN") or str(random.randint(100000, 999999))
TOK, UID = f"test_session_t60_admin_{RUN}", f"test-user-t60-admin-{RUN}"
TOK_OP, UID_OP = f"test_session_t60_op_{RUN}", f"test-user-t60-op-{RUN}"
PIVA, PIVA2 = "86" + RUN + "601", "86" + RUN + "602"
T = date.today()
Y = T.year
COLLS = ["invoices", "passive_invoices", "parties", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "partite_aperte", "comunicazioni"]
ST = {}
ON = {"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True, "corrispettivi": True, "contabilita": True}
NS = {"p": "http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2"}


def sess(tok=TOK, cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    if cid or ST.get("cid"):
        s.headers["X-Company-Id"] = cid or ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{partita_iva:{{$in:["{PIVA}","{PIVA2}"]}}}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:["{UID}","{UID_OP}"]}}}}); db.user_sessions.deleteMany({{user_id:{{$in:["{UID}","{UID_OP}"]}}}});')


def company(name, piva):
    r = sess(cid="").post(f"{API}/companies", json={"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01",
                                                   "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    assert sess(cid=cid).put(f"{API}/companies/{cid}/moduli", json=ON).status_code == 200
    return cid


def party(name, piva, addebito, cid=None):
    r = sess(cid=cid).post(f"{API}/parties", json={"tipo": "cliente", "denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "codice_destinatario": "ABC1234",
                                                   "indirizzo": "Via Milano 2", "cap": "20100", "comune": "Milano", "provincia": "MI", "bollo_addebito": addebito})
    assert r.status_code == 200, r.text
    assert r.json()["bollo_addebito"] is addebito
    return r.json()["id"]


def setup_data():
    clean()
    for uid, tok, role in ((UID, TOK, "admin"), (UID_OP, TOK_OP, "operatore")):
        mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.t60.{uid}@example.com", name:"TEST_T60 {role}", picture:"", role:"{role}", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
              f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    ST["cid"] = company(f"TEST_T60 Bolli {RUN} Srl", PIVA)
    ST["cid2"] = company(f"TEST_T60 Altra {RUN} Srl", PIVA2)
    mongo(f'db.users.updateOne({{user_id:"{UID_OP}"}}, {{$set:{{company_ids:["{ST["cid"]}"]}}}})')
    ST["c_no"] = party("TEST_T60 Cliente NoAddebito", "0" + RUN + "6011", False)
    ST["c_si"] = party("TEST_T60 Cliente Addebito", "0" + RUN + "6012", True)
    ST["c_x"] = party("TEST_T60 Cliente Altra", "0" + RUN + "6013", True, ST["cid2"])
    return ST


@pytest.fixture(scope="module", autouse=True)
def setup():
    setup_data()
    yield
    clean()


def ln(desc, prezzo, aliquota=0, natura="N2.2", **k):
    return {"descrizione": desc, "quantita": 1, "prezzo_unitario": prezzo, "aliquota": aliquota, "natura": natura if aliquota == 0 else None, **k}


def inv(party_id, lines, data=None, cid=None, **k):
    return sess(cid=cid).post(f"{API}/invoices", json={"tipo_documento": "TD01", "data": data or T.isoformat(), "party_id": party_id, "lines": lines, **k})


def bollo_lines(j):
    return [x for x in j["lines"] if x.get("bollo")]


# Bollo auto/forzato
class TestBolloAuto:
    def test_01_auto_on_exempt(self):
        r = inv(ST["c_no"], [ln("TEST esente", 50, natura="N2.2"), ln("TEST esente2", 30, natura="N4")])
        assert r.status_code == 200, r.text
        j = r.json()
        ST["i_auto"] = j["id"]
        assert j["bollo_virtuale"] is True and j["bollo_importo"] == 2 and j["bollo_esenti"] == 80 and j["bollo_addebitato"] is False
        assert not bollo_lines(j) and j["totale"] == 80

    def test_02_threshold_and_non_bollo_nature(self):
        j = inv(ST["c_no"], [ln("TEST soglia", 77.47)]).json()
        assert j["bollo_virtuale"] is False and j["bollo_importo"] == 0
        ST["tmp"] = [j["id"]]
        for nat in ("N3.1", "N3.2", "N6.1", "N1"):
            j = inv(ST["c_no"], [ln(f"TEST {nat}", 200, natura=nat)]).json()
            assert j.get("bollo_virtuale") is False, (nat, j)
            ST["tmp"].append(j["id"])
        j = inv(ST["c_no"], [ln("TEST imponibile", 500, aliquota=22)]).json()
        assert j["bollo_virtuale"] is False and j["bollo_esenti"] == 0
        ST["tmp"].append(j["id"])

    def test_03_mixed_and_natures(self):
        for nat in ("N2.1", "N3.6"):
            j = inv(ST["c_no"], [ln("TEST imp", 100, aliquota=22), ln(f"TEST {nat}", 78, natura=nat)]).json()
            assert j.get("bollo_virtuale") is True, (nat, j)
            ST["tmp"].append(j["id"])

    def test_04_forced(self):
        j = inv(ST["c_no"], [ln("TEST esente", 100)], bollo=False).json()
        assert j["bollo_virtuale"] is False and j["bollo_dovuto"] is True
        ST["tmp"].append(j["id"])
        j = inv(ST["c_no"], [ln("TEST piccola", 10)], bollo=True).json()
        assert j["bollo_virtuale"] is True and j["bollo_importo"] == 2 and j["bollo_dovuto"] is False
        ST["tmp"].append(j["id"])

    def test_05_put_recompute(self):
        cur = sess().get(f"{API}/invoices/{ST['i_auto']}").json()
        body = {k: cur[k] for k in ("tipo_documento", "data", "party_id", "lines")}
        body["lines"] = [ln("TEST esente", 20)]
        j = sess().put(f"{API}/invoices/{ST['i_auto']}", json=body).json()
        assert j["bollo_virtuale"] is False
        body["lines"] = [ln("TEST esente", 120)]
        j = sess().put(f"{API}/invoices/{ST['i_auto']}", json=body).json()
        assert j["bollo_virtuale"] is True and j["bollo_esenti"] == 120


# Addebito al cliente
class TestBolloAddebito:
    def test_01_line_added(self):
        r = inv(ST["c_si"], [ln("TEST esente", 100)], rate=[{"scadenza": T.isoformat(), "importo": 102}])
        assert r.status_code == 200, r.text
        j = r.json()
        ST["i_add"] = j["id"]
        b = bollo_lines(j)
        assert len(b) == 1 and b[0]["prezzo_unitario"] == 2 and b[0]["natura"] == "N1" and b[0]["aliquota"] == 0
        assert b[0]["descrizione"] == "Imposta di bollo assolta in modo virtuale (art. 6 DM 17/06/2014)"
        assert j["totale"] == 102 and j["bollo_addebitato"] is True and j["bollo_esenti"] == 100

    def test_02_rate_without_bollo_rejected(self):
        r = inv(ST["c_si"], [ln("TEST esente", 100)], rate=[{"scadenza": T.isoformat(), "importo": 100}])
        assert r.status_code == 422, r.text

    def test_03_resave_no_dup(self):
        cur = sess().get(f"{API}/invoices/{ST['i_add']}").json()
        body = {k: cur[k] for k in ("tipo_documento", "data", "party_id", "lines", "rate")}
        r = sess().put(f"{API}/invoices/{ST['i_add']}", json=body)
        assert r.status_code == 200, r.text
        j = r.json()
        assert len(bollo_lines(j)) == 1 and j["totale"] == 102 and len(j["lines"]) == 2

    def test_04_forced_off_removes_line(self):
        j = inv(ST["c_si"], [ln("TEST esente", 100)], bollo=False).json()
        assert not bollo_lines(j) and j["totale"] == 100 and j["bollo_addebitato"] is False
        ST["tmp"].append(j["id"])

    def test_05_xml_dati_bollo(self):
        r = sess().get(f"{API}/invoices/{ST['i_add']}/xml")
        assert r.status_code == 200, r.text[:300]
        root = ET.fromstring(r.content)
        dg = root.find(".//DatiGeneraliDocumento")
        tags = [c.tag for c in dg]
        assert "DatiBollo" in tags, tags
        assert tags.index("DatiBollo") < tags.index("ImportoTotaleDocumento")
        db_ = dg.find("DatiBollo")
        assert db_.find("BolloVirtuale").text == "SI" and db_.find("ImportoBollo").text == "2.00"
        assert dg.find("ImportoTotaleDocumento").text == "102.00"
        r2 = sess().get(f"{API}/invoices/{ST['tmp'][0]}/xml")
        assert b"DatiBollo" not in r2.content

    def test_06_courtesy_pdf(self):
        sys.path.insert(0, "/app/backend")
        import io
        from pypdf import PdfReader
        from export_comm import courtesy_pdf
        j = sess().get(f"{API}/invoices/{ST['i_add']}").json()
        c = sess().get(f"{API}/company").json()
        txt = "".join(p.extract_text() for p in PdfReader(io.BytesIO(courtesy_pdf(c, j["cliente"], j))).pages).replace("\n", " ")
        assert "assolta in modo virtuale" in txt and "addebitata al cliente" in txt, txt[-800:]


# Storno totale and send flow
class TestStorno:
    def test_01_send_and_storno(self):
        assert sess().post(f"{API}/invoices/{ST['i_add']}/send").status_code == 200
        r = sess().post(f"{API}/invoices/{ST['i_add']}/storno-totale", json={})
        assert r.status_code == 200, r.text
        nc = r.json()
        ST["nc"] = nc["id"]
        assert nc["tipo_documento"] == "TD04"
        assert len(bollo_lines(nc)) <= 1 and len(nc["lines"]) == 1 + len(bollo_lines(nc)), nc["lines"]
        assert nc["totale"] == 102 and nc["bollo_virtuale"] is True


# Report bolli
class TestReport:
    def test_01_report(self):
        # send automatica 'i_auto' -> counts; insert autofattura in Feb and other company doc
        assert sess().post(f"{API}/invoices/{ST['i_auto']}/send").status_code == 200
        assert sess().post(f"{API}/invoices/{ST['nc']}/send").status_code == 200
        mongo(f'db.invoices.insertOne({{id:"t60af-{RUN}", company_id:"{ST["cid"]}", anno:{Y}, data:"{Y}-02-10", numero:1, numero_display:"TEST_T60 AF-1", sezionale:"AF",'
              f'tipo_documento:"TD17", autofattura:true, status:"consegnata", bollo_virtuale:true, bollo_importo:2, bollo_addebitato:false, bollo_esenti:90, totale:90, cliente:{{denominazione:"TEST forn"}}}})')
        x = inv(ST["c_x"], [ln("TEST esente altra", 100)], cid=ST["cid2"]).json()
        assert x["bollo_virtuale"] is True
        sess(cid=ST["cid2"]).post(f"{API}/invoices/{x['id']}/send")
        r = sess().get(f"{API}/bolli", params={"anno": Y})
        assert r.status_code == 200, r.text
        j = r.json()
        ST["rep"] = j
        assert len(j["mesi"]) == 12 and len(j["trimestri"]) == 4
        m = j["mesi"][T.month - 1]
        assert m["fatture"] == 2 and m["note_credito"] == 1 and m["n"] >= 3, m
        assert m["importo"] == 2 * m["n"] and m["addebitati"] >= 4  # i_add + nc both addebitati
        assert m["bozze"] >= 3  # forced/aux drafts with bollo on
        feb = j["mesi"][1]
        assert feb["autofatture"] >= 1
        exp_n = 4  # i_auto, i_add, nc (this month) + autofattura (Feb)
        assert j["n"] == exp_n and j["totale"] == 2 * exp_n, j
        assert [q["codice_tributo"] for q in j["trimestri"]] == ["2521", "2522", "2523", "2524"]
        # scadenze are now shifted to the next working day (iteration 62)
        from datetime import timedelta
        def lav(d):
            while d.weekday() >= 5:
                d += timedelta(days=1)
            return d.isoformat()
        assert [q["scadenza"] for q in j["trimestri"]] == [lav(date(Y, 5, 31)), lav(date(Y, 9, 30)), lav(date(Y, 11, 30)), lav(date(Y + 1, 2, 28))]
        assert round(sum(q["importo"] for q in j["trimestri"]), 2) == j["totale"]
        ids = {r_["id"]: r_ for r_ in j["righe"]}
        assert x["id"] not in ids
        assert ids[ST["nc"]]["tipo"] == "note_credito" and ids[f"t60af-{RUN}"]["tipo"] == "autofatture"
        bz = [r_ for r_ in j["righe"] if r_["status"] == "bozza"]
        assert bz and all(not r_["da_pagare"] for r_ in bz)

    def test_02_validation_roles(self):
        assert sess().get(f"{API}/bolli", params={"anno": 1990}).status_code == 422
        assert sess().get(f"{API}/bolli").status_code == 422
        assert sess(TOK_OP).get(f"{API}/bolli", params={"anno": Y}).status_code == 200

    def test_03_module_menu_off(self):
        u = f"{API}/companies/{ST['cid']}/moduli"
        sess().put(u, json={**ON, "fatture_attive": False})
        try:
            assert sess().get(f"{API}/bolli", params={"anno": Y}).status_code == 403
        finally:
            sess().put(u, json=ON)
        m = f"{API}/companies/{ST['cid']}/menu"
        assert sess().put(m, json={"off": ["bolli-virtuali"]}).status_code == 200
        try:
            assert sess().get(f"{API}/bolli", params={"anno": Y}).status_code == 403
        finally:
            sess().put(m, json={"off": []})
        assert sess().get(f"{API}/bolli", params={"anno": Y}).status_code == 200


# Contabilità: GET registrazione, edit -> bilancio/mastrino
class TestRegistrazione:
    def test_01_get_reg_and_edit(self):
        s = sess()
        r = s.post(f"{API}/contabilita/registrazioni", json={"data": T.isoformat(), "causale": "GE", "descrizione": "TEST_T60 man",
                                                           "righe": [{"conto": "06.02.001", "dare": 100}, {"conto": "06.01.001", "avere": 100}]})
        assert r.status_code == 200, r.text
        rid = r.json()["id"]
        ST["rid"] = rid
        g = s.get(f"{API}/contabilita/registrazioni/{rid}")
        assert g.status_code == 200 and g.json()["id"] == rid and "_id" not in g.json()
        assert g.json()["righe"][0]["conto"] == "06.02.001"
        assert sess(cid=ST["cid2"]).get(f"{API}/contabilita/registrazioni/{rid}").status_code == 404
        assert s.get(f"{API}/contabilita/registrazioni/nope").status_code == 404
        assert sess(TOK_OP).get(f"{API}/contabilita/registrazioni/{rid}").status_code == 200
        b0 = {x["codice"]: x for x in s.get(f"{API}/contabilita/bilancio").json()["righe"]}
        assert b0["06.02.001"]["dare"] >= 100
        u = s.put(f"{API}/contabilita/registrazioni/{rid}", json={"data": T.isoformat(), "causale": "GE", "descrizione": "TEST_T60 man edit",
                                                                "righe": [{"conto": "06.02.001", "dare": 150}, {"conto": "06.01.001", "avere": 150}]})
        assert u.status_code == 200, u.text
        b1 = {x["codice"]: x for x in s.get(f"{API}/contabilita/bilancio").json()["righe"]}
        assert round(b1["06.02.001"]["dare"] - b0["06.02.001"]["dare"], 2) == 50
        m = s.get(f"{API}/contabilita/mastrino", params={"conto": "06.02.001"}).json()
        mv = [x for x in m["movimenti"] if x["id"] == rid]
        assert mv and mv[0]["dare"] == 150 and mv[0]["descrizione"] == "TEST_T60 man edit"
        assert sess(TOK_OP).put(f"{API}/contabilita/registrazioni/{rid}", json={"data": T.isoformat(), "causale": "GE", "descrizione": "x",
                                                                               "righe": [{"conto": "06.02.001", "dare": 1}, {"conto": "06.01.001", "avere": 1}]}).status_code == 403

    def test_02_sale_with_bollo_registered(self):
        s = sess()
        r = s.post(f"{API}/invoices/{ST['i_add']}/refresh")
        assert r.status_code == 200, r.text
        regs = s.get(f"{API}/contabilita/registrazioni", params={"origine": "vendita"}).json()["registrazioni"]
        e = [x for x in regs if x.get("ref_id") == ST["i_add"]]
        assert e, [x.get("documento") for x in regs]
        assert e[0]["totale"] == 102, e[0]


if __name__ == "__main__":
    if sys.argv[1] == "setup":
        print(json.dumps({**setup_data(), "tok": TOK, "tok_op": TOK_OP}))
    else:
        clean()

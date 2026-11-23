# Iteration 125: rateizzazioni fiscali (AI PDF reading, CRUD, payment -> prima nota), avvisi, situazione finanziaria.
# Run: pytest tests/test_iteration125_rateizzazioni.py -v -n 0   (T125_KEEP=1 keeps data for UI testing in /tmp/t125.json)
import json
import os
import random
import sys
from datetime import date, timedelta

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

RUN = str(random.randint(100000, 999999))
TOK, UID = "test_session_t125_admin", "test-user-t125-admin"
PIVA = "15" + RUN + "151"
ST = {}
COLLS = ["invoices", "passive_invoices", "parties", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "audit", "partite_aperte", "bank_tx", "bank_accounts", "rateizzazioni", "rateizzazioni_pdf", "ai_crediti_mov", "iva_registri"]
T = date.today()
D = lambda n: (T - timedelta(days=n)).isoformat()  # noqa: E731
F = lambda n: (T + timedelta(days=n)).isoformat()  # noqa: E731
PDF = os.path.join(os.path.dirname(__file__), "fixtures_piano_ade.pdf")


def sess(cid=None):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {TOK}", "X-Requested-With": "invoix"})
    c = cid if cid is not None else ST.get("cid")
    if c:
        s.headers["X-Company-Id"] = c
    return s


def clean():
    mongo(f'db.companies.find({{denominazione:/^TEST_T125/}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def mk_company(name, piva, contab):
    r = sess("").post(f"{API}/companies", json={"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01",
                                               "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    s = sess(cid)
    s.put(f"{API}/companies/{cid}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                 "corrispettivi": True, "contabilita": contab})
    c = s.get(f"{API}/company").json()
    c["banche"] = [{"nome": "TEST_Banca Uno", "iban": "IT60X0542811101000000123456", "predefinita": True}]
    assert s.put(f"{API}/company", json=c).status_code == 200
    return cid


def plan(rate, data=None, **kw):
    return {"ente": "Agenzia delle Entrate", "numero": f"TEST_{RUN}", "descrizione": "TEST_ avviso bonario", "data": data or D(60),
            "rate": rate, **kw}


def entries(ref):
    out = mongo(f'print(JSON.stringify(db.coa_entries.find({{company_id:"{ST["cid"]}", origine:"rateizzazione", ref_id:"{ref}"}}, {{_id:0}}).toArray()))')
    return json.loads(out or "[]")


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t125.admin@example.com", name:"TEST_T125 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    ST["cid"] = mk_company("TEST_T125 Contab Srl", PIVA, True)
    ST["cid2"] = mk_company("TEST_T125 NoContab Srl", "16" + RUN + "161", False)
    sess().get(f"{API}/contabilita/conti")
    yield
    if os.environ.get("T125_KEEP"):
        json.dump({**ST, "tok": TOK}, open("/tmp/t125.json", "w"))
        print("\nKEEP", ST)
    else:
        clean()


class TestRateizzazioni:
    # AI PDF reading
    def test_01_leggi_pdf_non_pdf(self):
        r = sess().post(f"{API}/rateizzazioni/leggi-pdf", files={"file": ("x.txt", b"hello world", "text/plain")})
        assert r.status_code == 400, r.text

    def test_02_leggi_pdf_ai(self):
        before = sess().get(f"{API}/company").json()
        with open(PDF, "rb") as f:
            r = sess().post(f"{API}/rateizzazioni/leggi-pdf", files={"file": ("piano.pdf", f.read(), "application/pdf")}, timeout=180)
        assert r.status_code == 200, r.text
        j = r.json()
        print("AI", json.dumps(j)[:1500])
        ST["ai"] = j
        assert j["pdf_id"] and j["ente"]
        assert "2026/0012345" in j["numero"], j["numero"]
        assert [x["scadenza"] for x in j["rate"]] == ["2026-04-15", "2026-07-31", "2026-10-31", "2027-01-31"], j["rate"]
        assert all(x["capitale"] == 1000 and x["sanzioni"] == 100 for x in j["rate"]), j["rate"]
        assert [x["interessi"] for x in j["rate"]] == [20, 15, 10, 5], j["rate"]
        assert j["conto_debito"] == "13.05.003"
        print("crediti before", {k: v for k, v in before.items() if "credit" in k.lower()})

    # create / list
    def test_03_create_from_ai_and_pdf(self):
        j = ST["ai"]
        body = {k: j[k] for k in ("ente", "numero", "descrizione", "data", "note", "pdf_id", "conto_debito", "conto_sanzioni", "conto_interessi")}
        body["numero"] = f"TEST_{j['numero']}"
        body["data"] = D(60)
        body["rate"] = j["rate"]
        r = sess().post(f"{API}/rateizzazioni", json=body)
        assert r.status_code == 200, r.text
        p = r.json()
        ST["P_ai"] = p["id"]
        assert p["totale"] == 4450.0 and p["residuo"] == 4450.0 and p["pagato"] == 0, p
        g = sess().get(f"{API}/rateizzazioni/{p['id']}/pdf")
        assert g.status_code == 200 and g.headers["content-type"].startswith("application/pdf") and g.content.startswith(b"%PDF")

    def test_04_create_manual_stati(self):
        rate = [{"scadenza": D(5), "capitale": 500, "sanzioni": 50, "interessi": 5},
                {"scadenza": F(5), "capitale": 300, "sanzioni": 0, "interessi": 3},
                {"scadenza": F(70), "capitale": 300, "sanzioni": 0, "interessi": 2}]
        r = sess().post(f"{API}/rateizzazioni", json=plan(list(reversed(rate))))
        assert r.status_code == 200, r.text
        p = r.json()
        ST["P"] = p["id"]
        assert [x["stato"] for x in p["rate"]] == ["scaduta", "in_scadenza", "da_pagare"], p["rate"]
        assert [x["n"] for x in p["rate"]] == [1, 2, 3]
        assert p["rate_scadute"] == 1 and p["totale"] == 1160.0
        lst = sess().get(f"{API}/rateizzazioni").json()
        assert any(x["id"] == p["id"] for x in lst["piani"]) and lst["conti_pagamento"]["conti"], lst.get("conti_pagamento")
        g = sess().get(f"{API}/rateizzazioni/{p['id']}/pdf")
        assert g.status_code == 404

    def test_05_validation(self):
        assert sess().post(f"{API}/rateizzazioni", json=plan([{"scadenza": F(5), "capitale": 0}])).status_code in (400, 422)
        assert sess().post(f"{API}/rateizzazioni", json=plan([])).status_code in (400, 422)
        assert sess().post(f"{API}/rateizzazioni", json=plan([{"scadenza": F(5), "capitale": 10}], conto_debito="99.99.999")).status_code == 400

    def test_06_put_edit(self):
        body = plan([{"scadenza": D(5), "capitale": 500, "sanzioni": 50, "interessi": 5},
                     {"scadenza": F(5), "capitale": 300, "sanzioni": 0, "interessi": 3},
                     {"scadenza": F(70), "capitale": 400, "sanzioni": 0, "interessi": 2}])
        body["descrizione"] = "TEST_ modificato"
        r = sess().put(f"{API}/rateizzazioni/{ST['P']}", json=body)
        assert r.status_code == 200, r.text
        assert r.json()["descrizione"] == "TEST_ modificato" and r.json()["totale"] == 1260.0

    # avvisi
    def test_07_avvisi(self):
        j = sess().get(f"{API}/rateizzazioni-avvisi").json()
        assert j["giorni"] == 15
        assert any(x["piano_id"] == ST["P"] and x["n"] == 1 for x in j["scadute"]), j
        assert any(x["piano_id"] == ST["P"] and x["n"] == 2 for x in j["in_scadenza"]), j
        assert not any(x["piano_id"] == ST["P"] and x["n"] == 3 for x in j["scadute"] + j["in_scadenza"])
        assert j["totale_scaduto"] >= 555.0

    # pay
    def test_08_paga_before_data_piano(self):
        r = sess().post(f"{API}/rateizzazioni/{ST['P']}/rate/1/paga", json={"data": D(61)})
        assert r.status_code == 400 and "data" in r.text, r.text

    def test_09_paga_bad_conto(self):
        r = sess().post(f"{API}/rateizzazioni/{ST['P']}/rate/1/paga", json={"data": D(1), "conto": "99.99.999"})
        assert r.status_code == 400, r.text

    def test_10_paga_ok(self):
        conti = sess().get(f"{API}/rateizzazioni").json()["conti_pagamento"]["conti"]
        bank = next(x for x in conti if x["tipo"] == "banca")["conto"]
        ST["bank"] = bank
        r = sess().post(f"{API}/rateizzazioni/{ST['P']}/rate/1/paga", json={"data": D(1), "conto": bank})
        assert r.status_code == 200, r.text
        p = r.json()
        r1 = p["rate"][0]
        assert r1["stato"] == "pagata" and r1["pagamento"]["conto"] == bank and "prima nota" in (r1["pagamento"]["coge_rif"] or ""), r1
        assert p["pagato"] == 555.0 and p["rate_pagate"] == 1
        e = entries(f"{ST['P']}-1")
        assert len(e) == 1, e
        rg = e[0]["righe"]
        print("righe", rg)
        d = {x["conto"]: x.get("dare", 0) for x in rg if x.get("dare")}
        a = {x["conto"]: x.get("avere", 0) for x in rg if x.get("avere")}
        assert d == {"13.05.003": 500, "30.14.003": 50, "40.02.001": 5}, d
        assert a == {bank: 555}, a
        assert e[0]["data"] == D(1)
        r = sess().post(f"{API}/rateizzazioni/{ST['P']}/rate/1/paga", json={"data": D(1), "conto": bank})
        assert r.status_code == 400

    def test_11_put_delete_refused_when_paid(self):
        r = sess().put(f"{API}/rateizzazioni/{ST['P']}", json=plan([{"scadenza": F(5), "capitale": 10}]))
        assert r.status_code == 400, r.text
        r = sess().delete(f"{API}/rateizzazioni/{ST['P']}")
        assert r.status_code == 400, r.text

    def test_12_annulla_pagamento(self):
        r = sess().delete(f"{API}/rateizzazioni/{ST['P']}/rate/1/paga")
        assert r.status_code == 200, r.text
        assert r.json()["rate"][0]["stato"] == "scaduta" and r.json()["rate"][0]["pagamento"] is None
        assert entries(f"{ST['P']}-1") == []
        assert sess().delete(f"{API}/rateizzazioni/{ST['P']}/rate/1/paga").status_code == 400
        # re-pay so the plan has a paid rata for situazione/UI
        r = sess().post(f"{API}/rateizzazioni/{ST['P']}/rate/1/paga", json={"data": D(1), "conto": ST["bank"]})
        assert r.status_code == 200, r.text

    def test_13_delete_soft(self):
        r = sess().post(f"{API}/rateizzazioni", json=plan([{"scadenza": F(100), "capitale": 99}]))
        pid = r.json()["id"]
        assert sess().delete(f"{API}/rateizzazioni/{pid}").status_code == 200
        assert not any(x["id"] == pid for x in sess().get(f"{API}/rateizzazioni").json()["piani"])
        assert mongo(f'print(db.rateizzazioni.countDocuments({{id:"{pid}", annullata:true}}))') == "1"
        assert sess().get(f"{API}/rateizzazioni/{pid}/pdf").status_code == 404

    def test_14_tenant_isolation(self):
        assert sess(ST["cid2"]).get(f"{API}/rateizzazioni/{ST['P']}/pdf").status_code == 404
        assert not any(x["id"] == ST["P"] for x in sess(ST["cid2"]).get(f"{API}/rateizzazioni").json()["piani"])

    def test_15_paga_no_contabilita(self):
        s = sess(ST["cid2"])
        r = s.post(f"{API}/rateizzazioni", json=plan([{"scadenza": F(3), "capitale": 100}]))
        print("no-contab create", r.status_code, r.text[:300])
        if r.status_code == 200:
            pid = r.json()["id"]
            p = s.post(f"{API}/rateizzazioni/{pid}/rate/1/paga", json={"data": D(1)})
            print("no-contab paga", p.status_code, p.text[:300])
            assert p.status_code == 200 and p.json()["rate"][0]["stato"] == "pagata"

    # situazione finanziaria
    def test_16_situazione_contabile(self):
        j = sess().get(f"{API}/situazione-finanziaria", params={"mesi": 6}).json()
        assert len(j["mesi"]) == 6
        assert j["fonte_saldo"] == "contabilita", j["fonte_saldo"]
        assert j["saldo_iniziale"] == -555.0, (j["saldo_iniziale"], j["banche_contabili"])
        s = j["saldo_iniziale"]
        for m in j["mesi"]:
            assert round(m["incasso"] + m["fornitore"] + m["rateizzazione"] + m["fisco"], 2) == m["netto"]
            s = round(s + m["netto"], 2)
            assert m["saldo"] == s
        assert j["saldo_finale"] == s
        rv = [v for v in j["voci"] if v["tipo"] == "rateizzazione" and v["ref"] == ST["P"]]
        assert rv and all(v["importo"] < 0 for v in rv), rv
        assert len(rv) == 2  # rata 1 paid, rate 2 (+5d) and 3 (+70d) within 6 months
        assert j["scaduto"]["rateizzazione"] <= 0
        print("mesi", j["mesi"][:2], "scaduto", j["scaduto"])

    def test_17_situazione_estratto(self):
        mongo(f'db.bank_accounts.insertOne({{id:"t125-ba-{RUN}", company_id:"{ST["cid"]}", nome:"TEST_Conto", banca:"TEST_Banca", iban:"IT60X0542811101000000123456", saldo:10000, saldo_at:new Date().toISOString()}})')
        j = sess().get(f"{API}/situazione-finanziaria", params={"mesi": 12}).json()
        assert j["fonte_saldo"] == "estratto" and j["saldo_iniziale"] == 10000.0, j["fonte_saldo"]
        assert len(j["mesi"]) == 12
        j3 = sess().get(f"{API}/situazione-finanziaria", params={"mesi": 3}).json()
        assert len(j3["mesi"]) == 3

    def test_18_situazione_no_contab(self):
        r = sess(ST["cid2"]).get(f"{API}/situazione-finanziaria", params={"mesi": 6})
        assert r.status_code == 200, r.text
        assert r.json()["fonte_saldo"] == "nessuna"

    # customer and supplier open rate feed the forecast
    def test_19_situazione_incassi_fornitori(self):
        from test_iteration7_pa_scartate_registro import party, inv
        import test_iteration89_rigenera_passive as t89
        s = sess()
        pid = s.post(f"{API}/parties", json=party("TEST_T125 Cliente", piva="01234567892", cf="01234567892")).json()["id"]
        r = s.post(f"{API}/invoices", json=inv(pid, data=D(3), price=1000))
        assert r.status_code == 200, r.text
        iid = r.json()["id"]
        assert s.post(f"{API}/invoices/{iid}/send").status_code == 200
        x = t89.xml(f"T125P{RUN}", D(3), "01111111111", 500.0).replace(t89.PIVA.encode(), PIVA.encode()).replace(b"TEST_T89", b"TEST_T125")
        u = s.post(f"{API}/passive/upload", files=[("files", (f"t125_{RUN}.xml", x, "application/octet-stream"))])
        assert u.status_code == 200 and u.json()[0]["ok"], u.text
        ppid = u.json()[0]["documenti"][0]["id"]
        j = s.get(f"{API}/situazione-finanziaria", params={"mesi": 6}).json()
        inc = [v for v in j["voci"] if v["tipo"] == "incasso" and v["ref"] == iid]
        forn = [v for v in j["voci"] if v["tipo"] == "fornitore" and v["ref"] == ppid]
        print("inc", inc, "forn", forn, "totali", j["totali"], "fisco voci", [v for v in j["voci"] if v["tipo"] == "fisco"][:3])
        assert inc and inc[0]["importo"] > 0
        assert forn and forn[0]["importo"] < 0
        assert j["totali"]["incasso"] >= inc[0]["importo"] and j["totali"]["fornitore"] <= forn[0]["importo"]

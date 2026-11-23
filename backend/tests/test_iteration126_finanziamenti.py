# Iteration 126: finanziamenti e leasing (calcolo francese, PDF IA, CRUD, erogazione/pagamento rate -> prima nota, collegamento fatture passive,
# situazione finanziaria, avvisi dashboard) + regression rateizzazioni paga.
# Run: pytest tests/test_iteration126_finanziamenti.py -v -n 0   (T126_KEEP=1 keeps data for UI testing in /tmp/t126.json)
import json
import os
import random
import sys
from datetime import date, timedelta

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402
import test_iteration89_rigenera_passive as t89  # noqa: E402

RUN = str(random.randint(100000, 999999))
TOK, UID = "test_session_t126_admin", "test-user-t126-admin"
PIVA = "17" + RUN + "171"
CED = "0" + RUN + "1234"  # supplier piva 11 digits
ST = {}
COLLS = ["invoices", "passive_invoices", "parties", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "audit", "partite_aperte", "bank_tx", "bank_accounts", "rateizzazioni", "rateizzazioni_pdf", "finanziamenti", "ai_crediti_mov", "iva_registri"]
T = date.today()
D = lambda n: (T - timedelta(days=n)).isoformat()  # noqa: E731
F = lambda n: (T + timedelta(days=n)).isoformat()  # noqa: E731
PDF = os.path.join(os.path.dirname(__file__), "fixtures_piano_mutuo.pdf")


def sess(cid=None):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {TOK}", "X-Requested-With": "invoix"})
    c = cid if cid is not None else ST.get("cid")
    if c:
        s.headers["X-Company-Id"] = c
    return s


def clean():
    mongo(f'db.companies.find({{denominazione:/^TEST_T126/}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
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


def entries(ref):
    out = mongo(f'print(JSON.stringify(db.coa_entries.find({{company_id:"{ST["cid"]}", origine:"finanziamento", ref_id:"{ref}"}}, {{_id:0}}).toArray()))')
    return json.loads(out or "[]")


def dare_avere(e):
    rg = e["righe"]
    return ({x["conto"]: x["dare"] for x in rg if x.get("dare")}, {x["conto"]: x["avere"] for x in rg if x.get("avere")})


def upload_passive(numero, imp):
    x = t89.xml(numero, D(10), CED, imp).replace(t89.PIVA.encode(), PIVA.encode()).replace(b"TEST_T89", b"TEST_T126")
    u = sess().post(f"{API}/passive/upload", files=[("files", (f"t126_{numero}.xml", x, "application/octet-stream"))])
    assert u.status_code == 200 and u.json()[0]["ok"], u.text
    return u.json()[0]["documenti"][0]["id"]


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t126.admin@example.com", name:"TEST_T126 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    ST["cid"] = mk_company("TEST_T126 Contab Srl", PIVA, True)
    sess().get(f"{API}/contabilita/conti")
    yield
    if os.environ.get("T126_KEEP"):
        json.dump({**ST, "tok": TOK}, open("/tmp/t126.json", "w"))
        print("\nKEEP", ST)
    else:
        clean()


FIN = lambda **kw: {"tipo": "finanziamento", "ente": "TEST_Banca", "numero": f"TEST_F{RUN}", "data": D(60), "importo": 10000, "tasso": 6, **kw}  # noqa: E731


class TestFinanziamenti:
    # calcolo
    def test_01_calcola_finanziamento(self):
        r = sess().post(f"{API}/finanziamenti/calcola", json={"tipo": "finanziamento", "importo": 10000, "tasso": 6, "n_rate": 12, "prima_scadenza": "2026-02-28"})
        assert r.status_code == 200, r.text
        rate = r.json()["rate"]
        assert len(rate) == 12
        tot = [round(x["capitale"] + x["interessi"], 2) for x in rate]
        assert all(abs(t - 860.66) <= 0.05 for t in tot), tot
        assert round(sum(x["capitale"] for x in rate), 2) == 10000
        assert rate[0]["interessi"] == 50.0
        assert [x["scadenza"] for x in rate[:3]] == ["2026-02-28", "2026-03-28", "2026-04-28"]

    def test_02_calcola_leasing(self):
        r = sess().post(f"{API}/finanziamenti/calcola", json={"tipo": "leasing", "importo": 30000, "tasso": 5, "n_rate": 36, "prima_scadenza": "2026-03-01",
                                                              "maxicanone": 3000, "riscatto": 1000, "data": "2026-02-01"})
        assert r.status_code == 200, r.text
        rate = r.json()["rate"]
        assert len(rate) == 38
        assert rate[0]["descrizione"] == "Maxicanone" and rate[0]["capitale"] == 3000 and rate[0]["scadenza"] == "2026-02-01"
        assert rate[-1]["descrizione"] == "Riscatto" and rate[-1]["capitale"] == 1000
        assert all(x["descrizione"] == "Canone" for x in rate[1:-1])
        assert round(sum(x["capitale"] for x in rate), 2) == 30000

    def test_03_calcola_validation(self):
        r = sess().post(f"{API}/finanziamenti/calcola", json={"tipo": "leasing", "importo": 1000, "n_rate": 3, "prima_scadenza": "2026-03-01", "maxicanone": 1000})
        assert r.status_code == 400
        r = sess().post(f"{API}/finanziamenti/calcola", json={"tipo": "finanziamento", "importo": 0, "n_rate": 3, "prima_scadenza": "2026-03-01"})
        assert r.status_code in (400, 422)
        # tasso 0
        r = sess().post(f"{API}/finanziamenti/calcola", json={"tipo": "finanziamento", "importo": 900, "tasso": 0, "n_rate": 3, "prima_scadenza": "2026-03-01"})
        assert r.status_code == 200 and [x["capitale"] for x in r.json()["rate"]] == [300, 300, 300]

    # PDF IA
    def test_04_leggi_pdf_non_pdf(self):
        r = sess().post(f"{API}/finanziamenti/leggi-pdf", files={"file": ("x.txt", b"hello", "text/plain")})
        assert r.status_code == 400, r.text

    def test_05_leggi_pdf_ai(self):
        with open(PDF, "rb") as f:
            r = sess().post(f"{API}/finanziamenti/leggi-pdf", files={"file": ("mutuo.pdf", f.read(), "application/pdf")}, timeout=180)
        assert r.status_code == 200, r.text
        j = r.json()
        print("AI", json.dumps(j)[:1500])
        ST["ai"] = j
        assert j["pdf_id"] and j["tipo"] == "finanziamento"
        assert "FIN-778899" in j["numero"], j["numero"]
        assert j["importo"] == 6000 and j["tasso"] == 6
        assert len(j["rate"]) == 6 and all(x["capitale"] > 0 and x["interessi"] >= 0 for x in j["rate"])
        assert round(sum(x["capitale"] for x in j["rate"]), 0) == 6000
        assert j["conto_debito"] == "13.01.003"

    def test_06_create_from_ai_and_pdf(self):
        j = ST["ai"]
        body = {k: j[k] for k in ("tipo", "ente", "descrizione", "data", "importo", "tasso", "pdf_id", "rate")}
        body["numero"] = f"TEST_{j['numero']}"
        r = sess().post(f"{API}/finanziamenti", json=body)
        assert r.status_code == 200, r.text
        ST["F_ai"] = r.json()["id"]
        g = sess().get(f"{API}/finanziamenti/{ST['F_ai']}/pdf")
        assert g.status_code == 200 and g.content.startswith(b"%PDF")

    # CRUD
    def test_07_create_finanziamento(self):
        rate = sess().post(f"{API}/finanziamenti/calcola", json={"tipo": "finanziamento", "importo": 10000, "tasso": 6, "n_rate": 12, "prima_scadenza": D(30)}).json()["rate"]
        r = sess().post(f"{API}/finanziamenti", json=FIN(rate=rate))
        assert r.status_code == 200, r.text
        p = r.json()
        ST["F"] = p["id"]
        assert p["totale"] == round(sum(x["totale"] for x in p["rate"]), 2) and p["pagato"] == 0
        assert p["debito_residuo"] == 10000 and p["rate"][0]["iva"] == 0 and p["rate"][0]["stato"] == "scaduta"
        assert p["rate"][1]["stato"] in ("in_scadenza", "da_pagare")
        assert p["rate_scadute"] == 1

    def test_08_create_leasing_with_supplier(self):
        s = sess()
        pid = upload_passive(f"T126A{RUN}", 500.0)
        ST["inv1"] = pid
        ST["inv2"] = upload_passive(f"T126B{RUN}", 500.0)
        party = mongo(f'print(db.passive_invoices.findOne({{id:"{pid}"}}).party_id)')
        ST["party"] = party
        rate = [{"scadenza": D(20), "capitale": 3000, "interessi": 0, "descrizione": "Maxicanone"},
                {"scadenza": F(5), "capitale": 450, "interessi": 50, "descrizione": "Canone"},
                {"scadenza": F(35), "capitale": 455, "interessi": 45, "descrizione": "Canone"},
                {"scadenza": F(65), "capitale": 1000, "interessi": 0, "descrizione": "Riscatto"}]
        r = s.post(f"{API}/finanziamenti", json={"tipo": "leasing", "ente": "TEST_Leasing Spa", "numero": f"TEST_L{RUN}", "data": D(30), "importo": 4905,
                                                 "tasso": 5, "aliquota_iva": 22, "party_id": party, "rate": rate})
        assert r.status_code == 200, r.text
        p = r.json()
        ST["L"] = p["id"]
        r2 = p["rate"][1]
        assert r2["iva"] == 110.0 and r2["totale"] == 610.0, r2
        assert p["rate"][0]["totale"] == 3660.0

    def test_09_list_and_validation(self):
        j = sess().get(f"{API}/finanziamenti").json()
        ids = {p["id"]: p for p in j["piani"]}
        assert ST["F"] in ids and ST["L"] in ids
        for k in ("totale", "pagato", "residuo", "debito_residuo", "rate_scadute", "prossima"):
            assert k in ids[ST["L"]]
        assert j["conti_pagamento"]["conti"]
        bad = sess().post(f"{API}/finanziamenti", json=FIN(rate=[{"scadenza": F(5), "capitale": 0, "interessi": 0}]))
        assert bad.status_code in (400, 422)
        bad = sess().post(f"{API}/finanziamenti", json=FIN(rate=[{"scadenza": F(5), "capitale": 10}], conto_debito="99.99.999"))
        assert bad.status_code == 400
        bad = sess().post(f"{API}/finanziamenti", json={**FIN(rate=[{"scadenza": F(5), "capitale": 10}]), "tipo": "leasing", "party_id": "nope"})
        assert bad.status_code == 400

    def test_10_put_and_soft_delete(self):
        r = sess().post(f"{API}/finanziamenti", json=FIN(rate=[{"scadenza": F(100), "capitale": 99}]))
        pid = r.json()["id"]
        u = sess().put(f"{API}/finanziamenti/{pid}", json=FIN(descrizione="TEST_ mod", rate=[{"scadenza": F(100), "capitale": 199}]))
        assert u.status_code == 200 and u.json()["descrizione"] == "TEST_ mod" and u.json()["totale"] == 199
        assert sess().delete(f"{API}/finanziamenti/{pid}").status_code == 200
        assert not any(x["id"] == pid for x in sess().get(f"{API}/finanziamenti").json()["piani"])
        assert mongo(f'print(db.finanziamenti.countDocuments({{id:"{pid}", annullata:true}}))') == "1"

    # erogazione
    def test_11_erogazione(self):
        conti = sess().get(f"{API}/finanziamenti").json()["conti_pagamento"]["conti"]
        ST["bank"] = next(x for x in conti if x["tipo"] == "banca")["conto"]
        r = sess().post(f"{API}/finanziamenti/{ST['F']}/erogazione", json={"data": D(60), "conto": ST["bank"]})
        assert r.status_code == 200, r.text
        assert r.json()["erogazione"]["coge_rif"]
        e = entries(f"{ST['F']}-E")
        assert len(e) == 1
        assert dare_avere(e[0]) == ({ST["bank"]: 10000}, {"13.01.003": 10000}), e[0]["righe"]
        assert sess().post(f"{API}/finanziamenti/{ST['F']}/erogazione", json={"data": D(60), "conto": ST["bank"]}).status_code == 409
        assert sess().post(f"{API}/finanziamenti/{ST['L']}/erogazione", json={"data": D(10)}).status_code == 400
        # edit/delete blocked
        assert sess().put(f"{API}/finanziamenti/{ST['F']}", json=FIN(rate=[{"scadenza": F(5), "capitale": 10}])).status_code == 400
        assert sess().delete(f"{API}/finanziamenti/{ST['F']}").status_code == 400

    def test_12_annulla_erogazione(self):
        r = sess().delete(f"{API}/finanziamenti/{ST['F']}/erogazione")
        assert r.status_code == 200 and r.json()["erogazione"] is None
        assert entries(f"{ST['F']}-E") == []
        assert sess().delete(f"{API}/finanziamenti/{ST['F']}/erogazione").status_code == 400
        assert sess().post(f"{API}/finanziamenti/{ST['F']}/erogazione", json={"data": D(60), "conto": ST["bank"]}).status_code == 200

    # pagamento rate
    def test_13_paga_finanziamento(self):
        assert sess().post(f"{API}/finanziamenti/{ST['F']}/rate/1/paga", json={"data": D(61), "conto": ST["bank"]}).status_code == 400
        assert sess().post(f"{API}/finanziamenti/{ST['F']}/rate/1/paga", json={"data": D(1), "conto": "99.99.999"}).status_code == 400
        r = sess().post(f"{API}/finanziamenti/{ST['F']}/rate/1/paga", json={"data": D(1), "conto": ST["bank"]})
        assert r.status_code == 200, r.text
        p = r.json()
        x = p["rate"][0]
        assert x["stato"] == "pagata" and "prima nota" in x["pagamento"]["coge_rif"]
        e = entries(f"{ST['F']}-1")
        assert len(e) == 1
        d, a = dare_avere(e[0])
        assert d == {"13.01.003": x["capitale"], "40.02.002": x["interessi"]}, d
        assert a == {ST["bank"]: x["totale"]}, a
        assert p["debito_residuo"] == round(10000 - x["capitale"], 2)
        assert sess().post(f"{API}/finanziamenti/{ST['F']}/rate/1/paga", json={"data": D(1), "conto": ST["bank"]}).status_code == 409
        assert sess().post(f"{API}/finanziamenti/{ST['F']}/rate/99/paga", json={"data": D(1), "conto": ST["bank"]}).status_code == 404

    def test_14_annulla_paga(self):
        r = sess().delete(f"{API}/finanziamenti/{ST['F']}/rate/1/paga")
        assert r.status_code == 200 and r.json()["rate"][0]["pagamento"] is None
        assert entries(f"{ST['F']}-1") == []
        assert sess().delete(f"{API}/finanziamenti/{ST['F']}/rate/1/paga").status_code == 400

    def test_15_paga_leasing(self):
        r = sess().post(f"{API}/finanziamenti/{ST['L']}/rate/1/paga", json={"data": D(1), "conto": ST["bank"]})
        assert r.status_code == 200, r.text
        e = entries(f"{ST['L']}-1")
        assert len(e) == 1
        assert dare_avere(e[0]) == ({"30.08.002": 3000, "05.02.002": 660}, {ST["bank"]: 3660}), e[0]["righe"]

    # collega fatture
    def test_16_fatture_list_and_collega(self):
        j = sess().get(f"{API}/finanziamenti/{ST['L']}/fatture").json()
        ids = [x["id"] for x in j]
        assert ST["inv1"] in ids and ST["inv2"] in ids, j
        assert sess().post(f"{API}/finanziamenti/{ST['F']}/rate/2/collega", json={"invoice_id": ST["inv1"]}).status_code == 400
        assert sess().post(f"{API}/finanziamenti/{ST['L']}/rate/1/collega", json={"invoice_id": ST["inv1"]}).status_code == 400  # paid rata
        r = sess().post(f"{API}/finanziamenti/{ST['L']}/rate/2/collega", json={"invoice_id": ST["inv1"]})
        assert r.status_code == 200, r.text
        assert r.json()["rate"][1]["stato"] == "fattura" and r.json()["rate"][1]["fattura_id"] == ST["inv1"]
        assert sess().post(f"{API}/finanziamenti/{ST['L']}/rate/3/collega", json={"invoice_id": ST["inv1"]}).status_code == 400
        assert sess().post(f"{API}/finanziamenti/{ST['L']}/rate/2/paga", json={"data": D(1), "conto": ST["bank"]}).status_code == 400
        assert ST["inv1"] not in [x["id"] for x in sess().get(f"{API}/finanziamenti/{ST['L']}/fatture").json()]
        assert sess().post(f"{API}/finanziamenti/{ST['L']}/rate/3/collega", json={"invoice_id": "nope"}).status_code == 404

    def test_17_pay_invoice_marks_rata_paid(self):
        r = sess().post(f"{API}/passive/{ST['inv1']}/pagamenti", json={"data": D(5), "importo": 610.0, "metodo": "bonifico", "conto": ST["bank"]})
        assert r.status_code == 200, r.text
        p = next(x for x in sess().get(f"{API}/finanziamenti").json()["piani"] if x["id"] == ST["L"])
        assert p["rate"][1]["stato"] == "pagata", p["rate"][1]
        assert p["rate_pagate"] == 2

    def test_18_scollega(self):
        r = sess().post(f"{API}/finanziamenti/{ST['L']}/rate/3/collega", json={"invoice_id": ST["inv2"]})
        assert r.status_code == 200 and r.json()["rate"][2]["stato"] == "fattura"
        r = sess().delete(f"{API}/finanziamenti/{ST['L']}/rate/3/collega")
        assert r.status_code == 200 and r.json()["rate"][2]["fattura_id"] is None and r.json()["rate"][2]["stato"] != "fattura"

    # situazione + avvisi
    def test_19_situazione(self):
        j = sess().get(f"{API}/situazione-finanziaria", params={"mesi": 6}).json()
        assert "finanziamento" in j["totali"] and "finanziamento" in j["scaduto"] and all("finanziamento" in m for m in j["mesi"])
        fv = [v for v in j["voci"] if v["tipo"] == "finanziamento"]
        assert any(v["ref"] == ST["F"] for v in fv) and any(v["ref"] == ST["L"] for v in fv)
        lv = [v for v in fv if v["ref"] == ST["L"]]
        assert len(lv) == 2, lv  # rata1 paid, rata2 linked -> only rate 3,4
        assert all(v["importo"] < 0 for v in fv)
        assert j["scaduto"]["finanziamento"] < 0  # F rata 1 scaduta unpaid
        for m in j["mesi"]:
            assert round(m["incasso"] + m["fornitore"] + m["rateizzazione"] + m["finanziamento"] + m["fisco"], 2) == m["netto"]

    def test_20_avvisi(self):
        j = sess().get(f"{API}/rateizzazioni-avvisi").json()
        sc = [x for x in j["scadute"] if x["piano_id"] == ST["F"]]
        assert sc and sc[0]["link"] == "/finanziamenti" and "Finanziamento" in sc[0]["label"], sc
        allx = j["scadute"] + j["in_scadenza"]
        assert not any(x["piano_id"] == ST["L"] and x["n"] == 2 for x in allx)  # linked
        assert any(x["piano_id"] == ST["L"] and x["n"] == 3 for x in allx) is False  # +35d
        ST["avviso_label"] = sc[0]["label"]

    # regression rateizzazioni paga
    def test_21_rateizzazioni_regression(self):
        r = sess().post(f"{API}/rateizzazioni", json={"ente": "Agenzia delle Entrate", "numero": f"TEST_R{RUN}", "data": D(30),
                                                       "rate": [{"scadenza": F(3), "capitale": 100, "sanzioni": 10, "interessi": 1}]})
        assert r.status_code == 200, r.text
        ST["R"] = r.json()["id"]
        p = sess().post(f"{API}/rateizzazioni/{ST['R']}/rate/1/paga", json={"data": D(1), "conto": ST["bank"]})
        assert p.status_code == 200 and p.json()["rate"][0]["stato"] == "pagata", p.text

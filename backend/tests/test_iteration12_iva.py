# Iteration 12: Registro IVA vendite, Registro IVA acquisti regression (refactor to _iva_register), Liquidazione IVA
# (monthly/quarterly, split payment, credit carried forward, 1% quarterly interest), company isolation.
# Run with: pytest test_iteration12_iva.py -n 0
import random
import pytest
import requests
from test_iteration7_pa_scartate_registro import API, mongo, party, inv
from test_iteration11_passive import variant

RUN = str(random.randint(100000, 999999))
TOK, UID = f"test_session_t12_admin_{RUN}", f"test-user-t12-admin-{RUN}"
OTOK, OUID = f"test_session_t12_oper_{RUN}", f"test-user-t12-oper-{RUN}"
PIVA_FIX = "01234567890"
PIVA2 = "89" + RUN + "012"


def clean_all():
    mongo('db.companies.find({denominazione:/^TEST_T12/}).forEach(c=>{["invoices","parties","payments","passive_invoices","passive_payments"].forEach(k=>db[k].deleteMany({company_id:c.id}));'
          'db.counters.deleteMany({key:{$regex:c.id}}); db.companies.deleteOne({id:c.id});});'
          'db.users.deleteMany({user_id:/^test-user-t12-/}); db.user_sessions.deleteMany({session_token:/^test_session_t12_/});')


def comp(name, piva):
    return {"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01", "iban": "IT60X0542811101000000123456",
            "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"}


def user(uid, tok, role, cids):
    mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.{uid}@example.com", name:"TEST_T12 {role}", picture:"", role:"{role}", status:"approved", company_ids:{cids}, created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+7*864e5), created_at:new Date().toISOString()}});')


def sess(tok):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    return s


def create_send(s, h, body, expect):
    r = s.post(f"{API}/invoices", json=body, headers=h)
    assert r.status_code == 200, r.text
    iid = r.json()["id"]
    assert s.post(f"{API}/invoices/{iid}/send", headers=h).status_code == 200
    r = s.post(f"{API}/invoices/{iid}/refresh", headers=h)
    assert r.json()["status"] == expect, r.text
    return r.json()


def seed(s, h, tag="TEST_T12"):
    """Known dataset (year 2026). Returns dict of ids."""
    ids = {}
    b2b = s.post(f"{API}/parties", json=party(f"{tag} Cliente B2B", piva="0" + RUN + "0011"), headers=h).json()["id"]
    pa = s.post(f"{API}/parties", json=party(f"{tag} Comune Split", codice="UFAB12", pa=True, split=True, cf="80012345678", piva="80012345678"), headers=h).json()["id"]
    priv = s.post(f"{API}/parties", json=party(f"{tag} Privato", codice="0000000", piva="", cf="RSSMRA80A01H501U"), headers=h).json()["id"]
    bad = s.post(f"{API}/parties", json=party(f"{tag} B2B NoPec", codice="", piva="0" + RUN + "0022"), headers=h).json()["id"]
    ids["F1"] = create_send(s, h, inv(b2b, data="2026-01-15", price=1000), "consegnata")
    ids["F2"] = create_send(s, h, {**inv(b2b, data="2026-02-10"), "lines": [
        {"descrizione": "A", "quantita": 1, "prezzo_unitario": 500, "aliquota": 22},
        {"descrizione": "B", "quantita": 1, "prezzo_unitario": 200, "aliquota": 10}]}, "consegnata")
    ids["F3"] = create_send(s, h, inv(pa, data="2026-04-05", price=1000), "consegnata")
    ids["F4"] = create_send(s, h, inv(priv, data="2026-05-10", price=100), "mancata_consegna")
    ids["F6"] = create_send(s, h, inv(bad, data="2026-08-01", price=300), "scartata")
    ids["F7"] = create_send(s, h, {**inv(b2b, data="2026-10-01"), "lines": [
        {"descrizione": "Esente", "quantita": 1, "prezzo_unitario": 100, "aliquota": 0, "natura": "N2.2"},
        {"descrizione": "C", "quantita": 1, "prezzo_unitario": 200, "aliquota": 22}]}, "consegnata")
    r = s.post(f"{API}/invoices", json=inv(b2b, data="2026-10-20", price=5000), headers=h)  # bozza -> excluded
    assert r.status_code == 200, r.text
    ids["F8"] = r.json()
    ids["NC1"] = create_send(s, h, {**inv(b2b, data="2026-03-20", price=100), "tipo_documento": "TD04", "fattura_collegata_id": ids["F1"]["id"]}, "consegnata")
    # purchases: 5 x fixture (imponibile 471.25, imposta 103.68), registered, then dates moved
    dates = ["2026-01-20", "2026-03-10", "2026-03-11", "2026-05-05", None]
    pids = []
    for i, dr in enumerate(dates):
        r = s.post(f"{API}/passive/upload", files=[("files", (f"p{i}.xml", variant(f"T12-{RUN}-{i}", data="2026-01-02"), "application/octet-stream"))], headers=h)
        assert r.status_code == 200, r.text
        pid = r.json()[0]["documenti"][0]["id"]
        r = s.patch(f"{API}/passive/{pid}", json={"stato_reg": "registrata"}, headers=h)
        assert r.status_code == 200 and r.json()["protocollo"] == i + 1, r.text
        if dr:
            mongo(f'db.passive_invoices.updateOne({{id:"{pid}"}}, {{$set:{{data_registrazione:"{dr}"}}}})')
        pids.append(pid)
    # one passive left da_registrare -> excluded
    r = s.post(f"{API}/passive/upload", files=[("files", ("px.xml", variant(f"T12-{RUN}-X", data="2026-01-02"), "application/octet-stream"))], headers=h)
    ids["PX"] = r.json()[0]["documenti"][0]["id"]
    ids["P"] = pids
    return ids


@pytest.fixture(scope="module")
def ctx():
    clean_all()
    user(UID, TOK, "admin", "[]")
    s = sess(TOK)
    r = s.post(f"{API}/companies", json=comp("TEST_T12 Iva Srl", PIVA_FIX))
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    cid2 = s.post(f"{API}/companies", json=comp("TEST_T12 Vuota Srl", PIVA2)).json()["id"]
    user(OUID, OTOK, "operatore", f'["{cid}"]')
    h = {"X-Company-Id": cid}
    ids = seed(s, h)
    yield {"s": s, "o": sess(OTOK), "h": h, "h2": {"X-Company-Id": cid2}, "ids": ids}
    clean_all()


class TestRegistroVendite:
    def test_01_rows_filter_and_order(self, ctx):
        r = ctx["s"].get(f"{API}/registro-iva-vendite", params={"anno": 2026}, headers=ctx["h"])
        assert r.status_code == 200, r.text
        d = r.json()
        ids = ctx["ids"]
        got = [x["id"] for x in d["rows"]]
        assert got == [ids[k]["id"] for k in ("F1", "F2", "F3", "F4", "F7", "NC1")], [x["numero"] for x in d["rows"]]
        assert d["anno"] == 2026 and 2026 in d["anni"]
        assert d["azienda"]["partita_iva"] == PIVA_FIX
        f1 = d["rows"][0]
        assert f1["numero"] == ids["F1"]["numero_display"] and f1["data"] == "2026-01-15" and f1["tipo_documento"] == "TD01"
        assert f1["cliente"].startswith("TEST_T12 Cliente B2B") and f1["partita_iva"] == "0" + RUN + "0011"
        assert f1["riepilogo"] == [{"aliquota": 22.0, "natura": None, "imponibile": 1000.0, "imposta": 220.0}] and f1["totale"] == 1220.0
        nc = d["rows"][-1]
        assert nc["tipo_documento"] == "TD04" and nc["totale"] == -122.0 and nc["riepilogo"][0]["imponibile"] == -100.0 and nc["riepilogo"][0]["imposta"] == -22.0
        assert d["rows"][2]["split_payment"] is True and d["rows"][3]["partita_iva"] == "RSSMRA80A01H501U"
        assert "_id" not in str(d)

    def test_02_totals(self, ctx):
        d = ctx["s"].get(f"{API}/registro-iva-vendite", params={"anno": 2026}, headers=ctx["h"]).json()
        tot = {t["codice"]: t for t in d["totali"]}
        assert [t["codice"] for t in d["totali"]] == ["22%", "10%", "N2.2"]
        assert (tot["22%"]["documenti"], tot["22%"]["imponibile"], tot["22%"]["imposta"]) == (6, 2700.0, 594.0)
        assert (tot["10%"]["documenti"], tot["10%"]["imponibile"], tot["10%"]["imposta"]) == (1, 200.0, 20.0)
        assert (tot["N2.2"]["documenti"], tot["N2.2"]["imponibile"], tot["N2.2"]["imposta"]) == (1, 100.0, 0.0)
        assert d["imponibile"] == 3000.0 and d["imposta"] == 614.0 and d["imposta_split"] == 220.0
        assert d["totale"] == round(1220 + 830 + 1220 + 122 + 344 - 122, 2)

    def test_03_date_filter(self, ctx):
        s, h, ids = ctx["s"], ctx["h"], ctx["ids"]
        d = s.get(f"{API}/registro-iva-vendite", params={"anno": 2026, "dal": "2026-01-01", "al": "2026-03-31"}, headers=h).json()
        assert [x["id"] for x in d["rows"]] == [ids["F1"]["id"], ids["F2"]["id"], ids["NC1"]["id"]]
        assert d["imposta"] == 328.0 and d["imposta_split"] == 0
        d = s.get(f"{API}/registro-iva-vendite", params={"anno": 2026, "dal": "2026-04-01", "al": "2026-04-30"}, headers=h).json()
        assert [x["id"] for x in d["rows"]] == [ids["F3"]["id"]] and d["imposta_split"] == 220.0
        # invalid date format is ignored (no 500)
        r = s.get(f"{API}/registro-iva-vendite", params={"anno": 2026, "dal": "bad", "al": "2026-13"}, headers=h)
        assert r.status_code == 200 and len(r.json()["rows"]) == 6

    def test_04_other_year_and_company(self, ctx):
        d = ctx["s"].get(f"{API}/registro-iva-vendite", params={"anno": 2025}, headers=ctx["h"]).json()
        assert d["rows"] == [] and d["imposta"] == 0 and d["totali"] == []
        d = ctx["s"].get(f"{API}/registro-iva-vendite", headers=ctx["h2"]).json()
        assert d["rows"] == [] and d["anno"] == 2026

    def test_05_operatore_can_read(self, ctx):
        r = ctx["o"].get(f"{API}/registro-iva-vendite", params={"anno": 2026}, headers=ctx["h"])
        assert r.status_code == 200 and len(r.json()["rows"]) == 6


class TestRegistroAcquisti:
    def test_06_acquisti_unchanged(self, ctx):
        r = ctx["s"].get(f"{API}/registro-iva-acquisti", params={"anno": 2026}, headers=ctx["h"])
        assert r.status_code == 200, r.text
        d = r.json()
        assert [x["id"] for x in d["rows"]] == ctx["ids"]["P"]
        assert [x["protocollo"] for x in d["rows"]] == [1, 2, 3, 4, 5]
        keys = {"id", "protocollo", "data_registrazione", "data", "numero", "tipo_documento", "split_payment", "fornitore", "partita_iva", "riepilogo", "totale"}
        assert set(d["rows"][0]) == keys, set(d["rows"][0])
        assert set(d) >= {"anno", "anni", "rows", "totali", "imponibile", "imposta", "imposta_split", "totale", "azienda"}
        assert d["imposta"] == round(5 * 103.68, 2) and d["imponibile"] == round(5 * 471.25, 2) and d["imposta_split"] == 0
        assert d["totali"][0]["codice"] == "22%" and d["totali"][0]["documenti"] == 5
        assert d["rows"][0]["data_registrazione"] == "2026-01-20"

    def test_07_acquisti_date_filter(self, ctx):
        d = ctx["s"].get(f"{API}/registro-iva-acquisti", params={"anno": 2026, "dal": "2026-03-01", "al": "2026-03-31"}, headers=ctx["h"]).json()
        assert [x["protocollo"] for x in d["rows"]] == [2, 3] and d["imposta"] == 207.36


class TestLiquidazione:
    def test_08_mensile(self, ctx):
        r = ctx["s"].get(f"{API}/liquidazione-iva", params={"anno": 2026, "periodicita": "mensile"}, headers=ctx["h"])
        assert r.status_code == 200, r.text
        d = r.json()
        p = d["periodi"]
        assert len(p) == 12 and p[0]["label"] == "Gennaio"
        exp = {  # periodo: (debito, split, credito, prec, saldo, versare, riporto)
            1: (220.0, 0, 103.68, 0, 116.32, 116.32, 0),
            2: (130.0, 0, 0, 0, 130.0, 130.0, 0),
            3: (-22.0, 0, 207.36, 0, -229.36, 0, 229.36),
            4: (0.0, 220.0, 0, 229.36, -229.36, 0, 229.36),
            5: (22.0, 0, 103.68, 229.36, -311.04, 0, 311.04),
            6: (0, 0, 0, 311.04, -311.04, 0, 311.04),
            10: (44.0, 0, 103.68, 311.04, -370.72, 0, 370.72),
            12: (0, 0, 0, 370.72, -370.72, 0, 370.72),
        }
        for k, (deb, spl, cre, prec, saldo, vers, rip) in exp.items():
            x = p[k - 1]
            got = (x["iva_debito"], x["iva_split"], x["iva_credito"], x["credito_precedente"], x["saldo"], x["da_versare"], x["credito_riporto"])
            assert got == (deb, spl, cre, prec, saldo, vers, rip), (k, got)
            assert x["interessi"] == 0
        assert p[0]["documenti_vendite"] == 1 and p[0]["documenti_acquisti"] == 1 and p[7]["documenti_vendite"] == 0  # Aug scartata excluded
        assert p[9]["documenti_vendite"] == 1  # bozza F8 excluded
        assert d["totale_versare"] == 246.32 and d["credito_finale"] == 370.72

    def test_09_trimestrale(self, ctx):
        d = ctx["s"].get(f"{API}/liquidazione-iva", params={"anno": 2026, "periodicita": "trimestrale"}, headers=ctx["h"]).json()
        p = d["periodi"]
        assert len(p) == 4 and p[0]["label"] == "1° trimestre"
        q1 = p[0]
        # 17.13 <= 25.82: not paid, deferred to Q2
        assert (q1["iva_debito"], q1["iva_credito"], q1["saldo"], q1["interessi"], q1["da_versare"], q1["sotto_soglia"]) == (328.0, 311.04, 16.96, 0.17, 0.0, True), q1
        q2 = p[1]
        assert (q2["iva_debito"], q2["iva_split"], q2["iva_credito"], q2["saldo"], q2["credito_riporto"], q2["interessi"], q2["debito_precedente"]) == (22.0, 220.0, 103.68, -81.68, 64.55, 0, 17.13)
        assert p[2]["credito_precedente"] == 64.55 and p[2]["credito_riporto"] == 64.55
        assert p[3]["saldo"] == -124.23 and p[3]["interessi"] == 0
        assert d["totale_versare"] == 0 and d["credito_finale"] == 124.23

    def test_10_q4_positive_no_interest(self, ctx):
        # temporarily move split invoice F3 to October as a normal invoice -> Q4 positive, but no 1% interest on Q4
        iid = ctx["ids"]["F3"]["id"]
        mongo(f'db.invoices.updateOne({{id:"{iid}"}}, {{$set:{{data:"2026-10-02", split_payment:false}}}})')
        try:
            d = ctx["s"].get(f"{API}/liquidazione-iva", params={"anno": 2026, "periodicita": "trimestrale"}, headers=ctx["h"]).json()
            q2, q4 = d["periodi"][1], d["periodi"][3]
            assert q2["saldo"] == -81.68 and q2["iva_split"] == 0
            # Q4: 44 + 220 - 103.68 - 64.55 = 95.77
            assert (q4["saldo"], q4["interessi"], q4["da_versare"]) == (95.77, 0, 95.77), q4
            assert d["totale_versare"] == 95.77 and d["credito_finale"] == 0
        finally:
            mongo(f'db.invoices.updateOne({{id:"{iid}"}}, {{$set:{{data:"2026-04-05", split_payment:true}}}})')

    def test_11_empty_and_validation(self, ctx):
        d = ctx["s"].get(f"{API}/liquidazione-iva", params={"anno": 2026}, headers=ctx["h2"]).json()
        assert d["periodicita"] == "mensile" and d["totale_versare"] == 0 and d["credito_finale"] == 0 and len(d["periodi"]) == 12
        r = ctx["s"].get(f"{API}/liquidazione-iva", params={"anno": 2026, "periodicita": "annuale"}, headers=ctx["h"])
        assert r.status_code == 422
        r = requests.get(f"{API}/liquidazione-iva")
        assert r.status_code == 401

# Iteration 9: scadenzario clienti - invoice installments (rate), XML DatiPagamento, payments (incassi),
# credit-note offsetting (auto + compensazione), /scadenzario aggregation, roles, company isolation.
# Run with: pytest test_iteration9_scadenzario.py -n 0
from datetime import date, timedelta
import pytest
import requests
from test_iteration7_pa_scartate_registro import API, mongo, party, inv, strip_ns

TOK, UID = "test_session_t9_admin", "test-user-t9-admin"
OTOK, OUID = "test_session_t9_oper", "test-user-t9-oper"
PIVA, PIVA2 = "77777777791", "77777777792"
TODAY = date.today()
D0 = (TODAY - timedelta(days=60)).isoformat()
R1 = (TODAY - timedelta(days=45)).isoformat()
R2 = (TODAY - timedelta(days=15)).isoformat()
R3 = (TODAY + timedelta(days=15)).isoformat()


def _clean():
    for p in (PIVA, PIVA2):
        c = mongo(f'const c=db.companies.findOne({{partita_iva:"{p}"}}); print(c?c.id:"")')
        if c:
            mongo(f'db.invoices.deleteMany({{company_id:"{c}"}}); db.parties.deleteMany({{company_id:"{c}"}}); db.payments.deleteMany({{company_id:"{c}"}});'
                  f'db.counters.deleteMany({{key:{{$regex:"{c}"}}}}); db.companies.deleteMany({{id:"{c}"}});')
    mongo(f'db.users.deleteMany({{user_id:{{$in:["{UID}","{OUID}"]}}}}); db.user_sessions.deleteMany({{user_id:{{$in:["{UID}","{OUID}"]}}}});')


def comp(name, piva):
    return {"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01", "iban": "IT60X0542811101000000123456",
            "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"}


@pytest.fixture(scope="module")
def ctx():
    _clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t9.admin@example.com", name:"TEST_T9 Admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+7*864e5), created_at:new Date().toISOString()}});')
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    r = s.post(f"{API}/companies", json=comp("TEST_T9 Srl", PIVA))
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    cid2 = s.post(f"{API}/companies", json=comp("TEST_T9 Altra Srl", PIVA2)).json()["id"]
    mongo(f'db.users.insertOne({{user_id:"{OUID}", email:"test.user.t9.oper@example.com", name:"TEST_T9 Oper", picture:"", role:"operatore", status:"approved", company_ids:["{cid}"], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{OUID}", session_token:"{OTOK}", expires_at:new Date(Date.now()+7*864e5), created_at:new Date().toISOString()}});')
    h = {"X-Company-Id": cid}
    st = {}
    st["A"] = s.post(f"{API}/parties", json=party("TEST_T9 Cliente A", piva="01234567801"), headers=h).json()["id"]
    st["B"] = s.post(f"{API}/parties", json=party("TEST_T9 Cliente B", piva="01234567802"), headers=h).json()["id"]
    yield {"s": s, "h": h, "cid": cid, "h2": {"X-Company-Id": cid2}, "st": st}
    _clean()


def sent(s, h, body):
    r = s.post(f"{API}/invoices", json=body, headers=h)
    assert r.status_code == 200, r.text
    iid = r.json()["id"]
    assert s.post(f"{API}/invoices/{iid}/send", headers=h).status_code == 200
    r = s.post(f"{API}/invoices/{iid}/refresh", headers=h)
    assert r.json()["status"] == "consegnata", r.text
    return r.json()


def loc(r):
    return [tuple(e["loc"]) for e in r.json()["detail"]]


class TestRate:
    def test_01_sum_mismatch(self, ctx):
        r = ctx["s"].post(f"{API}/invoices", json=inv(ctx["st"]["A"], data=D0, rate=[{"scadenza": R1, "importo": 500}, {"scadenza": R2, "importo": 500}]), headers=ctx["h"])
        assert r.status_code == 422 and ("body", "rate") in loc(r), r.text

    def test_02_scadenza_before_data(self, ctx):
        r = ctx["s"].post(f"{API}/invoices", json=inv(ctx["st"]["A"], data=D0, rate=[{"scadenza": R1, "importo": 610}, {"scadenza": "2020-01-01", "importo": 610}]), headers=ctx["h"])
        assert r.status_code == 422 and ("body", "rate", "1", "scadenza") in loc(r), r.text

    def test_03_sorted_and_last_scadenza(self, ctx):
        body = inv(ctx["st"]["A"], data=D0, rate=[{"scadenza": R3, "importo": 420}, {"scadenza": R1, "importo": 400}, {"scadenza": R2, "importo": 400}])
        d = sent(ctx["s"], ctx["h"], body)
        assert [x["scadenza"] for x in d["rate"]] == [R1, R2, R3]
        assert d["scadenza"] == R3 and d["netto"] == 1220
        ctx["st"]["inv3"] = d["id"]

    def test_04_xml_tp01(self, ctx):
        x = strip_ns(ctx["s"].get(f"{API}/invoices/{ctx['st']['inv3']}/xml", headers=ctx["h"]).text)
        dp = x.find(".//DatiPagamento")
        assert dp.find("CondizioniPagamento").text == "TP01"
        dets = dp.findall("DettaglioPagamento")
        assert [d.find("ImportoPagamento").text for d in dets] == ["400.00", "400.00", "420.00"]
        assert [d.find("DataScadenzaPagamento").text for d in dets] == [R1, R2, R3]
        ctx["st"]["iban_per_det"] = [d.find("IBAN") is not None for d in dets]

    def test_05_xml_tp02_and_td04_ignores_rate(self, ctx):
        s, h = ctx["s"], ctx["h"]
        r = s.post(f"{API}/invoices", json=inv(ctx["st"]["A"], scadenza=R3), headers=h)
        x = strip_ns(s.get(f"{API}/invoices/{r.json()['id']}/xml", headers=h).text)
        assert x.find(".//CondizioniPagamento").text == "TP02" and len(x.findall(".//DettaglioPagamento")) == 1
        s.delete(f"{API}/invoices/{r.json()['id']}", headers=h)
        r = s.post(f"{API}/invoices", json=inv(ctx["st"]["B"], tipo_documento="TD04", price=10, rate=[{"scadenza": R3, "importo": 1}]), headers=h)
        assert r.status_code == 200, r.text
        assert r.json().get("rate") in ([], None)
        s.delete(f"{API}/invoices/{r.json()['id']}", headers=h)


class TestPayments:
    def test_06_draft_rejected(self, ctx):
        s, h = ctx["s"], ctx["h"]
        r = s.post(f"{API}/invoices", json=inv(ctx["st"]["A"]), headers=h)
        p = s.post(f"{API}/invoices/{r.json()['id']}/pagamenti", json={"data": TODAY.isoformat(), "importo": 10}, headers=h)
        assert p.status_code == 400, p.text
        s.delete(f"{API}/invoices/{r.json()['id']}", headers=h)

    def test_07_initial_ledger(self, ctx):
        d = ctx["s"].get(f"{API}/invoices/{ctx['st']['inv3']}/pagamenti", headers=ctx["h"]).json()
        sc = d["scadenzario"]
        assert sc["residuo"] == 1220 and len(sc["rate"]) == 3
        assert [r["stato"] for r in sc["rate"]] == ["aperta"] * 3
        assert [r["scaduta"] for r in sc["rate"]] == [True, True, False]
        assert sc["rate"][0]["giorni_ritardo"] == 45

    def test_08_partial_payment_allocation(self, ctx):
        s, h = ctx["s"], ctx["h"]
        p = s.post(f"{API}/invoices/{ctx['st']['inv3']}/pagamenti", json={"data": TODAY.isoformat(), "importo": 500, "metodo": "bonifico", "note": "TEST"}, headers=h)
        assert p.status_code == 200, p.text
        assert p.json()["importo"] == 500 and "_id" not in p.json()
        ctx["st"]["pay1"] = p.json()["id"]
        d = s.get(f"{API}/invoices/{ctx['st']['inv3']}/pagamenti", headers=h).json()
        rr = d["scadenzario"]["rate"]
        assert [r["stato"] for r in rr] == ["pagata", "parziale", "aperta"]
        assert rr[1]["pagato"] == 100 and rr[1]["residuo"] == 300 and rr[1]["scaduta"] is True and rr[1]["giorni_ritardo"] == 15
        assert d["scadenzario"]["incassato"] == 500 and d["scadenzario"]["residuo"] == 720
        assert len(d["pagamenti"]) == 1

    def test_09_over_residuo_and_future(self, ctx):
        s, h = ctx["s"], ctx["h"]
        p = s.post(f"{API}/invoices/{ctx['st']['inv3']}/pagamenti", json={"data": TODAY.isoformat(), "importo": 720.5}, headers=h)
        assert p.status_code == 400 and ("body", "importo") in loc(p), p.text
        p = s.post(f"{API}/invoices/{ctx['st']['inv3']}/pagamenti", json={"data": (TODAY + timedelta(days=5)).isoformat(), "importo": 10}, headers=h)
        assert p.status_code == 422 and ("body", "data") in loc(p), p.text

    def test_10_operatore_forbidden(self, ctx):
        o = {"Authorization": f"Bearer {OTOK}", **ctx["h"]}
        p = requests.post(f"{API}/invoices/{ctx['st']['inv3']}/pagamenti", json={"data": TODAY.isoformat(), "importo": 10}, headers=o)
        assert p.status_code == 403
        assert requests.delete(f"{API}/pagamenti/{ctx['st']['pay1']}", headers=o).status_code == 403
        assert requests.get(f"{API}/scadenzario", headers=o).status_code == 200


class TestCreditNotes:
    def test_11_auto_offset_linked_nc(self, ctx):
        s, h, st = ctx["s"], ctx["h"], ctx["st"]
        b = sent(s, h, inv(st["B"], data=D0, scadenza=R2))
        st["invB"] = b["id"]
        nc = sent(s, h, inv(st["B"], tipo_documento="TD04", price=200, fattura_collegata_id=b["id"]))
        st["ncB"] = nc["id"]
        sc = s.get(f"{API}/invoices/{b['id']}/pagamenti", headers=h).json()["scadenzario"]
        assert sc["compensato_auto"] == 244 and sc["residuo"] == 976, sc

    def test_12_nc_credit_on_paid_invoice(self, ctx):
        s, h, st = ctx["s"], ctx["h"], ctx["st"]
        c = sent(s, h, inv(st["B"], price=100))
        assert s.post(f"{API}/invoices/{c['id']}/pagamenti", json={"data": TODAY.isoformat(), "importo": 122}, headers=h).status_code == 200
        nc = sent(s, h, inv(st["B"], tipo_documento="TD04", price=50, fattura_collegata_id=c["id"]))
        st["ncCredit"] = nc["id"]
        d = s.get(f"{API}/scadenzario", headers=h).json()
        cr = [x for x in d["crediti"] if x["id"] == nc["id"]]
        assert cr and cr[0]["residuo"] == 61, d["crediti"]

    def test_13_compensation_validations(self, ctx):
        s, h, st = ctx["s"], ctx["h"], ctx["st"]
        # other client's NC -> nc_id
        p = s.post(f"{API}/invoices/{st['inv3']}/pagamenti", json={"data": TODAY.isoformat(), "importo": 10, "metodo": "compensazione", "nc_id": st["ncCredit"]}, headers=h)
        assert p.status_code == 400 and ("body", "nc_id") in loc(p), p.text
        p = s.post(f"{API}/invoices/{st['invB']}/pagamenti", json={"data": TODAY.isoformat(), "importo": 10, "metodo": "compensazione"}, headers=h)
        assert p.status_code == 400 and ("body", "nc_id") in loc(p), p.text
        p = s.post(f"{API}/invoices/{st['invB']}/pagamenti", json={"data": TODAY.isoformat(), "importo": 70, "metodo": "compensazione", "nc_id": st["ncCredit"]}, headers=h)
        assert p.status_code == 400 and ("body", "importo") in loc(p), p.text

    def test_14_compensation_ok(self, ctx):
        s, h, st = ctx["s"], ctx["h"], ctx["st"]
        p = s.post(f"{API}/invoices/{st['invB']}/pagamenti", json={"data": TODAY.isoformat(), "importo": 61, "metodo": "compensazione", "nc_id": st["ncCredit"]}, headers=h)
        assert p.status_code == 200, p.text
        assert p.json()["metodo"] == "compensazione" and p.json()["nc_numero"]
        st["comp"] = p.json()["id"]
        d = s.get(f"{API}/invoices/{st['invB']}/pagamenti", headers=h).json()
        assert d["scadenzario"]["compensato"] == 305 and d["scadenzario"]["residuo"] == 915
        assert not [x for x in d["crediti"] if x["id"] == st["ncCredit"]]


class TestScadenzario:
    def test_15_aggregation(self, ctx):
        d = ctx["s"].get(f"{API}/scadenzario", headers=ctx["h"]).json()
        cl = {c["party_id"]: c for c in d["clienti"]}
        a = cl[ctx["st"]["A"]]
        assert a["aperto"] == 720 and a["scaduto"] == 300 and a["entro_30"] == 420 and a["oltre_30"] == 0 and a["prossima"] == R3 and a["rate_aperte"] == 2
        b = cl[ctx["st"]["B"]]
        assert b["aperto"] == 915 and b["scaduto"] == 915 and b["crediti"] == 0
        assert d["totali"]["aperto"] == 1635 and d["totali"]["scaduto"] == 1215
        assert all(r["invoice_id"] for r in d["rate"])

    def test_16_party_filter(self, ctx):
        d = ctx["s"].get(f"{API}/scadenzario", params={"party_id": ctx["st"]["A"]}, headers=ctx["h"]).json()
        assert {c["party_id"] for c in d["clienti"]} == {ctx["st"]["A"]}

    def test_17_delete_payment(self, ctx):
        s, h, st = ctx["s"], ctx["h"], ctx["st"]
        assert s.delete(f"{API}/pagamenti/{st['comp']}", headers=ctx["h2"]).status_code in (404, 403)
        assert s.delete(f"{API}/pagamenti/{st['comp']}", headers=h).status_code == 200
        assert s.delete(f"{API}/pagamenti/{st['comp']}", headers=h).status_code == 404
        d = s.get(f"{API}/scadenzario", headers=h).json()
        assert [x for x in d["crediti"] if x["id"] == st["ncCredit"]][0]["residuo"] == 61

    def test_18_company_isolation(self, ctx):
        d = ctx["s"].get(f"{API}/scadenzario", headers=ctx["h2"]).json()
        assert d["rate"] == [] and d["clienti"] == [] and d["crediti"] == []
        r = ctx["s"].get(f"{API}/invoices/{ctx['st']['inv3']}/pagamenti", headers=ctx["h2"])
        assert r.status_code == 404

    def test_19_iban_on_each_rata(self, ctx):
        # FatturaPA: IBAN should be present on each DettaglioPagamento for MP05
        assert all(ctx["st"]["iban_per_det"]), ctx["st"]["iban_per_det"]

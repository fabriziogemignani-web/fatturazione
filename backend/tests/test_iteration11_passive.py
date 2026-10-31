# Iteration 11: fatture passive (simulated SDI sync, XML/P7M upload, parsing, registration status, rate edit, payments,
# scadenzario passivo, linked TD04 offset, roles, company isolation) + regression of the active scadenzario.
# Run with: pytest test_iteration11_passive.py -n 0
import base64
import random
from datetime import date, timedelta
from pathlib import Path
import pytest
import requests
from test_iteration7_pa_scartate_registro import API, mongo

RUN = str(random.randint(100000, 999999))
TOK, UID = f"test_session_t11_admin_{RUN}", f"test-user-t11-admin-{RUN}"
CTOK, CUID = f"test_session_t11_cont_{RUN}", f"test-user-t11-cont-{RUN}"
OTOK, OUID = f"test_session_t11_oper_{RUN}", f"test-user-t11-oper-{RUN}"
PIVA_FIX = "01234567890"
PIVA2 = "89" + RUN + "002"
FIX = Path(__file__).parent / "fixtures"
XML = (FIX / "sample_fattura.xml").read_bytes()
P7M = (FIX / "sample_fattura.xml.p7m").read_bytes()
TODAY = date.today().isoformat()


def clean_all():
    mongo('db.companies.find({denominazione:/^TEST_T11/}).forEach(c=>{["invoices","parties","payments","passive_invoices","passive_payments"].forEach(k=>db[k].deleteMany({company_id:c.id}));'
          'db.counters.deleteMany({key:{$regex:c.id}}); db.companies.deleteOne({id:c.id});});'
          'db.users.deleteMany({user_id:/^test-user-t11-/}); db.user_sessions.deleteMany({session_token:/^test_session_t11_/});')


def comp(name, piva):
    return {"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01", "iban": "IT60X0542811101000000123456",
            "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"}


def user(uid, tok, role, cids):
    mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.{uid}@example.com", name:"TEST_T11 {role}", picture:"", role:"{role}", status:"approved", company_ids:{cids}, created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+7*864e5), created_at:new Date().toISOString()}});')


def sess(tok):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    return s


def variant(numero, tipo="TD01", collegata=None, rate=None, ritenuta=None, piva_supp=None, data="2026-10-30"):
    x = XML.decode()
    x = x.replace("<Numero>5674/2026</Numero>", f"<Numero>{numero}</Numero>").replace("<TipoDocumento>TD01</TipoDocumento>", f"<TipoDocumento>{tipo}</TipoDocumento>")
    x = x.replace("<Data>2026-10-30</Data>", f"<Data>{data}</Data>")
    if piva_supp:
        x = x.replace("02345670481", piva_supp).replace("DEMO Energia Toscana SpA", f"TEST_T11 Fornitore {piva_supp}")
    extra = ""
    if ritenuta:
        extra += f"<DatiRitenuta><TipoRitenuta>RT01</TipoRitenuta><ImportoRitenuta>{ritenuta:.2f}</ImportoRitenuta><AliquotaRitenuta>20.00</AliquotaRitenuta><CausalePagamento>A</CausalePagamento></DatiRitenuta>"
    x = x.replace("<ImportoTotaleDocumento>574.93</ImportoTotaleDocumento>", f"<ImportoTotaleDocumento>574.93</ImportoTotaleDocumento>{extra}")
    if collegata:
        x = x.replace("</DatiGeneraliDocumento>", f"</DatiGeneraliDocumento><DatiFattureCollegate><IdDocumento>{collegata}</IdDocumento></DatiFattureCollegate>")
    if rate is not None:
        start, end = x.index("<DatiPagamento>"), x.index("</DatiPagamento>") + len("</DatiPagamento>")
        dp = "".join(f"<DettaglioPagamento><ModalitaPagamento>MP05</ModalitaPagamento><DataScadenzaPagamento>{s}</DataScadenzaPagamento><ImportoPagamento>{i:.2f}</ImportoPagamento><IBAN>IT02A0306902887100000001234</IBAN></DettaglioPagamento>" for s, i in rate)
        x = x[:start] + (f"<DatiPagamento><CondizioniPagamento>TP01</CondizioniPagamento>{dp}</DatiPagamento>" if rate else "") + x[end:]
    return x.encode()


def up(s, h, *files):
    r = s.post(f"{API}/passive/upload", files=[("files", (n, b, "application/octet-stream")) for n, b in files], headers=h)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def ctx():
    clean_all()
    user(UID, TOK, "admin", "[]")
    s = sess(TOK)
    r = s.post(f"{API}/companies", json=comp("TEST_T11 Fix Srl", PIVA_FIX))
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    r = s.post(f"{API}/companies", json=comp("TEST_T11 Altra Srl", PIVA2))
    assert r.status_code == 200, r.text
    cid2 = r.json()["id"]
    user(CUID, CTOK, "contabile", f'["{cid}"]')
    user(OUID, OTOK, "operatore", f'["{cid}", "{cid2}"]')
    yield {"s": s, "c": sess(CTOK), "o": sess(OTOK), "cid": cid, "cid2": cid2, "h": {"X-Company-Id": cid}, "h2": {"X-Company-Id": cid2}, "st": {}}
    clean_all()


class TestSdiSync:
    def test_01_sync_creates_demo_and_suppliers(self, ctx):
        s, h2 = ctx["s"], ctx["h2"]
        total = 0
        for _ in range(4):
            r = s.post(f"{API}/passive/sdi-sync", headers=h2)
            assert r.status_code == 200, r.text
            ric = r.json()["ricevute"]
            assert 0 <= len(ric) <= 3
            total += len(ric)
        assert total >= 1
        lst = s.get(f"{API}/passive", headers=h2).json()
        assert len(lst) == total
        assert all(p["origine"] == "sdi_simulato" and p["stato_reg"] == "da_registrare" and "xml" not in p and "_id" not in p for p in lst)
        assert all(p["fornitore"]["denominazione"].startswith("DEMO") for p in lst)
        # suppliers auto-created once per P.IVA
        parties = s.get(f"{API}/parties", headers=h2).json()
        forn = [p for p in parties if p.get("tipo") == "fornitore"]
        pivas = [p["partita_iva"] for p in forn]
        assert len(pivas) == len(set(pivas)), pivas
        assert all(p.get("origine") == "fattura_passiva" for p in forn)
        assert {p["party_id"] for p in lst} == {p["id"] for p in forn}

    def test_02_sync_operatore_403(self, ctx):
        assert ctx["o"].post(f"{API}/passive/sdi-sync", headers=ctx["h2"]).status_code == 403

    def test_03_sync_no_piva_400(self, ctx):
        mongo(f'db.companies.updateOne({{id:"{ctx["cid2"]}"}}, {{$set:{{partita_iva:""}}}})')
        try:
            r = ctx["s"].post(f"{API}/passive/sdi-sync", headers=ctx["h2"])
            assert r.status_code == 400 and "Partita IVA" in r.json()["detail"], r.text
        finally:
            mongo(f'db.companies.updateOne({{id:"{ctx["cid2"]}"}}, {{$set:{{partita_iva:"{PIVA2}"}}}})')


class TestUpload:
    def test_04_upload_xml_parsed(self, ctx):
        res = up(ctx["c"], ctx["h"], ("sample_fattura.xml", XML))
        assert res[0]["ok"] is True, res
        doc = res[0]["documenti"][0]
        assert doc["numero"] == "5674/2026" and doc["totale"] == 574.93
        ctx["st"]["p1"] = doc["id"]
        d = ctx["s"].get(f"{API}/passive/{doc['id']}", headers=ctx["h"]).json()
        assert d["numero"] == "5674/2026" and d["data"] == "2026-10-30" and d["tipo_documento"] == "TD01"
        assert d["imponibile"] == 471.25 and d["iva"] == 103.68 and d["ritenuta_importo"] == 0 and d["netto"] == 574.93
        assert d["rate"] == [{"scadenza": "2026-11-29", "importo": 574.93, "modalita": "MP05", "iban": "IT02A0306902887100000001234"}]
        assert len(d["lines"]) == 2 and d["lines"][0]["prezzo_totale"] == 412.35
        assert d["riepilogo"][0]["imposta"] == 103.68
        assert d["fornitore"]["partita_iva"] == "02345670481" and d["fornitore"]["comune"] == "Firenze"
        assert d["origine"] == "upload" and "xml" not in d and "_id" not in d

    def test_05_p7m_same_doc_duplicate(self, ctx):
        res = up(ctx["s"], ctx["h"], ("sample_fattura.xml.p7m", P7M))
        assert res[0]["ok"] is False and "già importato" in res[0]["error"], res

    def test_06_p7m_base64_and_der_parse(self, ctx):
        # base64 p7m of the same document in another (clean) company is accepted only if cessionario matches -> use main company after deleting? use parse via other numero
        b64 = base64.b64encode(P7M)
        res = up(ctx["s"], ctx["h"], ("b64.xml.p7m", b64))
        assert res[0]["ok"] is False and "già importato" in res[0]["error"], res  # extracted fine, hash dup

    def test_07_same_doc_different_bytes_duplicate(self, ctx):
        res = up(ctx["s"], ctx["h"], ("dup.xml", XML + b"\n<!-- x -->\n"))
        assert res[0]["ok"] is False and "già presente" in res[0]["error"], res

    def test_08_other_company_rejected(self, ctx):
        res = up(ctx["s"], ctx["h2"], ("sample_fattura.xml", XML))
        assert res[0]["ok"] is False and "intestata a un altro soggetto" in res[0]["error"], res

    def test_09_bad_files(self, ctx):
        res = up(ctx["s"], ctx["h"], ("a.xml", b"<?xml version='1.0'?><Foo><Bar/></Foo>"), ("b.xml", b"<FatturaElettronica><unclosed>"),
                 ("c.p7m", b"\x00\x01garbage binary"), ("d.xml", b"<FatturaElettronica></FatturaElettronica>"))
        assert [r["ok"] for r in res] == [False] * 4
        assert "FatturaPA" in res[0]["error"]
        assert "XML non valido" in res[1]["error"]
        assert "non riconosciuto" in res[2]["error"]
        assert "Intestazione" in res[3]["error"]
        assert all(r["file"] for r in res)

    def test_10_too_many_and_too_big(self, ctx):
        r = ctx["s"].post(f"{API}/passive/upload", files=[("files", (f"f{i}.xml", b"<a/>", "text/xml")) for i in range(21)], headers=ctx["h"])
        assert r.status_code == 400, r.text
        res = up(ctx["s"], ctx["h"], ("big.xml", b"<" + b"a" * (5 * 1024 * 1024 + 10)))
        assert res[0]["ok"] is False and "5 MB" in res[0]["error"]

    def test_11_upload_operatore_403(self, ctx):
        r = ctx["o"].post(f"{API}/passive/upload", files=[("files", ("x.xml", XML, "text/xml"))], headers=ctx["h"])
        assert r.status_code == 403

    def test_12_multi_rate_ritenuta_supplier_reuse(self, ctx):
        x = variant("R-1", rate=[("2026-11-15", 200.0), ("2026-12-15", 274.93)], ritenuta=100.0)
        res = up(ctx["s"], ctx["h"], ("rate.xml", x))
        assert res[0]["ok"], res
        pid = res[0]["documenti"][0]["id"]
        ctx["st"]["p2"] = pid
        d = ctx["s"].get(f"{API}/passive/{pid}", headers=ctx["h"]).json()
        assert d["ritenuta_importo"] == 100.0 and d["netto"] == 474.93 and len(d["rate"]) == 2 and d["scadenza"] == "2026-12-15"
        p1 = ctx["s"].get(f"{API}/passive/{ctx['st']['p1']}", headers=ctx["h"]).json()
        assert d["party_id"] == p1["party_id"]  # same supplier reused
        # no DatiPagamento -> netto = totale - ritenuta, scadenza = data
        res = up(ctx["s"], ctx["h"], ("norate.xml", variant("R-2", rate=[], ritenuta=50.0)))
        d = ctx["s"].get(f"{API}/passive/{res[0]['documenti'][0]['id']}", headers=ctx["h"]).json()
        assert d["netto"] == 524.93 and d["rate"] == [] and d["scadenza"] == "2026-10-30"
        ctx["st"]["p3"] = d["id"]


class TestReadPatch:
    def test_13_list_filters_and_xml(self, ctx):
        s, h = ctx["s"], ctx["h"]
        lst = s.get(f"{API}/passive", headers=h).json()
        assert len(lst) == 3 and all("lines" not in p for p in lst)
        pid_party = lst[0]["party_id"]
        assert len(s.get(f"{API}/passive", params={"party_id": pid_party}, headers=h).json()) == 3
        assert len(s.get(f"{API}/passive", params={"party_id": "nope"}, headers=h).json()) == 0
        r = s.get(f"{API}/passive/{ctx['st']['p1']}/xml", headers=h)
        assert r.status_code == 200 and "xml" in r.headers["content-type"] and b"5674/2026" in r.content
        assert 'filename="sample_fattura.xml"' in r.headers["content-disposition"]
        # operatore can read
        assert ctx["o"].get(f"{API}/passive/{ctx['st']['p1']}", headers=h).status_code == 200

    def test_14_isolation(self, ctx):
        s = ctx["s"]
        assert s.get(f"{API}/passive/{ctx['st']['p1']}", headers=ctx["h2"]).status_code == 404
        assert s.get(f"{API}/passive/{ctx['st']['p1']}/xml", headers=ctx["h2"]).status_code == 404
        assert s.patch(f"{API}/passive/{ctx['st']['p1']}", json={"note": "x"}, headers=ctx["h2"]).status_code == 404
        assert s.delete(f"{API}/passive/{ctx['st']['p1']}", headers=ctx["h2"]).status_code == 404
        assert s.post(f"{API}/passive/{ctx['st']['p1']}/pagamenti", json={"data": TODAY, "importo": 1}, headers=ctx["h2"]).status_code == 404
        ids = {p["id"] for p in s.get(f"{API}/passive", headers=ctx["h2"]).json()}
        assert ctx["st"]["p1"] not in ids
        # contabile not assigned to cid2
        assert ctx["c"].get(f"{API}/passive", headers=ctx["h2"]).status_code == 404

    def test_15_patch_stato_note_and_filters(self, ctx):
        s, h, p1 = ctx["c"], ctx["h"], ctx["st"]["p1"]
        r = s.patch(f"{API}/passive/{p1}", json={"stato_reg": "registrata", "note": "Prot. 12"}, headers=h)
        assert r.status_code == 200 and r.json()["stato_reg"] == "registrata" and r.json()["note"] == "Prot. 12"
        assert s.get(f"{API}/passive/{p1}", headers=h).json()["stato_reg"] == "registrata"
        assert [p["id"] for p in s.get(f"{API}/passive", params={"stato": "registrata"}, headers=h).json()] == [p1]
        assert p1 not in [p["id"] for p in s.get(f"{API}/passive", params={"stato": "da_registrare"}, headers=h).json()]
        assert s.patch(f"{API}/passive/{p1}", json={"stato_reg": "bogus"}, headers=h).status_code == 422
        assert ctx["o"].patch(f"{API}/passive/{p1}", json={"note": "x"}, headers=h).status_code == 403

    def test_16_patch_rate(self, ctx):
        s, h, p1 = ctx["s"], ctx["h"], ctx["st"]["p1"]
        r = s.patch(f"{API}/passive/{p1}", json={"rate": [{"scadenza": "2026-12-01", "importo": 300}, {"scadenza": "2026-11-01", "importo": 200}]}, headers=h)
        assert r.status_code == 422, r.text
        det = r.json()["detail"]
        assert "rate" in str(det)
        r = s.patch(f"{API}/passive/{p1}", json={"rate": [{"scadenza": "2026-12-01", "importo": 374.93}, {"scadenza": "2026-10-15", "importo": 200}]}, headers=h)
        assert r.status_code == 200, r.text
        d = s.get(f"{API}/passive/{p1}", headers=h).json()
        assert [x["scadenza"] for x in d["rate"]] == ["2026-10-15", "2026-12-01"] and d["scadenza"] == "2026-12-01"


class TestPayments:
    def test_17_payments_validation_and_delete_block(self, ctx):
        s, h, p1 = ctx["s"], ctx["h"], ctx["st"]["p1"]
        assert s.post(f"{API}/passive/{p1}/pagamenti", json={"data": TODAY, "importo": 600}, headers=h).status_code == 400
        r = s.post(f"{API}/passive/{p1}/pagamenti", json={"data": "2026-10-01", "importo": 10}, headers=h)
        assert r.status_code == 400 and "data" in str(r.json()), r.text
        fut = (date.today() + timedelta(days=5)).isoformat()
        assert s.post(f"{API}/passive/{p1}/pagamenti", json={"data": fut, "importo": 10}, headers=h).status_code == 422
        assert ctx["o"].post(f"{API}/passive/{p1}/pagamenti", json={"data": TODAY, "importo": 10}, headers=h).status_code == 403
        r = ctx["c"].post(f"{API}/passive/{p1}/pagamenti", json={"data": TODAY, "importo": 250, "metodo": "bonifico", "note": "TEST"}, headers=h)
        assert r.status_code == 200, r.text
        pay = r.json()
        assert "_id" not in pay and pay["importo"] == 250
        ctx["st"]["pay1"] = pay["id"]
        g = s.get(f"{API}/passive/{p1}/pagamenti", headers=h).json()
        assert g["scadenzario"]["residuo"] == 324.93 and g["scadenzario"]["incassato"] == 250 and len(g["pagamenti"]) == 1
        assert g["scadenzario"]["rate"][0]["stato"] == "pagata" and g["scadenzario"]["rate"][1]["stato"] == "parziale"
        r = s.delete(f"{API}/passive/{p1}", headers=h)
        assert r.status_code == 400 and "pagamenti" in r.json()["detail"]

    def test_18_scadenzario_passivo_shape(self, ctx):
        s, h = ctx["s"], ctx["h"]
        a = s.get(f"{API}/scadenzario", headers=h).json()
        p = s.get(f"{API}/scadenzario-passivo", headers=h).json()
        assert set(a.keys()) == set(p.keys()) == {"oggi", "rate", "clienti", "crediti", "totali"}
        # p1 residuo 324.93 (rate 2 res), p2 474.93, p3 524.93
        assert p["totali"]["aperto"] == round(324.93 + 474.93 + 524.93, 2), p["totali"]
        assert len(p["clienti"]) == 1 and p["clienti"][0]["cliente"] == "DEMO Energia Toscana SpA"
        assert {r["invoice_id"] for r in p["rate"]} == {ctx["st"]["p1"], ctx["st"]["p2"], ctx["st"]["p3"]}
        # scaduto: p3 scadenza 2026-10-30 < today 2026-10-31
        assert p["totali"]["scaduto"] == 524.93

    def test_19_contestata_excluded(self, ctx):
        s, h, p3 = ctx["s"], ctx["h"], ctx["st"]["p3"]
        assert s.patch(f"{API}/passive/{p3}", json={"stato_reg": "contestata"}, headers=h).status_code == 200
        p = s.get(f"{API}/scadenzario-passivo", headers=h).json()
        assert p3 not in {r["invoice_id"] for r in p["rate"]} and p["totali"]["scaduto"] == 0
        assert s.post(f"{API}/passive/{p3}/pagamenti", json={"data": TODAY, "importo": 1}, headers=h).status_code == 400
        assert s.patch(f"{API}/passive/{p3}", json={"stato_reg": "da_registrare"}, headers=h).status_code == 200

    def test_20_td04_linked_and_free_nc(self, ctx):
        s, h, p2 = ctx["s"], ctx["h"], ctx["st"]["p2"]
        res = up(s, h, ("nc.xml", variant("NC-1", tipo="TD04", collegata="R-1", rate=[])))
        assert res[0]["ok"], res
        nc = s.get(f"{API}/passive/{res[0]['documenti'][0]['id']}", headers=h).json()
        assert nc["fattura_collegata_id"] == p2 and nc["netto"] == 574.93
        g = s.get(f"{API}/passive/{p2}/pagamenti", headers=h).json()
        assert g["scadenzario"]["residuo"] == 0 and g["scadenzario"]["compensato_auto"] == 474.93
        # leftover credit 100 shows in crediti
        assert any(c["id"] == nc["id"] and c["residuo"] == 100.0 for c in g["crediti"])
        assert s.patch(f"{API}/passive/{nc['id']}", json={"rate": [{"scadenza": TODAY, "importo": 1}]}, headers=h).status_code == 400
        assert s.post(f"{API}/passive/{nc['id']}/pagamenti", json={"data": TODAY, "importo": 1}, headers=h).status_code == 400
        # compensation on p1 (residuo 324.93) with NC credit 100
        p1 = ctx["st"]["p1"]
        assert s.post(f"{API}/passive/{p1}/pagamenti", json={"data": TODAY, "importo": 150, "metodo": "compensazione", "nc_id": nc["id"]}, headers=h).status_code == 400
        assert s.post(f"{API}/passive/{p1}/pagamenti", json={"data": TODAY, "importo": 50, "metodo": "compensazione", "nc_id": "nope"}, headers=h).status_code == 400
        r = s.post(f"{API}/passive/{p1}/pagamenti", json={"data": TODAY, "importo": 100, "metodo": "compensazione", "nc_id": nc["id"]}, headers=h)
        assert r.status_code == 200 and r.json()["nc_numero"] == "NC-1", r.text
        ctx["st"]["pay2"], ctx["st"]["nc"] = r.json()["id"], nc["id"]
        g = s.get(f"{API}/passive/{p1}/pagamenti", headers=h).json()
        assert g["scadenzario"]["residuo"] == 224.93 and g["crediti"] == []
        # NC with payments (as nc_id) cannot be deleted
        assert s.delete(f"{API}/passive/{nc['id']}", headers=h).status_code == 400

    def test_21_delete_payments_then_invoice(self, ctx):
        s, h = ctx["s"], ctx["h"]
        assert ctx["o"].delete(f"{API}/passive-pagamenti/{ctx['st']['pay1']}", headers=h).status_code == 403
        assert s.delete(f"{API}/passive-pagamenti/{ctx['st']['pay1']}", headers=ctx["h2"]).status_code == 404
        for k in ("pay1", "pay2"):
            assert s.delete(f"{API}/passive-pagamenti/{ctx['st'][k]}", headers=h).status_code == 200
        assert s.delete(f"{API}/passive-pagamenti/{ctx['st']['pay1']}", headers=h).status_code == 404
        assert ctx["o"].delete(f"{API}/passive/{ctx['st']['p3']}", headers=h).status_code == 403
        assert s.delete(f"{API}/passive/{ctx['st']['p3']}", headers=h).status_code == 200
        assert s.get(f"{API}/passive/{ctx['st']['p3']}", headers=h).status_code == 404
        # after deleting, the same file can be re-imported
        res = up(s, h, ("norate.xml", variant("R-2", rate=[], ritenuta=50.0)))
        assert res[0]["ok"], res

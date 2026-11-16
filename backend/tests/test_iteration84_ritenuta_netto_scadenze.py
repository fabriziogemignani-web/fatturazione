# Iteration 84: fatture passive con ritenuta d'acconto -> netto/scadenze = totale - ritenuta.
# (1) parse_fattura rescales gross DettaglioPagamento; (2) _ritenuta_upd / registra_passiva rescale rate_mod;
# (3) startup migration _fix_netto_ritenute; coge entry, scadenzario-passivo, pagamenti-fornitori, ritenute/mese, reg-veloce regression.
# Run: pytest tests/test_iteration84_ritenuta_netto_scadenze.py -v -n 0
import json
import os
import random
import subprocess
import sys
import time
import uuid

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402
from passive import parse_fattura  # noqa: E402

RUN = str(random.randint(100000, 999999))
TOK, UID = "test_session_t84_admin", "test-user-t84-admin"
PIVA = "84" + RUN + "841"
IBAN = "IT60X0542811101000000123456"
IBAN_F = "IT07X0542811101000000654321"
DD, DR, MESE = "2026-11-02", "2026-11-05", "2026-11"
ST = {}
COLLS = ["invoices", "passive_invoices", "parties", "articles", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "partite_aperte", "f24_versamenti", "pag_distinte", "ratei_risconti", "counters"]


def sess():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{denominazione:/^TEST_T84/}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def xml(numero, ced_piva, totale=1220.0, imp=1000.0, iva=220.0, rit=200.0, rate=(610.0, 610.0), esig="I"):
    dr = (f"<DatiRitenuta><TipoRitenuta>RT01</TipoRitenuta><ImportoRitenuta>{rit:.2f}</ImportoRitenuta><AliquotaRitenuta>20.00</AliquotaRitenuta>"
          f"<CausalePagamento>A</CausalePagamento></DatiRitenuta>") if rit else ""
    det = "".join(f"<DettaglioPagamento><ModalitaPagamento>MP05</ModalitaPagamento><DataScadenzaPagamento>2026-{12 if i == 0 else 12}-{10 + i * 10}</DataScadenzaPagamento>"
                  f"<ImportoPagamento>{v:.2f}</ImportoPagamento><IBAN>{IBAN_F}</IBAN></DettaglioPagamento>" for i, v in enumerate(rate))
    pag = f"<DatiPagamento><CondizioniPagamento>TP01</CondizioniPagamento>{det}</DatiPagamento>" if rate else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica versione="FPR12" xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
<FatturaElettronicaHeader>
<DatiTrasmissione><IdTrasmittente><IdPaese>IT</IdPaese><IdCodice>{ced_piva}</IdCodice></IdTrasmittente><ProgressivoInvio>T84{random.randint(100, 999)}</ProgressivoInvio>
<FormatoTrasmissione>FPR12</FormatoTrasmissione><CodiceDestinatario>0000000</CodiceDestinatario></DatiTrasmissione>
<CedentePrestatore><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>{ced_piva}</IdCodice></IdFiscaleIVA><CodiceFiscale>{ced_piva}</CodiceFiscale>
<Anagrafica><Nome>Mario</Nome><Cognome>TEST_T84 Rossi {ced_piva}</Cognome></Anagrafica><RegimeFiscale>RF01</RegimeFiscale></DatiAnagrafici>
<Sede><Indirizzo>Via Verdi 1</Indirizzo><CAP>20100</CAP><Comune>Milano</Comune><Provincia>MI</Provincia><Nazione>IT</Nazione></Sede></CedentePrestatore>
<CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>{PIVA}</IdCodice></IdFiscaleIVA><CodiceFiscale>{PIVA}</CodiceFiscale>
<Anagrafica><Denominazione>TEST_T84 Srl</Denominazione></Anagrafica></DatiAnagrafici>
<Sede><Indirizzo>Via Roma 1</Indirizzo><CAP>00100</CAP><Comune>Roma</Comune><Provincia>RM</Provincia><Nazione>IT</Nazione></Sede></CessionarioCommittente>
</FatturaElettronicaHeader>
<FatturaElettronicaBody>
<DatiGenerali><DatiGeneraliDocumento><TipoDocumento>TD01</TipoDocumento><Divisa>EUR</Divisa><Data>{DD}</Data><Numero>{numero}</Numero>{dr}
<ImportoTotaleDocumento>{totale:.2f}</ImportoTotaleDocumento></DatiGeneraliDocumento></DatiGenerali>
<DatiBeniServizi><DettaglioLinee><NumeroLinea>1</NumeroLinea><Descrizione>Consulenza</Descrizione><Quantita>1.00</Quantita><PrezzoUnitario>{imp:.2f}</PrezzoUnitario>
<PrezzoTotale>{imp:.2f}</PrezzoTotale><AliquotaIVA>22.00</AliquotaIVA>{'<Ritenuta>SI</Ritenuta>' if rit else ''}</DettaglioLinee>
<DatiRiepilogo><AliquotaIVA>22.00</AliquotaIVA><ImponibileImporto>{imp:.2f}</ImponibileImporto><Imposta>{iva:.2f}</Imposta><EsigibilitaIVA>{esig}</EsigibilitaIVA></DatiRiepilogo>
</DatiBeniServizi>{pag}
</FatturaElettronicaBody>
</p:FatturaElettronica>""".encode()


def upload(x):
    r = sess().post(f"{API}/passive/upload", files=[("files", (f"t84_{uuid.uuid4().hex[:6]}.xml", x, "application/octet-stream"))])
    assert r.status_code == 200, r.text
    j = r.json()[0]
    assert j["ok"], j
    return j["documenti"][0]["id"]


def get(pid):
    r = sess().get(f"{API}/passive/{pid}")
    assert r.status_code == 200, r.text
    return r.json()


def scad(pid):
    """Per-document ledger (/passive/{pid}/pagamenti) cross-checked with /scadenzario-passivo rate list."""
    x = sess().get(f"{API}/passive/{pid}/pagamenti").json()["scadenzario"]
    rows = [r for r in sess().get(f"{API}/scadenzario-passivo").json()["rate"] if r["invoice_id"] == pid]
    assert [r["importo"] for r in rows] == [r["importo"] for r in x["rate"]]
    return x


def pf(pid):
    return sorted([x for x in sess().get(f"{API}/pagamenti-fornitori/scadenze").json() if x["invoice_id"] == pid], key=lambda x: x["rata_n"])


def entries(ref):
    q = {"company_id": ST["cid"], "origine": "acquisto", "ref_id": ref}
    return json.loads(mongo(f'print(JSON.stringify(db.coa_entries.find({json.dumps(q)},{{_id:0}}).toArray()))') or "[]")


def side(e, conto):
    rows = [r for r in e["righe"] if r["conto"] == conto]
    return round(sum(r.get("dare") or 0 for r in rows), 2), round(sum(r.get("avere") or 0 for r in rows), 2)


def party(tipo, name, piva, **kw):
    r = sess().post(f"{API}/parties", json={"tipo": tipo, "denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "codice_destinatario": "ABC1234",
                                           "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT", **kw})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def reg_body(d, **kw):
    b = {"data_registrazione": DR, "numero": d["numero"], "data": d["data"],
         "riepilogo": [{"aliquota": r["aliquota"], "natura": r.get("natura"), "imponibile": r["imponibile"], "imposta": r["imposta"], "conto": ""} for r in d["riepilogo"]]}
    return b | kw


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t84.admin@example.com", name:"TEST_T84 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": f"TEST_T84 Ritenute {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    sess().put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                            "corrispettivi": True, "contabilita": True})
    s = sess()
    c = s.get(f"{API}/company").json()
    c["banche"] = [{"nome": "TEST Banca", "iban": IBAN, "abi": "05428", "cab": "11101", "sia": "A1B2C", "predefinita": True}]
    assert s.put(f"{API}/company", json=c).status_code == 200
    s.get(f"{API}/contabilita/conti")
    ST["FR"] = party("fornitore", "TEST_T84 Professionista Auto", "11223344556", soggetto_ritenuta=True, ritenuta_aliquota=20, ritenuta_base=100, iban=IBAN_F)
    yield
    if os.environ.get("T84_KEEP"):
        print("\nKEEP", RUN, ST["cid"])
    else:
        clean()


# (1) parser unit
class TestParser:
    def test_gross_rescaled(self):
        d = parse_fattura(xml("U1", "01234567890"))["docs"][0]
        assert d["ritenuta_importo"] == 200 and d["netto"] == 1020
        assert [r["importo"] for r in d["rate"]] == [510, 510]

    def test_already_net_unchanged(self):
        d = parse_fattura(xml("U2", "01234567890", rate=(510.0, 510.0)))["docs"][0]
        assert d["netto"] == 1020 and [r["importo"] for r in d["rate"]] == [510, 510]

    def test_odd_cents(self):
        d = parse_fattura(xml("U3", "01234567890", totale=1000.0, imp=819.67, iva=180.33, rit=163.93, rate=(333.33, 333.33, 333.34)))["docs"][0]
        assert d["netto"] == 836.07 and round(sum(r["importo"] for r in d["rate"]), 2) == 836.07

    def test_split_payment(self):
        d = parse_fattura(xml("U4", "01234567890", esig="S", rate=(1000.0,)))["docs"][0]
        assert d["split_payment"] and d["netto"] == 800 and d["rate"][0]["importo"] == 800

    def test_no_rate(self):
        d = parse_fattura(xml("U5", "01234567890", rate=()))["docs"][0]
        assert d["netto"] == 1020 and d["rate"] == []

    def test_no_ritenuta(self):
        d = parse_fattura(xml("U6", "01234567890", rit=0))["docs"][0]
        assert d["netto"] == 1220 and [r["importo"] for r in d["rate"]] == [610, 610]


# (1) import + scadenzario + pagamenti fornitori + coge
class TestImport:
    def test_01_import_gross(self):
        pid = upload(xml(f"T84A-{RUN}", "01234567890"))
        ST["A"] = pid
        d = get(pid)
        assert d["netto"] == 1020 and d["ritenuta_importo"] == 200 and d["totale"] == 1220
        assert [r["importo"] for r in d["rate"]] == [510, 510]

    def test_02_scadenzario(self):
        x = scad(ST["A"])
        assert x["netto"] == 1020 and [r["importo"] for r in x["rate"]] == [510, 510]

    def test_03_pagamenti_fornitori(self):
        assert [x["importo"] for x in pf(ST["A"])] == [510, 510]

    def test_04_coge(self):
        e = entries(ST["A"])
        assert len(e) == 1
        assert side(e[0], "13.03.002") == (0, 200)
        fa = [x for x in e[0]["righe"] if x.get("avere") and x.get("party_id")]
        assert round(sum(x["avere"] for x in fa), 2) == 1020

    def test_05_import_net(self):
        pid = upload(xml(f"T84B-{RUN}", "01234567891", rate=(510.0, 510.0)))
        d = get(pid)
        assert d["netto"] == 1020 and [r["importo"] for r in d["rate"]] == [510, 510]

    def test_06_auto_ritenuta_supplier(self):
        pid = upload(xml(f"T84C-{RUN}", "11223344556", rit=0))
        d = get(pid)
        assert d.get("ritenuta_auto") and d["ritenuta_importo"] == 200 and d["netto"] == 1020
        assert [r["importo"] for r in d["rate"]] == [510, 510]
        assert [x["importo"] for x in pf(pid)] == [510, 510]
        assert side(entries(pid)[0], "13.03.002") == (0, 200)


# (2) rate_mod rescaled by registrazione and by PUT ritenuta
class TestRateMod:
    def test_01_registra_rescales_rate_mod(self):
        pid = upload(xml(f"T84D-{RUN}", "01234567892", rit=0))
        ST["D"] = pid
        r = sess().put(f"{API}/scadenze/passive/{pid}", json={"rate": [{"scadenza": "2026-12-15", "importo": 400}, {"scadenza": "2027-01-15", "importo": 820}]})
        assert r.status_code == 200, r.text
        d = get(pid)
        assert d["netto"] == 1220
        r = sess().post(f"{API}/passive/{pid}/registrazione", json=reg_body(d, ritenuta_aliquota=20, ritenuta_imponibile=1000))
        assert r.status_code == 200, r.text
        g = get(pid)
        assert g["netto"] == 1020 and g["ritenuta_importo"] == 200
        assert round(sum(x["importo"] for x in g["rate_mod"]), 2) == 1020
        assert [x["scadenza"] for x in g["rate_mod"]] == ["2026-12-15", "2027-01-15"]
        x = scad(pid)
        assert round(sum(r["importo"] for r in x["rate"]), 2) == 1020 and x["residuo"] == 1020
        assert round(sum(x["importo"] for x in pf(pid)), 2) == 1020

    def test_02_put_ritenuta_rescales_rate_mod(self):
        pid = upload(xml(f"T84E-{RUN}", "01234567893", rit=0))
        ST["E"] = pid
        assert sess().put(f"{API}/scadenze/passive/{pid}", json={"rate": [{"scadenza": "2026-12-15", "importo": 610}, {"scadenza": "2027-01-15", "importo": 610}]}).status_code == 200
        r = sess().put(f"{API}/passive/{pid}/ritenuta", json={"aliquota": 20, "imponibile": 1000})
        assert r.status_code == 200, r.text
        g = get(pid)
        assert g["netto"] == 1020 and [x["importo"] for x in g["rate_mod"]] == [510, 510]
        assert [x["importo"] for x in pf(pid)] == [510, 510]
        assert side(entries(pid)[0], "13.03.002") == (0, 200)


# Payment of netto + ritenute page; reg-veloce regression
class TestPayAndRegVeloce:
    def test_01_pay_netto_then_ritenute(self):
        pid = ST["A"]
        r = sess().post(f"{API}/passive/{pid}/pagamenti", json={"data": DR, "importo": 1020.01, "metodo": "bonifico"})
        assert r.status_code == 400, r.text
        r = sess().post(f"{API}/passive/{pid}/pagamenti", json={"data": DR, "importo": 1020, "metodo": "bonifico"})
        assert r.status_code == 200, r.text
        x = scad(pid)
        assert x["residuo"] == 0
        assert pf(pid) == []
        j = sess().get(f"{API}/ritenute/mese", params={"mese": MESE}).json()
        righe = [i for f in j["fornitori"] for i in f["righe"]]
        assert any(abs(i["ritenuta"] - 200) < 0.01 for i in righe), j
        dv = sess().get(f"{API}/ritenute/da-versare").json()
        assert any(m["key"] == f"RIT-{MESE}" and m["importo"] >= 200 for m in dv["mesi"]), dv

    def test_02_reg_veloce(self):
        r = sess().post(f"{API}/reg-veloce", json={"tipo": "acquisto", "party_id": ST["FR"], "numero": f"T84RV-{RUN}", "data_documento": DD, "data_registrazione": DR,
                                                  "scadenza": "2026-12-31", "righe": [{"aliquota": 22, "totale": 1220}]})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ritenuta"] == 200 and j["netto"] == 1020
        d = get(j["id"])
        assert d["rate"][0]["importo"] == 1020
        assert [x["importo"] for x in pf(j["id"])] == [1020]


# (3) startup migration
class TestMigration:
    def test_01_insert_restart_verify(self):
        cid = ST["cid"]
        base = {"company_id": cid, "origine": "manuale", "tipo_documento": "TD01", "data": DD, "party_id": ST["FR"], "fornitore": {"denominazione": "TEST_T84 Mig"},
                "totale": 1220, "imponibile": 1000, "iva": 220, "ritenuta_importo": 200, "split_payment": False, "stato_reg": "da_registrare",
                "riepilogo": [{"aliquota": 22, "natura": None, "imponibile": 1000, "imposta": 220}], "scadenza": "2026-12-20"}
        ids = {k: f"t84-mig-{k}-{RUN}" for k in ("gross", "ratemod", "paid", "ok")}
        docs = [
            base | {"id": ids["gross"], "hash": ids["gross"], "numero": "MIG1", "numero_display": "MIG1", "netto": 1220,
                    "rate": [{"scadenza": "2026-12-10", "importo": 610}, {"scadenza": "2026-12-20", "importo": 610}]},
            base | {"id": ids["ratemod"], "hash": ids["ratemod"], "numero": "MIG2", "numero_display": "MIG2", "netto": 1020,
                    "rate": [{"scadenza": "2026-12-10", "importo": 1020}], "rate_mod": [{"scadenza": "2026-12-10", "importo": 610}, {"scadenza": "2026-12-20", "importo": 610}]},
            base | {"id": ids["paid"], "hash": ids["paid"], "numero": "MIG3", "numero_display": "MIG3", "netto": 1220,
                    "rate": [{"scadenza": "2026-12-10", "importo": 1220}]},
            base | {"id": ids["ok"], "hash": ids["ok"], "numero": "MIG4", "numero_display": "MIG4", "netto": 1020,
                    "rate": [{"scadenza": "2026-12-10", "importo": 1020}]},
        ]
        mongo(f'db.passive_invoices.insertMany({json.dumps(docs)});'
              f'db.passive_payments.insertOne({{id:"t84-pay-{RUN}", company_id:"{cid}", invoice_id:"{ids["paid"]}", party_id:"{ST["FR"]}", data:"{DR}", importo:100}});')
        subprocess.run(["sudo", "supervisorctl", "restart", "backend"], capture_output=True)
        for _ in range(40):
            time.sleep(2)
            try:
                if requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {TOK}"}, timeout=5).status_code == 200:
                    break
            except Exception:
                pass
        g = get(ids["gross"])
        assert g["netto"] == 1020 and [r["importo"] for r in g["rate"]] == [510, 510]
        m = get(ids["ratemod"])
        assert m["netto"] == 1020 and [r["importo"] for r in m["rate_mod"]] == [510, 510]
        p = get(ids["paid"])
        assert p["netto"] == 1220, "doc with payments must not be touched"
        o = get(ids["ok"])
        assert o["netto"] == 1020 and o["rate"][0]["importo"] == 1020
        assert round(sum(r["importo"] for r in scad(ids["gross"])["rate"]), 2) == 1020

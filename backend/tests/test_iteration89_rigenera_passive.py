# Iteration 89: Prima nota "Registra documenti mancanti" (POST /api/contabilita/rigenera) must also register passive invoices
# still "da_registrare": stato_reg, data/anno registrazione, protocollo IVA per year, reverse charge (N6.x @ aliquota_rc),
# regenerated coge entry (ritenuta/RC); contestata untouched; closed years -> errori; idempotent; sales/bank regression.
# Run: pytest tests/test_iteration89_rigenera_passive.py -v -n 0
import json
import os
import random
import sys
import uuid
from datetime import date

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

RUN = str(random.randint(100000, 999999))
TOK, UID = "test_session_t89_admin", "test-user-t89-admin"
PIVA = "89" + RUN + "891"
ST = {}
COLLS = ["invoices", "passive_invoices", "parties", "articles", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "partite_aperte", "f24_versamenti", "pag_distinte", "ratei_risconti", "counters", "bank_tx", "bank_accounts"]
TODAY = date.today().isoformat()
Y = date.today().year


def sess():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{denominazione:/^TEST_T89/}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def xml(numero, data, ced, imp=1000.0, rit=0.0, rc=False):
    iva = 0.0 if rc else round(imp * 0.22, 2)
    tot = round(imp + iva, 2)
    dr = (f"<DatiRitenuta><TipoRitenuta>RT01</TipoRitenuta><ImportoRitenuta>{rit:.2f}</ImportoRitenuta><AliquotaRitenuta>20.00</AliquotaRitenuta>"
          f"<CausalePagamento>A</CausalePagamento></DatiRitenuta>") if rit else ""
    aliq = "<AliquotaIVA>0.00</AliquotaIVA><Natura>N6.3</Natura>" if rc else "<AliquotaIVA>22.00</AliquotaIVA>"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica versione="FPR12" xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
<FatturaElettronicaHeader>
<DatiTrasmissione><IdTrasmittente><IdPaese>IT</IdPaese><IdCodice>{ced}</IdCodice></IdTrasmittente><ProgressivoInvio>T89{random.randint(100, 999)}</ProgressivoInvio>
<FormatoTrasmissione>FPR12</FormatoTrasmissione><CodiceDestinatario>0000000</CodiceDestinatario></DatiTrasmissione>
<CedentePrestatore><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>{ced}</IdCodice></IdFiscaleIVA><CodiceFiscale>{ced}</CodiceFiscale>
<Anagrafica><Denominazione>TEST_T89 Fornitore {ced}</Denominazione></Anagrafica><RegimeFiscale>RF01</RegimeFiscale></DatiAnagrafici>
<Sede><Indirizzo>Via Verdi 1</Indirizzo><CAP>20100</CAP><Comune>Milano</Comune><Provincia>MI</Provincia><Nazione>IT</Nazione></Sede></CedentePrestatore>
<CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>{PIVA}</IdCodice></IdFiscaleIVA><CodiceFiscale>{PIVA}</CodiceFiscale>
<Anagrafica><Denominazione>TEST_T89 Srl</Denominazione></Anagrafica></DatiAnagrafici>
<Sede><Indirizzo>Via Roma 1</Indirizzo><CAP>00100</CAP><Comune>Roma</Comune><Provincia>RM</Provincia><Nazione>IT</Nazione></Sede></CessionarioCommittente>
</FatturaElettronicaHeader>
<FatturaElettronicaBody>
<DatiGenerali><DatiGeneraliDocumento><TipoDocumento>TD01</TipoDocumento><Divisa>EUR</Divisa><Data>{data}</Data><Numero>{numero}</Numero>{dr}
<ImportoTotaleDocumento>{tot:.2f}</ImportoTotaleDocumento></DatiGeneraliDocumento></DatiGenerali>
<DatiBeniServizi><DettaglioLinee><NumeroLinea>1</NumeroLinea><Descrizione>Servizio</Descrizione><Quantita>1.00</Quantita><PrezzoUnitario>{imp:.2f}</PrezzoUnitario>
<PrezzoTotale>{imp:.2f}</PrezzoTotale>{aliq}{'<Ritenuta>SI</Ritenuta>' if rit else ''}</DettaglioLinee>
<DatiRiepilogo>{aliq}<ImponibileImporto>{imp:.2f}</ImponibileImporto><Imposta>{iva:.2f}</Imposta><EsigibilitaIVA>I</EsigibilitaIVA></DatiRiepilogo>
</DatiBeniServizi>
</FatturaElettronicaBody>
</p:FatturaElettronica>""".encode()


def upload(x):
    r = sess().post(f"{API}/passive/upload", files=[("files", (f"t89_{uuid.uuid4().hex[:6]}.xml", x, "application/octet-stream"))])
    assert r.status_code == 200, r.text
    j = r.json()[0]
    assert j["ok"], j
    return j["documenti"][0]["id"]


def get(pid):
    r = sess().get(f"{API}/passive/{pid}")
    assert r.status_code == 200, r.text
    return r.json()


def entries(ref, origine="acquisto"):
    q = {"company_id": ST["cid"], "origine": origine, "ref_id": ref}
    return json.loads(mongo(f'print(JSON.stringify(db.coa_entries.find({json.dumps(q)},{{_id:0}}).toArray()))') or "[]")


def side(e, conto):
    rows = [r for r in e["righe"] if r["conto"] == conto]
    return round(sum(r.get("dare") or 0 for r in rows), 2), round(sum(r.get("avere") or 0 for r in rows), 2)


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t89.admin@example.com", name:"TEST_T89 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": f"TEST_T89 Rigenera {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    sess().put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                            "corrispettivi": True, "contabilita": True})
    s = sess()
    s.get(f"{API}/contabilita/conti")
    pr = s.get(f"{API}/contabilita/parametri").json()
    p = pr["parametri"]
    body = {"conti": {k: p[k] for k, _ in pr["ruoli"]}, "contropartita_vendite": p["contropartita_vendite"],
            "contropartita_acquisti": p["contropartita_acquisti"], "aliquota_rc": 10, "categorie": p["categorie"]}
    rr = s.put(f"{API}/contabilita/parametri", json=body)
    assert rr.status_code == 200, rr.text
    ST["p"] = rr.json()["parametri"]
    yield
    if os.environ.get("T89_KEEP"):
        print("\nKEEP", RUN, ST["cid"])
    else:
        clean()


class TestRigenera:
    def test_01_setup_docs(self):
        s = sess()
        ST["F"] = upload(xml("F-1", f"{Y}-02-01", "01111111111"))  # registered manually before -> protocollo 1
        r = s.patch(f"{API}/passive/{ST['F']}", json={"stato_reg": "registrata", "data_registrazione": f"{Y}-02-05"})
        assert r.status_code == 200 and r.json()["protocollo"] == 1, r.text
        ST["A"] = upload(xml("A-1", f"{Y}-03-01", "02222222222"))
        ST["B"] = upload(xml("B-1", f"{Y}-04-01", "03333333333", rit=200.0))
        ST["C"] = upload(xml("C-1", f"{Y}-05-01", "04444444444", rc=True))
        ST["P"] = upload(xml("P-1", f"{Y-1}-12-10", "05555555555"))
        ST["D"] = upload(xml("D-1", f"{Y}-06-01", "06666666666"))
        r = s.patch(f"{API}/passive/{ST['D']}", json={"stato_reg": "contestata"})
        assert r.status_code == 200 and r.json()["stato_reg"] == "contestata"
        ST["E"] = upload(xml("E-1", f"{Y-2}-06-01", "07777777777"))
        mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}}, {{$set:{{coge_chiusi:[{Y-2}]}}}})')
        das = s.get(f"{API}/passive", params={"stato": "da_registrare"}).json()
        items = das if isinstance(das, list) else das.get("items", das.get("rows", []))
        ids = {x["id"] for x in items}
        assert {ST["A"], ST["B"], ST["C"], ST["P"], ST["E"]} <= ids, ids
        ST["b_before"] = entries(ST["B"])

    def test_02_sales_and_bank_missing(self):
        s = sess()
        r = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": "TEST_T89 Cliente", "partita_iva": "08888888888", "codice_fiscale": "08888888888",
                                           "codice_destinatario": "ABC1234", "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"})
        assert r.status_code == 200, r.text
        r = s.post(f"{API}/invoices", json={"tipo_documento": "TD01", "data": TODAY, "party_id": r.json()["id"], "modalita_pagamento": "MP05",
                                            "lines": [{"descrizione": "TEST", "quantita": 1, "prezzo_unitario": 100, "aliquota": 22}]})
        assert r.status_code == 200, r.text
        iid = r.json()["id"]
        assert s.post(f"{API}/invoices/{iid}/send").status_code == 200
        assert s.post(f"{API}/invoices/{iid}/refresh").status_code == 200
        assert s.get(f"{API}/invoices/{iid}").json()["status"] == "consegnata"
        ST["I"] = iid
        txid = f"t89-tx-{RUN}"
        ST["T"] = txid
        mongo(f'db.coa_entries.deleteMany({{company_id:"{ST["cid"]}", ref_id:"{iid}"}});'
              f'db.bank_tx.insertOne({{id:"{txid}", company_id:"{ST["cid"]}", data:"{Y}-07-01", importo:-50, descrizione:"TEST_T89 spesa", stato:"riconciliato",'
              f' match:{{tipo:"spesa", categoria:"Altro", label:"TEST_T89 spesa"}}}})')
        assert entries(iid, "vendita") == []

    def test_03_rigenera(self):
        r = sess().post(f"{API}/contabilita/rigenera", json={"ricrea": False})
        assert r.status_code == 200, r.text
        j = r.json()
        print("RIGENERA", j)
        ST["r1"] = j
        assert j["acquisti"] == 4, j  # A, B, C, P (E closed year, D contestata, F already)
        assert j["vendite"] >= 1 and j["banca"] >= 1, j
        assert any(f"{Y-2}-06-01" in e for e in j["errori"]), j["errori"]

    def test_04_passive_registered(self):
        a, b, c, p = (get(ST[k]) for k in "ABCP")
        for d in (a, b, c, p):
            assert d["stato_reg"] == "registrata"
            assert d["data_registrazione"] == d["data"]
            assert d["anno_registrazione"] == int(d["data"][:4])
            assert d.get("registrata_auto") is True
        assert [a["protocollo"], b["protocollo"], c["protocollo"]] == [2, 3, 4]
        assert p["protocollo"] == 1 and p["anno_registrazione"] == Y - 1
        rc = c["reverse_charge"]
        assert rc and rc[0]["natura"] == "N6.3" and rc[0]["aliquota"] == 10 and rc[0]["imposta"] == 100.0, rc
        assert not a.get("reverse_charge")

    def test_05_untouched(self):
        d, e, f = get(ST["D"]), get(ST["E"]), get(ST["F"])
        assert d["stato_reg"] == "contestata" and not d.get("protocollo")
        assert e["stato_reg"] == "da_registrare" and not e.get("protocollo")
        assert f["protocollo"] == 1 and f["data_registrazione"] == f"{Y}-02-05" and not f.get("registrata_auto")

    def test_06_entries(self):
        p = ST["p"]
        eb = entries(ST["B"])
        assert len(eb) == 1
        assert eb[0]["data"] == f"{Y}-04-01"
        assert side(eb[0], p["ritenute_operate"]) == (0, 200.0)
        assert side(eb[0], p["fornitori"]) == (0, 1020.0)
        ec = entries(ST["C"])
        assert len(ec) == 1 and ec[0]["data"] == f"{Y}-05-01"
        assert side(ec[0], p["iva_vendite"]) == (0, 100.0)
        assert side(ec[0], p["iva_acquisti"])[0] == 100.0
        for k in "AP":
            assert len(entries(ST[k])) == 1
        assert len(entries(ST["I"], "vendita")) == 1
        assert len(entries(ST["T"], "banca")) == 1

    def test_07_lists_and_dashboard(self):
        s = sess()
        das = s.get(f"{API}/passive", params={"stato": "da_registrare"}).json()
        items = das if isinstance(das, list) else das.get("items", das.get("rows", []))
        assert {x["id"] for x in items} == {ST["E"]}, [x.get("numero") for x in items]
        dash = s.get(f"{API}/dashboard/riquadri").json()
        print("DASH passive_da_registrare", json.dumps(dash)[:300])
        reg = s.get(f"{API}/registro-iva-acquisti", params={"anno": Y}).json()
        ids = [x["id"] for x in reg["rows"]]
        assert {ST["F"], ST["A"], ST["B"], ST["C"]} <= set(ids)
        crow = next(x for x in reg["rows"] if x["id"] == ST["C"])
        print("REG C row", crow)
        reg2 = s.get(f"{API}/registro-iva-acquisti", params={"anno": Y - 1}).json()
        assert ST["P"] in [x["id"] for x in reg2["rows"]]

    def test_08_idempotent(self):
        r = sess().post(f"{API}/contabilita/rigenera", json={"ricrea": False})
        assert r.status_code == 200
        j = r.json()
        assert j["acquisti"] == 0 and j["vendite"] == 0 and j["banca"] == 0, j
        assert [get(ST[k])["protocollo"] for k in "FABC"] == [1, 2, 3, 4]
        for k in "ABCPF":
            assert len(entries(ST[k])) == 1, k
        assert len(entries(ST["I"], "vendita")) == 1 and len(entries(ST["T"], "banca")) == 1

    def test_09_reopen_closed_year(self):
        mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}}, {{$set:{{coge_chiusi:[]}}}})')
        j = sess().post(f"{API}/contabilita/rigenera", json={"ricrea": False}).json()
        assert j["acquisti"] == 1, j
        e = get(ST["E"])
        assert e["stato_reg"] == "registrata" and e["protocollo"] == 1 and e["anno_registrazione"] == Y - 2

# Iteration 86: automatic intra-UE/extra-UE VAT integration + TD17 proposal at passive registration,
# 'mancano' list on suppliers to review and bulk confirmation POST /parties/da-verificare/conferma.
# Run: pytest tests/test_iteration86_iva_intra_conferma.py -v -n 0   (T86_KEEP=1 keeps the company for UI tests)
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
TOK, UID = "test_session_t86_admin", "test-user-t86-admin"
PIVA = "86" + RUN + "861"
TODAY = date.today().isoformat()
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
    mongo(f'db.companies.find({{denominazione:/^TEST_T86/}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def piva():
    return "".join(str(random.randint(0, 9)) for _ in range(11))


def xml(ced_id, paese="IT", naz=None, den="TEST_T86 Fornitore", nome=None, cognome=None, riep=((22.0, None, 1000.0, 220.0),), cf=None, rit=None):
    naz = naz or paese
    numero = f"T86-{uuid.uuid4().hex[:6]}"
    ana = f"<Nome>{nome}</Nome><Cognome>{cognome}</Cognome>" if nome else f"<Denominazione>{den}</Denominazione>"
    tot = round(sum(r[2] + r[3] for r in riep), 2)
    cfx = f"<CodiceFiscale>{cf}</CodiceFiscale>" if cf else ""
    dr = (f"<DatiRitenuta><TipoRitenuta>RT01</TipoRitenuta><ImportoRitenuta>{rit:.2f}</ImportoRitenuta><AliquotaRitenuta>20.00</AliquotaRitenuta>"
          f"<CausalePagamento>A</CausalePagamento></DatiRitenuta>") if rit else ""
    rs = "".join(f"<DatiRiepilogo><AliquotaIVA>{a:.2f}</AliquotaIVA>{f'<Natura>{n}</Natura>' if n else ''}<ImponibileImporto>{i:.2f}</ImponibileImporto>"
                 f"<Imposta>{v:.2f}</Imposta><EsigibilitaIVA>I</EsigibilitaIVA></DatiRiepilogo>" for a, n, i, v in riep)
    ls = "".join(f"<DettaglioLinee><NumeroLinea>{k + 1}</NumeroLinea><Descrizione>Servizio</Descrizione><Quantita>1.00</Quantita><PrezzoUnitario>{i:.2f}</PrezzoUnitario>"
                 f"<PrezzoTotale>{i:.2f}</PrezzoTotale><AliquotaIVA>{a:.2f}</AliquotaIVA>{f'<Natura>{n}</Natura>' if n else ''}</DettaglioLinee>" for k, (a, n, i, v) in enumerate(riep))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica versione="FPR12" xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
<FatturaElettronicaHeader>
<DatiTrasmissione><IdTrasmittente><IdPaese>IT</IdPaese><IdCodice>{PIVA}</IdCodice></IdTrasmittente><ProgressivoInvio>T86{random.randint(100, 999)}</ProgressivoInvio>
<FormatoTrasmissione>FPR12</FormatoTrasmissione><CodiceDestinatario>0000000</CodiceDestinatario></DatiTrasmissione>
<CedentePrestatore><DatiAnagrafici><IdFiscaleIVA><IdPaese>{paese}</IdPaese><IdCodice>{ced_id}</IdCodice></IdFiscaleIVA>{cfx}
<Anagrafica>{ana}</Anagrafica><RegimeFiscale>{'RF01' if paese == 'IT' else 'RF18'}</RegimeFiscale></DatiAnagrafici>
<Sede><Indirizzo>Via Verdi 1</Indirizzo><CAP>{'20100' if naz == 'IT' else '00000'}</CAP><Comune>Citta</Comune><Nazione>{naz}</Nazione></Sede></CedentePrestatore>
<CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>{PIVA}</IdCodice></IdFiscaleIVA><CodiceFiscale>{PIVA}</CodiceFiscale>
<Anagrafica><Denominazione>TEST_T86 Srl</Denominazione></Anagrafica></DatiAnagrafici>
<Sede><Indirizzo>Via Roma 1</Indirizzo><CAP>00100</CAP><Comune>Roma</Comune><Provincia>RM</Provincia><Nazione>IT</Nazione></Sede></CessionarioCommittente>
</FatturaElettronicaHeader>
<FatturaElettronicaBody>
<DatiGenerali><DatiGeneraliDocumento><TipoDocumento>TD01</TipoDocumento><Divisa>EUR</Divisa><Data>2026-01-10</Data><Numero>{numero}</Numero>{dr}
<ImportoTotaleDocumento>{tot:.2f}</ImportoTotaleDocumento></DatiGeneraliDocumento></DatiGenerali>
<DatiBeniServizi>{ls}{rs}</DatiBeniServizi>
</FatturaElettronicaBody>
</p:FatturaElettronica>""".encode()


def upload(x):
    r = sess().post(f"{API}/passive/upload", files=[("files", (f"t86_{uuid.uuid4().hex[:6]}.xml", x, "application/octet-stream"))])
    assert r.status_code == 200, r.text
    j = r.json()[0]
    assert j["ok"], j
    return j["documenti"][0]


def getdoc(i):
    return sess().get(f"{API}/passive/{i}").json()


def body_for(doc, **kw):
    b = {"data_registrazione": TODAY, "numero": doc["numero"], "data": doc["data"], "aliquota_rc": 22, "detraibilita_iva": 100,
         "riepilogo": [{"aliquota": r["aliquota"], "natura": r.get("natura"), "imponibile": r["imponibile"], "imposta": r["imposta"], "conto": ""} for r in doc["riepilogo"]]}
    return b | kw


def prev(i, **kw):
    r = sess().post(f"{API}/passive/{i}/registrazione/anteprima", json=body_for(getdoc(i), **kw))
    assert r.status_code == 200, r.text
    return r.json()


def elenco():
    return {r["id"]: r for r in sess().get(f"{API}/parties/da-verificare/elenco").json()}


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t86.admin@example.com", name:"TEST_T86 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": f"TEST_T86 IvaUE {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    sess().put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                            "corrispettivi": True, "contabilita": True})
    sess().get(f"{API}/contabilita/conti")
    ST["params"] = sess().get(f"{API}/contabilita/parametri").json()["parametri"]
    yield
    if not os.environ.get("T86_KEEP"):
        clean()


# --- anteprima: reverse charge + autofattura proposal
def test_ue_supplier_td17_proposal():
    doc = upload(xml(piva(), paese="DE", den="TEST_T86 GmbH", riep=((0.0, "N2.1", 1000.0, 0.0),)))
    ST["de_doc"] = doc["id"]
    j = prev(doc["id"])
    assert j["estero"] is True
    assert j["autofattura_proposta"] == "TD17"
    assert [(x["imponibile"], x["aliquota"], x["imposta"]) for x in j["reverse_charge"]] == [(1000.0, 22.0, 220.0)]
    j10 = prev(doc["id"], aliquota_rc=10)
    assert j10["reverse_charge"][0]["imposta"] == 100.0
    assert getdoc(doc["id"])["stato_reg"] == "da_registrare"


def test_ue_supplier_with_foreign_vat_no_rc():
    doc = upload(xml(piva(), paese="FR", den="TEST_T86 SARL", riep=((20.0, None, 1000.0, 200.0),)))
    j = prev(doc["id"])
    assert not j["reverse_charge"] and j["autofattura_proposta"] is None


def test_extra_ue_supplier_td17():
    doc = upload(xml(piva(), paese="US", den="TEST_T86 Inc", riep=((0.0, "N2.2", 500.0, 0.0),)))
    j = prev(doc["id"])
    assert j["autofattura_proposta"] == "TD17" and j["reverse_charge"][0]["imposta"] == 110.0


def test_nazione_it_but_paese_iva_de_is_estero():
    doc = upload(xml(piva(), paese="DE", naz="IT", den="TEST_T86 Mixed GmbH", riep=((0.0, "N2.1", 1000.0, 0.0),)))
    d = getdoc(doc["id"])
    assert (d["fornitore"].get("paese_iva") or "").upper() == "DE", d["fornitore"]
    ST["mix_doc"] = doc["id"]
    j = prev(doc["id"])
    assert j["estero"] is True and j["autofattura_proposta"] == "TD17" and j["reverse_charge"]


def test_gestione_intra_ue_on_italian_snapshot():
    # supplier snapshot fully IT but party gestione_iva set to intra_ue -> estero
    doc = upload(xml(piva(), den="TEST_T86 Gest Intra Srl", riep=((0.0, "N2.1", 300.0, 0.0),), cf="01234567890"))
    pid = getdoc(doc["id"])["party_id"]
    r = sess().post(f"{API}/parties/{pid}/revisione", json={"gestione_iva": "intra_ue"})
    assert r.status_code == 200, r.text
    j = prev(doc["id"])
    assert j["estero"] is True and j["autofattura_proposta"] == "TD17" and j["reverse_charge"][0]["imposta"] == 66.0


def test_italian_n6_td16():
    doc = upload(xml(piva(), den="TEST_T86 Edile Srl", riep=((0.0, "N6.3", 1000.0, 0.0),)))
    j = prev(doc["id"])
    assert j["estero"] is False and j["autofattura_proposta"] == "TD16" and j["reverse_charge"][0]["natura"] == "N6.3"


def test_italian_ordinary_no_proposal():
    doc = upload(xml(piva(), den="TEST_T86 Ordinario Srl"))
    j = prev(doc["id"])
    assert not j["reverse_charge"] and j["autofattura_proposta"] is None and j["estero"] is False
    r = sess().post(f"{API}/passive/{doc['id']}/registrazione", json=body_for(getdoc(doc["id"]), autofattura="TD17"))
    assert r.status_code == 422


def test_register_td17_creates_autofattura_and_entry():
    i = ST["de_doc"]
    r = sess().post(f"{API}/passive/{i}/registrazione", json=body_for(getdoc(i), autofattura="TD17"))
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["stato_reg"] == "registrata" and j["autofattura_id"]
    inv = mongo(f'print(JSON.stringify(db.invoices.findOne({{id:"{j["autofattura_id"]}"}},{{_id:0}})))')
    inv = json.loads(inv)
    assert inv["tipo_documento"] == "TD17" and inv["status"] == "bozza" and inv["autofattura"] is True
    assert inv["cedente"]["nazione"] == "DE"
    assert round(inv["imponibile"], 2) == 1000.0 and round(inv["iva"], 2) == 220.0
    q = {"company_id": ST["cid"], "origine": "acquisto", "ref_id": i}
    es = json.loads(mongo(f'print(JSON.stringify(db.coa_entries.find({json.dumps(q)},{{_id:0}}).toArray()))') or "[]")
    assert len(es) == 1
    p = ST["params"]
    rows = es[0]["righe"]
    assert any(x["conto"] == p["iva_acquisti"] and (x.get("dare") or 0) == 220 for x in rows), rows
    assert any(x["conto"] == p["iva_vendite"] and (x.get("avere") or 0) == 220 for x in rows), rows
    assert round(sum(x.get("dare") or 0 for x in rows), 2) == round(sum(x.get("avere") or 0 for x in rows), 2)


def test_register_mixed_td17_cedente_country():
    # snapshot nazione IT, paese_iva DE: autofattura cedente must be foreign (DE)
    i = ST["mix_doc"]
    r = sess().post(f"{API}/passive/{i}/registrazione", json=body_for(getdoc(i), autofattura="TD17"))
    assert r.status_code == 200, r.text
    inv = json.loads(mongo(f'print(JSON.stringify(db.invoices.findOne({{id:"{r.json()["autofattura_id"]}"}},{{_id:0}})))'))
    ST["mix_ced"] = inv["cedente"]
    assert inv["cedente"]["nazione"] == "DE", inv["cedente"]


# --- mancano + bulk confirmation
def test_mancano_and_bulk_conferma():
    ok = upload(xml(piva(), den="TEST_T86 Completo Srl", cf="09876543210"))
    nocf = upload(xml(piva(), den="TEST_T86 SenzaCF Srl"))
    est = upload(xml(piva(), paese="DE", den="TEST_T86 Estero GmbH", riep=((0.0, "N2.1", 100.0, 0.0),)))
    fis = upload(xml(piva(), nome="Luca", cognome="TEST_T86 Bianchi", cf="BNCLCU80A01H501X", rit=200.0))
    ids = {k: getdoc(v["id"])["party_id"] for k, v in {"ok": ok, "nocf": nocf, "est": est, "fis": fis}.items()}
    ST["ids"] = ids
    # make 'fis' miss its codice tributo and 'est' miss its address (records created by this test)
    mongo(f'db.parties.updateOne({{id:"{ids["fis"]}"}},{{$set:{{ritenuta_codice_tributo:""}}}}); db.parties.updateOne({{id:"{ids["est"]}"}},{{$set:{{comune:""}}}})')
    e = elenco()
    print({k: (e[v].get("codice_fiscale"), e[v]["mancano"]) for k, v in ids.items()})
    assert e[ids["ok"]]["mancano"] == []
    assert "indirizzo" in e[ids["est"]]["mancano"] and "codice fiscale" not in e[ids["est"]]["mancano"]
    assert "codice tributo" in e[ids["fis"]]["mancano"]
    assert all(isinstance(r["mancano"], list) for r in e.values())
    complete = [k for k, r in e.items() if not r["mancano"]]
    r = sess().post(f"{API}/parties/da-verificare/conferma")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["confermati"] == len(complete) and j["restanti"] == len(e) - len(complete)
    e2 = elenco()
    assert ids["ok"] not in e2 and ids["est"] in e2 and ids["fis"] in e2
    assert all(r["mancano"] for r in e2.values())
    j2 = sess().post(f"{API}/parties/da-verificare/conferma").json()
    assert j2 == {"confermati": 0, "restanti": len(e2)}


def test_mancano_cf_for_italian_without_cf():
    e = elenco()
    pid = ST["ids"]["nocf"]
    if pid in e:
        assert "codice fiscale" in e[pid]["mancano"]
    else:
        # auto-detection filled CF from P.IVA; verify via parties list
        p = next(x for x in sess().get(f"{API}/parties", params={"tipo": "fornitore"}).json() if x["id"] == pid)
        assert p.get("codice_fiscale"), p


def test_mancano_conto_costo_when_contropartita_fornitore():
    s = sess()
    p = s.get(f"{API}/contabilita/parametri").json()["parametri"]
    body = {"conti": {k: v for k, v in p.items() if isinstance(v, str)}, "contropartita_vendite": p.get("contropartita_vendite", "unica"),
            "contropartita_acquisti": "fornitore", "aliquota_rc": p.get("aliquota_rc", 22), "categorie": p.get("categorie") or {}}
    assert s.put(f"{API}/contabilita/parametri", json=body).status_code == 200
    try:
        pid = ST["ids"]["est"]
        mongo(f'db.parties.updateOne({{id:"{pid}"}},{{$set:{{conto_costo:""}}}})')
        assert "conto di costo" in elenco()[pid]["mancano"]
    finally:
        body["contropartita_acquisti"] = "unica"
        s.put(f"{API}/contabilita/parametri", json=body)


def test_conferma_requires_auth():
    r = requests.post(f"{API}/parties/da-verificare/conferma")
    assert r.status_code in (401, 403)

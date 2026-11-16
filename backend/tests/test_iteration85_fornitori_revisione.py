# Iteration 85: nuovi fornitori da fatture passive -> auto-detect persona/ritenuta/cassa/gestione IVA/pagamento/conto costo,
# elenco da-verificare and POST /parties/{pid}/revisione (validation, apply ritenuta + re-generate coge entries).
# Run: pytest tests/test_iteration85_fornitori_revisione.py -v -n 0
import json
import os
import random
import sys
import uuid

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

RUN = str(random.randint(100000, 999999))
TOK, UID = "test_session_t85_admin", "test-user-t85-admin"
PIVA = "85" + RUN + "851"
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
    mongo(f'db.companies.find({{denominazione:/^TEST_T85/}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def piva():
    return "".join(str(random.randint(0, 9)) for _ in range(11))


def xml(ced_id, numero=None, paese="IT", den=None, nome=None, cognome=None, riep=((22.0, None, 1000.0, 220.0),), esig="I", rit=None,
        cassa=None, rate=None, data="2026-01-15", tipo="TD01"):
    numero = numero or f"T85-{uuid.uuid4().hex[:6]}"
    ana = f"<Denominazione>{den}</Denominazione>" if den else f"<Nome>{nome}</Nome><Cognome>{cognome}</Cognome>"
    imp = sum(r[2] for r in riep)
    iva = sum(r[3] for r in riep)
    tot = round(imp + iva, 2)
    dr = (f"<DatiRitenuta><TipoRitenuta>{rit[0]}</TipoRitenuta><ImportoRitenuta>{rit[1]:.2f}</ImportoRitenuta><AliquotaRitenuta>{rit[2]:.2f}</AliquotaRitenuta>"
          f"<CausalePagamento>{rit[3]}</CausalePagamento></DatiRitenuta>") if rit else ""
    cp = (f"<DatiCassaPrevidenziale><TipoCassa>{cassa[0]}</TipoCassa><AlCassa>{cassa[1]:.2f}</AlCassa><ImportoContributoCassa>{cassa[2]:.2f}</ImportoContributoCassa>"
          f"<ImponibileCassa>1000.00</ImponibileCassa><AliquotaIVA>22.00</AliquotaIVA>{'<Ritenuta>SI</Ritenuta>' if cassa[3] else ''}</DatiCassaPrevidenziale>") if cassa else ""
    rs = "".join(f"<DatiRiepilogo><AliquotaIVA>{a:.2f}</AliquotaIVA>{f'<Natura>{n}</Natura>' if n else ''}<ImponibileImporto>{i:.2f}</ImponibileImporto>"
                 f"<Imposta>{v:.2f}</Imposta><EsigibilitaIVA>{esig}</EsigibilitaIVA></DatiRiepilogo>" for a, n, i, v in riep)
    ls = "".join(f"<DettaglioLinee><NumeroLinea>{k + 1}</NumeroLinea><Descrizione>Servizio</Descrizione><Quantita>1.00</Quantita><PrezzoUnitario>{i:.2f}</PrezzoUnitario>"
                 f"<PrezzoTotale>{i:.2f}</PrezzoTotale><AliquotaIVA>{a:.2f}</AliquotaIVA>{f'<Natura>{n}</Natura>' if n else ''}</DettaglioLinee>" for k, (a, n, i, v) in enumerate(riep))
    pag = ""
    if rate:
        det = "".join(f"<DettaglioPagamento><ModalitaPagamento>{m}</ModalitaPagamento><DataScadenzaPagamento>{s}</DataScadenzaPagamento>"
                      f"<ImportoPagamento>{round(tot / len(rate), 2):.2f}</ImportoPagamento></DettaglioPagamento>" for m, s in rate)
        pag = f"<DatiPagamento><CondizioniPagamento>{'TP01' if len(rate) > 1 else 'TP02'}</CondizioniPagamento>{det}</DatiPagamento>"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica versione="FPR12" xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
<FatturaElettronicaHeader>
<DatiTrasmissione><IdTrasmittente><IdPaese>IT</IdPaese><IdCodice>{PIVA}</IdCodice></IdTrasmittente><ProgressivoInvio>T85{random.randint(100, 999)}</ProgressivoInvio>
<FormatoTrasmissione>FPR12</FormatoTrasmissione><CodiceDestinatario>0000000</CodiceDestinatario></DatiTrasmissione>
<CedentePrestatore><DatiAnagrafici><IdFiscaleIVA><IdPaese>{paese}</IdPaese><IdCodice>{ced_id}</IdCodice></IdFiscaleIVA>
<Anagrafica>{ana}</Anagrafica><RegimeFiscale>{'RF01' if paese == 'IT' else 'RF18'}</RegimeFiscale></DatiAnagrafici>
<Sede><Indirizzo>Via Verdi 1</Indirizzo><CAP>{'20100' if paese == 'IT' else '00000'}</CAP><Comune>Citta</Comune><Nazione>{paese}</Nazione></Sede></CedentePrestatore>
<CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>{PIVA}</IdCodice></IdFiscaleIVA><CodiceFiscale>{PIVA}</CodiceFiscale>
<Anagrafica><Denominazione>TEST_T85 Srl</Denominazione></Anagrafica></DatiAnagrafici>
<Sede><Indirizzo>Via Roma 1</Indirizzo><CAP>00100</CAP><Comune>Roma</Comune><Provincia>RM</Provincia><Nazione>IT</Nazione></Sede></CessionarioCommittente>
</FatturaElettronicaHeader>
<FatturaElettronicaBody>
<DatiGenerali><DatiGeneraliDocumento><TipoDocumento>{tipo}</TipoDocumento><Divisa>EUR</Divisa><Data>{data}</Data><Numero>{numero}</Numero>{dr}{cp}
<ImportoTotaleDocumento>{tot:.2f}</ImportoTotaleDocumento></DatiGeneraliDocumento></DatiGenerali>
<DatiBeniServizi>{ls}{rs}</DatiBeniServizi>{pag}
</FatturaElettronicaBody>
</p:FatturaElettronica>""".encode()


def upload(x):
    r = sess().post(f"{API}/passive/upload", files=[("files", (f"t85_{uuid.uuid4().hex[:6]}.xml", x, "application/octet-stream"))])
    assert r.status_code == 200, r.text
    j = r.json()[0]
    assert j["ok"], j
    return j["documenti"][0]


def gp(pid):
    return next(x for x in sess().get(f"{API}/parties", params={"tipo": "fornitore"}).json() if x["id"] == pid)


def party_of(doc_id):
    d = sess().get(f"{API}/passive/{doc_id}").json()
    return d, gp(d["party_id"])


def entries(ref):
    q = {"company_id": ST["cid"], "origine": "acquisto", "ref_id": ref}
    return json.loads(mongo(f'print(JSON.stringify(db.coa_entries.find({json.dumps(q)},{{_id:0}}).toArray()))') or "[]")


def set_contropartita(v):
    s = sess()
    p = s.get(f"{API}/contabilita/parametri").json()["parametri"]
    body = {"conti": {k: v2 for k, v2 in p.items() if isinstance(v2, str)}, "contropartita_vendite": p.get("contropartita_vendite", "unica"),
            "contropartita_acquisti": v, "aliquota_rc": p.get("aliquota_rc", 22), "categorie": p.get("categorie") or {}}
    r = s.put(f"{API}/contabilita/parametri", json=body)
    assert r.status_code == 200, r.text
    return r.json()["parametri"]


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t85.admin@example.com", name:"TEST_T85 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": f"TEST_T85 Fornitori {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    sess().put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                            "corrispettivi": True, "contabilita": True})
    sess().get(f"{API}/contabilita/conti")
    ST["params"] = sess().get(f"{API}/contabilita/parametri").json()["parametri"]
    yield
    if not os.environ.get("T85_KEEP"):
        clean()


# --- auto-detect on import
def test_fisica_ritenuta_cassa_pagamento_unica():
    doc = upload(xml(piva(), nome="Mario", cognome="TEST_T85 Rossi", riep=((22.0, None, 1040.0, 228.8),), rit=("RT01", 200.0, 20.0, "A"),
                     cassa=("TC22", 4.0, 40.0, False), rate=(("MP05", "2026-02-28"), ("MP05", "2026-03-31"))))
    assert doc["nuovo_fornitore_id"]
    d, p = party_of(doc["id"])
    ST["fisica_pid"] = p["id"]
    assert p["da_verificare"] is True
    assert p["persona"] == "fisica" and p["nome"] == "Mario" and p["cognome"] == "TEST_T85 Rossi"
    assert p["soggetto_ritenuta"] is True and p["ritenuta_tipo"] == "RT01" and p["ritenuta_aliquota"] == 20
    assert p["ritenuta_causale"] == "A" and p["ritenuta_codice_tributo"] == "1040" and p["ritenuta_base"] == 100
    assert p["cassa_tipo"] == "TC22" and p["cassa_aliquota"] == 4 and p["cassa_ritenuta"] is False
    assert p["pagamento_modalita"] == "MP05" and p["pagamento_rate"] == 2 and p["pagamento_giorni"] == 30 and p["pagamento_fine_mese"] is True
    assert p.get("gestione_iva", "") == ""
    assert not p.get("conto_costo")
    assert d["ritenuta_importo"] == 200 and d["netto"] == 1068.8


def test_causale_q_and_base_50_and_giuridica():
    doc = upload(xml(piva(), den="TEST_T85 Agente Srl", rit=("RT01", 100.0, 20.0, "Q"), rate=(("MP12", "2026-02-14"),)))
    _, p = party_of(doc["id"])
    assert p["persona"] == "giuridica"
    assert p["ritenuta_codice_tributo"] == "1038" and p["ritenuta_causale"] == "Q"
    assert p["ritenuta_base"] == 50
    assert p["pagamento_modalita"] == "MP12" and p["pagamento_rate"] == 1 and p["pagamento_giorni"] == 30 and p["pagamento_fine_mese"] is False


@pytest.mark.parametrize("paese,riep,esig,exp,nat", [
    ("DE", ((0.0, "N2.1", 1000.0, 0.0),), "I", "intra_ue", "N2.1"),
    ("FR", ((20.0, None, 1000.0, 200.0),), "I", "intra_ue", ""),
    ("US", ((0.0, "N2.1", 500.0, 0.0),), "I", "extra_ue", "N2.1"),
    ("CH", ((22.0, None, 500.0, 110.0),), "I", "extra_ue", ""),
    ("IT", ((0.0, "N6.3", 1000.0, 0.0),), "I", "reverse_charge", "N6.3"),
    ("IT", ((22.0, None, 1000.0, 220.0),), "S", "split_payment", ""),
    ("IT", ((22.0, None, 1000.0, 220.0), (0.0, "N4", 100.0, 0.0)), "I", "", ""),
])
def test_gestione_iva_detect(paese, riep, esig, exp, nat):
    doc = upload(xml(piva(), paese=paese, den=f"TEST_T85 {paese} {exp} Ltd", riep=riep, esig=esig))
    _, p = party_of(doc["id"])
    assert p.get("gestione_iva", "") == exp
    assert (p.get("natura_default") or "") == nat
    assert p.get("soggetto_ritenuta") in (None, False)


def test_contropartita_fornitore_proposes_costi():
    par = set_contropartita("fornitore")
    doc = upload(xml(piva(), den="TEST_T85 ContoCosto Srl"))
    _, p = party_of(doc["id"])
    assert p["conto_costo"] == par["costi"] and par["costi"]
    ST["cc_pid"], ST["cc_doc"] = p["id"], doc["id"]


def test_existing_supplier_not_modified():
    pv = piva()
    r = sess().post(f"{API}/parties", json={"tipo": "fornitore", "denominazione": "TEST_T85 Esistente Srl", "partita_iva": pv, "codice_fiscale": pv,
                                           "codice_destinatario": "ABC1234", "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"})
    assert r.status_code == 200, r.text
    before = gp(r.json()['id'])
    doc = upload(xml(pv, den="TEST_T85 Altro nome", rit=("RT01", 200.0, 20.0, "A"), rate=(("MP05", "2026-02-14"),)))
    assert doc["nuovo_fornitore_id"] is None
    after = gp(before['id'])
    assert after == before


# --- elenco
def test_elenco_da_verificare():
    rows = sess().get(f"{API}/parties/da-verificare/elenco").json()
    ids = {r["id"]: r for r in rows}
    assert ST["fisica_pid"] in ids and all("Esistente" not in r["denominazione"] for r in rows)
    r = ids[ST["fisica_pid"]]
    assert r["fatture"] == 1 and r["totale"] == 1268.8 and r["da_registrare"] == 1 and r["con_ritenuta"] == 1 and r["iva_rilevata"] == ["22%"]
    assert r["persona"] == "fisica" and r["soggetto_ritenuta"] is True


# --- revisione
def rev(pid, **kw):
    return sess().post(f"{API}/parties/{pid}/revisione", json=kw)


def test_revisione_validation():
    pid = ST["fisica_pid"]
    assert rev(pid, persona="fisica", nome="", cognome="X").status_code == 422
    assert rev(pid, persona="fisica", nome="A", cognome=" ").status_code == 422
    assert rev(pid, conto_costo="99.99.99").status_code == 400
    assert rev(pid, soggetto_ritenuta=True, ritenuta_codice_tributo="ZZZZ").status_code == 422
    assert rev(pid, gestione_iva="boh").status_code == 422
    assert rev(str(uuid.uuid4())).status_code == 404
    assert gp(pid)["da_verificare"] is True


def test_revisione_fisica_sets_denominazione():
    pid = ST["fisica_pid"]
    r = rev(pid, persona="fisica", nome="Mario", cognome="TEST_T85 Rossi", soggetto_ritenuta=True, ritenuta_tipo="RT01", ritenuta_aliquota=20,
            ritenuta_base=100, ritenuta_causale="A", ritenuta_codice_tributo="1040", cassa_tipo="TC22", cassa_aliquota=4, pagamento_modalita="MP05",
            pagamento_rate=2, pagamento_giorni=30, pagamento_fine_mese=True)
    assert r.status_code == 200, r.text
    p = gp(pid)
    assert p["da_verificare"] is False and p["denominazione"] == "TEST_T85 Rossi Mario"
    assert pid not in {x["id"] for x in sess().get(f"{API}/parties/da-verificare/elenco").json()}


def test_revisione_applies_ritenuta_and_regenerates_entry():
    doc = upload(xml(piva(), den="TEST_T85 Studio Senza Rit", rate=(("MP05", "2026-02-14"),)))
    d0, p = party_of(doc["id"])
    assert d0["ritenuta_importo"] == 0 and d0["netto"] == 1220
    e0 = entries(doc["id"])
    r = rev(p["id"], soggetto_ritenuta=True, ritenuta_tipo="RT01", ritenuta_aliquota=20, ritenuta_base=100, ritenuta_causale="A", ritenuta_codice_tributo="1040")
    assert r.status_code == 200, r.text
    assert r.json()["fatture_aggiornate"] == 1
    d1 = sess().get(f"{API}/passive/{doc['id']}").json()
    assert d1["ritenuta_importo"] == 200 and d1["netto"] == 1020
    assert sum(x["importo"] for x in d1["rate"]) == 1020 or sum(x["importo"] for x in (d1.get("rate_mod") or d1["rate"])) == 1020
    e1 = entries(doc["id"])
    assert len(e1) == 1
    if e0:
        assert e1[0]["id"] != e0[0]["id"]
    avere = sorted(round(x.get("avere") or 0, 2) for x in e1[0]["righe"] if x.get("avere"))
    assert 200 in avere or 1020 in avere, e1[0]["righe"]


def test_revisione_conto_costo_regenerates_entry():
    pid, did = ST["cc_pid"], ST["cc_doc"]
    alt = mongo(f'print((db.coa_accounts.findOne({{company_id:"{ST["cid"]}", livello:3, codice:{{$ne:"{ST["params"]["costi"]}", $regex:"^(6|7|8|C)"}}}})||{{}}).codice)')
    if not alt or alt == "undefined":
        alt = mongo(f'print(db.coa_accounts.find({{company_id:"{ST["cid"]}", livello:3, codice:{{$ne:"{ST["params"]["costi"]}"}}}}).sort({{codice:-1}}).limit(1).toArray()[0].codice)')
    r = rev(pid, conto_costo=alt)
    assert r.status_code == 200, r.text
    assert r.json()["fatture_aggiornate"] == 1
    assert gp(pid)["conto_costo"] == alt
    e = entries(did)
    assert len(e) == 1 and any(x["conto"] == alt and (x.get("dare") or 0) == 1000 for x in e[0]["righe"]), e[0]["righe"]
    set_contropartita("unica")

# Iteration 113: professionisti in Registrazione veloce (cassa, bollo art.15 N1, default ritenuta via base_ritenuta) and ritenuta_proposta in passive anteprima.
# Run: pytest tests/test_iteration113_professionisti_regv.py -v -n 0   (T113_KEEP=1 keeps data for UI tests)
import json
import os
import random
import sys
import uuid

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

RUN = os.environ.get("T113_RUN", str(random.randint(100000, 999999)))
TOK, UID = f"test_session_t113_admin_{RUN}", f"test-user-t113-admin-{RUN}"
TOK2, UID2 = f"test_session_t113_op_{RUN}", f"test-user-t113-op-{RUN}"
PIVA = "11" + RUN + "113"
ST = {}
DATA = "2026-11-02"
COLLS = ["invoices", "passive_invoices", "parties", "articles", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "audit_log", "partite_aperte", "f24_versamenti", "pag_distinte", "ratei_risconti", "counters"]


def sess(tok=TOK):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "X-Requested-With": "invoix"})
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{partita_iva:"{PIVA}"}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:["{UID}","{UID2}"]}}}}); db.user_sessions.deleteMany({{user_id:{{$in:["{UID}","{UID2}"]}}}});')


def piva():
    return "".join(str(random.randint(0, 9)) for _ in range(11))


def xml(ced_id, riep, rit=None, cassa=None, numero=None, data=DATA, den="TEST_T113 Prof"):
    numero = numero or f"T113-{uuid.uuid4().hex[:6]}"
    tot = round(sum(r[2] + r[3] for r in riep), 2)
    dr = (f"<DatiRitenuta><TipoRitenuta>{rit[0]}</TipoRitenuta><ImportoRitenuta>{rit[1]:.2f}</ImportoRitenuta><AliquotaRitenuta>{rit[2]:.2f}</AliquotaRitenuta>"
          f"<CausalePagamento>A</CausalePagamento></DatiRitenuta>") if rit else ""
    cp = (f"<DatiCassaPrevidenziale><TipoCassa>{cassa[0]}</TipoCassa><AlCassa>{cassa[1]:.2f}</AlCassa><ImportoContributoCassa>{cassa[2]:.2f}</ImportoContributoCassa>"
          f"<ImponibileCassa>1000.00</ImponibileCassa><AliquotaIVA>22.00</AliquotaIVA></DatiCassaPrevidenziale>") if cassa else ""
    rs = "".join(f"<DatiRiepilogo><AliquotaIVA>{a:.2f}</AliquotaIVA>{f'<Natura>{n}</Natura>' if n else ''}<ImponibileImporto>{i:.2f}</ImponibileImporto>"
                 f"<Imposta>{v:.2f}</Imposta><EsigibilitaIVA>I</EsigibilitaIVA></DatiRiepilogo>" for a, n, i, v in riep)
    ls = "".join(f"<DettaglioLinee><NumeroLinea>{k + 1}</NumeroLinea><Descrizione>Prestazione</Descrizione><Quantita>1.00</Quantita><PrezzoUnitario>{i:.2f}</PrezzoUnitario>"
                 f"<PrezzoTotale>{i:.2f}</PrezzoTotale><AliquotaIVA>{a:.2f}</AliquotaIVA>{f'<Natura>{n}</Natura>' if n else ''}</DettaglioLinee>" for k, (a, n, i, v) in enumerate(riep))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica versione="FPR12" xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
<FatturaElettronicaHeader>
<DatiTrasmissione><IdTrasmittente><IdPaese>IT</IdPaese><IdCodice>{PIVA}</IdCodice></IdTrasmittente><ProgressivoInvio>T{random.randint(1000, 9999)}</ProgressivoInvio>
<FormatoTrasmissione>FPR12</FormatoTrasmissione><CodiceDestinatario>0000000</CodiceDestinatario></DatiTrasmissione>
<CedentePrestatore><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>{ced_id}</IdCodice></IdFiscaleIVA>
<Anagrafica><Denominazione>{den}</Denominazione></Anagrafica><RegimeFiscale>RF01</RegimeFiscale></DatiAnagrafici>
<Sede><Indirizzo>Via Verdi 1</Indirizzo><CAP>20100</CAP><Comune>Milano</Comune><Nazione>IT</Nazione></Sede></CedentePrestatore>
<CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>{PIVA}</IdCodice></IdFiscaleIVA><CodiceFiscale>{PIVA}</CodiceFiscale>
<Anagrafica><Denominazione>TEST_T113 Srl</Denominazione></Anagrafica></DatiAnagrafici>
<Sede><Indirizzo>Via Roma 1</Indirizzo><CAP>00100</CAP><Comune>Roma</Comune><Provincia>RM</Provincia><Nazione>IT</Nazione></Sede></CessionarioCommittente>
</FatturaElettronicaHeader>
<FatturaElettronicaBody>
<DatiGenerali><DatiGeneraliDocumento><TipoDocumento>TD01</TipoDocumento><Divisa>EUR</Divisa><Data>{data}</Data><Numero>{numero}</Numero>{dr}{cp}
<ImportoTotaleDocumento>{tot:.2f}</ImportoTotaleDocumento></DatiGeneraliDocumento></DatiGenerali>
<DatiBeniServizi>{ls}{rs}</DatiBeniServizi>
</FatturaElettronicaBody>
</p:FatturaElettronica>""".encode()


def upload(x):
    r = sess().post(f"{API}/passive/upload", files=[("files", (f"t113_{uuid.uuid4().hex[:6]}.xml", x, "application/octet-stream"))])
    assert r.status_code == 200, r.text
    j = r.json()[0]
    assert j["ok"], j
    return j["documenti"][0]


def mk_sup(name, pi, **kw):
    body = {"tipo": "fornitore", "denominazione": name, "partita_iva": pi, "codice_fiscale": pi, "indirizzo": "Via Verdi 1", "cap": "20100",
            "comune": "Milano", "provincia": "MI", "nazione": "IT", "soggetto_ritenuta": True, "ritenuta_tipo": "RT01", "ritenuta_aliquota": 20,
            "ritenuta_base": 100, "ritenuta_causale": "A"} | kw
    r = sess().post(f"{API}/parties", json=body)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def pdoc(i):
    r = sess().get(f"{API}/passive/{i}")
    assert r.status_code == 200, r.text
    return r.json()


def entries(ref):
    q = {"company_id": ST["cid"], "origine": "acquisto", "ref_id": ref}
    return json.loads(mongo(f'print(JSON.stringify(db.coa_entries.find({json.dumps(q)},{{_id:0}}).toArray()))') or "[]")


def amt(righe, conto, k):
    return round(sum(r.get(k) or 0 for r in righe if r["conto"] == conto), 2)


def reg_body(d):
    return {"data_registrazione": d["data"], "numero": d["numero"], "data": d["data"],
            "riepilogo": [{"aliquota": r["aliquota"], "natura": r.get("natura"), "imponibile": r["imponibile"], "imposta": r["imposta"]} for r in d["riepilogo"]]}


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t113.admin.{RUN}@example.com", name:"TEST_T113 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": "TEST_T113 Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    assert sess().put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                                   "corrispettivi": True, "contabilita": True}).status_code == 200
    sess().get(f"{API}/contabilita/conti")
    ST["p"] = sess().get(f"{API}/contabilita/parametri").json()["parametri"]
    mongo(f'db.users.insertOne({{user_id:"{UID2}", email:"test.user.t113.op.{RUN}@example.com", name:"TEST_T113 op", picture:"", role:"operatore", status:"approved", company_ids:["{ST["cid"]}"], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID2}", session_token:"{TOK2}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    yield
    if os.environ.get("T113_KEEP"):
        print("\nKEEP", RUN, ST["cid"], TOK, json.dumps({k: v for k, v in ST.items() if k != "p"}))
    else:
        clean()


def rv(pid, righe, **kw):
    body = {"tipo": "acquisto", "party_id": pid, "numero": f"T113-{uuid.uuid4().hex[:6]}", "data_documento": DATA, "data_registrazione": DATA, "scadenza": "",
            "righe": righe} | kw
    return sess().post(f"{API}/reg-veloce", json=body)


# --- Registrazione veloce: default ritenuta via base_ritenuta when ritenuta_aliquota is omitted
class TestRegVeloce:
    def test_ordinario_cassa_privata_default(self):
        ST["s_priv"] = mk_sup("TEST_T113 Ingegnere privata", piva(), cassa_tipo="TC01", cassa_aliquota=4, cassa_ritenuta=False)
        r = rv(ST["s_priv"], [{"aliquota": 22, "totale": 1268.80}])
        assert r.status_code == 200, r.text
        j = r.json()
        ST["rv_priv"] = j["id"]
        assert j["imponibile"] == 1040 and j["iva"] == 228.8 and j["ritenuta"] == 200 and j["netto"] == 1068.8, j
        x = pdoc(j["id"])
        assert x["ritenuta_imponibile"] == 1000 and x["ritenuta_aliquota"] == 20 and x["ritenuta_causale"] == "A"

    def test_ordinario_cassa_privata_explicit(self):
        r = rv(ST["s_priv"], [{"aliquota": 22, "totale": 1268.80}], ritenuta_aliquota=20, ritenuta_imponibile=1000)
        assert r.status_code == 200, r.text
        j = r.json()
        ST["rv_priv2"] = j["id"]
        assert j["ritenuta"] == 200 and j["netto"] == 1068.8

    def test_ordinario_inps_default(self):
        ST["s_inps"] = mk_sup("TEST_T113 Prof INPS", piva(), cassa_tipo="TC22", cassa_aliquota=4, cassa_ritenuta=True)
        r = rv(ST["s_inps"], [{"aliquota": 22, "totale": 1268.80}])
        assert r.status_code == 200, r.text
        j = r.json()
        ST["rv_inps"] = j["id"]
        assert j["ritenuta"] == 208 and j["netto"] == 1060.8, j

    def test_forfettario_bollo_no_ritenuta(self):
        p = ST["p"]
        ST["s_forf"] = mk_sup("TEST_T113 Forfettario", piva(), regime_percipiente="forfettario", cassa_tipo="TC22", cassa_aliquota=4, cassa_ritenuta=True)
        r = rv(ST["s_forf"], [{"aliquota": 0, "natura": "N2.2", "totale": 1040}, {"aliquota": 0, "natura": "N1", "totale": 2}])
        assert r.status_code == 200, r.text
        j = r.json()
        ST["rv_forf"] = j["id"]
        assert not j["ritenuta"] and j["totale"] == 1042 and j["netto"] == 1042, j
        e = entries(j["id"])
        assert len(e) == 1, e
        rg = e[0]["righe"]
        assert amt(rg, p["spese_anticipate"], "dare") == 2
        assert amt(rg, p["costi"], "dare") == 1040
        assert amt(rg, p["fornitori"], "avere") == 1042

    def test_ordinario_n1_bollo_excluded_from_base(self):
        r = rv(ST["s_inps"], [{"aliquota": 0, "natura": "N4", "totale": 1040}, {"aliquota": 0, "natura": "N1", "totale": 2}])
        assert r.status_code == 200, r.text
        j = r.json()
        ST["rv_esente"] = j["id"]
        assert j["ritenuta"] == 208 and j["totale"] == 1042 and j["netto"] == 834, j

    def test_explicit_zero_opt_out(self):
        r = rv(ST["s_priv"], [{"aliquota": 22, "totale": 1268.80}], ritenuta_aliquota=0)
        assert r.status_code == 200, r.text
        j = r.json()
        ST["rv_zero"] = j["id"]
        assert not j["ritenuta"] and j["netto"] == 1268.8


# --- Registra passiva anteprima: ritenuta_proposta for soggetto_ritenuta supplier invoice without ritenuta
class TestProposta:
    def test_proposta_cassa_privata(self):
        pi = piva()
        sid = mk_sup("TEST_T113 Prof XML", pi, soggetto_ritenuta=False, cassa_tipo="TC01", cassa_aliquota=4, cassa_ritenuta=False)
        d = upload(xml(pi, ((22.0, None, 1040.0, 228.8),), cassa=("TC01", 4, 40)))
        ST["inv_xml"] = d["id"]
        assert not pdoc(d["id"]).get("ritenuta_importo")
        mongo(f'db.parties.updateOne({{id:"{sid}"}}, {{$set:{{soggetto_ritenuta:true}}}})')
        x = pdoc(d["id"])
        r = sess().post(f"{API}/passive/{d['id']}/registrazione/anteprima", json=reg_body(x))
        assert r.status_code == 200, r.text
        assert r.json()["ritenuta_proposta"] == {"aliquota": 20.0, "imponibile": 1000.0}, r.json().get("ritenuta_proposta")

    def test_no_proposta_when_ritenuta_given(self):
        x = pdoc(ST["inv_xml"])
        r = sess().post(f"{API}/passive/{ST['inv_xml']}/registrazione/anteprima", json=reg_body(x) | {"ritenuta_aliquota": 20, "ritenuta_imponibile": 1000})
        assert r.status_code == 200
        assert r.json()["ritenuta_proposta"] is None and r.json()["ritenuta_importo"] == 200

    def test_no_proposta_forfettario(self):
        pi = piva()
        sid = mk_sup("TEST_T113 Forf XML", pi, soggetto_ritenuta=False, regime_percipiente="forfettario")
        d = upload(xml(pi, ((0.0, "N2.2", 1000.0, 0.0),)))
        mongo(f'db.parties.updateOne({{id:"{sid}"}}, {{$set:{{soggetto_ritenuta:true}}}})')
        x = pdoc(d["id"])
        r = sess().post(f"{API}/passive/{d['id']}/registrazione/anteprima", json=reg_body(x))
        assert r.status_code == 200
        assert r.json()["ritenuta_proposta"] is None

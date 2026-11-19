# Iteration 114: passive XML upload recomputes ritenuta from the supplier anagrafica (ritenuta_auto/ritenuta_xml),
# bollo read from XML DatiBollo -> spese_anticipate in prima nota, POST /ritenute/riallinea (manuali, idempotent).
# Run: pytest tests/test_iteration114_ritenuta_anagrafica_bollo.py -v -n 0   (T114_KEEP=1 keeps data for UI tests)
import json
import os
import random
import sys
import uuid

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

RUN = os.environ.get("T114_RUN", str(random.randint(100000, 999999)))
TOK, UID = f"test_session_t114_admin_{RUN}", f"test-user-t114-admin-{RUN}"
PIVA = "11" + RUN + "114"
ST = {}
DATA = "2026-11-02"
COLLS = ["invoices", "passive_invoices", "parties", "articles", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "audit_log", "partite_aperte", "f24_versamenti", "pag_distinte", "ratei_risconti", "counters"]


def sess():
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {TOK}", "X-Requested-With": "invoix"})
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{partita_iva:"{PIVA}"}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def piva():
    return "".join(str(random.randint(0, 9)) for _ in range(11))


def xml(ced_id, riep, rit=None, cassa=None, bollo=None, extra_tot=0.0, rate=None, den="TEST_T114 Prof"):
    numero = f"T114-{uuid.uuid4().hex[:6]}"
    tot = round(sum(r[2] + r[3] for r in riep) + extra_tot, 2)
    dr = (f"<DatiRitenuta><TipoRitenuta>{rit[0]}</TipoRitenuta><ImportoRitenuta>{rit[1]:.2f}</ImportoRitenuta><AliquotaRitenuta>{rit[2]:.2f}</AliquotaRitenuta>"
          f"<CausalePagamento>A</CausalePagamento></DatiRitenuta>") if rit else ""
    db_ = f"<DatiBollo><BolloVirtuale>SI</BolloVirtuale><ImportoBollo>{bollo:.2f}</ImportoBollo></DatiBollo>" if bollo else ""
    cp = (f"<DatiCassaPrevidenziale><TipoCassa>{cassa[0]}</TipoCassa><AlCassa>{cassa[1]:.2f}</AlCassa><ImportoContributoCassa>{cassa[2]:.2f}</ImportoContributoCassa>"
          f"<ImponibileCassa>1000.00</ImponibileCassa><AliquotaIVA>{cassa[3]:.2f}</AliquotaIVA>{f'<Natura>{cassa[4]}</Natura>' if len(cassa) > 4 else ''}"
          f"</DatiCassaPrevidenziale>") if cassa else ""
    rs = "".join(f"<DatiRiepilogo><AliquotaIVA>{a:.2f}</AliquotaIVA>{f'<Natura>{n}</Natura>' if n else ''}<ImponibileImporto>{i:.2f}</ImponibileImporto>"
                 f"<Imposta>{v:.2f}</Imposta><EsigibilitaIVA>I</EsigibilitaIVA></DatiRiepilogo>" for a, n, i, v in riep)
    ls = "".join(f"<DettaglioLinee><NumeroLinea>{k + 1}</NumeroLinea><Descrizione>Prestazione</Descrizione><Quantita>1.00</Quantita><PrezzoUnitario>{i:.2f}</PrezzoUnitario>"
                 f"<PrezzoTotale>{i:.2f}</PrezzoTotale><AliquotaIVA>{a:.2f}</AliquotaIVA>{f'<Natura>{n}</Natura>' if n else ''}</DettaglioLinee>" for k, (a, n, i, v) in enumerate(riep))
    pg = ""
    if rate:
        pg = "<DatiPagamento><CondizioniPagamento>TP01</CondizioniPagamento>" + "".join(
            f"<DettaglioPagamento><ModalitaPagamento>MP05</ModalitaPagamento><DataScadenzaPagamento>{s}</DataScadenzaPagamento><ImportoPagamento>{v:.2f}</ImportoPagamento></DettaglioPagamento>"
            for s, v in rate) + "</DatiPagamento>"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica versione="FPR12" xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
<FatturaElettronicaHeader>
<DatiTrasmissione><IdTrasmittente><IdPaese>IT</IdPaese><IdCodice>{PIVA}</IdCodice></IdTrasmittente><ProgressivoInvio>T{random.randint(1000, 9999)}</ProgressivoInvio>
<FormatoTrasmissione>FPR12</FormatoTrasmissione><CodiceDestinatario>0000000</CodiceDestinatario></DatiTrasmissione>
<CedentePrestatore><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>{ced_id}</IdCodice></IdFiscaleIVA>
<Anagrafica><Denominazione>{den}</Denominazione></Anagrafica><RegimeFiscale>RF01</RegimeFiscale></DatiAnagrafici>
<Sede><Indirizzo>Via Verdi 1</Indirizzo><CAP>20100</CAP><Comune>Milano</Comune><Nazione>IT</Nazione></Sede></CedentePrestatore>
<CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>{PIVA}</IdCodice></IdFiscaleIVA><CodiceFiscale>{PIVA}</CodiceFiscale>
<Anagrafica><Denominazione>TEST_T114 Srl</Denominazione></Anagrafica></DatiAnagrafici>
<Sede><Indirizzo>Via Roma 1</Indirizzo><CAP>00100</CAP><Comune>Roma</Comune><Provincia>RM</Provincia><Nazione>IT</Nazione></Sede></CessionarioCommittente>
</FatturaElettronicaHeader>
<FatturaElettronicaBody>
<DatiGenerali><DatiGeneraliDocumento><TipoDocumento>TD01</TipoDocumento><Divisa>EUR</Divisa><Data>{DATA}</Data><Numero>{numero}</Numero>{dr}{db_}{cp}
<ImportoTotaleDocumento>{tot:.2f}</ImportoTotaleDocumento></DatiGeneraliDocumento></DatiGenerali>
<DatiBeniServizi>{ls}{rs}</DatiBeniServizi>{pg}
</FatturaElettronicaBody>
</p:FatturaElettronica>""".encode()


def upload(x):
    r = sess().post(f"{API}/passive/upload", files=[("files", (f"t114_{uuid.uuid4().hex[:6]}.xml", x, "application/octet-stream"))])
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
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t114.admin.{RUN}@example.com", name:"TEST_T114 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": "TEST_T114 Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    assert sess().put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                                   "corrispettivi": True, "contabilita": True}).status_code == 200
    sess().get(f"{API}/contabilita/conti")
    ST["p"] = sess().get(f"{API}/contabilita/parametri").json()["parametri"]
    yield
    if os.environ.get("T114_KEEP"):
        print("\nKEEP", RUN, ST["cid"], TOK, json.dumps({k: v for k, v in ST.items() if k != "p"}))
    else:
        clean()


# --- ritenuta recomputed from anagrafica on XML upload
class TestRitenutaAnagrafica:
    def test_privata_overrides_xml_208(self):
        pi = piva()
        ST["s_priv"] = mk_sup("TEST_T114 Ing privata", pi, cassa_tipo="TC04", cassa_aliquota=4, cassa_ritenuta=False)
        ST["pi_priv"] = pi
        # XML says 208 on 1040 and rate already netted 1060.80
        d = upload(xml(pi, ((22.0, None, 1040.0, 228.8),), rit=("RT01", 208.0, 20.0), cassa=("TC04", 4, 40, 22), rate=(("2026-12-02", 1060.8),)))
        x = pdoc(d["id"])
        ST["inv_priv"] = d["id"]
        assert x["ritenuta_importo"] == 200 and x["ritenuta_imponibile"] == 1000 and x["ritenuta_aliquota"] == 20, x
        assert x["ritenuta_auto"] is True and x["ritenuta_xml"] == 208
        assert round(x["netto"], 2) == 1068.8
        assert round(sum(r["importo"] for r in x["rate"]), 2) == 1068.8, x["rate"]
        e = entries(d["id"])
        assert len(e) == 1 and amt(e[0]["righe"], ST["p"]["ritenute_operate"], "avere") == 200 and amt(e[0]["righe"], ST["p"]["fornitori"], "avere") == 1068.8

    def test_privata_no_xml_ritenuta(self):
        x = pdoc(upload(xml(ST["pi_priv"], ((22.0, None, 1040.0, 228.8),), cassa=("TC04", 4, 40, 22)))["id"])
        assert x["ritenuta_importo"] == 200 and x["ritenuta_auto"] is True and "ritenuta_xml" not in x

    def test_inps_208(self):
        pi = piva()
        mk_sup("TEST_T114 Prof INPS", pi, cassa_tipo="TC22", cassa_aliquota=4, cassa_ritenuta=True)
        x = pdoc(upload(xml(pi, ((22.0, None, 1040.0, 228.8),), rit=("RT01", 200.0, 20.0), cassa=("TC22", 4, 40, 22)))["id"])
        assert x["ritenuta_importo"] == 208 and x["ritenuta_imponibile"] == 1040 and x["ritenuta_xml"] == 200 and round(x["netto"], 2) == 1060.8

    def test_forfettario_zero(self):
        pi = piva()
        ST["s_forf"] = mk_sup("TEST_T114 Forfettario", pi, regime_percipiente="forfettario", cassa_tipo="TC22", cassa_aliquota=4, cassa_ritenuta=True)
        ST["pi_forf"] = pi
        d = upload(xml(pi, ((0.0, "N2.2", 1040.0, 0.0),), rit=("RT01", 208.0, 20.0), rate=(("2026-12-02", 832.0),)))
        x = pdoc(d["id"])
        assert not x["ritenuta_importo"] and x["ritenuta_xml"] == 208 and x["ritenuta_auto"] is True
        assert round(x["netto"], 2) == round(x["totale"], 2) == 1040
        assert round(sum(r["importo"] for r in x["rate"]), 2) == 1040
        e = entries(d["id"])
        assert amt(e[0]["righe"], ST["p"]["ritenute_operate"], "avere") == 0 and amt(e[0]["righe"], ST["p"]["fornitori"], "avere") == 1040

    def test_non_soggetto_keeps_xml(self):
        pi = piva()
        mk_sup("TEST_T114 Normale", pi, soggetto_ritenuta=False)
        x = pdoc(upload(xml(pi, ((22.0, None, 1000.0, 220.0),), rit=("RT01", 150.0, 20.0)))["id"])
        assert x["ritenuta_importo"] == 150 and "ritenuta_auto" not in x


# --- bollo read from XML DatiBollo
class TestBollo:
    def test_bollo_in_total_without_n1(self):
        p = ST["p"]
        d = upload(xml(ST["pi_forf"], ((0.0, "N2.2", 1040.0, 0.0),), bollo=2.0, extra_tot=2.0))
        x = pdoc(d["id"])
        ST["inv_bollo"] = d["id"]
        assert x["bollo"] == 2 and x["totale"] == 1042 and round(x["netto"], 2) == 1042
        rg = entries(d["id"])[0]["righe"]
        assert amt(rg, p["spese_anticipate"], "dare") == 2 and amt(rg, p["costi"], "dare") == 1040 and amt(rg, p["fornitori"], "avere") == 1042
        a = sess().post(f"{API}/passive/{d['id']}/registrazione/anteprima", json=reg_body(x))
        assert a.status_code == 200, a.text
        ar = a.json()["righe"]
        assert amt(ar, p["spese_anticipate"], "dare") == 2 and amt(ar, p["costi"], "dare") == 1040, ar

    def test_bollo_with_n1_no_double(self):
        p = ST["p"]
        d = upload(xml(ST["pi_forf"], ((0.0, "N2.2", 1040.0, 0.0), (0.0, "N1", 2.0, 0.0)), bollo=2.0))
        x = pdoc(d["id"])
        assert x["bollo"] == 2 and x["totale"] == 1042
        rg = entries(d["id"])[0]["righe"]
        assert amt(rg, p["spese_anticipate"], "dare") == 2 and amt(rg, p["costi"], "dare") == 1040, rg

    def test_bollo_not_in_total(self):
        p = ST["p"]
        d = upload(xml(ST["pi_forf"], ((0.0, "N2.2", 1040.0, 0.0),), bollo=2.0))
        rg = entries(d["id"])[0]["righe"]
        assert amt(rg, p["spese_anticipate"], "dare") == 0 and amt(rg, p["costi"], "dare") == 1040, rg

    def test_bollo_ordinario_with_ritenuta(self):
        # esente N4 professional (INPS-like no cassa) with bollo in total: ritenuta base must exclude the bollo
        p = ST["p"]
        pi = piva()
        mk_sup("TEST_T114 Esente", pi)
        d = upload(xml(pi, ((0.0, "N4", 1000.0, 0.0),), bollo=2.0, extra_tot=2.0))
        x = pdoc(d["id"])
        rg = entries(d["id"])[0]["righe"]
        print("esente+bollo:", x["ritenuta_importo"], x["ritenuta_imponibile"], rg)
        assert amt(rg, p["spese_anticipate"], "dare") == 2 and amt(rg, p["costi"], "dare") == 1000
        assert x["ritenuta_importo"] == 200 and round(x["netto"], 2) == 802


# --- riallinea
class TestRiallinea:
    def test_riallinea(self):
        p = ST["p"]
        old = ST["inv_priv"]
        mongo(f'db.passive_invoices.updateOne({{id:"{old}"}}, {{$set:{{ritenuta_importo:208, ritenuta_imponibile:1040, netto:1060.8}}, $unset:{{ritenuta_auto:""}}}})')
        man = upload(xml(ST["pi_priv"], ((22.0, None, 1040.0, 228.8),)))["id"]
        assert sess().put(f"{API}/passive/{man}/ritenuta", json={"aliquota": 20, "imponibile": 1040}).status_code == 200
        ST["man"] = man
        c = sess().post(f"{API}/ritenute/riallinea").json()
        print("riallinea 1:", c)
        assert set(c) == {"aggiornate", "invariate", "pagate", "manuali", "periodi_chiusi"}
        assert c["aggiornate"] == 1 and c["manuali"] == 1 and c["pagate"] == 0 and c["periodi_chiusi"] == 0
        x = pdoc(old)
        assert x["ritenuta_importo"] == 200 and x["ritenuta_auto"] is True and round(x["netto"], 2) == 1068.8
        e = entries(old)
        assert len(e) == 1 and amt(e[0]["righe"], p["ritenute_operate"], "avere") == 200
        assert pdoc(man)["ritenuta_importo"] == 208

    def test_idempotent(self):
        c = sess().post(f"{API}/ritenute/riallinea").json()
        print("riallinea 2:", c)
        assert c["aggiornate"] == 0 and c["manuali"] == 1

    def test_bollo_entry_intact(self):
        rg = entries(ST["inv_bollo"])
        assert len(rg) == 1 and amt(rg[0]["righe"], ST["p"]["spese_anticipate"], "dare") == 2

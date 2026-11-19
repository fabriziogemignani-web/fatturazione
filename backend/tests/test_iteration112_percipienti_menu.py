# Iteration 112: (A1) menu PUT drops stale ids; (B) professional invoices: regime_percipiente/cassa, base_ritenuta on upload,
# N1 rimborsi art.15 on spese_anticipate, avvisi_percipiente in anteprima, POST /ritenute/riallinea.
# Run: pytest tests/test_iteration112_percipienti_menu.py -v -n 0   (T112_KEEP=1 keeps data for UI tests)
import json
import os
import random
import sys
import uuid

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

RUN = os.environ.get("T112_RUN", str(random.randint(100000, 999999)))
TOK, UID = f"test_session_t112_admin_{RUN}", f"test-user-t112-admin-{RUN}"
TOK2, UID2 = f"test_session_t112_op_{RUN}", f"test-user-t112-op-{RUN}"
PIVA = "11" + RUN + "112"
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


def xml(ced_id, riep, rit=None, cassa=None, numero=None, data=DATA, den="TEST_T112 Prof"):
    numero = numero or f"T112-{uuid.uuid4().hex[:6]}"
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
<Anagrafica><Denominazione>TEST_T112 Srl</Denominazione></Anagrafica></DatiAnagrafici>
<Sede><Indirizzo>Via Roma 1</Indirizzo><CAP>00100</CAP><Comune>Roma</Comune><Provincia>RM</Provincia><Nazione>IT</Nazione></Sede></CessionarioCommittente>
</FatturaElettronicaHeader>
<FatturaElettronicaBody>
<DatiGenerali><DatiGeneraliDocumento><TipoDocumento>TD01</TipoDocumento><Divisa>EUR</Divisa><Data>{data}</Data><Numero>{numero}</Numero>{dr}{cp}
<ImportoTotaleDocumento>{tot:.2f}</ImportoTotaleDocumento></DatiGeneraliDocumento></DatiGenerali>
<DatiBeniServizi>{ls}{rs}</DatiBeniServizi>
</FatturaElettronicaBody>
</p:FatturaElettronica>""".encode()


def upload(x):
    r = sess().post(f"{API}/passive/upload", files=[("files", (f"t112_{uuid.uuid4().hex[:6]}.xml", x, "application/octet-stream"))])
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
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t112.admin.{RUN}@example.com", name:"TEST_T112 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": "TEST_T112 Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    assert sess().put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                                   "corrispettivi": True, "contabilita": True}).status_code == 200
    sess().get(f"{API}/contabilita/conti")
    ST["p"] = sess().get(f"{API}/contabilita/parametri").json()["parametri"]
    mongo(f'db.users.insertOne({{user_id:"{UID2}", email:"test.user.t112.op.{RUN}@example.com", name:"TEST_T112 op", picture:"", role:"operatore", status:"approved", company_ids:["{ST["cid"]}"], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID2}", session_token:"{TOK2}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    yield
    if os.environ.get("T112_KEEP"):
        print("\nKEEP", RUN, ST["cid"], TOK, json.dumps({k: v for k, v in ST.items() if k != "p"}))
    else:
        clean()


# --- A1 menu stale ids
class TestMenu:
    def test_company_menu_stale_ids(self):
        r = sess().put(f"{API}/companies/{ST['cid']}/menu", json={"off": ["registro-iva-acquisti", "registro-iva-vendite", "bem"]})
        assert r.status_code == 200, r.text
        assert r.json()["off"] == ["bem"]
        assert sess().put(f"{API}/companies/{ST['cid']}/menu", json={"off": []}).status_code == 200

    def test_user_menu_stale_ids(self):
        r = sess().put(f"{API}/users/{UID2}/menu", json={"off": ["registro-iva-acquisti", "registro-iva-vendite"]})
        assert r.status_code == 200, r.text
        assert r.json()["off"] == []

    def test_param_has_spese_anticipate(self):
        assert ST["p"].get("spese_anticipate") == "30.07.019"
        conti = sess().get(f"{API}/contabilita/conti").json()
        lst = conti if isinstance(conti, list) else conti.get("conti", [])
        assert any(c.get("codice") == "30.07.019" for c in lst)


# --- B1/B2 supplier settings + ritenuta base on upload
class TestBase:
    def test_regime_persisted_and_validated(self):
        pi = piva()
        pid = mk_sup("TEST_T112 Ordinario Privata", pi, regime_percipiente="ordinario", cassa_tipo="TC04", cassa_aliquota=4, cassa_ritenuta=False)
        ST["sup_priv"], ST["pi_priv"] = pid, pi
        p = next(x for x in sess().get(f"{API}/parties", params={"tipo": "fornitore"}).json() if x["id"] == pid)
        assert p["regime_percipiente"] == "ordinario" and p["cassa_tipo"] == "TC04" and p["cassa_ritenuta"] is False
        r = sess().post(f"{API}/parties", json={"tipo": "fornitore", "denominazione": "TEST_T112 bad", "indirizzo": "x", "cap": "1", "comune": "x", "regime_percipiente": "agente"})
        assert r.status_code == 422

    def test_ordinario_cassa_privata(self):
        d = upload(xml(ST["pi_priv"], ((22.0, None, 1040.0, 228.8),)))
        ST["inv_priv"] = d["id"]
        x = pdoc(d["id"])
        assert x["ritenuta_imponibile"] == 1000 and x["ritenuta_importo"] == 200 and x["ritenuta_auto"] is True
        assert round(x["netto"], 2) == round(1268.8 - 200, 2)

    def test_ordinario_cassa_inps(self):
        pi = piva()
        ST["sup_inps"] = mk_sup("TEST_T112 Ordinario INPS", pi, cassa_tipo="TC22", cassa_aliquota=4, cassa_ritenuta=True)
        x = pdoc(upload(xml(pi, ((22.0, None, 1040.0, 228.8),)))["id"])
        assert x["ritenuta_imponibile"] == 1040 and x["ritenuta_importo"] == 208

    def test_forfettario(self):
        pi = piva()
        ST["sup_forf"] = mk_sup("TEST_T112 Forfettario", pi, regime_percipiente="forfettario")
        d = upload(xml(pi, ((0.0, "N2.2", 1000.0, 0.0),)))
        ST["inv_forf"] = d["id"]
        x = pdoc(d["id"])
        assert not x.get("ritenuta_importo")

    def test_occasionale_minus_n1(self):
        pi = piva()
        ST["sup_occ"] = mk_sup("TEST_T112 Occasionale", pi, regime_percipiente="occasionale")
        x = pdoc(upload(xml(pi, ((0.0, "N2.2", 1000.0, 0.0), (0.0, "N1", 100.0, 0.0))))["id"])
        assert x["ritenuta_imponibile"] == 1000 and x["ritenuta_importo"] == 200


# --- B3/B4 N1 rimborsi accounting + avvisi
class TestRimborsi:
    def test_n1_coa_entry(self):
        p = ST["p"]
        pi = piva()
        ST["sup_n1"] = mk_sup("TEST_T112 Avvocato", pi, persona="fisica", nome="Mario", cognome="TEST_T112 Rossi")
        d = upload(xml(pi, ((22.0, None, 1000.0, 220.0), (0.0, "N1", 50.0, 0.0))))
        ST["inv_n1"] = d["id"]
        x = pdoc(d["id"])
        assert x["ritenuta_importo"] == 200 and x["ritenuta_imponibile"] == 1000
        e = entries(d["id"])
        assert len(e) == 1, e
        rg = e[0]["righe"]
        assert amt(rg, p["spese_anticipate"], "dare") == 50
        assert amt(rg, p["costi"], "dare") == 1000
        assert amt(rg, p["fornitori"], "avere") == 1070
        assert amt(rg, p["ritenute_operate"], "avere") == 200
        assert round(sum(r.get("dare") or 0 for r in rg), 2) == round(sum(r.get("avere") or 0 for r in rg), 2)

    def test_anteprima_righe_and_avvisi(self):
        p = ST["p"]
        d = pdoc(ST["inv_n1"])
        r = sess().post(f"{API}/passive/{ST['inv_n1']}/registrazione/anteprima", json=reg_body(d))
        assert r.status_code == 200, r.text
        j = r.json()
        rg = j["righe"]
        assert amt(rg, p["spese_anticipate"], "dare") == 50 and amt(rg, p["costi"], "dare") == 1000
        assert amt(rg, p["fornitori"], "avere") == 1070 and amt(rg, p["ritenute_operate"], "avere") == 200
        av = j["avvisi_percipiente"]
        assert "manca il comune di nascita" in av and "manca la data di nascita" in av, av
        assert "manca il codice fiscale" not in av

    def test_avvisi_missing_cf(self):
        mongo(f'db.parties.updateOne({{id:"{ST["sup_n1"]}"}}, {{$set:{{codice_fiscale:""}}}})')
        d = pdoc(ST["inv_n1"])
        j = sess().post(f"{API}/passive/{ST['inv_n1']}/registrazione/anteprima", json=reg_body(d)).json()
        assert "manca il codice fiscale" in j["avvisi_percipiente"]
        mongo(f'db.parties.updateOne({{id:"{ST["sup_n1"]}"}}, {{$set:{{codice_fiscale:"RSSMRA80A01F205X"}}}})')

    def test_avvisi_empty_for_normal_supplier(self):
        pi = piva()
        r = sess().post(f"{API}/parties", json={"tipo": "fornitore", "denominazione": "TEST_T112 Normale", "partita_iva": pi, "codice_fiscale": pi,
                                                "indirizzo": "x", "cap": "20100", "comune": "Milano", "nazione": "IT"})
        assert r.status_code == 200
        d = pdoc(upload(xml(pi, ((22.0, None, 100.0, 22.0),)))["id"])
        j = sess().post(f"{API}/passive/{d['id']}/registrazione/anteprima", json=reg_body(d)).json()
        assert j["avvisi_percipiente"] == []


# --- B5 riallinea
class TestRiallinea:
    def test_riallinea(self):
        p = ST["p"]
        # old rule: ritenuta on full 1040 for cassa privata
        old = ST["inv_priv"]
        mongo(f'db.passive_invoices.updateOne({{id:"{old}"}}, {{$set:{{ritenuta_importo:208, ritenuta_imponibile:1040, netto:1060.8, ritenuta_auto:true}}}})')
        # paid invoice with wrong ritenuta
        pi_paid = mk_sup("TEST_T112 Pagato", piva(), cassa_tipo="TC04", cassa_aliquota=4, cassa_ritenuta=False)
        mongo(f'db.parties.updateOne({{id:"{pi_paid}"}}, {{$set:{{soggetto_ritenuta:false}}}})')
        pp = next(x for x in sess().get(f"{API}/parties", params={"tipo": "fornitore"}).json() if x["id"] == pi_paid)
        paid = upload(xml(pp["partita_iva"], ((22.0, None, 1040.0, 228.8),)))["id"]
        mongo(f'db.parties.updateOne({{id:"{pi_paid}"}}, {{$set:{{soggetto_ritenuta:true}}}});'
              f'db.passive_payments.insertOne({{id:"t112pay-{RUN}", company_id:"{ST["cid"]}", invoice_id:"{paid}", importo:10, data:"{DATA}"}})')
        # ritenuta from XML document (wrong vs rules but must be kept)
        xmlrit = upload(xml(ST["pi_priv"], ((22.0, None, 1040.0, 228.8),), rit=("RT01", 150.0, 20.0)))["id"]
        assert pdoc(xmlrit)["ritenuta_importo"] == 150
        r = sess(TOK2).post(f"{API}/ritenute/riallinea")
        assert r.status_code == 403
        r = sess().post(f"{API}/ritenute/riallinea")
        assert r.status_code == 200, r.text
        c = r.json()
        print("riallinea 1:", c)
        assert set(c) == {"aggiornate", "invariate", "pagate", "ritenuta_da_fattura", "periodi_chiusi"}
        assert c["aggiornate"] >= 1 and c["pagate"] == 1 and c["ritenuta_da_fattura"] == 1 and c["periodi_chiusi"] == 0
        x = pdoc(old)
        assert x["ritenuta_importo"] == 200 and x["ritenuta_imponibile"] == 1000 and x["ritenuta_auto"] is True and round(x["netto"], 2) == 1068.8
        e = entries(old)
        assert len(e) == 1 and amt(e[0]["righe"], p["ritenute_operate"], "avere") == 200 and amt(e[0]["righe"], p["fornitori"], "avere") == 1068.8
        assert not pdoc(paid).get("ritenuta_importo")
        assert pdoc(xmlrit)["ritenuta_importo"] == 150
        ST["c1"] = c

    def test_riallinea_idempotent(self):
        c = sess().post(f"{API}/ritenute/riallinea").json()
        print("riallinea 2:", c)
        # second run should change nothing (N1 invoices are re-registered each time -> reported as aggiornate)
        assert c["aggiornate"] == 0, f"second run still reports aggiornate={c['aggiornate']} (N1 invoices always re-registered)"

    def test_n1_entry_intact_after_riallinea(self):
        p = ST["p"]
        e = entries(ST["inv_n1"])
        assert len(e) == 1
        assert amt(e[0]["righe"], p["spese_anticipate"], "dare") == 50 and amt(e[0]["righe"], p["ritenute_operate"], "avere") == 200

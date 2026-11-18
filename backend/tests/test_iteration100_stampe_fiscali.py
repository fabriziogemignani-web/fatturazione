# Iteration 100: Stampe fiscali - multiple IVA registers (VEN/ACQ/CEE/SPL) linked to causali, register assignment/proposal,
# prova/definitive prints (IVA + libro giornale), page numbering, reprint, admin delete/unlock, locks on prima nota and passive invoices.
# Run: pytest tests/test_iteration100_stampe_fiscali.py -v -n 0
import json
import os
import random
import sys

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo, party, inv  # noqa: E402

RUN = str(random.randint(100000, 999999))
TOK, UID = f"test_session_t100_admin_{RUN}", f"test-user-t100-admin-{RUN}"
TOK2, UID2 = f"test_session_t100_cont_{RUN}", f"test-user-t100-cont-{RUN}"
PIVA = "10" + RUN + "001"
ST = {}
COLLS = ["invoices", "passive_invoices", "parties", "articles", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "partite_aperte", "f24_versamenti", "pag_distinte", "ratei_risconti", "bank_tx", "bank_accounts", "iva_registri", "stampe_fiscali"]
Y = 2026


def sess(tok=TOK):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{denominazione:/^TEST_T100/}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:["{UID}","{UID2}"]}}}}); db.user_sessions.deleteMany({{user_id:{{$in:["{UID}","{UID2}"]}}}});')


def pxml(numero, data, ced, paese="IT", imp=1000.0):
    iva = round(imp * 0.22, 2)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica versione="FPR12" xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
<FatturaElettronicaHeader>
<DatiTrasmissione><IdTrasmittente><IdPaese>IT</IdPaese><IdCodice>{PIVA}</IdCodice></IdTrasmittente><ProgressivoInvio>T{random.randint(1000, 9999)}</ProgressivoInvio>
<FormatoTrasmissione>FPR12</FormatoTrasmissione><CodiceDestinatario>0000000</CodiceDestinatario></DatiTrasmissione>
<CedentePrestatore><DatiAnagrafici><IdFiscaleIVA><IdPaese>{paese}</IdPaese><IdCodice>{ced}</IdCodice></IdFiscaleIVA>
<Anagrafica><Denominazione>TEST_T100 Fornitore {paese} {ced}</Denominazione></Anagrafica><RegimeFiscale>RF01</RegimeFiscale></DatiAnagrafici>
<Sede><Indirizzo>Strasse 1</Indirizzo><CAP>10115</CAP><Comune>Berlin</Comune><Nazione>{paese}</Nazione></Sede></CedentePrestatore>
<CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>{PIVA}</IdCodice></IdFiscaleIVA><CodiceFiscale>{PIVA}</CodiceFiscale>
<Anagrafica><Denominazione>TEST_T100 Srl</Denominazione></Anagrafica></DatiAnagrafici>
<Sede><Indirizzo>Via Roma 1</Indirizzo><CAP>00100</CAP><Comune>Roma</Comune><Provincia>RM</Provincia><Nazione>IT</Nazione></Sede></CessionarioCommittente>
</FatturaElettronicaHeader>
<FatturaElettronicaBody>
<DatiGenerali><DatiGeneraliDocumento><TipoDocumento>TD01</TipoDocumento><Divisa>EUR</Divisa><Data>{data}</Data><Numero>{numero}</Numero>
<ImportoTotaleDocumento>{imp + iva:.2f}</ImportoTotaleDocumento></DatiGeneraliDocumento></DatiGenerali>
<DatiBeniServizi><DettaglioLinee><NumeroLinea>1</NumeroLinea><Descrizione>Servizio</Descrizione><Quantita>1.00</Quantita><PrezzoUnitario>{imp:.2f}</PrezzoUnitario>
<PrezzoTotale>{imp:.2f}</PrezzoTotale><AliquotaIVA>22.00</AliquotaIVA></DettaglioLinee>
<DatiRiepilogo><AliquotaIVA>22.00</AliquotaIVA><ImponibileImporto>{imp:.2f}</ImponibileImporto><Imposta>{iva:.2f}</Imposta><EsigibilitaIVA>I</EsigibilitaIVA></DatiRiepilogo>
</DatiBeniServizi></FatturaElettronicaBody></p:FatturaElettronica>""".encode()


def upload(numero, data, ced, paese="IT"):
    r = sess().post(f"{API}/passive/upload", files=[("files", (f"t100_{RUN}_{random.randint(1, 10**6)}.xml", pxml(numero, data, ced, paese), "application/octet-stream"))])
    assert r.status_code == 200, r.text
    j = r.json()[0]
    assert j["ok"], j
    return j["documenti"][0]["id"]


def passive(pid):
    return sess().get(f"{API}/passive/{pid}").json()


def reg_body(pid, dr, rid=None):
    d = passive(pid)
    return {"data_registrazione": dr, "numero": d["numero"], "data": d["data"], "registro_iva_id": rid,
            "riepilogo": [{"aliquota": r["aliquota"], "natura": r.get("natura"), "imponibile": r["imponibile"], "imposta": r["imposta"]} for r in d["riepilogo"]]}


def txt(b):
    import io
    from pypdf import PdfReader
    return "\n".join(pg.extract_text() or "" for pg in PdfReader(io.BytesIO(b)).pages)


def regs():
    r = sess().get(f"{API}/stampe-fiscali/registri")
    assert r.status_code == 200, r.text
    return r.json()


def rid(cod):
    return next(x["id"] for x in regs()["registri"] if x["codice"] == cod)


def stampa(**kw):
    return sess().post(f"{API}/stampe-fiscali/stampa", json={"anno": Y, **kw})


def entry_body(data, descr="TEST_T100 manuale"):
    return {"data": data, "causale": ST["causale"], "descrizione": descr,
            "righe": [{"conto": ST["c1"], "dare": 100}, {"conto": ST["c2"], "avere": 100}]}


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t100.admin.{RUN}@example.com", name:"TEST_T100 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": "TEST_T100 Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    sess().put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                            "corrispettivi": True, "contabilita": True})
    conti = sess().get(f"{API}/contabilita/conti").json()
    leaves = [c["codice"] for c in (conti if isinstance(conti, list) else conti.get("conti", [])) if c.get("livello") == 3]
    ST["c1"], ST["c2"] = leaves[0], leaves[1]
    caus = sess().get(f"{API}/contabilita/causali").json()
    caus = caus if isinstance(caus, list) else caus.get("causali", [])
    ST["causale"] = next((c["codice"] for c in caus if c["codice"] in ("GC", "GEN", "VAR")), caus[0]["codice"])
    mongo(f'db.users.insertOne({{user_id:"{UID2}", email:"test.user.t100.cont.{RUN}@example.com", name:"TEST_T100 contabile", picture:"", role:"contabile", status:"approved", company_ids:["{ST["cid"]}"], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID2}", session_token:"{TOK2}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    yield
    clean()


# --- Registri: seed + causali links
def test_01_registri_seed():
    j = regs()
    cods = {x["codice"]: x for x in j["registri"]}
    assert set(cods) >= {"VEN", "ACQ", "CEE", "SPL"}, cods
    assert cods["VEN"]["predefinito"] and cods["ACQ"]["predefinito"] and not cods["CEE"]["predefinito"]
    assert cods["CEE"]["tipo"] == "acquisti" and cods["SPL"]["tipo"] == "vendite"
    c = {x["codice"]: x.get("registro_id") for x in j["causali"]}
    assert c.get("FC") == cods["CEE"]["id"] and c.get("FS") == cods["SPL"]["id"], c
    assert c.get("FV") == cods["VEN"]["id"] and c.get("FA") == cods["ACQ"]["id"], c
    ST["reg"] = {k: v["id"] for k, v in cods.items()}


# --- Registri CRUD
def test_02_registri_crud():
    s = sess()
    r = s.post(f"{API}/stampe-fiscali/registri", json={"codice": "TST1", "descrizione": "TEST_T100 registro", "tipo": "acquisti", "causali": ["FA"]})
    assert r.status_code == 200, r.text
    new = r.json()
    assert s.post(f"{API}/stampe-fiscali/registri", json={"codice": "TST1", "descrizione": "dup", "tipo": "acquisti"}).status_code == 400
    assert s.post(f"{API}/stampe-fiscali/registri", json={"codice": "ts", "descrizione": "x", "tipo": "acquisti"}).status_code == 422
    c = {x["codice"]: x.get("registro_id") for x in regs()["causali"]}
    assert c["FA"] == new["id"]
    r = s.put(f"{API}/stampe-fiscali/registri/{new['id']}", json={"codice": "TST1", "descrizione": "TEST_T100 mod", "tipo": "acquisti", "causali": []})
    assert r.status_code == 200 and r.json()["descrizione"] == "TEST_T100 mod"
    c = {x["codice"]: x.get("registro_id") for x in regs()["causali"]}
    assert c["FA"] in (None, ""), c
    assert s.delete(f"{API}/stampe-fiscali/registri/{ST['reg']['ACQ']}").status_code == 400
    assert s.delete(f"{API}/stampe-fiscali/registri/{new['id']}").status_code == 200
    assert "TST1" not in {x["codice"] for x in regs()["registri"]}
    # re-link FA to ACQ (it was unlinked)
    r = s.put(f"{API}/stampe-fiscali/registri/{ST['reg']['ACQ']}", json={"codice": "ACQ", "descrizione": "Registro IVA acquisti", "tipo": "acquisti", "causali": ["FA", "NA"]})
    assert r.status_code == 200


def test_03_predefinito_tipo_change():
    r = sess().put(f"{API}/stampe-fiscali/registri/{ST['reg']['VEN']}", json={"codice": "VEN", "descrizione": "Registro IVA vendite", "tipo": "acquisti", "causali": []})
    code = r.status_code
    if code == 200:  # revert
        sess().put(f"{API}/stampe-fiscali/registri/{ST['reg']['VEN']}", json={"codice": "VEN", "descrizione": "Registro IVA vendite", "tipo": "vendite", "causali": ["FV", "NV"]})
    assert code == 400, "Predefinito VEN register can be switched to tipo acquisti (leaves vendite without predefinito)"


# --- Passive docs: proposal + register
def test_04_passive_proposal_and_register():
    ST["p_it"] = upload("IT1", f"{Y}-02-05", "01234567897", "IT")
    ST["p_de"] = upload("DE1", f"{Y}-02-06", "123456789", "DE")
    r = sess().get(f"{API}/stampe-fiscali/proposta", params={"id": ST["p_de"]})
    assert r.status_code == 200 and r.json()["registro_id"] == ST["reg"]["CEE"], r.text
    assert sess().get(f"{API}/stampe-fiscali/proposta", params={"id": ST["p_it"]}).json()["registro_id"] == ST["reg"]["ACQ"]
    for pid in (ST["p_it"], ST["p_de"]):
        r = sess().post(f"{API}/passive/{pid}/registrazione", json=reg_body(pid, f"{Y}-02-10"))
        assert r.status_code == 200, r.text
    r = sess().get(f"{API}/stampe-fiscali/registro", params={"registro_id": ST["reg"]["CEE"], "anno": Y})
    assert r.status_code == 200, r.text
    rows = r.json()["rows"]
    assert [x["id"] for x in rows] == [ST["p_de"]] and rows[0]["registro_proposto"] is True
    j = sess().get(f"{API}/stampe-fiscali/registro", params={"registro_id": ST["reg"]["ACQ"], "anno": Y}).json()
    assert [x["id"] for x in j["rows"]] == [ST["p_it"]]
    assert j["imponibile"] == 1000 and j["imposta"] == 220
    assert {x["codice"] for x in j["registri"]} >= {"ACQ", "CEE"}


# --- Sales: split payment -> SPL
def test_05_sales_split():
    s = sess()
    pa = s.post(f"{API}/parties", json=party("TEST_T100 Comune", codice="UFAB12", pa=True, split=True, cf="80012345678", piva="80012345678"))
    assert pa.status_code == 200, pa.text
    b2b = s.post(f"{API}/parties", json=party("TEST_T100 Cliente", piva="01234567897", cf="01234567897"))
    assert b2b.status_code == 200, b2b.text
    ids = []
    for i, (p, extra) in enumerate(((pa.json()["id"], {"rif_documento": "ORD1", "cig": "ABC1234567"}), (b2b.json()["id"], {}))):
        r = s.post(f"{API}/invoices", json=inv(p, data=f"{Y}-03-0{i + 1}", **extra))
        assert r.status_code == 200, r.text
        ids.append(r.json()["id"])
    for n, i in enumerate(ids, 1):
        mongo(f'db.invoices.updateOne({{id:"{i}"}}, {{$set:{{status:"consegnata", numero:{n}, numero_display:"{n}/{Y}", anno:{Y}}}}})')
    ST["s_pa"], ST["s_b2b"] = ids
    spl = s.get(f"{API}/stampe-fiscali/registro", params={"registro_id": ST["reg"]["SPL"], "anno": Y}).json()["rows"]
    ven = s.get(f"{API}/stampe-fiscali/registro", params={"registro_id": ST["reg"]["VEN"], "anno": Y}).json()["rows"]
    assert [x["id"] for x in spl] == [ids[0]], spl
    assert [x["id"] for x in ven] == [ids[1]], ven


# --- PUT /documento move
def test_06_move_document():
    s = sess()
    r = s.put(f"{API}/stampe-fiscali/documento", json={"kind": "acquisti", "id": ST["p_it"], "registro_id": ST["reg"]["CEE"]})
    assert r.status_code == 200, r.text
    rows = s.get(f"{API}/stampe-fiscali/registro", params={"registro_id": ST["reg"]["CEE"], "anno": Y}).json()["rows"]
    assert ST["p_it"] in [x["id"] for x in rows] and next(x for x in rows if x["id"] == ST["p_it"])["registro_proposto"] is False
    assert s.put(f"{API}/stampe-fiscali/documento", json={"kind": "acquisti", "id": ST["p_it"], "registro_id": ST["reg"]["VEN"]}).status_code == 400
    assert s.put(f"{API}/stampe-fiscali/documento", json={"kind": "acquisti", "id": ST["p_it"], "registro_id": ST["reg"]["ACQ"]}).status_code == 200


# --- Stampa prova
def test_07_stampa_prova():
    r = stampa(tipo="iva", registro_id=ST["reg"]["ACQ"], dal=f"{Y}-01-01", al=f"{Y}-12-31")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content[:4] == b"%PDF"
    assert "STAMPA DI PROVA" in txt(r.content)
    assert "_PROVA" in r.headers.get("content-disposition", "")
    assert sess().get(f"{API}/stampe-fiscali/stampe").json() == []
    assert stampa(tipo="iva", registro_id=ST["reg"]["ACQ"], dal=f"{Y}-03-01", al=f"{Y}-02-01").status_code == 400
    assert stampa(tipo="iva", registro_id=ST["reg"]["ACQ"], dal=f"{Y - 1}-12-01", al=f"{Y}-02-01").status_code == 400


# --- Stampa definitiva IVA + numbering + reprint
def test_08_definitiva_iva():
    acq = ST["reg"]["ACQ"]
    assert stampa(tipo="iva", registro_id=acq, dal=f"{Y}-02-01", al=f"{Y}-02-28", definitiva=True).status_code == 400
    assert stampa(tipo="iva", registro_id=acq, dal=f"{Y}-01-01", al=f"{Y}-12-31", definitiva=True).status_code == 400  # beyond today (2026-11-18)
    r = stampa(tipo="iva", registro_id=acq, dal=f"{Y}-01-01", al=f"{Y}-02-28", definitiva=True)
    assert r.status_code == 200 and "STAMPA DI PROVA" not in txt(r.content)
    st = sess().get(f"{API}/stampe-fiscali/stampe").json()
    assert len(st) == 1 and st[0]["pagina_da"] == 1 and st[0]["pagina_a"] >= 1 and st[0]["documenti"] == 1 and st[0]["blocca"] is True
    ST["s1"] = st[0]
    rp = sess().get(f"{API}/stampe-fiscali/stampe/{st[0]['id']}/pdf")
    assert rp.status_code == 200 and rp.content == r.content
    assert stampa(tipo="iva", registro_id=acq, dal=f"{Y}-02-01", al=f"{Y}-03-31", definitiva=True).status_code == 400
    r2 = stampa(tipo="iva", registro_id=acq, dal=f"{Y}-03-01", al=f"{Y}-03-31", definitiva=True)
    assert r2.status_code == 200
    s2 = next(x for x in sess().get(f"{API}/stampe-fiscali/stampe").json() if x["al"] == f"{Y}-03-31")
    assert s2["pagina_da"] == ST["s1"]["pagina_a"] + 1
    assert f"Pag. {Y}/{s2['pagina_da']}" in txt(r2.content)
    ST["s2"] = s2
    j = sess().get(f"{API}/stampe-fiscali/registro", params={"registro_id": acq, "anno": Y}).json()
    assert j["bloccato_al"] == f"{Y}-03-31"
    assert passive(ST["p_it"]).get("registro_iva_id") == acq  # proposal persisted on definitive


# --- IVA locks on passive docs
def test_09_iva_locks():
    s = sess()
    assert s.put(f"{API}/stampe-fiscali/documento", json={"kind": "acquisti", "id": ST["p_it"], "registro_id": ST["reg"]["CEE"]}).status_code == 400
    r = s.patch(f"{API}/passive/{ST['p_it']}", json={"stato_reg": "da_registrare"})
    assert r.status_code == 400 and "definitiva" in r.text, r.text
    assert s.delete(f"{API}/passive/{ST['p_it']}").status_code == 400
    p3 = upload("IT3", f"{Y}-02-07", "01234567897", "IT")
    ST["p3"] = p3
    r = s.post(f"{API}/passive/{p3}/registrazione", json=reg_body(p3, f"{Y}-02-20"))
    assert r.status_code == 400 and "definitiva" in r.text, r.text
    r = s.post(f"{API}/passive/{p3}/registrazione", json=reg_body(p3, f"{Y}-02-20", ST["reg"]["ACQ"]))
    assert r.status_code == 400
    # CEE register not printed -> allowed
    r = s.post(f"{API}/passive/{p3}/registrazione", json=reg_body(p3, f"{Y}-02-20", ST["reg"]["CEE"]))
    assert r.status_code == 200, r.text
    assert passive(p3)["registro_iva_id"] == ST["reg"]["CEE"]


def test_10_patch_registration_bypass():
    p4 = upload("IT4", f"{Y}-02-08", "01234567897", "IT")
    ST["p4"] = p4
    r = sess().patch(f"{API}/passive/{p4}", json={"stato_reg": "registrata", "data_registrazione": f"{Y}-02-21"})
    if r.status_code == 200:
        sess().patch(f"{API}/passive/{p4}", json={"stato_reg": "da_registrare"})
    assert r.status_code == 400, f"PATCH /passive registers into locked ACQ period: {r.status_code} {r.text[:200]}"


# --- Libro giornale
def test_11_giornale_definitiva_and_locks():
    s = sess()
    r = s.post(f"{API}/contabilita/registrazioni", json=entry_body(f"{Y}-04-10"))
    assert r.status_code == 200, r.text
    ST["e1"] = r.json()["id"]
    pr = stampa(tipo="giornale", dal=f"{Y}-01-01", al=f"{Y}-04-30")
    assert pr.status_code == 200 and "STAMPA DI PROVA" in txt(pr.content)
    r = stampa(tipo="giornale", dal=f"{Y}-01-01", al=f"{Y}-04-30", definitiva=True)
    assert r.status_code == 200, r.text
    g = next(x for x in s.get(f"{API}/stampe-fiscali/stampe").json() if x["tipo"] == "giornale")
    assert g["pagina_da"] == 1 and g["riporto"]["righe"] >= 2 and g["riporto"]["dare"] == g["riporto"]["avere"] and g["riporto"]["dare"] >= 100
    ST["g1"] = g
    r = s.post(f"{API}/contabilita/registrazioni", json=entry_body(f"{Y}-04-15"))
    assert r.status_code == 400 and "libro giornale" in r.text.lower(), r.text
    r = s.put(f"{API}/contabilita/registrazioni/{ST['e1']}", json=entry_body(f"{Y}-04-10", "TEST_T100 mod"))
    assert r.status_code == 400 and "libro giornale" in r.text.lower()
    assert s.delete(f"{API}/contabilita/registrazioni/{ST['e1']}").status_code == 400


def test_12_giornale_move_out_of_locked_period():
    r = sess().put(f"{API}/contabilita/registrazioni/{ST['e1']}", json=entry_body(f"{Y}-06-10", "TEST_T100 moved"))
    if r.status_code == 200:
        sess().put(f"{API}/contabilita/registrazioni/{ST['e1']}", json=entry_body(f"{Y}-04-10"))  # try restore
    assert r.status_code == 400, f"Entry dated inside locked giornale period moved to an unlocked date: {r.status_code}"


def test_13_giornale_provvisorie_and_riporto():
    s = sess()
    mongo(f'db.coa_entries.insertOne({{id:"t100-prov-{RUN}", company_id:"{ST["cid"]}", anno:{Y}, numero:9999, data:"{Y}-05-10", causale:"{ST["causale"]}", descrizione:"TEST_T100 prov", origine:"ratei", provvisoria:true, righe:[], totale:0}})')
    r = stampa(tipo="giornale", dal=f"{Y}-05-01", al=f"{Y}-05-31", definitiva=True)
    assert r.status_code == 400 and "provvisorie" in r.text
    mongo(f'db.coa_entries.deleteOne({{id:"t100-prov-{RUN}"}})')
    e = s.post(f"{API}/contabilita/registrazioni", json=entry_body(f"{Y}-05-12"))
    assert e.status_code == 200, e.text
    r = stampa(tipo="giornale", dal=f"{Y}-05-01", al=f"{Y}-05-31", definitiva=True)
    assert r.status_code == 200
    g2 = next(x for x in s.get(f"{API}/stampe-fiscali/stampe").json() if x["tipo"] == "giornale" and x["al"] == f"{Y}-05-31")
    assert g2["pagina_da"] == ST["g1"]["pagina_a"] + 1
    assert g2["riporto"]["dare"] == round(ST["g1"]["riporto"]["dare"] + 100, 2)
    ST["g2"] = g2


# --- Admin: unlock / delete
def test_14_admin_only():
    s2 = sess(TOK2)
    assert s2.get(f"{API}/stampe-fiscali/stampe").status_code == 200
    assert s2.delete(f"{API}/stampe-fiscali/stampe/{ST['g2']['id']}").status_code == 403
    assert s2.put(f"{API}/stampe-fiscali/stampe/{ST['g2']['id']}/blocco", json={"blocca": False}).status_code == 403


def test_15_unlock_and_delete():
    s = sess()
    for g in (ST["g1"], ST["g2"]):
        assert s.put(f"{API}/stampe-fiscali/stampe/{g['id']}/blocco", json={"blocca": False}).status_code == 200
    r = s.put(f"{API}/contabilita/registrazioni/{ST['e1']}", json=entry_body(f"{Y}-04-11", "TEST_T100 after unlock"))
    assert r.status_code == 200, r.text
    r = s.post(f"{API}/contabilita/registrazioni", json=entry_body(f"{Y}-04-16"))
    assert r.status_code == 200, r.text
    assert s.put(f"{API}/stampe-fiscali/stampe/{ST['g1']['id']}/blocco", json={"blocca": True}).status_code == 200
    assert s.post(f"{API}/contabilita/registrazioni", json=entry_body(f"{Y}-04-17")).status_code == 400
    # delete latest giornale -> next definitive starts again after g1
    assert s.delete(f"{API}/stampe-fiscali/stampe/{ST['g2']['id']}").status_code == 200
    assert s.get(f"{API}/stampe-fiscali/stampe/{ST['g2']['id']}/pdf").status_code == 404
    assert s.delete(f"{API}/stampe-fiscali/stampe/{ST['g2']['id']}").status_code == 404
    assert stampa(tipo="giornale", dal=f"{Y}-06-01", al=f"{Y}-06-30", definitiva=True).status_code == 400
    # IVA unlock -> unregister passive allowed
    for x in (ST["s1"], ST["s2"]):
        assert s.put(f"{API}/stampe-fiscali/stampe/{x['id']}/blocco", json={"blocca": False}).status_code == 200
    assert s.put(f"{API}/stampe-fiscali/documento", json={"kind": "acquisti", "id": ST["p_it"], "registro_id": ST["reg"]["CEE"]}).status_code == 200
    assert s.delete(f"{API}/stampe-fiscali/registri/{ST['reg']['CEE']}").status_code in (200, 400)


def test_16_auto_entry_in_locked_giornale():
    # giornale locked up to Y-04-30 (g1). Registering a passive with data_registrazione inside -> prima nota auto entry?
    s = sess()
    p5 = upload("IT5", f"{Y}-04-01", "01234567897", "IT")
    r = s.post(f"{API}/passive/{p5}/registrazione", json=reg_body(p5, f"{Y}-04-20"))
    created = mongo(f'print(db.coa_entries.countDocuments({{company_id:"{ST["cid"]}", ref_id:"{p5}"}}))')
    assert r.status_code == 400 or created == "1", f"Passive registered ({r.status_code}) in locked giornale period but no prima nota entry created (silently skipped)"

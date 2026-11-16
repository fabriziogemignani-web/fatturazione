# Iteration 91: POST /api/contabilita/rigenera auto-creates autofatture TD16 (IT supplier N6.x) / TD17 (foreign supplier or party intra/extra UE)
# for passive invoices registered in bulk; ordinary invoices get none; idempotent (no duplicates on 2nd run).
# Run: pytest tests/test_iteration91_rigenera_autofatture.py -v -n 0
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
TOK, UID = "test_session_t91_admin", "test-user-t91-admin"
PIVA = "91" + RUN + "911"
ST = {}
COLLS = ["invoices", "passive_invoices", "parties", "articles", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "partite_aperte", "f24_versamenti", "pag_distinte", "ratei_risconti", "counters", "bank_tx", "bank_accounts"]
Y = date.today().year


def sess():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{denominazione:/^TEST_T91/}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def xml(numero, data, ced, imp=1000.0, mode="ord", paese="IT"):
    # mode: ord (22%), n6 (N6.3 RC), est (0% N2.2 no imposta)
    iva = round(imp * 0.22, 2) if mode == "ord" else 0.0
    tot = round(imp + iva, 2)
    aliq = {"ord": "<AliquotaIVA>22.00</AliquotaIVA>", "n6": "<AliquotaIVA>0.00</AliquotaIVA><Natura>N6.3</Natura>",
            "est": "<AliquotaIVA>0.00</AliquotaIVA><Natura>N2.2</Natura>"}[mode]
    cf = f"<CodiceFiscale>{ced}</CodiceFiscale>" if paese == "IT" else ""
    prov = "<Provincia>MI</Provincia>" if paese == "IT" else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica versione="FPR12" xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
<FatturaElettronicaHeader>
<DatiTrasmissione><IdTrasmittente><IdPaese>IT</IdPaese><IdCodice>01234567890</IdCodice></IdTrasmittente><ProgressivoInvio>T91{random.randint(100, 999)}</ProgressivoInvio>
<FormatoTrasmissione>FPR12</FormatoTrasmissione><CodiceDestinatario>0000000</CodiceDestinatario></DatiTrasmissione>
<CedentePrestatore><DatiAnagrafici><IdFiscaleIVA><IdPaese>{paese}</IdPaese><IdCodice>{ced}</IdCodice></IdFiscaleIVA>{cf}
<Anagrafica><Denominazione>TEST_T91 Fornitore {ced}</Denominazione></Anagrafica><RegimeFiscale>RF01</RegimeFiscale></DatiAnagrafici>
<Sede><Indirizzo>Strasse 1</Indirizzo><CAP>20100</CAP><Comune>Citta</Comune>{prov}<Nazione>{paese}</Nazione></Sede></CedentePrestatore>
<CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>{PIVA}</IdCodice></IdFiscaleIVA><CodiceFiscale>{PIVA}</CodiceFiscale>
<Anagrafica><Denominazione>TEST_T91 Srl</Denominazione></Anagrafica></DatiAnagrafici>
<Sede><Indirizzo>Via Roma 1</Indirizzo><CAP>00100</CAP><Comune>Roma</Comune><Provincia>RM</Provincia><Nazione>IT</Nazione></Sede></CessionarioCommittente>
</FatturaElettronicaHeader>
<FatturaElettronicaBody>
<DatiGenerali><DatiGeneraliDocumento><TipoDocumento>TD01</TipoDocumento><Divisa>EUR</Divisa><Data>{data}</Data><Numero>{numero}</Numero>
<ImportoTotaleDocumento>{tot:.2f}</ImportoTotaleDocumento></DatiGeneraliDocumento></DatiGenerali>
<DatiBeniServizi><DettaglioLinee><NumeroLinea>1</NumeroLinea><Descrizione>Servizio</Descrizione><Quantita>1.00</Quantita><PrezzoUnitario>{imp:.2f}</PrezzoUnitario>
<PrezzoTotale>{imp:.2f}</PrezzoTotale>{aliq}</DettaglioLinee>
<DatiRiepilogo>{aliq}<ImponibileImporto>{imp:.2f}</ImponibileImporto><Imposta>{iva:.2f}</Imposta><EsigibilitaIVA>I</EsigibilitaIVA></DatiRiepilogo>
</DatiBeniServizi>
</FatturaElettronicaBody>
</p:FatturaElettronica>""".encode()


def upload(x):
    r = sess().post(f"{API}/passive/upload", files=[("files", (f"t91_{uuid.uuid4().hex[:6]}.xml", x, "application/octet-stream"))])
    assert r.status_code == 200, r.text
    j = r.json()[0]
    assert j["ok"], j
    return j["documenti"][0]["id"]


def get(pid):
    r = sess().get(f"{API}/passive/{pid}")
    assert r.status_code == 200, r.text
    return r.json()


def afs():
    q = {"company_id": ST["cid"], "autofattura": True}
    return json.loads(mongo(f'print(JSON.stringify(db.invoices.find({json.dumps(q)},{{_id:0}}).toArray()))') or "[]")


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t91.admin@example.com", name:"TEST_T91 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": f"TEST_T91 Autofatture {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
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
    yield
    if os.environ.get("T91_KEEP"):
        print("\nKEEP", RUN, ST["cid"], TOK)
    else:
        clean()


class TestRigeneraAutofatture:
    def test_01_setup_docs(self):
        ST["A"] = upload(xml("A-1", f"{Y}-01-10", "02222222222"))                       # ordinary
        ST["C"] = upload(xml("C-1", f"{Y}-01-11", "04444444444", mode="n6"))            # IT N6.3 -> TD16
        ST["G"] = upload(xml("G-1", f"{Y}-01-12", "123456789", mode="est", paese="DE"))  # DE -> TD17
        ST["H"] = upload(xml("H-1", f"{Y}-01-13", "05555555555", mode="est"))           # IT but party extra_ue -> TD17
        h = get(ST["H"])
        assert h.get("party_id"), h
        mongo(f'db.parties.updateOne({{id:"{h["party_id"]}", company_id:"{ST["cid"]}"}}, {{$set:{{gestione_iva:"extra_ue"}}}})')
        g = get(ST["G"])
        print("G fornitore", g.get("fornitore"))
        for k in "ACGH":
            assert get(ST[k])["stato_reg"] == "da_registrare", k

    def test_02_rigenera(self):
        r = sess().post(f"{API}/contabilita/rigenera", json={"ricrea": False})
        assert r.status_code == 200, r.text
        j = r.json()
        print("RIGENERA", j)
        assert j["acquisti"] == 4, j
        assert j["autofatture"] == 3, j
        assert not [e for e in j["errori"] if "utofattura" in e], j["errori"]

    def test_03_ordinary_no_af(self):
        a = get(ST["A"])
        assert a["stato_reg"] == "registrata"
        assert not a.get("autofattura_id") and not a.get("reverse_charge")

    def test_04_td16(self):
        c = get(ST["C"])
        assert c["stato_reg"] == "registrata" and c["reverse_charge"][0]["natura"] == "N6.3" and c["reverse_charge"][0]["aliquota"] == 10
        assert c.get("autofattura_id") and c.get("autofattura_numero", "").startswith("AF")
        af = next(x for x in afs() if x["id"] == c["autofattura_id"])
        assert af["tipo_documento"] == "TD16" and af["sezionale"] == "AF" and af["status"] == "bozza" and af["passive_id"] == ST["C"]
        assert af["cedente"]["nazione"] == "IT" and af["cedente"]["partita_iva"] == "04444444444"
        assert af["numero_display"] == f"AF{af['numero']}/{Y}"
        assert af["lines"][0]["aliquota"] == 10 and af["lines"][0]["prezzo_unitario"] == 1000.0
        assert round(af["iva"], 2) == 100.0, af

    def test_05_td17_foreign(self):
        g = get(ST["G"])
        assert g["stato_reg"] == "registrata" and g.get("estero") is True
        rc = g["reverse_charge"]
        assert rc and rc[0]["aliquota"] == 10 and rc[0]["imposta"] == 100.0, rc
        af = next(x for x in afs() if x["id"] == g["autofattura_id"])
        assert af["tipo_documento"] == "TD17" and af["status"] == "bozza"
        assert af["cedente"]["nazione"] == "DE", af["cedente"]

    def test_06_td17_party_extra_ue(self):
        h = get(ST["H"])
        assert h.get("estero") is True and h.get("reverse_charge"), h.get("reverse_charge")
        af = next(x for x in afs() if x["id"] == h["autofattura_id"])
        assert af["tipo_documento"] == "TD17", af["tipo_documento"]
        print("H cedente", af["cedente"])

    def test_07_numbering(self):
        nums = sorted(x["numero"] for x in afs())
        assert nums == [1, 2, 3], nums
        assert {x["numero_display"] for x in afs()} == {f"AF{n}/{Y}" for n in (1, 2, 3)}

    def test_08_idempotent(self):
        j = sess().post(f"{API}/contabilita/rigenera", json={"ricrea": False}).json()
        assert j["autofatture"] == 0 and j["acquisti"] == 0, j
        assert len(afs()) == 3

    def test_09_ricrea_no_dup(self):
        j = sess().post(f"{API}/contabilita/rigenera", json={"ricrea": True}).json()
        assert j["autofatture"] == 0, j
        assert len(afs()) == 3

    def test_10_af_visible_in_invoices(self):
        r = sess().get(f"{API}/invoices", params={"status": "bozza"})
        assert r.status_code == 200, r.text
        d = r.json()
        items = d if isinstance(d, list) else d.get("items", d.get("rows", []))
        ids = {x["id"] for x in items}
        assert {get(ST[k])["autofattura_id"] for k in "CGH"} <= ids

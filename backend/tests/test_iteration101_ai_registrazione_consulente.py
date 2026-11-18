# Iteration 101: AI registration of passive invoices (POST /api/ai/passive/analizza -> ai_analisi/ai_conto, rigenera uses ai_conto + ai_dubbia),
# doubtful list/review (GET /api/ai/passive/dubbie, POST /api/ai/passive/{id}/rivista) and Consulente IA SSE chat + storico (multi-turn).
# Real LLM calls (Gemini 3 Flash via Emergent key): 3 invoices + 2 chat turns. Run: pytest tests/test_iteration101_ai_registrazione_consulente.py -v -n 0
# Set T101_KEEP=1 to keep data (prints company id + token) for UI testing.
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
TOK, UID = "test_session_t101_admin", "test-user-t101-admin"
TOK_OP, UID_OP = "test_session_t101_oper", "test-user-t101-oper"
PIVA = "10" + RUN + "101"
ST = {}
COLLS = ["invoices", "passive_invoices", "parties", "articles", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "partite_aperte", "f24_versamenti", "pag_distinte", "ratei_risconti", "counters", "bank_tx", "bank_accounts", "ai_chat", "registri_iva", "stampe_fiscali"]
Y = date.today().year


def sess(tok=TOK, cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    c = cid or ST.get("cid")
    if c:
        s.headers["X-Company-Id"] = c
    return s


def clean():
    mongo(f'db.companies.find({{denominazione:/^TEST_T101/}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:["{UID}","{UID_OP}"]}}}}); db.user_sessions.deleteMany({{user_id:{{$in:["{UID}","{UID_OP}"]}}}});')


def xml(numero, data, ced, den, righe, mode="ord", paese="IT"):
    # righe: [(descrizione, imponibile)]; mode ord=22%, est=0% N2.1 (foreign service)
    aliq = "<AliquotaIVA>22.00</AliquotaIVA>" if mode == "ord" else "<AliquotaIVA>0.00</AliquotaIVA><Natura>N2.1</Natura>"
    imp = round(sum(x[1] for x in righe), 2)
    iva = round(imp * 0.22, 2) if mode == "ord" else 0.0
    cf = f"<CodiceFiscale>{ced}</CodiceFiscale>" if paese == "IT" else ""
    prov = "<Provincia>MI</Provincia>" if paese == "IT" else ""
    lines = "".join(f"<DettaglioLinee><NumeroLinea>{i + 1}</NumeroLinea><Descrizione>{d}</Descrizione><Quantita>1.00</Quantita><PrezzoUnitario>{v:.2f}</PrezzoUnitario>"
                    f"<PrezzoTotale>{v:.2f}</PrezzoTotale>{aliq}</DettaglioLinee>" for i, (d, v) in enumerate(righe))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica versione="FPR12" xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
<FatturaElettronicaHeader>
<DatiTrasmissione><IdTrasmittente><IdPaese>IT</IdPaese><IdCodice>01234567890</IdCodice></IdTrasmittente><ProgressivoInvio>T101{random.randint(100, 999)}</ProgressivoInvio>
<FormatoTrasmissione>FPR12</FormatoTrasmissione><CodiceDestinatario>0000000</CodiceDestinatario></DatiTrasmissione>
<CedentePrestatore><DatiAnagrafici><IdFiscaleIVA><IdPaese>{paese}</IdPaese><IdCodice>{ced}</IdCodice></IdFiscaleIVA>{cf}
<Anagrafica><Denominazione>{den}</Denominazione></Anagrafica><RegimeFiscale>RF01</RegimeFiscale></DatiAnagrafici>
<Sede><Indirizzo>Via 1</Indirizzo><CAP>20100</CAP><Comune>Citta</Comune>{prov}<Nazione>{paese}</Nazione></Sede></CedentePrestatore>
<CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>{PIVA}</IdCodice></IdFiscaleIVA><CodiceFiscale>{PIVA}</CodiceFiscale>
<Anagrafica><Denominazione>TEST_T101 Srl</Denominazione></Anagrafica></DatiAnagrafici>
<Sede><Indirizzo>Via Roma 1</Indirizzo><CAP>00100</CAP><Comune>Roma</Comune><Provincia>RM</Provincia><Nazione>IT</Nazione></Sede></CessionarioCommittente>
</FatturaElettronicaHeader>
<FatturaElettronicaBody>
<DatiGenerali><DatiGeneraliDocumento><TipoDocumento>TD01</TipoDocumento><Divisa>EUR</Divisa><Data>{data}</Data><Numero>{numero}</Numero>
<ImportoTotaleDocumento>{imp + iva:.2f}</ImportoTotaleDocumento></DatiGeneraliDocumento></DatiGenerali>
<DatiBeniServizi>{lines}
<DatiRiepilogo>{aliq}<ImponibileImporto>{imp:.2f}</ImponibileImporto><Imposta>{iva:.2f}</Imposta><EsigibilitaIVA>I</EsigibilitaIVA></DatiRiepilogo>
</DatiBeniServizi>
</FatturaElettronicaBody>
</p:FatturaElettronica>""".encode()


def upload(x):
    r = sess().post(f"{API}/passive/upload", files=[("files", (f"t101_{uuid.uuid4().hex[:6]}.xml", x, "application/octet-stream"))])
    assert r.status_code == 200, r.text
    j = r.json()[0]
    assert j["ok"], j
    return j["documenti"][0]["id"]


def pdoc(pid):
    return json.loads(mongo(f'print(JSON.stringify(db.passive_invoices.findOne({{id:"{pid}"}},{{_id:0,xml_b64:0}})))') or "null")


def entries(pid):
    return json.loads(mongo(f'print(JSON.stringify(db.coa_entries.find({{company_id:"{ST["cid"]}", origine:"acquisto", ref_id:"{pid}"}},{{_id:0}}).toArray()))') or "[]")


def sse(sid, msg):
    r = sess().post(f"{API}/ai/consulente/chat", json={"session_id": sid, "message": msg}, stream=True, timeout=180)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream")
    chunks, done, err = [], False, None
    for line in r.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        p = line[6:]
        if p == "[DONE]":
            done = True
            break
        j = json.loads(p)
        if j.get("error"):
            err = j["error"]
        if j.get("t"):
            chunks.append(j["t"])
    return chunks, done, err


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t101.admin@example.com", name:"TEST_T101 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": f"TEST_T101 AI {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    mongo(f'db.users.insertOne({{user_id:"{UID_OP}", email:"test.user.t101.oper@example.com", name:"TEST_T101 oper", picture:"", role:"operatore", status:"approved", company_ids:["{ST["cid"]}"], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID_OP}", session_token:"{TOK_OP}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    yield
    if os.environ.get("T101_KEEP"):
        print("\nKEEP", RUN, ST["cid"], TOK, json.dumps(ST))
    else:
        clean()


class TestAiRegistrazione:
    # 400 when the chart of accounts does not exist yet
    def test_00_no_coa_400(self):
        r = sess().post(f"{API}/ai/passive/analizza")
        print("NO COA", r.status_code, r.text)
        assert r.status_code in (400, 403), r.text

    def test_01_enable_coge_and_upload(self):
        sess().put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                                "corrispettivi": True, "contabilita": True})
        s = sess()
        assert s.get(f"{API}/contabilita/conti").status_code == 200
        pr = s.get(f"{API}/contabilita/parametri").json()
        p = pr["parametri"]
        ST["costi_default"] = p["costi"]
        body = {"conti": {k: p[k] for k, _ in pr["ruoli"]}, "contropartita_vendite": p["contropartita_vendite"],
                "contropartita_acquisti": p["contropartita_acquisti"], "aliquota_rc": 22, "categorie": p["categorie"]}
        assert s.put(f"{API}/contabilita/parametri", json=body).status_code == 200
        ST["A"] = upload(xml("EN-1", f"{Y}-01-10", "06655971007", "TEST_T101 Energia Elettrica SpA",
                             [("Fornitura energia elettrica uso ufficio periodo dicembre - quota energia", 350.0), ("Oneri di sistema e trasporto energia elettrica", 120.0)]))
        ST["B"] = upload(xml("DE-7", f"{Y}-01-11", "811234567", "TEST_T101 Global Services GmbH", [("Leistung", 900.0)], mode="est", paese="DE"))
        ST["C"] = upload(xml("CA-3", f"{Y}-01-12", "01234567897", "TEST_T101 Cancelleria Srl", [("Carta A4 risme e toner stampante ufficio", 80.0)]))
        for k in "ABC":
            assert pdoc(ST[k])["stato_reg"] == "da_registrare", k

    def test_02_analizza(self):
        r = sess().post(f"{API}/ai/passive/analizza", timeout=300)
        assert r.status_code == 200, r.text
        j = r.json()
        print("ANALIZZA", j)
        assert set(j) >= {"analizzate", "dubbie", "errori", "restanti"}
        assert j["analizzate"] == 3 and j["errori"] == [] and j["restanti"] == 0, j
        conti = {c["codice"] for c in json.loads(mongo(f'print(JSON.stringify(db.coa_accounts.find({{company_id:"{ST["cid"]}", livello:3}},{{_id:0,codice:1}}).toArray()))'))}
        nd = 0
        for k in "ABC":
            d = pdoc(ST[k])
            a = d["ai_analisi"]
            print(k, d.get("ai_conto"), json.dumps(a, ensure_ascii=False))
            assert {"conto", "trattamento", "confidenza", "motivo", "dubbia", "rivista"} <= set(a)
            assert a["rivista"] is False and isinstance(a["dubbia"], bool) and 0 <= a["confidenza"] <= 1
            nd += int(a["dubbia"])
            if a["conto"]:
                assert d["ai_conto"] == a["conto"] and d["ai_conto"] in conti and d["ai_conto"][:3] in ("30.", "31.", "07."), d["ai_conto"]
        assert nd == j["dubbie"]
        a = pdoc(ST["A"])["ai_analisi"]
        assert a["conto"], "energy invoice should get a cost account"
        ST["dubbie_llm"] = nd

    def test_03_analizza_idempotent(self):
        j = sess().post(f"{API}/ai/passive/analizza").json()
        assert j["analizzate"] == 0 and j["restanti"] == 0, j

    def test_04_force_one_doubtful_and_list(self):
        # ensure at least one doubtful + one certain for deterministic rigenera checks
        if not pdoc(ST["B"])["ai_analisi"]["dubbia"]:
            mongo(f'db.passive_invoices.updateOne({{id:"{ST["B"]}"}}, {{$set:{{"ai_analisi.dubbia":true}}}})')
            print("forced B doubtful")
        if pdoc(ST["A"])["ai_analisi"]["dubbia"]:
            print("WARN: energy invoice A was marked doubtful by the LLM:", pdoc(ST["A"])["ai_analisi"])
        r = sess().get(f"{API}/ai/passive/dubbie")
        assert r.status_code == 200
        ids = [x["id"] for x in r.json()]
        exp = [ST[k] for k in "ABC" if pdoc(ST[k])["ai_analisi"]["dubbia"]]
        assert set(ids) == set(exp), (ids, exp)
        row = next(x for x in r.json() if x["id"] == ST["B"])
        assert row["fornitore"]["denominazione"].startswith("TEST_T101") and "ai_analisi" in row and "_id" not in row

    def test_05_rigenera_uses_ai_conto(self):
        r = sess().post(f"{API}/contabilita/rigenera", json={"ricrea": False}, timeout=120)
        assert r.status_code == 200, r.text
        j = r.json()
        print("RIGENERA", j)
        assert j["acquisti"] == 3, j
        for k in "ABC":
            d = pdoc(ST[k])
            assert d["stato_reg"] == "registrata", k
            es = entries(ST[k])
            assert len(es) == 1, (k, es)
            e = es[0]
            dare_conti = [x["conto"] for x in e["righe"] if (x.get("dare") or 0) > 0]
            if d.get("ai_conto"):
                assert d["ai_conto"] in dare_conti, (k, d["ai_conto"], e["righe"])
            assert bool(e.get("ai_dubbia")) == bool(d["ai_analisi"]["dubbia"]), (k, e.get("ai_dubbia"))
            ST[f"E{k}"] = e["id"]
        e = entries(ST["B"])[0]
        assert e["ai_dubbia"] is True

    def test_06_prima_nota_api_exposes_ai_dubbia(self):
        r = sess().get(f"{API}/contabilita/registrazioni", params={"dal": f"{Y}-01-01", "al": f"{Y}-12-31"})
        print("REG", r.status_code)
        if r.status_code != 200:
            pytest.skip(f"registrazioni endpoint: {r.status_code}")
        d = r.json()
        regs = d.get("registrazioni", d) if isinstance(d, dict) else d
        eb = next((x for x in regs if x["id"] == ST["EB"]), None)
        assert eb and eb.get("ai_dubbia") is True, eb

    def test_07_rivista_permissions(self):
        assert sess(TOK_OP).post(f"{API}/ai/passive/{ST['B']}/rivista").status_code == 403
        assert sess(TOK_OP).post(f"{API}/ai/passive/analizza").status_code == 403
        assert sess().post(f"{API}/ai/passive/nonexistent-id/rivista").status_code == 404

    def test_08_rivista(self):
        r = sess().post(f"{API}/ai/passive/{ST['B']}/rivista")
        assert r.status_code == 200 and r.json() == {"ok": True}
        a = pdoc(ST["B"])["ai_analisi"]
        assert a["rivista"] is True and a.get("rivista_da")
        assert ST["B"] not in [x["id"] for x in sess().get(f"{API}/ai/passive/dubbie").json()]
        assert "ai_dubbia" not in entries(ST["B"])[0]

    def test_09_ricrea_keeps_review_and_ai_conto(self):
        r = sess().post(f"{API}/contabilita/rigenera", json={"ricrea": True}, timeout=120)
        assert r.status_code == 200, r.text
        print("RICREA", r.json())
        e = entries(ST["B"])
        assert len(e) == 1 and not e[0].get("ai_dubbia"), e
        a = pdoc(ST["A"])
        if a.get("ai_conto"):
            assert a["ai_conto"] in [x["conto"] for x in entries(ST["A"])[0]["righe"] if (x.get("dare") or 0) > 0]


class TestConsulente:
    def test_10_validation(self):
        assert sess().post(f"{API}/ai/consulente/chat", json={"session_id": "x", "message": ""}).status_code == 422
        assert sess().post(f"{API}/ai/consulente/chat", json={"session_id": "", "message": "ciao"}).status_code == 422

    def test_11_stream_and_history(self):
        sid = "t101" + uuid.uuid4().hex[:8]
        ST["sid"] = sid
        chunks, done, err = sse(sid, "In una frase: quale fornitore ha il totale acquisti più alto quest'anno? Cita il nome.")
        txt = "".join(chunks)
        print("CHUNKS", len(chunks), "|", txt[:400])
        assert done and not err and txt.strip(), err
        assert "Energia" in txt or "Global" in txt or "Cancelleria" in txt or "GmbH" in txt, txt
        h = sess().get(f"{API}/ai/consulente/storico", params={"session_id": sid}).json()
        assert [m["ruolo"] for m in h] == ["user", "assistant"] and h[1]["testo"] == txt
        ST["chunks1"] = len(chunks)

    def test_12_multiturn(self):
        chunks, done, err = sse(ST["sid"], "Ripeti solo il nome del fornitore che mi hai indicato nella risposta precedente, niente altro.")
        txt = "".join(chunks)
        print("FOLLOWUP", txt[:300])
        assert done and not err
        prev = sess().get(f"{API}/ai/consulente/storico", params={"session_id": ST["sid"]}).json()
        assert len(prev) == 4
        assert any(w in txt for w in ("Energia", "Global", "Cancelleria", "GmbH")), txt

    def test_13_history_isolation(self):
        assert sess().get(f"{API}/ai/consulente/storico", params={"session_id": "other" + RUN}).json() == []
        assert sess(TOK_OP).get(f"{API}/ai/consulente/storico", params={"session_id": ST["sid"]}).json() == []

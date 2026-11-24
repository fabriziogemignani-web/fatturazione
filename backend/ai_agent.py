import asyncio
import hashlib
import json
import os
import re
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone, FileContentWithMimeType
except ImportError:  # libreria IA non installata: il resto del programma funziona
    LlmChat = UserMessage = TextDelta = StreamDone = FileContentWithMimeType = None

import ai_crediti

MODEL = ("gemini", "gemini-3-flash-preview")
SOGLIA = 0.7


def _key():
    k = os.environ.get("EMERGENT_LLM_KEY")
    if not k:
        raise HTTPException(503, f"Chiave IA non configurata sul server: aggiungere la riga EMERGENT_LLM_KEY=\"...\" nel file {os.environ.get('INVOIX_ENV_FILE', 'backend/.env')} e riavviare i servizi (riavvia.bat)")
    k = k.strip().strip('"').strip("'")
    if not k.startswith("sk-emergent-"):
        raise HTTPException(503, "Chiave IA non valida: deve iniziare con sk-emergent- (Emergent: Profilo - Universal Key). Reinserirla con imposta-chiave-ia.bat")
    return k


def _err_ia(ex: Exception) -> str:
    s = str(ex)
    if "AuthenticationError" in s or "API key" in s or "401" in s:
        return "Chiave IA rifiutata: controlla di aver copiato la Universal Key completa (Emergent: Profilo - Universal Key) e reinseriscila con imposta-chiave-ia.bat"
    if "budget" in s.lower() or "insufficient" in s.lower() or "402" in s:
        return "Credito della Universal Key esaurito: ricarica da Emergent (Profilo - Universal Key - Add Balance)"
    if "ServiceUnavailable" in s or "503" in s or "timeout" in s.lower():
        return "Servizio IA momentaneamente non disponibile: riprova tra qualche minuto"
    return s[:200]


def _now():
    return datetime.now(timezone.utc).isoformat()


def _json(txt: str) -> dict:
    m = re.search(r"\{.*\}", txt or "", re.S)
    if not m:
        raise ValueError("risposta IA non leggibile")
    return json.loads(m.group(0))


SYS_REG = ("Sei un contabile italiano esperto. Ricevi una fattura passiva (dati e righe) e il piano dei conti di costo. "
           "Scegli il sottoconto di costo pi\u00f9 adatto e il trattamento IVA. Rispondi SOLO con JSON: "
           '{"conto": "codice", "trattamento": "ordinario|reverse_charge|intra_ue|extra_ue|split_payment|esente", '
           '"detraibilita_iva": 0-100, "confidenza": 0-1, "motivo": "max 200 caratteri in italiano"}. '
           "Usa confidenza bassa (<0.7) se il conto \u00e8 incerto, se le righe sono generiche o se il trattamento IVA non \u00e8 coerente con i dati.")


class ChatIn(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=4000)


CONTI_RX = r"^(01\.0[1-8]|02\.0[1-8]|07|30\.0[6-9]|30\.14|31|40\.02)\."
CEE = [("01.01", "BI1 Costi di impianto e ampliamento"), ("01.02", "BI3 Diritti di brevetto e utilizzazione opere dell'ingegno"), ("01.03", "BI4 Concessioni, licenze, marchi"),
       ("01.04", "BI5 Avviamento"), ("01", "BI7 Altre immobilizzazioni immateriali"), ("02.01", "BII1 Terreni e fabbricati"), ("02.02", "BII2 Impianti e macchinario"),
       ("02.03", "BII3 Attrezzature industriali e commerciali"), ("02", "BII4 Altri beni"), ("07", "D Ratei e risconti attivi"), ("30.06", "B6 Materie prime, sussidiarie, di consumo e merci"),
       ("30.07", "B7 Servizi"), ("30.08", "B8 Godimento di beni di terzi"), ("30.09", "B9 Personale"), ("30.14", "B14 Oneri diversi di gestione"), ("31", "B Costi della produzione"),
       ("40.02", "C17 Interessi e altri oneri finanziari")]
SYS_RIGHE = ("Sei un contabile italiano esperto di bilancio civilistico (artt. 2424 e 2425 c.c., principi OIC). Ricevi le righe di una fattura passiva e il piano dei conti "
             "con la voce di bilancio CEE di ogni sottoconto. Per OGNI riga scegli il sottoconto più corretto secondo la natura della spesa: "
             "B6 acquisti di beni (merci, materie, materiali di consumo, carburanti, cancelleria); B7 servizi (utenze, consulenze, manutenzioni, trasporti, assicurazioni, pubblicità, telefonia, compensi professionali); "
             "B8 godimento beni di terzi (affitti, noleggi, canoni di leasing, software in abbonamento); B14 oneri diversi (imposte indirette, bolli, quote associative, sanzioni); "
             "C17 interessi e commissioni su finanziamenti; immobilizzazioni (BI/BII) per beni o diritti di utilità pluriennale (macchinari, attrezzature, mobili, PC, automezzi, software in licenza perpetua); "
             "i beni strumentali di costo unitario fino a 516,46 euro possono andare a costo (B6). Preferisci i conti già usati con lo stesso fornitore se coerenti. "
             'Rispondi SOLO con JSON: {"righe": [{"n": numero riga, "conto": "codice esatto dal piano", "motivo": "voce CEE e motivo in max 120 caratteri"}]}')


def voce_cee(codice: str) -> str:
    return next((v for p, v in CEE if codice == p or codice.startswith(p + ".")), "")


def chiave(desc: str) -> str:
    return " ".join(re.sub(r"[^a-zà-ù ]+", " ", (desc or "").lower()).split())[:80]


def _stessa(x: dict, rr: dict) -> bool:
    a = float(rr.get("aliquota") or 0)
    return float(x.get("aliquota") or 0) == a and (a or (x.get("natura") or None) == (rr.get("natura") or None))


def conti_finali(d: dict, riepilogo: list) -> dict:
    """Conto finale di ogni riga XML: quello proposto dall'IA se confermato, altrimenti l'unico conto usato per la sua aliquota."""
    ia = {x["n"]: x.get("conto") for x in (d.get("ai_righe") or {}).get("righe") or []}
    out = {}
    for x in d.get("lines") or []:
        fin = {rr.get("conto") for rr in riepilogo if rr.get("conto") and _stessa(x, rr)}
        prop = ia.get(x.get("n"))
        c = prop if prop in fin else (next(iter(fin)) if len(fin) == 1 else None)
        if c:
            out[x.get("n")] = c
    return out


async def impara(db, cid: str, d: dict, riepilogo: list, by: str):
    """Memorizza per fornitore il conto finale di ogni riga, segnando le correzioni rispetto alla proposta IA."""
    ia = {x["n"]: x.get("conto") for x in (d.get("ai_righe") or {}).get("righe") or []}
    fin = conti_finali(d, riepilogo)
    for x in d.get("lines") or []:
        k = chiave(x.get("descrizione"))
        prop, conto = ia.get(x.get("n")), fin.get(x.get("n"))
        if not k or not conto or not d.get("party_id"):
            continue
        await db.ai_regole_conti.update_one({"company_id": cid, "party_id": d["party_id"], "chiave": k},
                                            {"$set": {"conto": conto, "descrizione": (x.get("descrizione") or "")[:120], "conto_ia": prop, "corretto": bool(prop and prop != conto),
                                                      "fornitore": (d.get("fornitore") or {}).get("denominazione"), "updated_at": _now(), "by": by},
                                             "$inc": {"n": 1}}, upsert=True)


def ripartisci(riepilogo: list, righe: list) -> list:
    out = []
    for rr in riepilogo:
        w = {}
        for x in righe:
            if float(x.get("aliquota") or 0) == float(rr["aliquota"]) and (float(rr["aliquota"]) or (x.get("natura") or None) == (rr.get("natura") or None)) and x["conto"]:
                w[x["conto"]] = w.get(x["conto"], 0) + float(x["importo"] or 0)
        ws = sorted(((k, v) for k, v in w.items() if v > 0), key=lambda kv: -kv[1])
        tw = sum(v for _, v in ws)
        if not ws or tw <= 0:
            out.append({"aliquota": rr["aliquota"], "natura": rr.get("natura") or "", "imponibile": rr["imponibile"], "imposta": rr["imposta"], "conto": ""})
            continue
        ri, rt = rr["imponibile"], rr["imposta"]
        for i, (conto, v) in enumerate(ws):
            last = i == len(ws) - 1
            imp = round(ri if last else rr["imponibile"] * v / tw, 2)
            iva = round(rt if last else rr["imposta"] * v / tw, 2)
            ri, rt = round(ri - imp, 2), round(rt - iva, 2)
            out.append({"aliquota": rr["aliquota"], "natura": rr.get("natura") or "", "imponibile": imp, "imposta": iva, "conto": conto})
    return out


def build(db, tenant, tenant_accounting) -> APIRouter:
    r = APIRouter(prefix="/api/ai")

    async def _analizza(cid: str, d: dict, conti: list) -> dict:
        storico = await db.passive_invoices.find({"company_id": cid, "party_id": d.get("party_id"), "stato_reg": "registrata", "id": {"$ne": d["id"]}},
                                                 {"_id": 0, "ai_conto": 1, "riepilogo": 1}).sort("data", -1).to_list(5)
        righe = [{"descrizione": (x.get("descrizione") or "")[:160], "imponibile": x.get("prezzo_totale") or x.get("imponibile"), "aliquota": x.get("aliquota_iva", x.get("aliquota")), "natura": x.get("natura")}
                 for x in (d.get("lines") or d.get("righe") or [])[:25]]
        f = d.get("fornitore") or {}
        prompt = json.dumps({"fornitore": {k: f.get(k) for k in ("denominazione", "partita_iva", "paese_iva", "nazione")}, "tipo_documento": d.get("tipo_documento"),
                             "numero": d.get("numero"), "totale": d.get("totale"), "riepilogo_iva": d.get("riepilogo"), "righe": righe, "split_payment": d.get("split_payment"),
                             "conti_usati_in_passato": [x.get("ai_conto") for x in storico if x.get("ai_conto")], "piano_conti_costo": conti}, ensure_ascii=False, default=str)
        chat = LlmChat(api_key=_key(), session_id=f"reg-{d['id']}", system_message=SYS_REG).with_model(*MODEL)
        resp = await chat.send_message_with_tools(UserMessage(text=prompt))
        await ai_crediti.addebita(db, cid, resp.usage.total_tokens if resp.usage else 0, "registrazione")
        out = _json(resp.content)
        validi = {c["codice"] for c in conti}
        conf = float(out.get("confidenza") or 0)
        paese = f.get("paese_iva") or f.get("nazione") or "IT"
        incoerente = (out.get("trattamento") == "intra_ue" and paese == "IT") or (out.get("trattamento") == "ordinario" and paese != "IT")
        dubbia = conf < SOGLIA or out.get("conto") not in validi or incoerente
        return {"conto": out.get("conto") if out.get("conto") in validi else None, "trattamento": out.get("trattamento"), "detraibilita_iva": out.get("detraibilita_iva"),
                "confidenza": round(conf, 2), "motivo": (out.get("motivo") or "")[:300] + (" \u00b7 Trattamento IVA da verificare" if incoerente else ""),
                "dubbia": dubbia, "rivista": False, "at": _now(), "modello": MODEL[1]}

    async def _conti(cid):
        return await db.coa_accounts.find({"company_id": cid, "livello": 3, "codice": {"$regex": CONTI_RX}}, {"_id": 0, "codice": 1, "descrizione": 1}).to_list(800)

    async def _chiedi_ia(t: dict, d: dict, lines: list, conti: list, regole: list) -> dict:
        cid = t["cid"]
        ai_crediti.controlla(t["company"])
        storico = await db.passive_invoices.find({"company_id": cid, "party_id": d.get("party_id"), "stato_reg": "registrata", "id": {"$ne": d["id"]}},
                                                 {"_id": 0, "righe_costo": 1, "ai_conto": 1}).sort("data", -1).to_list(5)
        usati = sorted({x["conto"] for s in storico for x in s.get("righe_costo") or [] if x.get("conto")} | {s["ai_conto"] for s in storico if s.get("ai_conto")})
        corr = await db.ai_regole_conti.find({"company_id": cid, "corretto": True}, {"_id": 0, "descrizione": 1, "conto_ia": 1, "conto": 1}).sort("updated_at", -1).to_list(30)
        f = d.get("fornitore") or {}
        prompt = json.dumps({"fornitore": {k: f.get(k) for k in ("denominazione", "partita_iva", "nazione")}, "tipo_documento": d.get("tipo_documento"), "causale": (d.get("causale") or "")[:300],
                             "righe": [{"n": x["n"], "descrizione": (x.get("descrizione") or "")[:200], "quantita": x.get("quantita"), "importo": x.get("prezzo_totale"), "aliquota": x.get("aliquota")} for x in lines],
                             "conti_usati_in_passato_con_questo_fornitore": usati,
                             "scelte_dell_utente_con_questo_fornitore": [{"descrizione": x["descrizione"], "conto": x["conto"]} for x in regole[:40]],
                             "correzioni_dell_utente_alle_tue_proposte (seguile per righe simili)": [{"descrizione": x["descrizione"], "proposto": x.get("conto_ia"), "corretto": x["conto"]} for x in corr],
                             "piano_dei_conti": [{**c, "voce_cee": voce_cee(c["codice"])} for c in conti]}, ensure_ascii=False, default=str)
        try:
            chat = LlmChat(api_key=_key(), session_id=f"righe-{d['id']}-{uuid.uuid4().hex[:6]}", system_message=SYS_RIGHE).with_model(*MODEL)
            resp = await chat.send_message_with_tools(UserMessage(text=prompt))
            await ai_crediti.addebita(db, cid, resp.usage.total_tokens if resp.usage else 0, "registrazione")
            return _json(resp.content)
        except HTTPException:
            raise
        except Exception as ex:  # noqa: BLE001
            raise HTTPException(502, f"Classificazione IA non riuscita: {_err_ia(ex)}")

    @r.post("/passive/{pid}/conti")
    async def conti_righe(pid: str, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        d = await db.passive_invoices.find_one({"id": pid, "company_id": cid}, {"_id": 0, "xml_b64": 0})
        if not d:
            raise HTTPException(404, "Fattura ricevuta non trovata")
        lines = [x for x in d.get("lines") or [] if abs(x.get("prezzo_totale") or 0) > 0.004][:60]
        if not lines:
            raise HTTPException(400, "La fattura non ha righe da classificare")
        conti = await _conti(cid)
        if not conti:
            raise HTTPException(400, "Attiva la contabilità generale: serve il piano dei conti")
        regole = await db.ai_regole_conti.find({"company_id": cid, "party_id": d.get("party_id")}, {"_id": 0}).sort("updated_at", -1).to_list(300) if d.get("party_id") else []
        validi = {c["codice"] for c in conti}
        per_k = {x["chiave"]: x for x in regole if x["conto"] in validi}
        h = hashlib.sha1(json.dumps([lines, d.get("riepilogo"), [c["codice"] for c in conti], regole[0]["updated_at"] if regole else None], sort_keys=True, default=str).encode()).hexdigest()
        cache = d.get("ai_righe") or {}
        if cache.get("hash") != h:
            out = {"righe": []}
            if not all(chiave(x.get("descrizione")) in per_k for x in lines):
                out = await _chiedi_ia(t, d, lines, conti, regole)
            per_n = {int(x.get("n") or 0): x for x in out.get("righe") or [] if str(x.get("conto")) in validi}
            for x in lines:
                rg = per_k.get(chiave(x.get("descrizione")))
                if rg:
                    per_n[x["n"]] = {"conto": rg["conto"], "motivo": "Appreso dalle tue registrazioni precedenti" + (" (correzione)" if rg.get("corretto") else ""), "appreso": True}
            cache = {"hash": h, "at": _now(), "modello": MODEL[1], "righe": [{"n": x["n"], "descrizione": (x.get("descrizione") or "")[:120], "importo": x["prezzo_totale"], "aliquota": x.get("aliquota"),
                                                                    "natura": x.get("natura"), "conto": per_n.get(x["n"], {}).get("conto") or "", "motivo": (per_n.get(x["n"], {}).get("motivo") or "")[:200],
                                                                    "appreso": bool(per_n.get(x["n"], {}).get("appreso"))} for x in lines]}
            await db.passive_invoices.update_one({"id": pid, "company_id": cid}, {"$set": {"ai_righe": cache}})
        nomi = {c["codice"]: c["descrizione"] for c in conti}
        righe = [{**x, "conto_nome": nomi.get(x["conto"], ""), "voce_cee": voce_cee(x["conto"]) if x["conto"] else ""} for x in cache["righe"]]
        return {"riepilogo": ripartisci(d.get("riepilogo") or [], righe), "righe": righe, "at": cache["at"]}

    @r.post("/passive/analizza")
    async def analizza_tutte(t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        ai_crediti.controlla(t["company"])
        conti = await _conti(cid)
        if not conti:
            raise HTTPException(400, "Attiva la contabilit\u00e0 generale: serve il piano dei conti")
        docs = await db.passive_invoices.find({"company_id": cid, "stato_reg": "da_registrare", "ai_analisi": {"$exists": False}}, {"_id": 0, "xml_b64": 0}).to_list(10)
        res = {"analizzate": 0, "dubbie": 0, "errori": []}
        sem = asyncio.Semaphore(5)

        async def one(d):
            async with sem:
                c = await db.companies.find_one({"id": cid}, {"_id": 0, "ai_crediti": 1, "ai_attiva": 1})
                if ai_crediti.stato(c)["crediti"] <= 0:
                    return d, None, Exception("crediti IA esauriti")
                try:
                    return d, await _analizza(cid, d, conti), None
                except Exception as ex:  # noqa: BLE001
                    return d, None, Exception(_err_ia(ex))

        for d, a, ex in await asyncio.gather(*(one(d) for d in docs)):
            if ex:
                res["errori"].append(f"{d.get('numero')}: {str(ex)[:120]}")
                continue
            upd = {"ai_analisi": a, **({"ai_conto": a["conto"]} if a["conto"] else {})}
            if a.get("detraibilita_iva") is not None and 0 <= float(a["detraibilita_iva"]) <= 100 and not a["dubbia"]:
                upd["detraibilita_iva"] = float(a["detraibilita_iva"])
            await db.passive_invoices.update_one({"id": d["id"], "company_id": cid}, {"$set": upd})
            res["analizzate"] += 1
            res["dubbie"] += int(a["dubbia"])
        res["restanti"] = await db.passive_invoices.count_documents({"company_id": cid, "stato_reg": "da_registrare", "ai_analisi": {"$exists": False}})
        return res

    @r.get("/passive/dubbie")
    async def dubbie(t: dict = Depends(tenant)):
        return await db.passive_invoices.find({"company_id": t["cid"], "ai_analisi.dubbia": True, "ai_analisi.rivista": {"$ne": True}},
                                              {"_id": 0, "id": 1, "numero": 1, "data": 1, "totale": 1, "fornitore.denominazione": 1, "ai_analisi": 1, "ai_conto": 1, "stato_reg": 1}).sort("data", -1).to_list(200)

    @r.post("/passive/{pid}/rivista")
    async def rivista(pid: str, t: dict = Depends(tenant_accounting)):
        r_ = await db.passive_invoices.update_one({"id": pid, "company_id": t["cid"], "ai_analisi": {"$exists": True}}, {"$set": {"ai_analisi.rivista": True, "ai_analisi.rivista_da": t["user"].get("name") or t["user"]["email"]}})
        if not r_.matched_count:
            raise HTTPException(404, "Documento non trovato")
        await db.coa_entries.update_many({"company_id": t["cid"], "origine": "acquisto", "ref_id": pid}, {"$unset": {"ai_dubbia": ""}})
        return {"ok": True}

    async def _contesto(cid: str, comp: dict) -> str:
        y = date.today().year
        def agg(coll, field, extra):
            return coll.aggregate([{"$match": {"company_id": cid, field: {"$regex": f"^{y}"}, **extra}},
                                   {"$group": {"_id": {"$substr": [f"${field}", 5, 2]}, "tot": {"$sum": {"$cond": [{"$eq": ["$tipo_documento", "TD04"]}, {"$multiply": ["$totale", -1]}, "$totale"]}}, "n": {"$sum": 1}}}, {"$sort": {"_id": 1}}])
        ven = [x async for x in agg(db.invoices, "data", {"status": {"$nin": ["bozza", "scartata"]}})]
        acq = [x async for x in agg(db.passive_invoices, "data", {})]
        top = [x async for x in db.invoices.aggregate([{"$match": {"company_id": cid, "data": {"$regex": f"^{y}"}, "status": {"$nin": ["bozza", "scartata"]}}},
                                                       {"$group": {"_id": "$cliente.denominazione", "tot": {"$sum": "$totale"}}}, {"$sort": {"tot": -1}}, {"$limit": 8}])]
        topf = [x async for x in db.passive_invoices.aggregate([{"$match": {"company_id": cid, "data": {"$regex": f"^{y}"}}},
                                                                {"$group": {"_id": "$fornitore.denominazione", "tot": {"$sum": "$totale"}}}, {"$sort": {"tot": -1}}, {"$limit": 8}])]
        saldi = [x async for x in db.coa_entries.aggregate([{"$match": {"company_id": cid, "anno": y, "provvisoria": {"$ne": True}}}, {"$unwind": "$righe"},
                                                             {"$group": {"_id": {"$substr": ["$righe.conto", 0, 2]}, "dare": {"$sum": "$righe.dare"}, "avere": {"$sum": "$righe.avere"}}}, {"$sort": {"_id": 1}}])]
        return json.dumps({"azienda": comp.get("denominazione"), "anno": y, "oggi": date.today().isoformat(), "vendite per mese (_id = mese)": ven, "acquisti per mese (_id = mese)": acq,
                           "clienti principali (_id = nome cliente, tot = fatturato)": top, "fornitori principali (_id = nome fornitore, tot = acquisti)": topf, "saldi contabili per mastro": saldi}, ensure_ascii=False, default=str)

    @r.get("/consulente/storico")
    async def storico(session_id: str, t: dict = Depends(tenant)):
        return await db.ai_chat.find({"company_id": t["cid"], "user_id": t["user"]["user_id"], "session_id": session_id}, {"_id": 0}).sort("at", 1).to_list(200)

    @r.post("/consulente/chat")
    async def chat(body: ChatIn, t: dict = Depends(tenant)):
        cid, uid = t["cid"], t["user"]["user_id"]
        ai_crediti.controlla(t["company"])
        prev = await db.ai_chat.find({"company_id": cid, "user_id": uid, "session_id": body.session_id}, {"_id": 0}).sort("at", 1).to_list(40)
        ctx = await _contesto(cid, t["company"])
        system = ("Sei un consulente aziendale e contabile italiano. Analizza i dati dell'azienda forniti (JSON) e rispondi in italiano, in modo concreto e sintetico, "
                  "con punti elenco, numeri e avvisi su liquidit\u00e0, andamento vendite/acquisti, concentrazione clienti, costi anomali. "
                  "Non inventare dati che non ci sono; se mancano dillo. Usa i nomi reali di clienti e fornitori presenti nei dati. Nella risposta non nominare chiavi tecniche, JSON o 'dati forniti'. "
                  "Scrivi in testo semplice senza markdown (niente asterischi o cancelletti), usa trattini per gli elenchi. "
                  "Saldi per mastro: 05 crediti v/clienti, 06 banca e cassa, 13 debiti v/fornitori, 20 ricavi, 30 costi. Ricorda che i consigli sono indicativi e non sostituiscono il commercialista.\nDATI: " + ctx)
        hist = "\n".join(f"{'Utente' if m['ruolo'] == 'user' else 'Consulente'}: {m['testo']}" for m in prev[-10:])
        llm = LlmChat(api_key=_key(), session_id=f"cons-{cid}-{uid}-{body.session_id}-{uuid.uuid4().hex[:6]}", system_message=system).with_model(*MODEL)
        text = (f"Conversazione precedente:\n{hist}\n\n" if hist else "") + f"Domanda: {body.message}"

        async def gen():
            buf = []
            try:
                async for ev in llm.stream_message(UserMessage(text=text)):
                    if isinstance(ev, TextDelta):
                        buf.append(ev.content)
                        yield f"data: {json.dumps({'t': ev.content})}\n\n"
                    elif isinstance(ev, StreamDone):
                        await ai_crediti.addebita(db, cid, ev.usage.total_tokens if ev.usage else 0, "consulente")
                        break
            except Exception as ex:  # noqa: BLE001
                yield f"data: {json.dumps({'error': _err_ia(ex)})}\n\n"
            if buf:
                await db.ai_chat.insert_many([{"company_id": cid, "user_id": uid, "session_id": body.session_id, "ruolo": "user", "testo": body.message, "at": _now()},
                                              {"company_id": cid, "user_id": uid, "session_id": body.session_id, "ruolo": "assistant", "testo": "".join(buf), "at": _now()}])
            yield "data: [DONE]\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return r

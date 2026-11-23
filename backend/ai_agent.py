import asyncio
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
        return await db.coa_accounts.find({"company_id": cid, "livello": 3, "codice": {"$regex": r"^(30|31|07)\."}}, {"_id": 0, "codice": 1, "descrizione": 1}).to_list(800)

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

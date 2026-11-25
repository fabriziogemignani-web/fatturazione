import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import ai_agent
import ai_crediti
from ai_agent import LlmChat, UserMessage, TextDelta, StreamDone

MANUALE = json.loads((Path(__file__).parent / "manuale.json").read_text(encoding="utf-8"))


class AssistenteIn(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=4000)
    pagina: str = Field(default="", max_length=200)
    errori: list[str] = Field(default_factory=list, max_length=5)


def capitoli(role: str) -> list:
    return [c for c in MANUALE if not c.get("ruolo") or role in ("admin", "contabile")]


def testo_manuale(role: str) -> str:
    return "\n\n".join(f"## {c['titolo']}\n" + "\n".join(f"### {s['t']}\n" + "\n".join(s["p"]) for s in c["sezioni"]) for c in capitoli(role))


def build(db, tenant) -> APIRouter:
    r = APIRouter(prefix="/api")

    @r.get("/guida")
    async def guida(t: dict = Depends(tenant)):
        return capitoli(t["user"].get("role"))

    @r.get("/ai/assistente/storico")
    async def storico(session_id: str, t: dict = Depends(tenant)):
        return await db.ai_assistente.find({"company_id": t["cid"], "user_id": t["user"]["user_id"], "session_id": session_id}, {"_id": 0}).sort("at", 1).to_list(200)

    @r.post("/ai/assistente/chat")
    async def chat(body: AssistenteIn, t: dict = Depends(tenant)):
        cid, uid, role = t["cid"], t["user"]["user_id"], t["user"].get("role") or "operatore"
        ai_crediti.controlla(t["company"])
        prev = await db.ai_assistente.find({"company_id": cid, "user_id": uid, "session_id": body.session_id}, {"_id": 0}).sort("at", 1).to_list(40)
        system = ("Sei l'assistente di supporto del gestionale Invoix (fatturazione elettronica, contabilita, magazzino, tesoreria). Rispondi in italiano, in modo semplice e pratico, "
                  "con i passi numerati da seguire nel programma (menu → voce → pulsante). Basati SOLO sul manuale qui sotto: se una cosa non c'e, dillo e suggerisci di chiedere all'amministratore. "
                  "Considera gli 'ultimi errori mostrati a schermo' solo se la domanda riguarda un errore o un problema, altrimenti ignorali. "
                  "Quando l'utente riporta un errore spiega cosa significa, la causa probabile e come risolverlo; se sembra un difetto del programma (errore 500, 'Errore imprevisto', pagina bianca) dillo e indica cosa riferire all'assistenza (pagina, operazione, testo dell'errore). "
                  f"Il ruolo dell'utente e '{role}': non suggerire funzioni riservate ad altri ruoli senza dirlo. Non chiedere mai password. Testo semplice senza markdown (niente asterischi o cancelletti), trattini per gli elenchi.\n\nMANUALE:\n" + testo_manuale(role))
        hist = "\n".join(f"{'Utente' if m['ruolo'] == 'user' else 'Assistente'}: {m['testo']}" for m in prev[-10:])
        ctx = f"Pagina aperta: {body.pagina or 'sconosciuta'}\n" + ("Ultimi errori mostrati a schermo:\n" + "\n".join(f"- {e[:300]}" for e in body.errori) + "\n" if body.errori else "")
        llm = LlmChat(api_key=ai_agent._key(), session_id=f"help-{cid}-{uid}-{body.session_id}-{uuid.uuid4().hex[:6]}", system_message=system).with_model(*ai_agent.MODEL)
        text = (f"Conversazione precedente:\n{hist}\n\n" if hist else "") + ctx + f"Domanda: {body.message}"

        async def gen():
            buf = []
            try:
                async for ev in llm.stream_message(UserMessage(text=text)):
                    if isinstance(ev, TextDelta):
                        buf.append(ev.content)
                        yield f"data: {json.dumps({'t': ev.content})}\n\n"
                    elif isinstance(ev, StreamDone):
                        await ai_crediti.addebita(db, cid, ev.usage.total_tokens if ev.usage else 0, "assistente")
                        break
            except Exception as ex:  # noqa: BLE001
                yield f"data: {json.dumps({'error': ai_agent._err_ia(ex)})}\n\n"
            if buf:
                now = ai_agent._now()
                await db.ai_assistente.insert_many([{"company_id": cid, "user_id": uid, "session_id": body.session_id, "ruolo": "user", "testo": body.message, "pagina": body.pagina, "at": now},
                                                    {"company_id": cid, "user_id": uid, "session_id": body.session_id, "ruolo": "assistant", "testo": "".join(buf), "at": now}])
            yield "data: [DONE]\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return r

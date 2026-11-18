import asyncio
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2] / "backend"
env = next((dotenv_values(ROOT / n) for n in (".env", ".env.txt") if (ROOT / n).is_file()), {})
k = (env.get("EMERGENT_LLM_KEY") or "").strip().strip('"')
print(f"File: {ROOT / '.env'}")
if not k:
    raise SystemExit("EMERGENT_LLM_KEY assente: eseguire imposta-chiave-ia.bat")
print(f"Chiave trovata: {k[:12]}...{k[-4:]} ({len(k)} caratteri)")
if not k.startswith("sk-emergent-"):
    raise SystemExit("La chiave non inizia con sk-emergent-: non e' la Universal Key di Emergent")


async def prova():
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    c = LlmChat(api_key=k, session_id="test-ia", system_message="Rispondi in italiano.").with_model("gemini", "gemini-3-flash-preview")
    print("Risposta IA:", (await c.send_message(UserMessage(text="Rispondi solo: collegamento riuscito")))[:80])

try:
    asyncio.run(prova())
except Exception as e:  # noqa: BLE001
    print("ERRORE:", str(e)[:400])

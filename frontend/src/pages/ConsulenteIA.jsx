import { useEffect, useRef, useState } from "react";
import { Send, Sparkles, Plus } from "lucide-react";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { AiCreditiBanner } from "@/components/AiCreditiBanner";

const SUGG = ["Come sta andando l'azienda quest'anno?", "Ci sono rischi di liquidità?", "Quali clienti pesano troppo sul fatturato?", "Quali costi stanno crescendo?"];
const newSid = () => Math.random().toString(36).slice(2, 12);

export default function ConsulenteIA() {
  const [sid, setSid] = useState(() => localStorage.getItem("fe_ai_sid") || newSid());
  const [msgs, setMsgs] = useState([]);
  const [txt, setTxt] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef(null);
  useEffect(() => {
    localStorage.setItem("fe_ai_sid", sid);
    let alive = true;
    api.get("/ai/consulente/storico", { params: { session_id: sid } }).then(({ data }) => { if (alive) setMsgs((x) => (x.length ? x : data)); }).catch(() => {});
    return () => { alive = false; };
  }, [sid]);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);
  const send = async (q) => {
    const m = (q || txt).trim();
    if (!m || busy) return;
    setTxt(""); setBusy(true);
    setMsgs((x) => [...x, { ruolo: "user", testo: m }, { ruolo: "assistant", testo: "" }]);
    try {
      const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/ai/consulente/chat`, {
        method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-Requested-With": "invoix", ...(localStorage.getItem("fe_company_id") ? { "X-Company-Id": localStorage.getItem("fe_company_id") } : {}) }, body: JSON.stringify({ session_id: sid, message: m }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Errore del consulente");
      const rd = res.body.getReader(); const dec = new TextDecoder(); let buf = "";
      for (;;) {
        const { value, done } = await rd.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const parts = buf.split("\n\n"); buf = parts.pop();
        for (const p of parts) {
          const s = p.replace(/^data: /, "");
          if (s === "[DONE]") continue;
          const j = JSON.parse(s);
          setMsgs((x) => { if (!x.length) return x; const y = [...x]; y[y.length - 1] = { ...y[y.length - 1], testo: y[y.length - 1].testo + (j.t || (j.error ? `\n[Errore: ${j.error}]` : "")) }; return y; });
        }
      }
    } catch (e) {
      setMsgs((x) => { if (!x.length) return x; const y = [...x]; y[y.length - 1] = { ruolo: "assistant", testo: `Errore: ${e.message}` }; return y; });
    }
    setBusy(false);
  };
  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col">
      <PageHeader eyebrow="Intelligenza artificiale" title="Consulente IA">
        <Button variant="outline" disabled={busy} onClick={() => { setSid(newSid()); setMsgs([]); }} data-testid="ai-new-chat"><Plus className="mr-2 h-4 w-4" />Nuova conversazione</Button>
      </PageHeader>
      <p className="-mt-4 mb-3 text-xs text-slate-500">Legge vendite, acquisti, clienti, fornitori e saldi contabili dell'anno dell'azienda attiva. I consigli sono indicativi e non sostituiscono il commercialista.</p>
      <div className="flex-1 space-y-3 overflow-y-auto rounded-xl border border-slate-200 bg-white p-4" data-testid="ai-messages">
        {msgs.length === 0 && <div className="mb-3"><AiCreditiBanner /></div>}
        {msgs.length === 0 && <div className="flex flex-wrap gap-2">{SUGG.map((s) => <button key={s} onClick={() => send(s)} className="rounded-full border border-violet-200 bg-violet-50 px-3 py-1.5 text-xs text-violet-800 hover:bg-violet-100" data-testid="ai-suggestion">{s}</button>)}</div>}
        {msgs.map((m, i) => (
          <div key={i} className={`max-w-[85%] whitespace-pre-wrap rounded-xl px-4 py-2 text-sm ${m.ruolo === "user" ? "ml-auto bg-blue-600 text-white" : "bg-slate-100 text-slate-800"}`} data-testid={`ai-msg-${m.ruolo}`}>
            {m.ruolo !== "user" && <Sparkles className="mb-1 h-3.5 w-3.5 text-violet-600" />}{m.testo || (busy && i === msgs.length - 1 ? "Sto analizzando i dati…" : "")}
          </div>
        ))}
        <div ref={end} />
      </div>
      <div className="mt-3 flex gap-2">
        <Textarea value={txt} onChange={(e) => setTxt(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} placeholder="Chiedi qualcosa sull'andamento dell'azienda…" className="min-h-[44px] bg-white" data-testid="ai-input" />
        <Button onClick={() => send()} disabled={busy || !txt.trim()} data-testid="ai-send"><Send className="h-4 w-4" /></Button>
      </div>
    </div>
  );
}

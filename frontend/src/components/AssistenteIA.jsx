import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { Sparkles, Send, Plus, AlertTriangle } from "lucide-react";
import { api, ultimiErrori } from "@/lib/api";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

const SUGG = ["Come creo una nota di credito parziale?", "Come registro il pagamento di un fornitore?", "Come funzionano gli ordini sottoscorta?", "Come carico una rateizzazione?"];
const newSid = () => Math.random().toString(36).slice(2, 12);

const stream = async (body, onChunk) => {
  const cid = localStorage.getItem("fe_company_id");
  const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/ai/assistente/chat`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-Requested-With": "invoix", ...(cid ? { "X-Company-Id": cid } : {}) }, body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Assistente non disponibile");
  const rd = res.body.getReader(); const dec = new TextDecoder(); let buf = "";
  for (;;) {
    const { value, done } = await rd.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split("\n\n"); buf = parts.pop();
    parts.map((p) => p.replace(/^data: /, "")).filter((s) => s && s !== "[DONE]").forEach((s) => { const j = JSON.parse(s); onChunk(j.t || (j.error ? `\n[Errore: ${j.error}]` : "")); });
  }
};

const Bubble = ({ m, wait }) => (
  <div className={`max-w-[88%] whitespace-pre-wrap rounded-xl px-3.5 py-2 text-sm ${m.ruolo === "user" ? "ml-auto bg-blue-600 text-white" : "bg-white text-slate-800 shadow-sm ring-1 ring-slate-200"}`} data-testid={`assistente-msg-${m.ruolo}`}>
    {m.testo || (wait ? "Sto cercando la risposta…" : "")}
  </div>
);

const useChat = (pathname) => {
  const [sid, setSid] = useState(() => localStorage.getItem("fe_help_sid") || newSid());
  const [msgs, setMsgs] = useState([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    localStorage.setItem("fe_help_sid", sid);
    let alive = true;
    api.get("/ai/assistente/storico", { params: { session_id: sid } }).then(({ data }) => { if (alive) setMsgs((x) => (x.length ? x : data)); }).catch(() => {});
    return () => { alive = false; };
  }, [sid]);
  const last = (f) => setMsgs((x) => { const y = [...x]; y[y.length - 1] = f(y[y.length - 1]); return y; });
  const send = async (m) => {
    if (!m.trim() || busy) return;
    setBusy(true);
    setMsgs((x) => [...x, { ruolo: "user", testo: m }, { ruolo: "assistant", testo: "" }]);
    try { await stream({ session_id: sid, message: m, pagina: pathname, errori: ultimiErrori.slice(0, 5) }, (c) => last((z) => ({ ...z, testo: z.testo + c }))); }
    catch (e) { last(() => ({ ruolo: "assistant", testo: `Errore: ${e.message}` })); }
    setBusy(false);
  };
  return { msgs, busy, send, reset: () => { setSid(newSid()); setMsgs([]); } };
};

export const AssistenteIA = () => {
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const [txt, setTxt] = useState("");
  const { msgs, busy, send, reset } = useChat(pathname);
  const end = useRef(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, open]);
  const go = (m) => { setTxt(""); send(m); };
  return (
    <>
      <button onClick={() => setOpen(true)} title="Assistente IA: domande e errori" aria-label="Assistente IA"
        className="fixed bottom-[4.5rem] right-5 z-40 flex h-11 w-11 items-center justify-center rounded-full bg-violet-600 text-white shadow-lg transition-transform hover:scale-105 hover:bg-violet-700 print:hidden"
        data-testid="assistente-btn"><Sparkles className="h-5 w-5" /></button>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="right" className="flex w-full flex-col bg-slate-50 sm:max-w-lg" data-testid="assistente-sheet">
          <SheetHeader><SheetTitle className="flex items-center gap-2" data-testid="assistente-title"><Sparkles className="h-4 w-4 text-violet-600" />Assistente IA</SheetTitle></SheetHeader>
          <p className="text-xs text-slate-500">Domande sull'uso del programma e spiegazione degli errori. Risponde in base al manuale; non modifica i tuoi dati.</p>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" disabled={busy || !ultimiErrori.length} onClick={() => go(`Spiegami questo errore e come risolverlo: ${ultimiErrori[0]}`)} data-testid="assistente-errore-btn"><AlertTriangle className="mr-1.5 h-3.5 w-3.5 text-amber-600" />Spiega l'ultimo errore</Button>
            <Button size="sm" variant="ghost" disabled={busy} onClick={reset} data-testid="assistente-nuova-btn"><Plus className="mr-1.5 h-3.5 w-3.5" />Nuova conversazione</Button>
          </div>
          <div className="flex-1 space-y-2.5 overflow-y-auto rounded-xl border border-slate-200 bg-slate-100/60 p-3" data-testid="assistente-messages">
            {msgs.length === 0 && <div className="flex flex-wrap gap-2">{SUGG.map((s) => <button key={s} onClick={() => go(s)} className="rounded-full border border-violet-200 bg-violet-50 px-3 py-1.5 text-left text-xs text-violet-800 transition-colors hover:bg-violet-100" data-testid="assistente-suggerimento">{s}</button>)}</div>}
            {msgs.map((m, i) => <Bubble key={i} m={m} wait={busy && i === msgs.length - 1} />)}
            <div ref={end} />
          </div>
          <div className="flex gap-2">
            <Textarea value={txt} onChange={(e) => setTxt(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); go(txt); } }} placeholder="Scrivi una domanda o incolla un errore…" className="min-h-[44px] bg-white" data-testid="assistente-input" />
            <Button onClick={() => go(txt)} disabled={busy || !txt.trim()} className="bg-violet-600 hover:bg-violet-700" data-testid="assistente-send"><Send className="h-4 w-4" /></Button>
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
};

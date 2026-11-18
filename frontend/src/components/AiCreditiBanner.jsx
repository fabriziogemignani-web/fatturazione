import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Sparkles, ShoppingCart } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR } from "@/lib/fe";
import { useAuth, isAdmin } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";

export const useAiStato = () => {
  const [s, setS] = useState(null);
  const load = () => api.get("/ai/crediti").then(({ data }) => setS(data)).catch(() => setS(null));
  useEffect(() => { load(); }, []);
  return [s, load];
};

const fmtN = (n) => Number(n).toLocaleString("it-IT", { maximumFractionDigits: 1 });

export const AiCreditiBanner = () => {
  const [s] = useAiStato();
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState("");
  if (!s) return null;
  const low = s.crediti <= 20;
  const buy = async (p) => {
    setBusy(p.id);
    try {
      const { data } = await api.post("/ai/crediti/checkout", { pacchetto_id: p.id, origin_url: window.location.origin });
      window.location.href = data.checkout_url;
    } catch (e) { toast.error(errMsg(e)); setBusy(""); }
  };
  return (
    <div className={`mb-4 flex flex-wrap items-center gap-3 rounded-lg border px-3 py-2 text-sm ${low && s.attiva ? "border-rose-300 bg-rose-50" : "border-violet-200 bg-violet-50"}`} data-testid="ai-crediti-banner">
      <Sparkles className="h-4 w-4 text-violet-600" />
      <span className="text-slate-700">
        {s.attiva ? <>Crediti IA: <b className={low ? "text-rose-700" : "text-violet-800"} data-testid="ai-crediti-saldo">{fmtN(s.crediti)}</b> <span className="text-xs text-slate-500">(1 credito = {fmtN(s.token_per_credito)} token)</span>{s.crediti <= 0 && <b className="ml-2 text-rose-700">IA ferma: ricarica per riattivarla</b>}</>
          : <span data-testid="ai-crediti-disattiva">IA disattivata per questa azienda: le fatture si registrano con le regole impostate.</span>}
      </span>
      {s.attiva && <Button size="sm" className="ml-auto h-7 bg-violet-600 hover:bg-violet-700" onClick={() => setOpen(true)} data-testid="ai-crediti-acquista-btn"><ShoppingCart className="mr-1 h-3.5 w-3.5" />Acquista crediti</Button>}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid="ai-crediti-dialog">
          <DialogHeader>
            <DialogTitle>Acquista crediti IA</DialogTitle>
            <DialogDescription>{s.venditore ? `Venduti da ${s.venditore}. Pagamento con carta, i crediti si caricano appena il pagamento è confermato.` : "Il produttore del software non ha ancora configurato i pacchetti."}</DialogDescription>
          </DialogHeader>
          {!isAdmin(user) && <p className="text-sm text-amber-700" data-testid="ai-crediti-solo-admin">Solo un amministratore può acquistare crediti.</p>}
          <div className="grid gap-2 sm:grid-cols-3">
            {s.pacchetti.map((p) => (
              <button key={p.id} type="button" disabled={!isAdmin(user) || !!busy} onClick={() => buy(p)}
                className="rounded-lg border border-violet-200 p-3 text-left transition-colors hover:border-violet-500 hover:bg-violet-50 disabled:opacity-50" data-testid={`ai-pacchetto-${p.id}`}>
                <div className="text-xs font-semibold uppercase text-violet-700">{p.nome}</div>
                <div className="text-lg font-bold text-slate-900">{fmtN(p.crediti)} crediti</div>
                <div className="text-sm text-slate-600">{busy === p.id ? "Apertura pagamento..." : fmtEUR(p.prezzo)}</div>
              </button>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

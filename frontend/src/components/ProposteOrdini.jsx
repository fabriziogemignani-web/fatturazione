import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ClipboardCheck, PackagePlus, X } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { Button } from "@/components/ui/button";
import { OrdineDialog } from "@/components/OrdineDialog";

const stima = (p) => p.lines.reduce((s, l) => s + l.quantita * (l.prezzo_unitario || 0), 0);

export const ProposteOrdini = ({ compatto, onChange }) => {
  const [list, setList] = useState(null);
  const [rev, setRev] = useState(null);
  const load = useCallback(() => { api.get("/ordini-proposte").then(({ data }) => setList(data)).catch(() => setList([])); }, []);
  useEffect(() => { load(); }, [load]);
  const scarta = async (p) => {
    if (!window.confirm(`Scartare la proposta per ${p.fornitore || "fornitore non indicato"}? Verrà riproposta da domani se gli articoli restano sottoscorta.`)) return;
    try { await api.post(`/ordini-proposte/${p.id}/scarta`); toast.success("Proposta scartata"); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  if (!list || (compatto && !list.length)) return null;
  return (
    <section className={`rounded-2xl border border-amber-200 bg-amber-50/60 ${compatto ? "" : "mb-6"} p-4 fade-up`} data-testid="proposte-ordini">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 font-semibold text-amber-900"><PackagePlus className="h-4 w-4" />{list.length ? `${list.length} ${list.length === 1 ? "nuovo ordine" : "nuovi ordini"} a fornitore da confermare` : "Pianificazione ordini a fornitore"}</h3>
        {compatto ? <Link to="/ordini-fornitori" className="text-xs font-semibold text-amber-900 underline" data-testid="proposte-vai">Vai agli ordini fornitori</Link>
          : <span className="text-xs text-amber-800">Generati in automatico dagli articoli sottoscorta (fino alla scorta minima, arrotondati al lotto di riordino)</span>}
      </div>
      {list.length === 0 ? <p className="text-sm text-amber-800" data-testid="proposte-vuote">Nessun articolo da riordinare.</p> : (
        <ul className="divide-y divide-amber-100 rounded-xl bg-white">
          {list.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-sm" data-testid={`proposta-ord-${p.id}`}>
              <div className="min-w-0">
                <div className="font-semibold text-slate-900">{p.fornitore || "Fornitore abituale non indicato"}{!p.party_id && <span className="ml-2 text-xs font-normal text-amber-700">scegli il fornitore in conferma</span>}</div>
                <div className="truncate text-xs text-slate-500">{p.lines.map((l) => `${l.codice} × ${l.quantita}`).join(" · ")}</div>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-500">{fmtDate(p.updated_at)} · stima <b className="text-slate-800">{fmtEUR(stima(p))}</b></span>
                <Button size="sm" onClick={() => setRev(p)} data-testid={`proposta-ord-conferma-${p.id}`}><ClipboardCheck className="mr-1 h-3.5 w-3.5" />Rivedi e conferma</Button>
                <Button size="sm" variant="ghost" onClick={() => scarta(p)} title="Scarta" data-testid={`proposta-ord-scarta-${p.id}`}><X className="h-4 w-4" /></Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      <OrdineDialog tipo="fornitore" bozza={rev} open={!!rev} submitUrl={rev ? `/ordini-proposte/${rev.id}/conferma` : undefined} onOpenChange={(v) => !v && setRev(null)}
        onSaved={() => { setRev(null); load(); onChange?.(); }} />
    </section>
  );
};

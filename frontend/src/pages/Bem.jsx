import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Undo2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";

export default function Bem() {
  const [rows, setRows] = useState(null);
  const load = () => api.get("/bem").then(({ data }) => setRows(data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, []);
  const annulla = async (b) => {
    if (!window.confirm(`Annullare l'entrata merce ${b.numero_display}? Il carico di magazzino viene stornato e l'ordine torna da evadere.`)) return;
    try { await api.post(`/bem/${b.id}/annulla`); toast.success("Entrata merce annullata"); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div data-testid="bem-page">
      <PageHeader eyebrow="Acquisti" title="Entrate merce (BEM)" subtitle="Bolle di entrata merce generate dall'evasione degli ordini fornitori: caricano il magazzino al costo dell'ordine" />
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm" data-testid="bem-table">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500"><tr><th className="px-4 py-3">BEM</th><th className="px-4 py-3">Fornitore</th><th className="px-4 py-3">DDT fornitore</th><th className="px-4 py-3">Ordine</th><th className="px-4 py-3">Articoli</th><th className="px-4 py-3 text-right">Imponibile</th><th /></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {rows?.length === 0 && <tr><td colSpan={7} className="px-4 py-10 text-center text-slate-500" data-testid="bem-empty">Nessuna entrata merce: evadi un ordine fornitore per crearne una</td></tr>}
            {rows?.map((b) => (
              <tr key={b.id} className={b.status === "annullato" ? "text-slate-400" : ""} data-testid={`bem-row-${b.id}`}>
                <td className="px-4 py-3"><div className="mono text-xs font-semibold">{b.numero_display}</div><div className="text-xs">{fmtDate(b.data)}</div></td>
                <td className="px-4 py-3">{b.fornitore.denominazione}</td>
                <td className="px-4 py-3">{b.documento_fornitore || "—"}</td>
                <td className="mono px-4 py-3 text-xs">{b.ordine_numero}</td>
                <td className="px-4 py-3 text-xs">{b.lines.map((l) => `${l.quantita} × ${l.codice || l.descrizione.slice(0, 30)}`).join(", ")}</td>
                <td className="px-4 py-3 text-right">{fmtEUR(b.imponibile)}</td>
                <td className="px-4 py-3 text-right">{b.status === "annullato" ? <span className="text-xs font-semibold text-rose-600" data-testid={`bem-annullata-${b.id}`}>Annullata</span>
                  : <Button size="sm" variant="outline" onClick={() => annulla(b)} data-testid={`bem-annulla-${b.id}`}><Undo2 className="mr-1 h-3.5 w-3.5" />Annulla</Button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

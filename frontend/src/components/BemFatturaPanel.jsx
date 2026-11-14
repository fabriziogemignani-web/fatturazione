import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { PackageCheck, Link2, Unlink, CheckCircle2, AlertTriangle } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { Button } from "@/components/ui/button";

const ESITO = { ok: ["OK", "text-emerald-700"], quantita: ["Quantità diversa", "text-rose-700"], prezzo: ["Prezzo diverso", "text-amber-700"], mancante: ["Non in fattura", "text-rose-700"] };

const Confronto = ({ c }) => (
  <div className="mt-3" data-testid="bem-confronto">
    <div className={`mb-2 flex items-center gap-2 text-sm font-semibold ${c.tutto_ok ? "text-emerald-700" : "text-amber-700"}`} data-testid="bem-confronto-esito">
      {c.tutto_ok ? <CheckCircle2 className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
      {c.tutto_ok ? "Fattura coerente con merce ricevuta e prezzi d'ordine" : `Differenze da verificare · imponibile fattura ${fmtEUR(c.imponibile_fattura)} vs entrate merce ${fmtEUR(c.imponibile_bem)} (${fmtEUR(c.differenza)})`}
    </div>
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead className="text-left text-slate-500"><tr><th className="py-1">Articolo</th><th className="text-right">Q.tà ricevuta</th><th className="text-right">Q.tà fattura</th><th className="text-right">Prezzo ordine</th><th className="text-right">Prezzo fattura</th><th className="pl-2">Esito</th></tr></thead>
        <tbody>
          {c.righe.map((r, i) => (
            <tr key={i} className="border-t border-slate-100" data-testid={`bem-conf-row-${i}`}>
              <td className="py-1">{r.codice && <span className="mono">{r.codice} · </span>}{r.descrizione} <span className="text-slate-400">({r.bem})</span></td>
              <td className="text-right">{r.qta_bem}</td><td className="text-right">{r.qta_fattura ?? "—"}</td>
              <td className="text-right">{fmtEUR(r.prezzo_ordine)}</td><td className="text-right">{r.prezzo_fattura == null ? "—" : fmtEUR(r.prezzo_fattura)}</td>
              <td className={`pl-2 font-semibold ${ESITO[r.esito][1]}`} data-testid={`bem-conf-esito-${i}`}>{ESITO[r.esito][0]}</td>
            </tr>
          ))}
          {c.extra_fattura.map((x, i) => <tr key={`x${i}`} className="border-t border-slate-100 text-amber-700"><td className="py-1">{x.descrizione}</td><td className="text-right">—</td><td className="text-right">{x.qta_fattura}</td><td /><td className="text-right">{fmtEUR(x.importo)}</td><td className="pl-2 font-semibold">Solo in fattura</td></tr>)}
        </tbody>
      </table>
    </div>
  </div>
);

const BemRow = ({ b, action }) => (
  <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 py-2 text-sm" data-testid={`bem-link-row-${b.id}`}>
    <span className="mono text-xs font-semibold">BEM {b.numero_display}</span><span className="text-xs text-slate-500">{fmtDate(b.data)} · ordine {b.ordine_numero}{b.documento_fornitore ? ` · DDT forn. ${b.documento_fornitore}` : ""}</span>
    <span className="ml-auto font-semibold">{fmtEUR(b.imponibile)}</span>{action}
  </div>
);

export const BemFatturaPanel = ({ pid }) => {
  const [d, setD] = useState(null);
  useEffect(() => { api.get(`/passive/${pid}/bem`).then(({ data }) => setD(data)).catch(() => setD(null)); }, [pid]);
  const run = (p) => p.then(({ data }) => { setD(data); toast.success("Aggiornato"); }).catch((e) => toast.error(errMsg(e)));
  if (!d || (!d.collegate.length && !d.candidate.length)) return null;
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" data-testid="bem-fattura-panel">
      <h3 className="mb-1 flex items-center gap-2 font-semibold text-slate-800"><PackageCheck className="h-4 w-4" />Entrate merce e ordini</h3>
      <p className="text-xs text-slate-500">Collega le entrate merce (BEM) di questo fornitore per controllare quantità e prezzi rispetto all'ordine. <Link to="/bem" className="text-blue-700 hover:underline">Vai alle BEM</Link></p>
      {d.collegate.map((b) => <BemRow key={b.id} b={b} action={<Button size="sm" variant="outline" onClick={() => run(api.delete(`/passive/${pid}/bem/${b.id}`))} data-testid={`bem-scollega-${b.id}`}><Unlink className="mr-1 h-3.5 w-3.5" />Scollega</Button>} />)}
      {d.candidate.length > 0 && <div className="mt-3 text-xs font-semibold uppercase tracking-wider text-amber-700" data-testid="bem-candidate-title">Da collegare ({d.candidate.length})</div>}
      {d.candidate.map((b) => <BemRow key={b.id} b={b} action={<Button size="sm" onClick={() => run(api.post(`/passive/${pid}/bem`, { bem_id: b.id }))} data-testid={`bem-collega-${b.id}`}><Link2 className="mr-1 h-3.5 w-3.5" />Collega</Button>} />)}
      {d.confronto && <Confronto c={d.confronto} />}
    </div>
  );
};

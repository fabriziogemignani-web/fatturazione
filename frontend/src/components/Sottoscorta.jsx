import { Link } from "react-router-dom";
import { AlertTriangle, PackagePlus } from "lucide-react";
import { Button } from "@/components/ui/button";

export const STATO_SCORTA = {
  esaurito: ["Esaurito", "bg-rose-50 text-rose-700 border-rose-200"],
  sottoscorta: ["Sottoscorta", "bg-amber-50 text-amber-700 border-amber-200"],
  ok: ["Disponibile", "bg-emerald-50 text-emerald-700 border-emerald-200"],
  zero: ["Giacenza zero", "bg-slate-50 text-slate-600 border-slate-200"],
};

export const ScortaBadge = ({ s, testId }) => {
  const [l, c] = STATO_SCORTA[s] || ["—", "bg-slate-50 text-slate-500 border-slate-200"];
  return <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${c}`} data-testid={testId}>{l}</span>;
};

export const SottoscortaSection = ({ rows, onCarico }) => (
  <section className="mb-6 rounded-xl border border-amber-200 bg-amber-50/40 p-5" data-testid="sottoscorta-section">
    <div className="mb-3 flex items-center justify-between gap-3">
      <h3 className="flex items-center gap-2 text-base font-semibold text-slate-900"><AlertTriangle className="h-5 w-5 text-amber-600" />Sottoscorta ({rows.length})</h3>
      <Link to="/magazzino" className="text-xs font-semibold text-blue-700 hover:underline" data-testid="sottoscorta-magazzino-link">Vai al magazzino →</Link>
    </div>
    {rows.length === 0 ? <p className="text-sm text-slate-600" data-testid="sottoscorta-empty">Nessun articolo sotto la scorta minima.</p> : (
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase tracking-wider text-slate-500"><tr>
            <th className="px-3 py-2">Articolo</th><th className="px-3 py-2 text-right">Giacenza</th><th className="px-3 py-2 text-right">Scorta minima</th>
            <th className="px-3 py-2 text-right">Da ordinare</th><th className="px-3 py-2">Fornitore abituale</th><th className="px-3 py-2" />
          </tr></thead>
          <tbody className="divide-y divide-amber-100">
            {rows.map((a) => (
              <tr key={a.id} data-testid={`sottoscorta-row-${a.id}`}>
                <td className="px-3 py-2"><span className="mono text-xs font-medium">{a.codice}</span> · {a.descrizione} <ScortaBadge s={a.stato_scorta} /></td>
                <td className="px-3 py-2 text-right font-semibold">{a.giacenza ?? 0} {a.unita_misura}</td>
                <td className="px-3 py-2 text-right">{a.scorta_minima} {a.unita_misura}</td>
                <td className="px-3 py-2 text-right font-bold text-amber-800" data-testid={`sottoscorta-qty-${a.id}`}>{a.da_ordinare} {a.unita_misura}</td>
                <td className="px-3 py-2 text-slate-600">{a.fornitore_abituale || "—"}</td>
                <td className="px-3 py-2 text-right">{onCarico && <Button size="sm" variant="outline" onClick={() => onCarico(a)} data-testid={`sottoscorta-carico-${a.id}`}><PackagePlus className="mr-1 h-3.5 w-3.5" />Carico</Button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )}
  </section>
);

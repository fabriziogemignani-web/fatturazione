import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { CalendarClock } from "lucide-react";
import { api } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";

export const ScadenzePanel = () => {
  const [d, setD] = useState(null);
  const navigate = useNavigate();
  useEffect(() => { api.get("/scadenzario").then(({ data }) => setD(data)); }, []);
  if (!d) return null;

  return (
    <div className="mt-6 rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm" data-testid="scadenze-panel">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-lg font-semibold text-slate-800"><CalendarClock className="h-5 w-5 text-blue-600" />Scadenze per cliente</h3>
          <p className="text-xs text-slate-500">Rate aperte al netto di incassi e note di credito</p>
        </div>
        <div className="flex gap-6 text-sm">
          <div><div className="text-xs text-slate-500">Scaduto</div><div className="font-bold text-rose-700" data-testid="sp-scaduto">{fmtEUR(d.totali.scaduto)}</div></div>
          <div><div className="text-xs text-slate-500">Entro 30 gg</div><div className="font-bold text-amber-700" data-testid="sp-entro30">{fmtEUR(d.totali.entro_30)}</div></div>
          <div><div className="text-xs text-slate-500">Totale aperto</div><div className="font-bold text-slate-900" data-testid="sp-aperto">{fmtEUR(d.totali.aperto)}</div></div>
        </div>
      </div>
      {d.clienti.length === 0 ? <p className="text-sm text-slate-500" data-testid="sp-empty">Nessuna scadenza aperta.</p> : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 text-left text-xs uppercase tracking-wider text-slate-500">
              <tr><th className="py-2 pr-3 font-medium">Cliente</th><th className="py-2 pr-3 text-right font-medium">Scaduto</th><th className="py-2 pr-3 text-right font-medium">Entro 30 gg</th><th className="py-2 pr-3 text-right font-medium">Oltre</th><th className="py-2 pr-3 text-right font-medium">Totale aperto</th><th className="py-2 pr-3 font-medium">Prossima</th><th className="py-2 text-right font-medium">Crediti NC</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {d.clienti.slice(0, 8).map((c) => (
                <tr key={c.party_id} className="cursor-pointer hover:bg-slate-50" onClick={() => navigate(`/scadenzario?cliente=${c.party_id}`)} data-testid={`sp-row-${c.party_id}`}>
                  <td className="py-2.5 pr-3 font-medium text-slate-800">{c.cliente}<span className="ml-2 text-xs text-slate-400">{c.rate_aperte} rate</span></td>
                  <td className={`py-2.5 pr-3 text-right font-semibold ${c.scaduto ? "text-rose-700" : "text-slate-400"}`}>{fmtEUR(c.scaduto)}</td>
                  <td className="py-2.5 pr-3 text-right">{fmtEUR(c.entro_30)}</td>
                  <td className="py-2.5 pr-3 text-right text-slate-600">{fmtEUR(c.oltre_30)}</td>
                  <td className="py-2.5 pr-3 text-right font-bold">{fmtEUR(c.aperto)}</td>
                  <td className="py-2.5 pr-3 text-slate-600">{c.prossima ? fmtDate(c.prossima) : "—"}</td>
                  <td className="py-2.5 text-right text-violet-700">{c.crediti ? fmtEUR(c.crediti) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Link to="/scadenzario" className="mt-4 inline-block text-xs font-semibold text-blue-600 hover:text-blue-800" data-testid="sp-open-link">Apri lo scadenzario completo →</Link>
    </div>
  );
};

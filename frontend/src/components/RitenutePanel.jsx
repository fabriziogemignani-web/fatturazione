import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Percent } from "lucide-react";
import { api } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";

export const RitenutePanel = () => {
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/ritenute/da-versare").then(({ data }) => setD(data)).catch(() => {}); }, []);
  if (!d) return null;
  return (
    <div className="mt-6 rounded-xl border border-slate-200 bg-white shadow-sm" data-testid="ritenute-panel">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-5 py-4">
        <div className="flex items-center gap-2"><Percent className="h-4 w-4 text-blue-600" /><h3 className="font-semibold text-slate-900">Ritenute d'acconto da versare</h3></div>
        <span className="text-sm font-semibold text-slate-900" data-testid="ritenute-panel-totale">{fmtEUR(d.totale)}</span>
      </div>
      {d.mesi.length === 0 ? <p className="px-5 py-6 text-sm text-slate-500" data-testid="ritenute-panel-empty">Nessuna ritenuta da versare.</p> : (
        <ul className="divide-y divide-slate-100">
          {d.mesi.map((m) => (
            <li key={m.key} data-testid={`ritenute-panel-${m.mese}`}>
              <Link to={`/ritenute?mese=${m.mese}`} className="flex flex-wrap items-center justify-between gap-2 px-5 py-3 text-sm transition-colors hover:bg-slate-50">
                <span>Compensi pagati a <b>{m.label}</b> · {m.fornitori} professionist{m.fornitori === 1 ? "a" : "i"}{m.provvisorio ? " · mese in corso" : ""}</span>
                <span className="flex items-center gap-3">
                  <span className={m.giorni < 0 ? "font-semibold text-rose-700" : m.giorni <= 5 ? "font-semibold text-amber-700" : "text-slate-500"}>{m.giorni < 0 ? "scaduta il" : "entro il"} {fmtDate(m.scadenza)}</span>
                  <b>{fmtEUR(m.importo)}</b>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Landmark } from "lucide-react";
import { api } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";

export const BankPanel = () => {
  const [d, setD] = useState(null);
  const [f, setF] = useState(null);
  useEffect(() => {
    api.get("/banca/riepilogo").then(({ data }) => setD(data)).catch(() => {});
    api.get("/banca/previsione", { params: { giorni: 90 } }).then(({ data }) => setF(data)).catch(() => {});
  }, []);
  if (!d || !d.conti.length) return null;
  return (
    <section className="mt-6 rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm" data-testid="bank-panel">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-lg font-semibold text-slate-800"><Landmark className="h-5 w-5 text-blue-600" />Banca</h3>
        <Link to="/riconciliazione" className="text-xs font-semibold text-blue-700 hover:underline" data-testid="bank-panel-link">
          {d.da_riconciliare ? `${d.da_riconciliare} movimenti da riconciliare →` : "Tutto riconciliato →"}
        </Link>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="rounded-lg bg-slate-900 p-4 text-white"><div className="text-xs text-slate-300">Saldo totale</div><div className="text-2xl font-extrabold" data-testid="bank-panel-total">{fmtEUR(d.saldo_totale)}</div>
          {f && <Link to="/previsione-cassa" className={`mt-1 block text-xs hover:underline ${f.minimo.saldo < 0 ? "text-rose-300" : "text-slate-300"}`} data-testid="bank-panel-forecast">Tra 90 giorni: {fmtEUR(f.saldo_finale)}{f.minimo.saldo < 0 ? ` · sotto zero dal ${fmtDate(f.minimo.data)}` : ""} →</Link>}</div>
        {d.conti.slice(0, 5).map((a) => (
          <div key={a.id} className="rounded-lg border border-slate-200 p-4" data-testid={`bank-panel-account-${a.id}`}>
            <div className="truncate text-xs text-slate-500">{a.nome}</div>
            <div className="text-lg font-bold text-slate-900">{a.saldo != null ? fmtEUR(a.saldo) : "—"}</div>
            <div className={`text-xs ${a.consenso_in_scadenza ? "text-amber-700" : "text-slate-500"}`}>{a.consenso_in_scadenza ? "consenso in scadenza" : `${a.da_riconciliare} da riconciliare`}</div>
          </div>
        ))}
      </div>
    </section>
  );
};

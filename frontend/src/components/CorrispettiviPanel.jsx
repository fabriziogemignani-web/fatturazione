import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Receipt } from "lucide-react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from "recharts";
import { api } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";

const Stat = ({ label, value, testId, sub }) => (
  <div><div className="text-xs text-slate-500">{label}</div><div className="font-bold text-slate-900" data-testid={testId}>{value}</div>{sub && <div className="text-[11px] text-slate-500">{sub}</div>}</div>
);

export const CorrispettiviPanel = () => {
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/corrispettivi/riepilogo").then(({ data }) => setD(data)).catch(() => {}); }, []);
  if (!d) return null;
  const chart = d.giorni.map((g) => ({ giorno: fmtDate(g.data).slice(0, 5), totale: g.totale }));

  return (
    <div className="mt-6 rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm" data-testid="corrispettivi-panel">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-lg font-semibold text-slate-800"><Receipt className="h-5 w-5 text-emerald-600" />Incassi da corrispettivi</h3>
          <p className="text-xs text-slate-500">Ultimi 30 giorni dal registratore telematico (ricezione simulata)</p>
        </div>
        <div className="flex gap-6 text-sm">
          <Stat label="Ultimo giorno" value={d.ultimo ? fmtEUR(d.ultimo.totale) : "—"} sub={d.ultimo && fmtDate(d.ultimo.data)} testId="cp-ultimo" />
          <Stat label="Mese corrente" value={fmtEUR(d.mese)} testId="cp-mese" />
          <Stat label={`Anno ${d.anno}`} value={fmtEUR(d.totale_anno)} testId="cp-anno" />
        </div>
      </div>
      {chart.length === 0 ? <p className="text-sm text-slate-500" data-testid="cp-empty">Nessun corrispettivo negli ultimi 30 giorni.</p> : (
        <div className="h-48" data-testid="cp-chart">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chart}>
              <CartesianGrid vertical={false} stroke="#e2e8f0" />
              <XAxis dataKey="giorno" tickLine={false} axisLine={false} fontSize={11} />
              <YAxis tickLine={false} axisLine={false} fontSize={11} width={60} />
              <Tooltip formatter={(v) => fmtEUR(v)} cursor={{ fill: "#f1f5f9" }} />
              <Bar dataKey="totale" fill="#059669" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      <Link to="/corrispettivi" className="mt-4 inline-block text-xs font-semibold text-blue-600 hover:text-blue-800" data-testid="cp-open-link">Apri il registro dei corrispettivi →</Link>
    </div>
  );
};

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "@/lib/api";
import { fmtEUR } from "@/lib/fe";
import { DCard } from "@/components/dashboard/Card";

const lab = (k) => new Date(`${k}-01T00:00:00`).toLocaleDateString("it-IT", { month: "short" });
const ax = (v) => (Math.abs(v) >= 1000 ? `€${Math.round(v / 1000).toLocaleString("it-IT")}k` : `€${Math.round(v)}`);

export const CashFlowWidget = () => {
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/situazione-finanziaria", { params: { mesi: 12 } }).then(({ data }) => setD(data)).catch(() => setD({ mesi: [] })); }, []);
  const rows = (d?.mesi || []).map((m) => ({ mese: lab(m.mese), Entrate: m.incasso, Uscite: m.fornitore + m.rateizzazione + (m.finanziamento || 0) + m.fisco, Saldo: m.saldo }));
  return (
    <DCard title="Flusso di cassa e previsioni" sub="Entrate e uscite in scadenza nei prossimi 12 mesi, con saldo previsto" testId="dash-cashflow"
      action={<Link to="/situazione-finanziaria" className="text-xs font-semibold text-blue-700 hover:underline" data-testid="dash-cashflow-link">Dettaglio</Link>}>
      <div className="h-72">
        {!d ? <div className="text-sm text-slate-500">Caricamento…</div> : (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows} margin={{ top: 8, right: 4, left: 0, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="#eef2f7" />
              <XAxis dataKey="mese" tickLine={false} axisLine={false} fontSize={11} stroke="#64748b" />
              <YAxis yAxisId="f" tickLine={false} axisLine={false} fontSize={11} width={56} stroke="#64748b" tickFormatter={ax} />
              <YAxis yAxisId="s" orientation="right" tickLine={false} axisLine={false} fontSize={11} width={60} stroke="#64748b" tickFormatter={ax} />
              <Tooltip formatter={(v, n) => [fmtEUR(v), n]} cursor={{ fill: "#f8fafc" }} />
              <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
              <ReferenceLine yAxisId="f" y={0} stroke="#cbd5e1" />
              <Bar yAxisId="f" dataKey="Entrate" fill="#1e3a8a" radius={[4, 4, 0, 0]} maxBarSize={18} />
              <Bar yAxisId="f" dataKey="Uscite" fill="#e5484d" radius={[0, 0, 4, 4]} maxBarSize={18} />
              <Line yAxisId="s" dataKey="Saldo" name="Saldo previsto" stroke="#0f766e" strokeWidth={2.5} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>
    </DCard>
  );
};

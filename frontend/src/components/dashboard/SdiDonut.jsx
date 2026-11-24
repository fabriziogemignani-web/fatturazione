import { Link } from "react-router-dom";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { STATUS } from "@/lib/fe";
import { DCard } from "@/components/dashboard/Card";

const COLORI = { inviata: "#1e3a8a", consegnata: "#0f9488", mancata_consegna: "#f5c04e", scartata: "#e5484d", manuale: "#94a3b8", bozza: "#cbd5e1" };

export const SdiDonut = ({ counts }) => {
  const rows = Object.keys(STATUS).map((k) => ({ k, name: STATUS[k].label, value: counts?.[k] || 0 })).filter((r) => r.value > 0);
  const tot = rows.reduce((s, r) => s + r.value, 0);
  return (
    <DCard title="Stato fatturazione e SDI" sub="Documenti per stato di invio" testId="dash-sdi">
      {tot === 0 ? <p className="py-10 text-center text-sm text-slate-500">Nessuna fattura ancora.</p> : (
        <div className="flex flex-col items-center gap-4 sm:flex-row">
          <div className="relative h-56 w-56 shrink-0">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={rows} dataKey="value" nameKey="name" innerRadius="58%" outerRadius="92%" paddingAngle={1.5} stroke="#fff" strokeWidth={2}>
                  {rows.map((r) => <Cell key={r.k} fill={COLORI[r.k]} />)}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center"><span className="text-2xl font-bold text-slate-900" data-testid="dash-sdi-totale">{tot}</span><span className="text-[11px] text-slate-500">documenti</span></div>
          </div>
          <ul className="w-full space-y-2 text-sm">
            {rows.map((r) => (
              <li key={r.k} data-testid={`dash-sdi-${r.k}`}>
                <Link to={`/fatture?status=${r.k}`} className="flex items-center justify-between gap-3 rounded-md px-2 py-1 hover:bg-slate-50">
                  <span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full" style={{ background: COLORI[r.k] }} />{r.name}</span>
                  <b className="tabular-nums text-slate-900">{r.value}</b>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </DCard>
  );
};

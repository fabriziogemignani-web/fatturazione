import { Link } from "react-router-dom";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from "recharts";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { StatusBadge } from "@/components/Common";
import { DCard } from "@/components/dashboard/Card";

const MESI = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"];

export const FatturatoMensile = ({ d }) => (
  <DCard title={`Fatturato mensile ${d.anno}`} sub="Fatture inviate, consegnate e in mancata consegna" testId="dash-fatturato-mensile">
    <div className="h-56">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={d.mesi.map((m) => ({ mese: MESI[m.mese - 1], totale: m.totale }))}>
          <CartesianGrid vertical={false} stroke="#eef2f7" />
          <XAxis dataKey="mese" tickLine={false} axisLine={false} fontSize={11} />
          <YAxis tickLine={false} axisLine={false} fontSize={11} width={60} />
          <Tooltip formatter={(v) => fmtEUR(v)} cursor={{ fill: "#f8fafc" }} />
          <Bar dataKey="totale" fill="#1e3a8a" radius={[4, 4, 0, 0]} maxBarSize={22} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  </DCard>
);

export const UltimeFatture = ({ d }) => (
  <DCard title="Ultime fatture" testId="dash-ultime-fatture" action={<Link to="/fatture" className="text-xs font-semibold text-blue-700 hover:underline">Vedi tutte</Link>}>
    {d.recenti.length === 0 ? <p className="text-sm text-slate-500">Nessuna fattura ancora.</p> : (
      <div className="-mx-5 divide-y divide-slate-100">
        {d.recenti.map((i) => (
          <Link key={i.id} to={`/fatture/${i.id}`} className="flex items-center justify-between gap-4 px-5 py-2.5 hover:bg-slate-50" data-testid={`recent-invoice-${i.id}`}>
            <div className="min-w-0"><div className="truncate text-sm font-semibold text-slate-900">{i.cliente?.denominazione}</div><div className="mono text-xs text-slate-500">N. {i.numero_display} · {fmtDate(i.data)}</div></div>
            <div className="flex items-center gap-3"><span className="hidden text-sm font-semibold sm:inline">{i.tipo_documento === "TD04" ? `- ${fmtEUR(i.totale)}` : fmtEUR(i.totale)}</span><StatusBadge status={i.status} /></div>
          </Link>
        ))}
      </div>
    )}
  </DCard>
);

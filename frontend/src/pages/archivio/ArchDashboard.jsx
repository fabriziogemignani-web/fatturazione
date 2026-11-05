import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { DocBadge } from "@/lib/archivio";
import { PageHeader } from "@/components/Common";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const MESI = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"];

const Kpi = ({ label, value, sub, testId }) => (
  <div className="rounded-xl border border-slate-200/80 bg-white p-5 shadow-sm">
    <div className="text-xs font-medium uppercase tracking-wider text-slate-500">{label}</div>
    <div className="mt-2 text-2xl font-bold text-slate-900" data-testid={testId}>{value}</div>
    {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
  </div>
);

export default function ArchDashboard() {
  const [anno, setAnno] = useState("all");
  const [anni, setAnni] = useState([]);
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/archivio/years").then(({ data }) => setAnni(data)); }, []);
  useEffect(() => { api.get("/archivio/stats", { params: anno === "all" ? {} : { anno } }).then(({ data }) => setD(data)); }, [anno]);
  if (!d) return <div className="text-sm text-slate-500">Caricamento…</div>;
  const a = d.per_tipo.attiva || { n: 0, totale: 0, imposta: 0 };
  const p = d.per_tipo.passiva || { n: 0, totale: 0, imposta: 0 };

  return (
    <div>
      <PageHeader eyebrow="Archivio fatture" title="Dashboard archivio">
        <Select value={String(anno)} onValueChange={setAnno}>
          <SelectTrigger className="w-36 bg-white" data-testid="arch-dash-year-select"><SelectValue /></SelectTrigger>
          <SelectContent className="bg-white"><SelectItem value="all">Tutti gli anni</SelectItem>{anni.map((y) => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}</SelectContent>
        </Select>
      </PageHeader>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi label="Fatture attive" value={fmtEUR(a.totale)} sub={`${a.n} documenti · IVA ${fmtEUR(a.imposta)}`} testId="arch-kpi-attive" />
        <Kpi label="Fatture passive" value={fmtEUR(p.totale)} sub={`${p.n} documenti · IVA ${fmtEUR(p.imposta)}`} testId="arch-kpi-passive" />
        <Kpi label="Clienti" value={d.n_clienti} testId="arch-kpi-clienti" />
        <Kpi label="Fornitori" value={d.n_fornitori} testId="arch-kpi-fornitori" />
      </div>
      <div className="mt-6 rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm">
        <h3 className="mb-4 text-lg font-semibold text-slate-800">Andamento mensile</h3>
        <div className="h-64" data-testid="arch-chart">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={d.mensile.map((m, i) => ({ ...m, mese: MESI[i] }))}>
              <CartesianGrid vertical={false} stroke="#e2e8f0" />
              <XAxis dataKey="mese" tickLine={false} axisLine={false} fontSize={12} />
              <YAxis tickLine={false} axisLine={false} fontSize={11} width={70} />
              <Tooltip formatter={(v) => fmtEUR(v)} cursor={{ fill: "#f1f5f9" }} />
              <Legend />
              <Bar dataKey="attiva" name="Attive" fill="#2563eb" radius={[3, 3, 0, 0]} />
              <Bar dataKey="passiva" name="Passive" fill="#f59e0b" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="mt-6 rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm">
        <h3 className="mb-3 text-lg font-semibold text-slate-800">Ultime fatture importate</h3>
        {d.recenti.length === 0 ? <p className="text-sm text-slate-500" data-testid="arch-recent-empty">Nessuna fattura in archivio. <Link to="/archivio/carica" className="font-semibold text-blue-600">Carica le prime fatture →</Link></p> : (
          <div className="divide-y divide-slate-100">
            {d.recenti.map((r) => (
              <Link key={r.id} to={`/archivio/fatture/${r.id}`} className="flex items-center justify-between gap-3 py-2.5 text-sm hover:bg-slate-50" data-testid={`arch-recent-${r.id}`}>
                <span className="flex items-center gap-2"><DocBadge code={r.tipo_documento} /><b>{r.numero}</b> · {fmtDate(r.data)} · {r.controparte_nome}</span>
                <span className={r.tipo === "attiva" ? "text-blue-700" : "text-amber-700"}>{fmtEUR(r.totale)}</span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

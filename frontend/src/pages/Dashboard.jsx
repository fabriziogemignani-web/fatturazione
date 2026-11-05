import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Plus } from "lucide-react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from "recharts";
import { api } from "@/lib/api";
import { fmtEUR, fmtDate, STATUS } from "@/lib/fe";
import { PageHeader, StatusBadge } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { SdiPanel } from "@/components/SdiPanel";
import { ScadenzePanel } from "@/components/ScadenzePanel";
import { CorrispettiviPanel } from "@/components/CorrispettiviPanel";
import { SdiSchedulePanel } from "@/components/SdiSchedulePanel";
import { useCompany } from "@/context/CompanyContext";
import { mods } from "@/lib/moduli";

const MESI = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"];

const Kpi = ({ label, value, testId, accent, sub }) => (
  <div className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm transition-shadow hover:shadow-md fade-up">
    <div className="text-xs font-medium uppercase tracking-wider text-slate-500">{label}</div>
    <div className={`mt-3 text-2xl font-extrabold tracking-tight ${accent || "text-slate-900"}`} data-testid={testId}>{value}</div>
    {sub && <div className="mt-1 text-xs text-violet-700" data-testid={`${testId}-sub`}>{sub}</div>}
  </div>
);

export default function Dashboard() {
  const [d, setD] = useState(null);
  const m = mods(useCompany().company);

  useEffect(() => {
    api.get("/dashboard").then(({ data }) => setD(data));
  }, []);

  if (!d) return <div className="text-sm text-slate-500">Caricamento…</div>;
  const chart = d.mesi.map((m) => ({ mese: MESI[m.mese - 1], totale: m.totale }));

  return (
    <div>
      <PageHeader eyebrow={`Anno ${d.anno}`} title="Dashboard">
        {m.fatture_attive && <Button asChild data-testid="dashboard-new-invoice-btn"><Link to="/fatture/nuova"><Plus className="mr-2 h-4 w-4" />Nuova fattura</Link></Button>}
      </PageHeader>
      {m.fatture_attive && <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">
        <Kpi label="Totale fatturato" value={fmtEUR(d.fatturato)} testId="kpi-fatturato" sub={d.note_credito?.count ? `al netto di ${d.note_credito.count} note di credito (${fmtEUR(d.note_credito.totale)})` : null} />
        <Kpi label="Imponibile" value={fmtEUR(d.imponibile)} testId="kpi-imponibile" />
        <Kpi label="IVA" value={fmtEUR(d.iva)} testId="kpi-iva" />
        <Kpi label="Documenti totali (incl. bozze)" value={d.totale_fatture} testId="kpi-count" accent="text-blue-600" />
      </div>}
      {(m.fatture_attive || m.fatture_passive) && <SdiSchedulePanel />}
      {m.fatture_attive && <SdiPanel d={d} />}
      {m.fatture_attive && <ScadenzePanel />}
      {m.fatture_passive && <ScadenzePanel passive />}
      {m.corrispettivi && <CorrispettiviPanel />}
      {m.fatture_attive && <>
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm lg:col-span-2">
          <h3 className="text-lg font-semibold text-slate-800">Fatturato mensile</h3>
          <p className="text-xs text-slate-500">Fatture inviate, consegnate e in mancata consegna</p>
          <div className="mt-6 h-64" data-testid="monthly-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chart}>
                <CartesianGrid vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="mese" tickLine={false} axisLine={false} fontSize={12} />
                <YAxis tickLine={false} axisLine={false} fontSize={12} width={60} />
                <Tooltip formatter={(v) => fmtEUR(v)} cursor={{ fill: "#f1f5f9" }} />
                <Bar dataKey="totale" fill="#2563EB" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm">
          <h3 className="text-lg font-semibold text-slate-800">Stato SDI</h3>
          <div className="mt-6 space-y-3">
            {Object.keys(STATUS).map((s) => (
              <div key={s} className="flex items-center justify-between">
                <StatusBadge status={s} testId={`dashboard-status-${s}`} />
                <span className="mono text-sm font-medium text-slate-900" data-testid={`dashboard-count-${s}`}>{d.counts[s] || 0}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="mt-6 rounded-xl border border-slate-200/80 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-slate-100 p-6">
          <h3 className="text-lg font-semibold text-slate-800">Ultime fatture</h3>
          <Link to="/fatture" className="text-sm font-medium text-blue-600 hover:text-blue-700" data-testid="dashboard-all-invoices-link">Vedi tutte</Link>
        </div>
        {d.recenti.length === 0 ? (
          <div className="p-6 text-sm text-slate-500" data-testid="dashboard-empty">Nessuna fattura ancora. Crea la prima!</div>
        ) : (
          <div className="divide-y divide-slate-100">
            {d.recenti.map((i) => (
              <Link key={i.id} to={`/fatture/${i.id}`} className="flex items-center justify-between gap-4 px-6 py-4 transition-colors hover:bg-slate-50" data-testid={`recent-invoice-${i.id}`}>
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-slate-900">{i.cliente?.denominazione}</div>
                  <div className="mono text-xs text-slate-500">{i.tipo_documento === "TD04" && <span className="mr-1 rounded bg-violet-100 px-1 font-semibold text-violet-700">NC</span>}N. {i.numero_display} · {fmtDate(i.data)}</div>
                </div>
                <div className="flex items-center gap-4">
                  <span className={`hidden text-sm font-semibold sm:inline ${i.tipo_documento === "TD04" ? "text-violet-700" : "text-slate-900"}`}>{i.tipo_documento === "TD04" ? `- ${fmtEUR(i.totale)}` : fmtEUR(i.totale)}</span>
                  <StatusBadge status={i.status} testId={`recent-status-${i.id}`} />
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
      </>}
    </div>
  );
}

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, Moon, Sun } from "lucide-react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from "recharts";
import { api } from "@/lib/api";
import { fmtEUR, fmtDate, STATUS } from "@/lib/fe";
import { PageHeader, StatusBadge } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { SdiPanel } from "@/components/SdiPanel";
import { ScadenzePanel } from "@/components/ScadenzePanel";
import { CorrispettiviPanel } from "@/components/CorrispettiviPanel";
import { SdiSchedulePanel } from "@/components/SdiSchedulePanel";
import { BankPanel } from "@/components/BankPanel";
import { MagazzinoPanel } from "@/components/MagazzinoPanel";
import { ScadenzeFiscaliPanel } from "@/components/ScadenzeFiscaliPanel";
import { RitenutePanel } from "@/components/RitenutePanel";
import { IntentiPanel } from "@/components/Intenti";
import { RibaPanel } from "@/components/RibaPanel";
import { PagamentiPanel } from "@/components/PagamentiPanel";
import { RiquadriSezioni } from "@/components/RiquadriSezioni";
import { ComunicazioniPanel } from "@/components/ComunicazioniPanel";
import { SistemaAvvisi } from "@/components/SistemaAvvisi";
import { OrdiniPanel } from "@/components/OrdiniPanel";
import { FornitoriRevisionePanel } from "@/components/FornitoriRevisionePanel";
import { useCompany } from "@/context/CompanyContext";
import { useTheme } from "@/lib/theme";
import { AiDubbiePanel } from "@/components/AiDubbiePanel";
import { AiCreditiBanner } from "@/components/AiCreditiBanner";
import { mods, vede } from "@/lib/moduli";

const MESI = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"];
const BAR_COLORS = ["#2563eb", "#7c3aed", "#db2777", "#ea580c", "#16a34a", "#0891b2"];

const Kpi = ({ label, value, testId, color, sub }) => (
  <div className={`rounded-xl p-4 text-white shadow-sm transition-shadow hover:shadow-md fade-up ${color}`}>
    <div className="text-[11px] font-semibold uppercase tracking-wider text-white/80">{label}</div>
    <div className="mt-1 text-xl font-extrabold tracking-tight tabular-nums" data-testid={testId}>{value}</div>
    {sub && <div className="mt-0.5 text-[11px] text-white/85" data-testid={`${testId}-sub`}>{sub}</div>}
  </div>
);

export default function Dashboard() {
  const [d, setD] = useState(null);
  const [dark, setDark] = useTheme();
  const co = useCompany().company;
  const m = mods(co);

  useEffect(() => {
    api.get("/dashboard").then(({ data }) => setD(data));
  }, []);

  if (!d) return <div className="text-sm text-slate-500">Caricamento…</div>;
  const chart = d.mesi.map((m) => ({ mese: MESI[m.mese - 1], totale: m.totale }));

  return (
    <div>
      <PageHeader eyebrow={`Anno ${d.anno}`} title="Dashboard">
        <Button variant="outline" onClick={() => setDark(!dark)} className="dash-theme-btn" data-testid="dashboard-theme-toggle" title={dark ? "Passa allo sfondo chiaro" : "Passa allo sfondo scuro"}>
          {dark ? <Sun className="mr-2 h-4 w-4" /> : <Moon className="mr-2 h-4 w-4" />}{dark ? "Tema chiaro" : "Tema scuro"}
        </Button>
        {m.fatture_attive && vede(co, "fatture") && <Button asChild data-testid="dashboard-new-invoice-btn"><Link to="/fatture/nuova"><Plus className="mr-2 h-4 w-4" />Nuova fattura</Link></Button>}
      </PageHeader>
      <AiCreditiBanner />
      <SistemaAvvisi />
      <RiquadriSezioni />
      {m.fatture_attive && <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Dettagli</h2>}
      {m.fatture_attive && <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi label="Totale fatturato" value={fmtEUR(d.fatturato)} testId="kpi-fatturato" color="bg-blue-600" sub={d.note_credito?.count ? `al netto di ${d.note_credito.count} note di credito (${fmtEUR(d.note_credito.totale)})` : null} />
        <Kpi label="Imponibile" value={fmtEUR(d.imponibile)} testId="kpi-imponibile" color="bg-emerald-600" />
        <Kpi label="IVA" value={fmtEUR(d.iva)} testId="kpi-iva" color="bg-orange-600" />
        <Kpi label="Documenti totali (incl. bozze)" value={d.totale_fatture} testId="kpi-count" color="bg-fuchsia-600" />
      </div>}
      <div className="dash-grid" data-testid="dashboard-panels">
      {(vede(co, "liquidazione-iva") || vede(co, "passive") || vede(co, "bolli-virtuali")) && <ScadenzeFiscaliPanel />}
      {m.fatture_passive && vede(co, "passive") && <FornitoriRevisionePanel />}
      {m.fatture_passive && vede(co, "passive") && <AiDubbiePanel />}
      {m.fatture_passive && vede(co, "ritenute") && <RitenutePanel />}
      {m.fatture_attive && vede(co, "comunicazioni") && <ComunicazioniPanel />}
      {(m.fatture_attive || m.fatture_passive) && <SdiSchedulePanel />}
      {vede(co, "riconciliazione") && <BankPanel />}
      {vede(co, "magazzino") && <MagazzinoPanel />}
      {m.fatture_attive && vede(co, "fatture") && <SdiPanel d={d} />}
      {m.fatture_attive && vede(co, "scadenzario") && <ScadenzePanel />}
      {m.fatture_attive && <IntentiPanel />}
      {m.fatture_attive && m.contabilita && vede(co, "riba") && <RibaPanel />}
      {((m.fatture_attive && vede(co, "ordini-clienti")) || (m.fatture_passive && vede(co, "ordini-fornitori"))) && <OrdiniPanel clienti={m.fatture_attive && vede(co, "ordini-clienti")} fornitori={m.fatture_passive && vede(co, "ordini-fornitori")} />}
      {m.fatture_passive && vede(co, "pagamenti-fornitori") && <PagamentiPanel />}
      {m.fatture_passive && vede(co, "scadenzario-fornitori") && <ScadenzePanel passive />}
      {m.corrispettivi && vede(co, "corrispettivi") && <CorrispettiviPanel />}
      </div>
      {m.fatture_attive && <>
      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="rounded-xl border-t-4 border-blue-600 bg-white p-4 shadow-sm lg:col-span-2">
          <h3 className="text-base font-semibold text-slate-800">Fatturato mensile</h3>
          <p className="text-xs text-slate-500">Fatture inviate, consegnate e in mancata consegna</p>
          <div className="mt-3 h-52" data-testid="monthly-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chart}>
                <CartesianGrid vertical={false} stroke={dark ? "#1e293b" : "#e2e8f0"} />
                <XAxis dataKey="mese" tickLine={false} axisLine={false} fontSize={12} stroke={dark ? "#94a3b8" : "#666"} />
                <YAxis tickLine={false} axisLine={false} fontSize={12} width={60} stroke={dark ? "#94a3b8" : "#666"} />
                <Tooltip formatter={(v) => fmtEUR(v)} cursor={{ fill: dark ? "#1e293b" : "#f1f5f9" }} contentStyle={dark ? { background: "#0f172a", border: "1px solid #334155", color: "#f1f5f9" } : undefined} />
                <Bar dataKey="totale" radius={[4, 4, 0, 0]}>{chart.map((_, k) => <Cell key={k} fill={BAR_COLORS[k % BAR_COLORS.length]} />)}</Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="rounded-xl border-t-4 border-fuchsia-600 bg-white p-4 shadow-sm">
          <h3 className="text-base font-semibold text-slate-800">Stato SDI</h3>
          <div className="mt-3 space-y-2">
            {Object.keys(STATUS).map((s) => (
              <div key={s} className="flex items-center justify-between">
                <StatusBadge status={s} testId={`dashboard-status-${s}`} />
                <span className="mono text-sm font-medium text-slate-900" data-testid={`dashboard-count-${s}`}>{d.counts[s] || 0}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="mt-4 rounded-xl border-t-4 border-emerald-600 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
          <h3 className="text-base font-semibold text-slate-800">Ultime fatture</h3>
          <Link to="/fatture" className="text-sm font-medium text-blue-600 hover:text-blue-700" data-testid="dashboard-all-invoices-link">Vedi tutte</Link>
        </div>
        {d.recenti.length === 0 ? (
          <div className="p-6 text-sm text-slate-500" data-testid="dashboard-empty">Nessuna fattura ancora. Crea la prima!</div>
        ) : (
          <div className="divide-y divide-slate-100">
            {d.recenti.map((i) => (
              <Link key={i.id} to={`/fatture/${i.id}`} className="flex items-center justify-between gap-4 px-4 py-2.5 transition-colors hover:bg-slate-50" data-testid={`recent-invoice-${i.id}`}>
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

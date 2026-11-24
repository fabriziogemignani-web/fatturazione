import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { fmtEUR } from "@/lib/fe";
import { Delta } from "@/components/dashboard/Card";

const PER = { mese: "mese precedente", trimestre: "trimestre precedente", anno: "anno precedente", "12mesi": "12 mesi precedenti" };

const Kpi = ({ label, value, delta, invert, sub, to, testId }) => (
  <Link to={to} className="group min-w-0 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition-shadow hover:shadow-md fade-up" data-testid={testId}>
    <div className="flex items-center justify-between gap-2"><span className="truncate text-sm font-medium text-slate-600">{label}</span><Delta v={delta} invert={invert} /></div>
    <div className="mt-2 truncate text-2xl font-bold tracking-tight text-slate-900 tabular-nums" data-testid={`${testId}-value`}>{value}</div>
    {sub && <div className="mt-1 truncate text-xs text-slate-500">{sub}</div>}
  </Link>
);

export const KpiRow = ({ periodo, m }) => {
  const [k, setK] = useState(null);
  const [liq, setLiq] = useState(null);
  const [rq, setRq] = useState(null);
  const [mag, setMag] = useState(null);
  useEffect(() => { api.get("/dashboard/kpi", { params: { periodo } }).then(({ data }) => setK(data)).catch(() => {}); }, [periodo]);
  useEffect(() => {
    api.get("/situazione-finanziaria", { params: { mesi: 1 } }).then(({ data }) => setLiq(data)).catch(() => {});
    api.get("/dashboard/riquadri").then(({ data }) => setRq(data)).catch(() => {});
    if (m.magazzino) api.get("/magazzino/riepilogo").then(({ data }) => setMag(data)).catch(() => {});
  }, [m.magazzino]);
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4" data-testid="dash-kpi-row">
      <Kpi label="Fatturato emesso" value={k ? fmtEUR(k.fatturato) : "…"} delta={k?.delta} sub={k ? `imponibile · vs ${PER[periodo]} ${fmtEUR(k.fatturato_prec)}` : null} to="/fatture" testId="dash-kpi-fatturato" />
      <Kpi label="Liquidità / Saldo cassa" value={liq ? fmtEUR(liq.saldo_iniziale) : "…"} sub={liq ? (liq.fonte_saldo === "estratto" ? "dagli estratti conto" : liq.fonte_saldo === "contabilita" ? "dalla contabilità" : "nessuna banca con saldo") : null} to="/situazione-finanziaria" testId="dash-kpi-liquidita" />
      <Kpi label="Crediti scaduti" value={rq ? fmtEUR(rq.clienti_scaduto) : "…"} sub={rq ? `${rq.clienti_scaduto_n} rate scadute da incassare` : null} to="/scadenzario" testId="dash-kpi-crediti" />
      {m.magazzino
        ? <Kpi label="Valore magazzino" value={mag ? fmtEUR(mag.valore_totale) : "…"} sub={mag ? `${mag.articoli} articoli · ${mag.sottoscorta} sottoscorta` : null} to="/magazzino" testId="dash-kpi-magazzino" />
        : <Kpi label="Debiti fornitori scaduti" value={rq ? fmtEUR(rq.fornitori_scaduto) : "…"} sub={rq ? `${rq.fornitori_scaduto_n} rate scadute da pagare` : null} to="/scadenzario-fornitori" testId="dash-kpi-debiti" />}
    </div>
  );
};

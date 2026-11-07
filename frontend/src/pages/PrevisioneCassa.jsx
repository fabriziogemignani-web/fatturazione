import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, errMsg } from "@/lib/api";
import { PageHeader } from "@/components/Common";
import { Switch } from "@/components/ui/switch";
import { fmtEUR, fmtDate } from "@/lib/fe";

const GIORNI = [30, 60, 90, 180];

const Kpi = ({ label, value, tone = "text-slate-900", sub, testId }) => (
  <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-sm">
    <div className="text-xs uppercase tracking-wider text-slate-500">{label}</div>
    <div className={`mt-1 text-xl font-extrabold ${tone}`} data-testid={testId}>{value}</div>
    {sub && <div className="text-xs text-slate-500">{sub}</div>}
  </div>
);

const Chart = ({ serie }) => (
  <div className="h-72" data-testid="forecast-chart">
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={serie} margin={{ left: 10, right: 10, top: 10 }}>
        <defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#2563eb" stopOpacity={0.25} /><stop offset="100%" stopColor="#2563eb" stopOpacity={0} /></linearGradient></defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey="data" tickFormatter={(d) => d.slice(8, 10) + "/" + d.slice(5, 7)} fontSize={11} minTickGap={24} />
        <YAxis fontSize={11} tickFormatter={(v) => (Math.abs(v) >= 10000 ? `${(v / 1000).toLocaleString("it-IT", { maximumFractionDigits: 1 })}k` : Math.round(v).toLocaleString("it-IT"))} width={56} />
        <Tooltip formatter={(v, n) => [fmtEUR(v), n === "saldo" ? "Saldo previsto" : n]} labelFormatter={fmtDate} />
        <ReferenceLine y={0} stroke="#e11d48" strokeDasharray="4 4" />
        <Area type="stepAfter" dataKey="saldo" stroke="#2563eb" strokeWidth={2} fill="url(#g)" />
      </AreaChart>
    </ResponsiveContainer>
  </div>
);

const Voci = ({ voci }) => (
  <div className="overflow-x-auto">
    <table className="w-full text-left text-sm">
      <thead><tr className="border-b border-slate-200 text-xs uppercase tracking-wider text-slate-500"><th className="px-4 py-2">Data</th><th className="px-4 py-2">Documento</th><th className="px-4 py-2 text-right">Importo</th></tr></thead>
      <tbody>
        {voci.length === 0 && <tr><td colSpan={3} className="px-4 py-8 text-center text-slate-500" data-testid="forecast-empty">Nessuna scadenza nel periodo</td></tr>}
        {voci.map((v, i) => (
          <tr key={i} className="border-b border-slate-100" data-testid={`forecast-row-${i}`}>
            <td className="whitespace-nowrap px-4 py-2">{fmtDate(v.scadenza)}{v.scaduta && <span className="ml-2 rounded bg-amber-50 px-1.5 text-[10px] font-bold text-amber-700">SCADUTA</span>}</td>
            <td className="px-4 py-2"><Link className="hover:underline" to={v.tipo === "incasso" ? `/fatture/${v.invoice_id}` : `/passive/${v.invoice_id}`}>{v.label}</Link></td>
            <td className={`whitespace-nowrap px-4 py-2 text-right font-semibold ${v.importo > 0 ? "text-emerald-700" : "text-rose-700"}`}>{fmtEUR(v.importo)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

export default function PrevisioneCassa() {
  const [giorni, setGiorni] = useState(90);
  const [scaduti, setScaduti] = useState(true);
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/banca/previsione", { params: { giorni, scaduti } }).then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e))); }, [giorni, scaduti]);
  return (
    <div>
      <PageHeader eyebrow="Tesoreria" title="Previsione di cassa" />
      <div className="mb-5 flex flex-wrap items-center gap-3">
        {GIORNI.map((g) => (
          <button key={g} onClick={() => setGiorni(g)} data-testid={`forecast-days-${g}`}
            className={`rounded-full border px-3 py-1.5 text-xs font-semibold ${giorni === g ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 text-slate-600 hover:border-slate-400"}`}>{g} giorni</button>
        ))}
        <label className="ml-2 flex items-center gap-2 text-sm text-slate-600"><Switch checked={scaduti} onCheckedChange={setScaduti} data-testid="forecast-scaduti-switch" />Conta anche le scadenze già passate e non saldate, come se arrivassero oggi</label>
      </div>
      {d && <>
        {d.conti === 0 && <p className="mb-4 text-xs text-amber-700" data-testid="forecast-no-accounts">Nessun conto bancario: il saldo di partenza è 0. Collega la banca o importa un estratto conto in Riconciliazione.</p>}
        {d.conti > 0 && d.conti_senza_saldo > 0 && <p className="mb-4 text-xs text-amber-700" data-testid="forecast-missing-saldo">{d.conti_senza_saldo === 1 ? "Un conto non ha" : `${d.conti_senza_saldo} conti non hanno`} ancora un saldo e {d.conti_senza_saldo === 1 ? "viene contato" : "vengono contati"} come 0: importa un estratto CBI o sincronizza la banca per un saldo reale.</p>}
        <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-5">
          <Kpi label="Saldo attuale" value={fmtEUR(d.saldo_iniziale)} testId="forecast-start" sub={d.conti === 1 ? "1 conto" : `${d.conti} conti`} />
          <Kpi label="Incassi previsti" value={fmtEUR(d.entrate)} tone="text-emerald-700" testId="forecast-in" sub={d.scaduti.incassi ? `di cui scaduti ${fmtEUR(d.scaduti.incassi)}` : null} />
          <Kpi label="Pagamenti previsti" value={fmtEUR(-d.uscite)} tone="text-rose-700" testId="forecast-out" sub={d.scaduti.pagamenti ? `di cui scaduti ${fmtEUR(d.scaduti.pagamenti)}` : null} />
          <Kpi label={`Saldo tra ${d.giorni} giorni`} value={fmtEUR(d.saldo_finale)} tone={d.saldo_finale < 0 ? "text-rose-700" : "text-slate-900"} testId="forecast-end" />
          <Kpi label="Punto più basso" value={fmtEUR(d.minimo.saldo)} tone={d.minimo.saldo < 0 ? "text-rose-700" : "text-slate-900"} sub={fmtDate(d.minimo.data)} testId="forecast-min" />
        </div>
        <section className="mb-6 rounded-xl border border-slate-200/80 bg-white p-4 shadow-sm"><Chart serie={d.serie} /></section>
        <section className="rounded-xl border border-slate-200/80 bg-white shadow-sm"><Voci voci={d.voci} /></section>
      </>}
    </div>
  );
}

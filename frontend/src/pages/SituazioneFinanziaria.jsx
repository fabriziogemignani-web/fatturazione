import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend } from "recharts";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { PageHeader } from "@/components/Common";

const MESI = [3, 6, 12];
const TIPI = [["incasso", "Incassi clienti", "#059669"], ["fornitore", "Pagamenti fornitori", "#e11d48"], ["rateizzazione", "Rate rateizzazioni", "#d97706"], ["fisco", "F24 e scadenze fiscali", "#7c3aed"], ["finanziamento", "Finanziamenti e leasing", "#0891b2"]];
const meseLabel = (k) => new Date(`${k}-01T00:00:00`).toLocaleDateString("it-IT", { month: "short", year: "2-digit" });
const LINK = { incasso: (r) => `/fatture/${r}`, fornitore: (r) => `/passive/${r}`, rateizzazione: () => "/rateizzazioni", finanziamento: () => "/finanziamenti", fisco: () => "/liquidazione-iva" };

const Kpi = ({ label, value, tone = "text-slate-900", sub, testId }) => (
  <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-sm">
    <div className="text-xs uppercase tracking-wider text-slate-500">{label}</div>
    <div className={`mt-1 text-xl font-extrabold tabular-nums ${tone}`} data-testid={testId}>{value}</div>
    {sub && <div className="text-xs text-slate-500">{sub}</div>}
  </div>
);

const Banche = ({ d }) => (
  <section className="rounded-xl border border-slate-200/80 bg-white p-5 shadow-sm" data-testid="sf-banche">
    <h3 className="mb-3 font-semibold text-slate-900">Saldi delle banche</h3>
    {d.banche_estratto.length === 0 && d.banche_contabili.length === 0 && <p className="text-sm text-slate-500">Nessuna banca: aggiungila in Dati azienda o in Riconciliazione bancaria.</p>}
    {d.banche_estratto.length > 0 && <>
      <div className="mb-1 text-xs font-semibold uppercase text-slate-500">Da estratto conto</div>
      <ul className="mb-3 divide-y divide-slate-100 text-sm">{d.banche_estratto.map((b, i) => <li key={i} className="flex justify-between py-1.5" data-testid={`sf-banca-e-${i}`}><span>{b.nome} <span className="text-xs text-slate-400">{b.iban}</span></span><b className={b.saldo < 0 ? "text-rose-700" : ""}>{b.saldo == null ? "senza saldo" : fmtEUR(b.saldo)}</b></li>)}</ul>
    </>}
    {d.banche_contabili.length > 0 && <>
      <div className="mb-1 text-xs font-semibold uppercase text-slate-500">Da contabilità</div>
      <ul className="divide-y divide-slate-100 text-sm">{d.banche_contabili.map((b) => <li key={b.conto} className="flex justify-between py-1.5" data-testid={`sf-banca-c-${b.conto}`}><span>{b.nome} <span className="mono text-xs text-slate-400">{b.conto}</span></span><b className={b.saldo < 0 ? "text-rose-700" : ""}>{fmtEUR(b.saldo)}</b></li>)}</ul>
    </>}
  </section>
);

const Grafico = ({ mesi }) => (
  <div className="h-72" data-testid="sf-chart">
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={mesi.map((m) => ({ ...m, label: meseLabel(m.mese), u_forn: m.fornitore, u_fisco: m.rateizzazione + m.fisco, u_fin: m.finanziamento }))} margin={{ left: 10, right: 10, top: 10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey="label" fontSize={11} />
        <YAxis fontSize={11} width={64} tickFormatter={(v) => Math.round(v).toLocaleString("it-IT")} />
        <Tooltip formatter={(v, n) => [fmtEUR(v), n]} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <ReferenceLine y={0} stroke="#94a3b8" />
        <Bar dataKey="incasso" name="Entrate" fill="#059669" radius={[3, 3, 0, 0]} />
        <Bar dataKey="u_forn" stackId="u" name="Fornitori" fill="#e11d48" />
        <Bar dataKey="u_fisco" stackId="u" name="Rate fiscali e F24" fill="#d97706" />
        <Bar dataKey="u_fin" stackId="u" name="Finanziamenti e leasing" fill="#0891b2" radius={[0, 0, 3, 3]} />
        <Line dataKey="saldo" name="Saldo previsto" stroke="#1d4ed8" strokeWidth={2.5} dot />
      </ComposedChart>
    </ResponsiveContainer>
  </div>
);

const TabellaMesi = ({ d }) => (
  <div className="overflow-x-auto">
    <table className="w-full text-sm" data-testid="sf-mesi-table">
      <thead className="border-b border-slate-200 text-left text-xs uppercase tracking-wider text-slate-500"><tr><th className="px-4 py-2">Mese</th>{TIPI.map(([k, l]) => <th key={k} className={`px-4 py-2 text-right ${k === "finanziamento" ? "border-l border-cyan-100 bg-cyan-50/60 text-cyan-800" : ""}`}>{l}</th>)}<th className="px-4 py-2 text-right">Netto</th><th className="px-4 py-2 text-right">Saldo previsto</th></tr></thead>
      <tbody className="divide-y divide-slate-100">
        {d.mesi.map((m, i) => (
          <tr key={m.mese} data-testid={`sf-mese-${m.mese}`}>
            <td className="px-4 py-2 font-medium capitalize">{meseLabel(m.mese)}{i === 0 && <span className="ml-1 text-[10px] text-slate-400">(con scaduti)</span>}</td>
            {TIPI.map(([k]) => <td key={k} className={`px-4 py-2 text-right tabular-nums ${k === "finanziamento" ? "border-l border-cyan-100 bg-cyan-50/40" : ""} ${m[k] > 0 ? "text-emerald-700" : m[k] < 0 ? "text-rose-700" : "text-slate-400"}`}>{fmtEUR(m[k])}</td>)}
            <td className={`px-4 py-2 text-right font-semibold tabular-nums ${m.netto < 0 ? "text-rose-700" : "text-emerald-700"}`}>{fmtEUR(m.netto)}</td>
            <td className={`px-4 py-2 text-right font-bold tabular-nums ${m.saldo < 0 ? "text-rose-700" : "text-slate-900"}`} data-testid={`sf-saldo-${m.mese}`}>{fmtEUR(m.saldo)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

const Voci = ({ voci, vuoto = "Nessuna scadenza nel periodo" }) => (
  <ul className="divide-y divide-slate-100 text-sm" data-testid="sf-voci">
    {voci.length === 0 && <li className="px-5 py-8 text-center text-slate-500">{vuoto}</li>}
    {voci.map((v, i) => (
      <li key={i} className="flex items-center justify-between gap-3 px-5 py-2" data-testid={`sf-voce-${i}`}>
        <span className="min-w-0 truncate"><span className="mr-2 inline-block h-2 w-2 rounded-full" style={{ background: TIPI.find(([k]) => k === v.tipo)[2] }} />{fmtDate(v.scadenza)}{v.scaduta && <span className="ml-2 rounded bg-rose-50 px-1.5 text-[10px] font-bold text-rose-700">SCADUTA</span>}{v.provvisorio && <span className="ml-2 rounded bg-slate-100 px-1.5 text-[10px] font-bold text-slate-600">STIMA</span>} · <Link className="hover:underline" to={LINK[v.tipo](v.ref)}>{v.label}</Link></span>
        <b className={`whitespace-nowrap ${v.importo > 0 ? "text-emerald-700" : "text-rose-700"}`}>{fmtEUR(v.importo)}</b>
      </li>
    ))}
  </ul>
);

export default function SituazioneFinanziaria() {
  const [mesi, setMesi] = useState(6);
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/situazione-finanziaria", { params: { mesi } }).then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e))); }, [mesi]);
  const FONTE = { estratto: "dagli estratti conto", contabilita: "dalla contabilità", nessuna: "nessuna banca con saldo" };
  return (
    <div>
      <PageHeader eyebrow="Tesoreria" title="Situazione finanziaria" />
      <div className="mb-5 flex flex-wrap gap-2">
        {MESI.map((m) => <button key={m} onClick={() => setMesi(m)} data-testid={`sf-mesi-${m}`} className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${mesi === m ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 text-slate-600 hover:border-slate-400"}`}>{m} mesi</button>)}
      </div>
      {!d ? <div className="text-sm text-slate-500">Caricamento…</div> : <>
        <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-6">
          <Kpi label="Liquidità attuale" value={fmtEUR(d.saldo_iniziale)} sub={FONTE[d.fonte_saldo]} testId="sf-saldo-iniziale" />
          <Kpi label="Incassi attesi" value={fmtEUR(d.totali.incasso)} tone="text-emerald-700" sub={d.scaduto.incasso ? `di cui scaduti ${fmtEUR(d.scaduto.incasso)}` : null} testId="sf-tot-incassi" />
          <Kpi label="Fornitori" value={fmtEUR(d.totali.fornitore)} tone="text-rose-700" sub={d.scaduto.fornitore ? `di cui scaduti ${fmtEUR(d.scaduto.fornitore)}` : null} testId="sf-tot-fornitori" />
          <Kpi label="Rate fiscali e F24" value={fmtEUR(d.totali.rateizzazione + d.totali.fisco)} tone="text-amber-700" sub={`rateizzazioni ${fmtEUR(d.totali.rateizzazione)} · F24 ${fmtEUR(d.totali.fisco)}`} testId="sf-tot-fisco" />
          <Kpi label="Finanziamenti e leasing" value={fmtEUR(d.totali.finanziamento)} tone="text-cyan-700" sub={d.scaduto.finanziamento ? `di cui scaduti ${fmtEUR(d.scaduto.finanziamento)}` : "rate e canoni del periodo"} testId="sf-tot-finanziamenti" />
          <Kpi label={`Saldo tra ${d.mesi.length} mesi`} value={fmtEUR(d.saldo_finale)} tone={d.saldo_finale < 0 ? "text-rose-700" : "text-slate-900"} sub={d.minimo && `minimo ${fmtEUR(d.minimo.saldo)} a ${meseLabel(d.minimo.mese)}`} testId="sf-saldo-finale" />
        </div>
        <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
          <section className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-sm lg:col-span-2"><Grafico mesi={d.mesi} /></section>
          <Banche d={d} />
        </div>
        <section className="mb-6 rounded-xl border border-slate-200/80 bg-white shadow-sm"><TabellaMesi d={d} /></section>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <section className="rounded-xl border border-slate-200/80 bg-white shadow-sm" data-testid="sf-sezione-scadenze">
            <h3 className="border-b border-slate-100 px-5 py-3 font-semibold text-slate-900">Clienti, fornitori, rate fiscali e F24</h3>
            <Voci voci={d.voci.filter((v) => v.tipo !== "finanziamento")} />
          </section>
          <section className="rounded-xl border border-cyan-200 bg-white shadow-sm" data-testid="sf-sezione-finanziamenti">
            <h3 className="flex items-center justify-between border-b border-cyan-100 bg-cyan-50/60 px-5 py-3 font-semibold text-cyan-900">Finanziamenti e leasing<Link to="/finanziamenti" className="text-xs font-medium text-cyan-700 hover:underline" data-testid="sf-vai-finanziamenti">Apri piani</Link></h3>
            <Voci voci={d.voci.filter((v) => v.tipo === "finanziamento")} vuoto="Nessuna rata di finanziamento o leasing nel periodo" />
          </section>
        </div>
        <p className="mt-3 text-xs text-slate-500">Gli F24 previsti coprono i prossimi 75 giorni; le scadenze già passate e non saldate sono contate nel mese corrente. I piani di rateizzazione si caricano in <Link to="/rateizzazioni" className="text-blue-600 hover:underline">Rateizzazioni fiscali</Link>.</p>
      </>}
    </div>
  );
}

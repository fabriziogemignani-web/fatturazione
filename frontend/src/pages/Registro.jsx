import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Plus, CircleDashed } from "lucide-react";
import { api } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { PageHeader, StatusBadge } from "@/components/Common";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const REGISTRI = [["", "Fatture"], ["NC", "Note di credito"]];

const Stat = ({ label, value, testId, tone = "text-slate-900" }) => (
  <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
    <div className="text-xs uppercase tracking-wider text-slate-500">{label}</div>
    <div className={`mono mt-1 text-xl font-bold ${tone}`} data-testid={testId}>{value}</div>
  </div>
);

const FreeRow = ({ r, sez }) => (
  <tr className="bg-amber-50/60" data-testid={`registro-free-${r.numero}`}>
    <td className="mono px-4 py-3 font-medium text-amber-800"><CircleDashed className="mr-2 inline h-4 w-4" />{r.numero_display}</td>
    <td className="px-4 py-3 text-xs text-amber-800" colSpan={3}>Numero libero · data tra {fmtDate(r.data_min)} e {fmtDate(r.data_max)}</td>
    <td className="px-4 py-3 text-right" colSpan={2}>
      <Link to={`/fatture/nuova?numero=${r.numero}&data=${r.data_min}${sez === "NC" ? "&tipo=TD04" : ""}`} className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600 hover:text-blue-800" data-testid={`registro-use-${r.numero}`}><Plus className="h-3.5 w-3.5" />Usa questo numero</Link>
    </td>
  </tr>
);

export default function Registro() {
  const [anno, setAnno] = useState(null);
  const [sez, setSez] = useState("");
  const [data, setData] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    api.get("/registro", { params: { ...(anno ? { anno } : {}), sezionale: sez } }).then(({ data: d }) => setData(d));
  }, [anno, sez]);

  if (!data) return <div className="text-sm text-slate-500">Caricamento…</div>;

  return (
    <div>
      <PageHeader eyebrow="Numerazione" title="Registro numerazione">
        <Select value={String(data.anno)} onValueChange={(v) => setAnno(Number(v))}>
          <SelectTrigger className="w-32 bg-white" data-testid="registro-anno-select"><SelectValue /></SelectTrigger>
          <SelectContent className="bg-white">{data.anni.map((a) => <SelectItem key={a} value={String(a)} data-testid={`registro-anno-${a}`}>{a}</SelectItem>)}</SelectContent>
        </Select>
      </PageHeader>
      <div className="mb-4 inline-flex rounded-lg border border-slate-200 bg-white p-1 text-xs font-semibold">
        {REGISTRI.map(([k, l]) => (
          <button key={k || "ft"} onClick={() => setSez(k)} data-testid={`registro-tab-${k || "fatture"}`}
            className={`rounded-md px-3 py-1.5 transition-colors ${sez === k ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-50"}`}>{l}</button>
        ))}
      </div>
      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Documenti" value={data.documenti} testId="registro-count" />
        <Stat label="Primo numero" value={data.primo ?? "—"} testId="registro-primo" />
        <Stat label="Numeri liberi" value={data.liberi} testId="registro-liberi" tone={data.liberi ? "text-amber-700" : "text-emerald-700"} />
        <Stat label="Prossimo numero" value={data.prossimo.numero_display} testId="registro-prossimo" tone="text-blue-700" />
      </div>
      {data.primo > 1 && <p className="mb-4 text-xs text-slate-500" data-testid="registro-start-note">La numerazione {data.anno} in questa app parte dal n. {data.primo} (numeri precedenti emessi fuori dall'app).</p>}
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm" data-testid="registro-table">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr><th className="px-4 py-3 font-medium">Numero</th><th className="px-4 py-3 font-medium">Data</th><th className="px-4 py-3 font-medium">Cliente</th><th className="px-4 py-3 text-right font-medium">Totale</th><th className="px-4 py-3 font-medium">Stato</th><th className="px-4 py-3" /></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.rows.map((r) => r.libero ? <FreeRow key={`f${r.numero}`} r={r} sez={sez} /> : (
              <tr key={r.id} className="cursor-pointer hover:bg-slate-50" onClick={() => navigate(`/fatture/${r.id}`)} data-testid={`registro-row-${r.numero}`}>
                <td className="mono px-4 py-3 font-medium text-slate-900">{r.numero_display}</td>
                <td className="px-4 py-3 text-slate-600">{fmtDate(r.data)}</td>
                <td className="px-4 py-3 text-slate-800">{r.cliente?.denominazione}</td>
                <td className="px-4 py-3 text-right font-semibold">{fmtEUR(r.totale)}</td>
                <td className="px-4 py-3"><StatusBadge status={r.status} testId={`registro-status-${r.numero}`} /></td>
                <td />
              </tr>
            ))}
            <tr className="bg-blue-50/50" data-testid="registro-next-row">
              <td className="mono px-4 py-3 font-medium text-blue-800">{data.prossimo.numero_display}</td>
              <td className="px-4 py-3 text-xs text-blue-800" colSpan={3}>Prossimo numero automatico{data.prossimo.data_min && ` · data dal ${fmtDate(data.prossimo.data_min)}`}</td>
              <td className="px-4 py-3 text-right" colSpan={2}>
                <Link to={`/fatture/nuova${sez === "NC" ? "?tipo=TD04" : ""}`} className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600 hover:text-blue-800" data-testid="registro-new-btn"><Plus className="h-3.5 w-3.5" />Nuovo documento</Link>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

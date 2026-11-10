import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { ChevronLeft, ChevronRight, Printer, FileDown, CheckCircle2, Undo2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { useAuth, canSend } from "@/context/AuthContext";
import { useCompany } from "@/context/CompanyContext";

const ym = (d) => d.toISOString().slice(0, 7);
const shift = (m, n) => { const d = new Date(`${m}-01T00:00:00`); d.setMonth(d.getMonth() + n); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; };
const prevMonth = () => shift(ym(new Date()), -1);

const download = async (mese) => {
  try {
    const { data } = await api.get(`/ritenute/${mese}/f24`, { responseType: "blob" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(data); a.download = `F24_ritenute_${mese}.pdf`; a.click(); URL.revokeObjectURL(a.href);
  } catch (e) { toast.error(errMsg(e)); }
};

const Versamento = ({ d, edit, onDone }) => {
  const [data, setData] = useState(d.scadenza);
  if (d.versato) {
    return (
      <div className="flex flex-wrap items-center gap-3 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800" data-testid="rit-versato-info">
        <CheckCircle2 className="h-4 w-4" />Versato il {fmtDate(d.versato.data)} ({fmtEUR(d.versato.importo)}) · registrato in contabilità se attiva
        {edit && <button onClick={() => api.delete(`/scadenze-fiscali/versato/${d.key}`).then(onDone).catch((e) => toast.error(errMsg(e)))} className="ml-auto inline-flex items-center gap-1 text-xs font-semibold hover:underline" data-testid="rit-annulla-versato"><Undo2 className="h-3.5 w-3.5" />Annulla</button>}
      </div>
    );
  }
  if (!edit || d.totale <= 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-3 print:hidden" data-testid="rit-versa-form">
      <span className="text-sm text-slate-600">Data versamento</span>
      <input type="date" value={data} onChange={(e) => setData(e.target.value)} className="h-9 rounded-md border border-slate-200 px-2 text-sm" data-testid="rit-versato-data" />
      <Button onClick={() => api.post(`/ritenute/${d.mese}/versato`, { data }).then(() => { toast.success("Versamento registrato"); onDone(); }).catch((e) => toast.error(errMsg(e)))}
        disabled={d.provvisorio} data-testid="rit-versato-btn">Segna come versato</Button>
      {d.provvisorio && <span className="text-xs text-amber-700">Il mese non è ancora finito: importo provvisorio</span>}
    </div>
  );
};

export default function Ritenute() {
  const [qs] = useSearchParams();
  const [mese, setMese] = useState(/^\d{4}-\d{2}$/.test(qs.get("mese") || "") ? qs.get("mese") : prevMonth());
  const [d, setD] = useState(null);
  const { user } = useAuth();
  const { company } = useCompany();
  const load = () => api.get("/ritenute/mese", { params: { mese } }).then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, [mese]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div data-testid="ritenute-page">
      <PageHeader eyebrow="Fisco e IVA" title="Ritenute d'acconto" subtitle="Ritenute sulle fatture dei professionisti, maturate nel mese in cui le paghi (anche in parte)">
        <div className="flex items-center gap-2 print:hidden">
          <Button variant="outline" size="icon" onClick={() => setMese(shift(mese, -1))} data-testid="rit-prev-month"><ChevronLeft className="h-4 w-4" /></Button>
          <input type="month" value={mese} onChange={(e) => e.target.value && setMese(e.target.value)} className="h-9 rounded-md border border-slate-200 px-2 text-sm" data-testid="rit-month-input" />
          <Button variant="outline" size="icon" onClick={() => setMese(shift(mese, 1))} data-testid="rit-next-month"><ChevronRight className="h-4 w-4" /></Button>
          <Button variant="outline" onClick={() => window.print()} data-testid="rit-print-btn"><Printer className="mr-2 h-4 w-4" />Stampa</Button>
          {d?.totale > 0 && <Button variant="outline" onClick={() => download(mese)} data-testid="rit-f24-btn"><FileDown className="mr-2 h-4 w-4" />F24</Button>}
        </div>
      </PageHeader>
      {d && (
        <div className="space-y-5">
          <div className="hidden text-sm print:block">{company?.denominazione} · Ritenute d'acconto compensi pagati a {d.label}</div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
            {[["Compensi pagati", fmtEUR(d.pagato), "rit-tot-pagato"], ["Ritenute da versare", fmtEUR(d.totale), "rit-tot-ritenute"], ["Codice tributo", d.codice, "rit-codice"], ["Scadenza F24", fmtDate(d.scadenza), "rit-scadenza"]].map(([l, v, id]) => (
              <div key={id} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div className="text-xs uppercase tracking-wider text-slate-500">{l}</div><div className="mt-1 text-xl font-semibold text-slate-900" data-testid={id}>{v}</div></div>
            ))}
          </div>
          <Versamento d={d} edit={canSend(user)} onDone={load} />
          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
            <table className="w-full text-sm" data-testid="rit-table">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
                <tr><th className="px-4 py-3">Professionista</th><th className="px-4 py-3">Fattura</th><th className="px-4 py-3">Pagata il</th><th className="px-4 py-3 text-right">Pagato</th><th className="px-4 py-3 text-right">Aliquota</th><th className="px-4 py-3 text-right">Ritenuta</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {d.fornitori.length === 0 && <tr><td colSpan={6} className="px-4 py-10 text-center text-slate-500" data-testid="rit-empty">Nessun pagamento a professionisti con ritenuta in {d.label}</td></tr>}
                {d.fornitori.map((f) => f.righe.map((r, i) => (
                  <tr key={`${r.invoice_id}-${r.pagato_il}-${i}`} data-testid={`rit-row-${r.invoice_id}`}>
                    <td className="px-4 py-2">{i === 0 && <><div className="font-medium">{f.fornitore}</div><div className="text-xs text-slate-500">{f.partita_iva}</div></>}</td>
                    <td className="px-4 py-2">{r.documento} <span className="text-xs text-slate-500">del {fmtDate(r.data_fattura)}</span></td>
                    <td className="px-4 py-2">{fmtDate(r.pagato_il)}</td>
                    <td className="px-4 py-2 text-right">{fmtEUR(r.pagato)}</td>
                    <td className="px-4 py-2 text-right">{r.aliquota ? `${r.aliquota}%` : "—"}</td>
                    <td className="px-4 py-2 text-right font-semibold">{fmtEUR(r.ritenuta)}</td>
                  </tr>
                )))}
              </tbody>
              {d.fornitori.length > 0 && <tfoot className="bg-slate-50 font-semibold"><tr><td colSpan={3} className="px-4 py-3">Totale {d.label}</td><td className="px-4 py-3 text-right">{fmtEUR(d.pagato)}</td><td /><td className="px-4 py-3 text-right" data-testid="rit-table-totale">{fmtEUR(d.totale)}</td></tr></tfoot>}
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

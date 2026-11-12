import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Printer, RefreshCw, Pencil, Trash2, ArrowDownLeft, ArrowUpRight } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth, canSend } from "@/context/AuthContext";
import { useCompany } from "@/context/CompanyContext";
import { useConti, ORIGINE_BADGE } from "@/components/ContoSelect";
import { RegistrazioneDialog } from "@/components/coge/RegistrazioneDialog";
import { IncassoSheet } from "@/components/coge/IncassoSheet";

const y0 = () => `${new Date().getFullYear()}-01-01`;
const y1 = () => `${new Date().getFullYear()}-12-31`;

const Entry = ({ e, canEdit, onEdit, onDel, origini }) => (
  <tbody className="border-b-2 border-slate-200 print:break-inside-avoid" data-testid={`reg-row-${e.id}`}>
    {e.righe.map((r, i) => (
      <tr key={i} className="align-top">
        {i === 0 && (
          <td rowSpan={e.righe.length} className="whitespace-nowrap px-3 py-2">
            <div className="mono text-xs font-semibold">{e.numero}/{e.anno}</div>
            <div className="text-xs text-slate-500">{fmtDate(e.data)}</div>
          </td>
        )}
        {i === 0 && (
          <td rowSpan={e.righe.length} className="px-3 py-2">
            <div className="text-xs font-semibold text-slate-800">{e.causale} · {e.causale_descrizione}</div>
            <div className="text-xs text-slate-600">{e.descrizione}</div>
            <span className={`mt-1 inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold print:hidden ${ORIGINE_BADGE[e.origine]}`}>{origini[e.origine]}</span>
          </td>
        )}
        <td className="px-3 py-1.5 text-xs"><span className="mono">{r.conto}</span> {r.conto_descrizione}{r.party_nome && <div className="text-slate-500">{r.party_nome}</div>}</td>
        <td className="px-3 py-1.5 text-right text-xs">{r.dare ? fmtEUR(r.dare) : ""}</td>
        <td className="px-3 py-1.5 text-right text-xs">{r.avere ? fmtEUR(r.avere) : ""}</td>
        {i === 0 && (
          <td rowSpan={e.righe.length} className="whitespace-nowrap px-2 py-2 text-right print:hidden">
            {canEdit && <>
              <button onClick={() => onEdit(e)} className="rounded p-1.5 text-slate-500 hover:bg-slate-100" aria-label="Modifica" data-testid={`reg-edit-${e.id}`}><Pencil className="h-4 w-4" /></button>
              {!e.origine.startsWith("riba") && <button onClick={() => onDel(e)} className="rounded p-1.5 text-slate-500 hover:bg-rose-50 hover:text-rose-600" aria-label="Elimina" data-testid={`reg-delete-${e.id}`}><Trash2 className="h-4 w-4" /></button>}
            </>}
            {e.modificata && <span className="ml-1 rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700" title={`Modificata da ${e.modificata_da || ""}`} data-testid={`reg-modificata-${e.id}`}>modificata</span>}
          </td>
        )}
      </tr>
    ))}
  </tbody>
);

export default function PrimaNota() {
  const { user } = useAuth();
  const { company } = useCompany();
  const canEdit = canSend(user);
  const [conti] = useConti();
  const [causali, setCausali] = useState([]);
  const [flt, setFlt] = useState({ dal: y0(), al: y1(), origine: "", q: "" });
  const [d, setD] = useState({ registrazioni: [], dare: 0, avere: 0, origini: {} });
  const [dlg, setDlg] = useState(null);
  const [inc, setInc] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = () => api.get("/contabilita/registrazioni", { params: { ...flt, origine: flt.origine || undefined, q: flt.q || undefined } }).then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, [flt]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { api.get("/contabilita/causali").then(({ data }) => setCausali(data)).catch(() => {}); }, []);
  const del = async (e) => {
    const extra = { vendita: " La fattura resta invariata.", acquisto: " La fattura passiva resta: potrai registrarla di nuovo con Rigenera.", pagamenti: " Verrà annullata anche la distinta di pagamento e le partite torneranno aperte.", bolli: " Il trimestre dei bolli tornerà da versare.", ritenute: " Il versamento delle ritenute tornerà da fare." }[e.origine] || "";
    if (!window.confirm(`Eliminare la registrazione n. ${e.numero}/${e.anno}?${extra}`)) return;
    try { await api.delete(`/contabilita/registrazioni/${e.id}`); toast.success("Registrazione eliminata"); load(); } catch (er) { toast.error(errMsg(er)); }
  };
  const rigenera = async () => {
    if (!window.confirm("Registro in contabilità le fatture e i movimenti bancari riconciliati che non sono ancora registrati. Continuare?")) return;
    setBusy(true);
    try {
      const { data } = await api.post("/contabilita/rigenera", { ricrea: false });
      toast.success(`Registrate ${data.vendite} vendite, ${data.acquisti} acquisti, ${data.banca} movimenti bancari`);
      data.errori.forEach((x) => toast.error(x));
      load();
    } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };

  return (
    <div>
      <div className="print:hidden">
        <PageHeader eyebrow="Contabilità generale" title="Prima nota e libro giornale">
          <Button variant="outline" onClick={() => window.print()} data-testid="giornale-print-btn"><Printer className="mr-2 h-4 w-4" />Stampa giornale</Button>
          {canEdit && <Button variant="outline" onClick={rigenera} disabled={busy} data-testid="coge-rigenera-btn"><RefreshCw className={`mr-2 h-4 w-4 ${busy ? "animate-spin" : ""}`} />Registra documenti mancanti</Button>}
          {canEdit && <Button variant="outline" onClick={() => setInc("IN")} data-testid="new-incasso-btn"><ArrowDownLeft className="mr-2 h-4 w-4 text-emerald-600" />Incasso</Button>}
          {canEdit && <Button variant="outline" onClick={() => setInc("PG")} data-testid="new-pagamento-btn"><ArrowUpRight className="mr-2 h-4 w-4 text-rose-600" />Pagamento</Button>}
          {canEdit && <Button onClick={() => setDlg({})} data-testid="new-registrazione-btn"><Plus className="mr-2 h-4 w-4" />Nuova registrazione</Button>}
        </PageHeader>
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <label className="text-xs text-slate-600">Dal<Input type="date" value={flt.dal} onChange={(e) => setFlt({ ...flt, dal: e.target.value })} className="w-40 bg-white" data-testid="giornale-dal" /></label>
          <label className="text-xs text-slate-600">Al<Input type="date" value={flt.al} onChange={(e) => setFlt({ ...flt, al: e.target.value })} className="w-40 bg-white" data-testid="giornale-al" /></label>
          <label className="text-xs text-slate-600">Origine
            <select value={flt.origine} onChange={(e) => setFlt({ ...flt, origine: e.target.value })} className="block h-9 rounded-md border border-slate-200 bg-white px-2 text-sm" data-testid="giornale-origine">
              <option value="">Tutte</option>{Object.entries(d.origini).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </label>
          <label className="flex-1 text-xs text-slate-600">Cerca<Input value={flt.q} onChange={(e) => setFlt({ ...flt, q: e.target.value })} placeholder="Descrizione, documento, conto, cliente…" className="bg-white" data-testid="giornale-search" /></label>
        </div>
      </div>
      <div className="mb-4 hidden print:block">
        <div className="text-lg font-bold">{company?.denominazione} · P.IVA {company?.partita_iva}</div>
        <div className="text-sm">Libro giornale dal {fmtDate(flt.dal)} al {fmtDate(flt.al)}</div>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm print:overflow-visible print:shadow-none">
        <table className="w-full text-sm print:text-[10px]" data-testid="giornale-table">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr><th className="px-3 py-3">N. / Data</th><th className="px-3 py-3">Causale e descrizione</th><th className="px-3 py-3">Conto</th><th className="px-3 py-3 text-right">Dare</th><th className="px-3 py-3 text-right">Avere</th><th className="print:hidden" /></tr>
          </thead>
          {d.registrazioni.length === 0 && <tbody><tr><td colSpan={6} className="px-4 py-12 text-center text-slate-500" data-testid="giornale-empty">Nessuna registrazione nel periodo</td></tr></tbody>}
          {d.registrazioni.map((e) => <Entry key={e.id} e={e} canEdit={canEdit} onEdit={setDlg} onDel={del} origini={d.origini} />)}
          <tfoot className="border-t-2 border-slate-900 font-bold"><tr><td colSpan={3} className="px-3 py-3">Totali ({d.registrazioni.length} registrazioni)</td><td className="px-3 py-3 text-right" data-testid="giornale-tot-dare">{fmtEUR(d.dare)}</td><td className="px-3 py-3 text-right" data-testid="giornale-tot-avere">{fmtEUR(d.avere)}</td><td className="print:hidden" /></tr></tfoot>
        </table>
      </div>
      <RegistrazioneDialog open={!!dlg} item={dlg?.id ? dlg : null} conti={conti} causali={causali} onClose={() => setDlg(null)} onSaved={load} onIncasso={(c) => { setDlg(null); setInc(c); }} />
      {inc && <IncassoSheet tipo={inc} conti={conti} onClose={() => setInc(null)} onSaved={load} />}
    </div>
  );
}

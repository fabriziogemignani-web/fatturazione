import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Minus, Printer, RefreshCw, Pencil, Trash2, Lock, ArrowDownLeft, ArrowUpRight, ChevronsUpDown } from "lucide-react";
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

const Azioni = ({ e, canEdit, onEdit, onDel }) => (
  <td className="whitespace-nowrap px-2 py-2 text-right print:hidden">
    {canEdit && <>
      <button onClick={() => onEdit(e)} className="rounded p-1.5 text-slate-500 hover:bg-slate-100" aria-label="Modifica" data-testid={`reg-edit-${e.id}`}><Pencil className="h-4 w-4" /></button>
      {e.eliminabile ? <button onClick={() => onDel(e)} className="rounded p-1.5 text-slate-500 hover:bg-rose-50 hover:text-rose-600" aria-label="Elimina" data-testid={`reg-delete-${e.id}`}><Trash2 className="h-4 w-4" /></button>
        : <button type="button" onClick={() => toast.info(e.motivo_blocco)} className="rounded p-1.5 text-slate-500 hover:bg-slate-100" title={e.motivo_blocco} aria-label="Non eliminabile" data-testid={`reg-locked-${e.id}`}><Lock className="h-4 w-4" /></button>}
    </>}
    {e.modificata && <span className="ml-1 rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700" title={`Modificata da ${e.modificata_da || ""}`} data-testid={`reg-modificata-${e.id}`}>modificata</span>}
  </td>
);

const Entry = ({ e, open, onToggle, canEdit, onEdit, onDel, origini }) => {
  const dare = e.righe.reduce((s, r) => s + (r.dare || 0), 0);
  const party = e.righe.find((r) => r.party_nome)?.party_nome;
  const showParty = party && !(e.descrizione || "").includes(party);
  return (
    <tbody className="border-b border-slate-200 print:break-inside-avoid" data-testid={`reg-row-${e.id}`}>
      <tr className={`align-middle hover:bg-slate-50 ${open ? "bg-slate-50" : ""}`}>
        <td className="w-8 pl-2 print:hidden"><button onClick={onToggle} className="grid h-6 w-6 place-items-center rounded border border-slate-300 text-slate-600 hover:bg-slate-100" aria-label={open ? "Chiudi righe" : "Mostra righe"} data-testid={`reg-toggle-${e.id}`}>{open ? <Minus className="h-3.5 w-3.5" /> : <Plus className="h-3.5 w-3.5" />}</button></td>
        <td className="whitespace-nowrap px-3 py-2"><span className="mono text-xs font-semibold">{e.numero}/{e.anno}</span> <span className="text-xs text-slate-500">{fmtDate(e.data)}</span></td>
        <td className="px-3 py-2 text-xs"><b className="text-slate-800">{e.causale}</b> · {e.descrizione}{showParty && <span className="text-slate-500"> · {party}</span>} <span className={`ml-1 inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold print:hidden ${ORIGINE_BADGE[e.origine]}`}>{origini[e.origine]}</span></td>
        <td className="px-3 py-2 text-xs text-slate-500 print:invisible">{e.righe.length} righe</td>
        <td className="px-3 py-2 text-right text-xs font-semibold print:invisible" data-testid={`reg-tot-${e.id}`}>{fmtEUR(dare)}</td>
        <td className="px-3 py-2 text-right text-xs font-semibold print:invisible">{fmtEUR(dare)}</td>
        <Azioni e={e} canEdit={canEdit} onEdit={onEdit} onDel={onDel} />
      </tr>
      {e.righe.map((r, i) => (
        <tr key={i} className={`bg-slate-50/60 ${open ? "" : "hidden print:table-row"}`} data-testid={`reg-riga-${e.id}-${i}`}>
          <td className="print:hidden" /><td /><td className="px-3 py-1 text-xs text-slate-500">{i === 0 ? e.causale_descrizione : ""}</td>
          <td className="px-3 py-1 text-xs"><span className="mono">{r.conto}</span> {r.conto_descrizione}{r.party_nome && <span className="text-slate-500"> · {r.party_nome}</span>}</td>
          <td className="px-3 py-1 text-right text-xs">{r.dare ? fmtEUR(r.dare) : ""}</td>
          <td className="px-3 py-1 text-right text-xs">{r.avere ? fmtEUR(r.avere) : ""}</td>
          <td className="print:hidden" />
        </tr>
      ))}
    </tbody>
  );
};

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
  const [open, setOpen] = useState({});
  const tutte = d.registrazioni.length > 0 && d.registrazioni.every((e) => open[e.id]);
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
          <Button variant="outline" onClick={() => setOpen(tutte ? {} : Object.fromEntries(d.registrazioni.map((e) => [e.id, true])))} data-testid="giornale-espandi-tutto"><ChevronsUpDown className="mr-2 h-4 w-4" />{tutte ? "Chiudi tutte le righe" : "Espandi tutte le righe"}</Button>
        </div>
      </div>
      <div className="mb-4 hidden print:block">
        <div className="text-lg font-bold">{company?.denominazione} · P.IVA {company?.partita_iva}</div>
        <div className="text-sm">Libro giornale dal {fmtDate(flt.dal)} al {fmtDate(flt.al)}</div>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm print:overflow-visible print:shadow-none">
        <table className="w-full text-sm print:text-[10px]" data-testid="giornale-table">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr><th className="w-8 print:hidden" /><th className="px-3 py-3">N. / Data</th><th className="px-3 py-3">Causale e descrizione</th><th className="px-3 py-3">Conto</th><th className="px-3 py-3 text-right">Dare</th><th className="px-3 py-3 text-right">Avere</th><th className="print:hidden" /></tr>
          </thead>
          {d.registrazioni.length === 0 && <tbody><tr><td colSpan={7} className="px-4 py-12 text-center text-slate-500" data-testid="giornale-empty">Nessuna registrazione nel periodo</td></tr></tbody>}
          {d.registrazioni.map((e) => <Entry key={e.id} e={e} open={!!open[e.id]} onToggle={() => setOpen({ ...open, [e.id]: !open[e.id] })} canEdit={canEdit} onEdit={setDlg} onDel={del} origini={d.origini} />)}
          <tfoot className="border-t-2 border-slate-900 font-bold"><tr><td className="print:hidden" /><td colSpan={3} className="px-3 py-3">Totali ({d.registrazioni.length} registrazioni)</td><td className="px-3 py-3 text-right" data-testid="giornale-tot-dare">{fmtEUR(d.dare)}</td><td className="px-3 py-3 text-right" data-testid="giornale-tot-avere">{fmtEUR(d.avere)}</td><td className="print:hidden" /></tr></tfoot>
        </table>
      </div>
      <RegistrazioneDialog open={!!dlg} item={dlg?.id ? dlg : null} conti={conti} causali={causali} onClose={() => setDlg(null)} onSaved={load} onIncasso={(c) => { setDlg(null); setInc(c); }} />
      {inc && <IncassoSheet tipo={inc} conti={conti} onClose={() => setInc(null)} onSaved={load} />}
    </div>
  );
}

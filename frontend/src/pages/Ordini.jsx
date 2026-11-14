import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Pencil, Trash2, PackageCheck, Lock, Unlock, ChevronDown, ChevronRight } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { OrdineDialog } from "@/components/OrdineDialog";
import { EvadiDialog, Evasioni } from "@/components/EvadiDialog";
import { EmailOrdineDialog, apriOrdinePdf } from "@/components/EmailOrdineDialog";
import { Printer, Mail, FileCheck2 } from "lucide-react";

const STATI = { aperto: ["Aperto", "bg-blue-100 text-blue-800"], parziale: ["Parzialmente evaso", "bg-amber-100 text-amber-800"], evaso: ["Evaso", "bg-emerald-100 text-emerald-800"], chiuso: ["Chiuso forzato", "bg-slate-200 text-slate-700"] };
const residuo = (o) => Math.round(o.lines.reduce((s, l) => s + Math.max(l.quantita - (l.evasa || 0), 0), 0) * 100) / 100;

const Azioni = ({ o, onEdit, onEvadi, act, onMail, tipo }) => {
  const aperto = ["aperto", "parziale"].includes(o.status);
  const evasioni = (o.evasioni || []).some((e) => !e.annullata);
  return (
    <div className="flex justify-end gap-1">
      <Button size="sm" variant="outline" onClick={() => apriOrdinePdf(tipo, o, false)} title="Stampa ordine" data-testid={`ord-pdf-${o.id}`}><Printer className="h-3.5 w-3.5" /></Button>
      {tipo === "cliente" && <Button size="sm" variant="outline" onClick={() => apriOrdinePdf(tipo, o, true)} title="Stampa conferma d'ordine" data-testid={`ord-conferma-pdf-${o.id}`}><FileCheck2 className="h-3.5 w-3.5" /></Button>}
      <Button size="sm" variant="outline" onClick={() => onMail(o)} title="Invia per email" data-testid={`ord-email-${o.id}`}><Mail className="h-3.5 w-3.5" />{o.email_inviate?.length ? <span className="ml-1 text-[10px] text-emerald-700">{o.email_inviate.length}</span> : null}</Button>
      {aperto && <Button size="sm" onClick={() => onEvadi(o)} data-testid={`ord-evadi-${o.id}`}><PackageCheck className="mr-1 h-3.5 w-3.5" />Evadi</Button>}
      {aperto && <Button size="sm" variant="outline" onClick={() => onEdit(o)} title="Modifica" data-testid={`ord-edit-${o.id}`}><Pencil className="h-3.5 w-3.5" /></Button>}
      {aperto && <Button size="sm" variant="outline" onClick={() => act(o, "chiudi", "Chiudere l'ordine? Il residuo non evaso non sarà più impegnato.")} title="Chiudi forzatamente" data-testid={`ord-chiudi-${o.id}`}><Lock className="h-3.5 w-3.5" /></Button>}
      {o.status === "chiuso" && <Button size="sm" variant="outline" onClick={() => act(o, "riapri")} data-testid={`ord-riapri-${o.id}`}><Unlock className="mr-1 h-3.5 w-3.5" />Riapri</Button>}
      {!evasioni && <Button size="sm" variant="outline" className="text-rose-600" onClick={() => act(o, "elimina", `Eliminare l'ordine ${o.numero_display}?`)} title="Elimina" data-testid={`ord-elimina-${o.id}`}><Trash2 className="h-3.5 w-3.5" /></Button>}
    </div>
  );
};

const Righe = ({ o }) => (
  <tr className="bg-slate-50/60"><td /><td colSpan={7} className="px-4 pb-3">
    <table className="w-full text-xs" data-testid={`ord-righe-${o.id}`}>
      <thead className="text-left text-slate-500"><tr><th className="py-1">Articolo</th><th className="text-right">Ordinata</th><th className="text-right">Evasa</th><th className="text-right">Residuo</th><th className="text-right">Prezzo</th></tr></thead>
      <tbody>{o.lines.map((l) => <tr key={l.id} className="border-t border-slate-100"><td className="py-1">{l.codice && <span className="mono">{l.codice} · </span>}{l.descrizione}</td><td className="text-right">{l.quantita} {l.unita_misura}</td><td className="text-right">{l.evasa || 0}</td><td className="text-right font-semibold">{Math.max(l.quantita - (l.evasa || 0), 0)}</td><td className="text-right">{fmtEUR(l.prezzo_unitario)}</td></tr>)}</tbody>
    </table>
    {o.destinazione?.indirizzo && <div className="mt-2 text-xs text-slate-600">Destinazione: {o.destinazione.denominazione} {o.destinazione.indirizzo} {o.destinazione.cap} {o.destinazione.comune} {o.destinazione.provincia}</div>}
    <Evasioni o={o} />
  </td></tr>
);

export default function Ordini({ tipo }) {
  const [rows, setRows] = useState(null);
  const [stato, setStato] = useState("");
  const [dlg, setDlg] = useState(null);
  const [ev, setEv] = useState(null);
  const [mail, setMail] = useState(null);
  const [open, setOpen] = useState({});
  const load = () => api.get(`/ordini/${tipo}`, { params: stato ? { stato } : {} }).then(({ data }) => setRows(data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, [stato]); // eslint-disable-line react-hooks/exhaustive-deps
  const act = async (o, a, conf) => {
    if (conf && !window.confirm(conf)) return;
    try { a === "elimina" ? await api.delete(`/ordini/${tipo}/${o.id}`) : await api.post(`/ordini/${tipo}/${o.id}/${a}`); toast.success("Fatto"); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  const cli = tipo === "cliente";
  return (
    <div data-testid={`ordini-${tipo}-page`}>
      <PageHeader eyebrow={cli ? "Vendite" : "Acquisti"} title={cli ? "Ordini clienti" : "Ordini fornitori"} subtitle={cli ? "Gli ordini aperti impegnano gli articoli; l'evasione crea il DDT e scarica il magazzino" : "Gli ordini aperti aumentano l'ordinato; l'evasione registra l'entrata merce e carica il magazzino"}>
        <Button onClick={() => setDlg({})} data-testid="ord-new-btn"><Plus className="mr-2 h-4 w-4" />Nuovo ordine</Button>
      </PageHeader>
      <div className="mb-4 flex flex-wrap gap-2">
        {[["", "Tutti"], ["aperto", "Aperti"], ["parziale", "Parziali"], ["evaso", "Evasi"], ["chiuso", "Chiusi"]].map(([k, l]) => <button key={k} onClick={() => setStato(k)} className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${stato === k ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 text-slate-600 hover:bg-slate-50"}`} data-testid={`ord-filtro-${k || "tutti"}`}>{l}</button>)}
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm" data-testid="ord-table">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500"><tr><th className="w-8" /><th className="px-4 py-3">Ordine</th><th className="px-4 py-3">{cli ? "Cliente" : "Fornitore"}</th><th className="px-4 py-3">Consegna</th><th className="px-4 py-3">Stato</th><th className="px-4 py-3 text-right">Imponibile</th><th className="px-4 py-3 text-right">Residuo q.tà</th><th /></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {rows?.length === 0 && <tr><td colSpan={8} className="px-4 py-10 text-center text-slate-500" data-testid="ord-empty">Nessun ordine</td></tr>}
            {rows?.map((o) => [
              <tr key={o.id} className="hover:bg-slate-50" data-testid={`ord-row-${o.id}`}>
                <td className="pl-2"><button onClick={() => setOpen({ ...open, [o.id]: !open[o.id] })} className="text-slate-500" data-testid={`ord-toggle-${o.id}`}>{open[o.id] ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}</button></td>
                <td className="px-4 py-3"><div className="mono text-xs font-semibold">{o.numero_display}</div><div className="text-xs text-slate-500">{fmtDate(o.data)}{o.riferimento ? ` · rif. ${o.riferimento}` : ""}</div></td>
                <td className="px-4 py-3">{o.party.denominazione}</td>
                <td className="px-4 py-3">{o.data_consegna ? fmtDate(o.data_consegna) : "—"}</td>
                <td className="px-4 py-3"><span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${STATI[o.status]?.[1]}`} data-testid={`ord-stato-${o.id}`}>{STATI[o.status]?.[0] || o.status}</span></td>
                <td className="px-4 py-3 text-right">{fmtEUR(o.imponibile)}</td>
                <td className="px-4 py-3 text-right font-semibold" data-testid={`ord-residuo-${o.id}`}>{["evaso", "chiuso"].includes(o.status) ? "—" : residuo(o)}</td>
                <td className="px-4 py-3"><Azioni o={o} onEdit={setDlg} onEvadi={setEv} act={act} onMail={setMail} tipo={tipo} /></td>
              </tr>,
              open[o.id] && <Righe key={`${o.id}-r`} o={o} />,
            ])}
          </tbody>
        </table>
      </div>
      <OrdineDialog tipo={tipo} ordine={dlg?.id ? dlg : null} open={!!dlg} onOpenChange={(v) => !v && setDlg(null)} onSaved={load} />
      {mail && <EmailOrdineDialog tipo={tipo} o={mail} onClose={() => setMail(null)} onSent={load} />}
      {ev && <EvadiDialog tipo={tipo} o={ev} open={!!ev} onOpenChange={(v) => !v && setEv(null)} onDone={load} />}
    </div>
  );
}

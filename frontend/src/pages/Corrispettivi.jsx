import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Printer, CloudDownload, Trash2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { useAuth, canSend } from "@/context/AuthContext";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PERIODI, range, Totali } from "@/pages/RegistroIvaAcquisti";

const Row = ({ r, edit, onDelete }) => r.riepilogo.map((x, i) => (
  <tr key={`${r.id}-${i}`} data-testid={i ? undefined : `corr-row-${r.data}`}>
    {i === 0 && <>
      <td className="px-3 py-2 font-semibold" rowSpan={r.riepilogo.length}>{fmtDate(r.data)}</td>
      <td className="mono px-3 py-2 text-xs" rowSpan={r.riepilogo.length}>{r.matricola}</td>
      <td className="px-3 py-2 text-right" rowSpan={r.riepilogo.length}>{r.n_documenti}</td>
    </>}
    <td className="px-3 py-2">{x.natura || `${x.aliquota}%`}</td>
    <td className="px-3 py-2 text-right">{fmtEUR(x.imponibile)}</td>
    <td className="px-3 py-2 text-right">{fmtEUR(x.imposta)}</td>
    {i === 0 && <td className="px-3 py-2 text-right font-semibold" rowSpan={r.riepilogo.length} data-testid={`corr-totale-${r.data}`}>{fmtEUR(r.totale)}</td>}
    {i === 0 && <td className="px-2 py-2 text-right print:hidden" rowSpan={r.riepilogo.length}>{edit && <Button size="sm" variant="ghost" className="text-rose-600" onClick={() => onDelete(r)} data-testid={`corr-delete-${r.data}`}><Trash2 className="h-3.5 w-3.5" /></Button>}</td>}
  </tr>
));

export default function Corrispettivi() {
  const { user } = useAuth();
  const [anno, setAnno] = useState(null);
  const [per, setPer] = useState("anno");
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState(false);
  const y = anno || new Date().getFullYear();
  const [dal, al] = range(y, per);
  const load = useCallback(() => { api.get("/corrispettivi", { params: { anno: y, dal, al } }).then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e))); }, [y, dal, al]);
  useEffect(() => { load(); }, [load]);
  const sync = async () => {
    setBusy(true);
    try { const { data } = await api.post("/corrispettivi/sync"); toast.success(data.ricevuti ? `Ricevuti ${data.ricevuti} giorni di corrispettivi` : "Nessun nuovo corrispettivo"); load(); } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };
  const remove = async (r) => {
    if (!window.confirm(`Eliminare i corrispettivi del ${fmtDate(r.data)}?`)) return;
    try { await api.delete(`/corrispettivi/${r.id}`); toast.success("Eliminato"); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  if (!d) return <div className="text-sm text-slate-500">Caricamento…</div>;
  const edit = canSend(user);

  return (
    <div>
      <div className="print:hidden">
        <PageHeader eyebrow="IVA" title="Corrispettivi giornalieri">
          <Select value={String(y)} onValueChange={(v) => setAnno(Number(v))}>
            <SelectTrigger className="w-28 bg-white" data-testid="corr-anno-select"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-white">{d.anni.map((a) => <SelectItem key={a} value={String(a)} data-testid={`corr-anno-${a}`}>{a}</SelectItem>)}</SelectContent>
          </Select>
          <Select value={per} onValueChange={setPer}>
            <SelectTrigger className="w-44 bg-white" data-testid="corr-periodo-select"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-white">{PERIODI.map(([k, l]) => <SelectItem key={k} value={k} data-testid={`corr-periodo-${k}`}>{l}</SelectItem>)}</SelectContent>
          </Select>
          {edit && <Button variant="outline" onClick={sync} disabled={busy} data-testid="corr-sync-btn"><CloudDownload className="mr-2 h-4 w-4" />{busy ? "Ricezione…" : "Ricevi dal cassetto fiscale"}</Button>}
          <Button onClick={() => window.print()} data-testid="corr-print-btn"><Printer className="mr-2 h-4 w-4" />Stampa / PDF</Button>
        </PageHeader>
        <p className="-mt-4 mb-4 text-xs text-slate-500">Corrispettivi giornalieri trasmessi dal registratore telematico, totali per aliquota con IVA scorporata. Ricezione dal cassetto fiscale <b>SIMULATA</b>: arrivano i giorni mancanti fino a ieri (domeniche escluse). L'IVA entra a debito nella liquidazione.</p>
      </div>
      <div className="mb-4 hidden print:block">
        <div className="text-lg font-bold">{d.azienda.denominazione} · P.IVA {d.azienda.partita_iva}</div>
        <div className="text-sm">Registro dei corrispettivi dal {fmtDate(dal)} al {fmtDate(al)}</div>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm print:overflow-visible print:shadow-none">
        <table className="w-full text-sm print:text-[10px]" data-testid="corr-table">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr><th className="px-3 py-3 font-medium">Giorno</th><th className="px-3 py-3 font-medium">Matricola RT</th><th className="px-3 py-3 text-right font-medium">Documenti</th><th className="px-3 py-3 font-medium">Aliquota</th><th className="px-3 py-3 text-right font-medium">Imponibile</th><th className="px-3 py-3 text-right font-medium">Imposta</th><th className="px-3 py-3 text-right font-medium">Totale incassato</th><th className="print:hidden" /></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {d.rows.length === 0 && <tr><td colSpan={8} className="px-4 py-10 text-center text-slate-500" data-testid="corr-empty">Nessun corrispettivo nel periodo</td></tr>}
            {d.rows.map((r) => <Row key={r.id} r={r} edit={edit} onDelete={remove} />)}
          </tbody>
        </table>
      </div>
      <Totali d={d} />
      <p className="mt-3 text-sm font-semibold text-slate-700" data-testid="corr-totale-periodo">Totale incassato nel periodo: {fmtEUR(d.totale)}</p>
    </div>
  );
}

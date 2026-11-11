import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Download, Trash2, ChevronDown, ChevronRight, FileText } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";

const STATO = { presentato: ["Presentato", "bg-blue-100 text-blue-800"], maturato: ["Scaduto, buon fine", "bg-emerald-100 text-emerald-800"], insoluto: ["Insoluto", "bg-rose-100 text-rose-800"] };
const today = () => new Date().toISOString().slice(0, 10);
const plus30 = () => { const d = new Date(); d.setDate(d.getDate() + 30); return d.toISOString().slice(0, 10); };

export const InsolutoDialog = ({ effetto, onOpenChange, onDone }) => {
  const [f, setF] = useState({ data: today(), spese_banca: 0, spese_cliente: 0, nuova_scadenza: plus30() });
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (effetto) setF({ data: today(), spese_banca: 0, spese_cliente: 0, nuova_scadenza: plus30() }); }, [effetto]);
  const save = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/riba/effetti/${effetto.id}/insoluto`, { ...f, spese_banca: Number(f.spese_banca) || 0, spese_cliente: Number(f.spese_cliente) || 0 });
      toast.success("Insoluto registrato: partita riaperta con la nuova scadenza");
      onDone(data);
      onOpenChange(false);
    } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };
  const fld = (k, label, type = "number") => (
    <label className="text-xs text-slate-600">{label}<Input type={type} step="0.01" min={0} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} data-testid={`insoluto-${k}`} /></label>
  );
  return (
    <Dialog open={!!effetto} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white sm:max-w-md" data-testid="insoluto-dialog">
        <DialogHeader><DialogTitle>Registra insoluto</DialogTitle></DialogHeader>
        {effetto && <p className="text-sm text-slate-600">{effetto.cliente.denominazione} · {effetto.numero_display} · scadenza {fmtDate(effetto.scadenza)} · <b>{fmtEUR(effetto.importo)}</b></p>}
        <div className="grid grid-cols-2 gap-3">
          {fld("data", "Data insoluto", "date")}
          {fld("nuova_scadenza", "Nuova scadenza proposta", "date")}
          {fld("spese_banca", "Spese addebitate dalla banca €")}
          {fld("spese_cliente", "Spese da addebitare al cliente €")}
        </div>
        <p className="text-xs text-slate-500">Viene registrato lo storno in banca, le spese bancarie e il riaddebito al cliente; la rata torna aperta con la nuova scadenza e le spese diventano una nuova partita Ri.Ba.</p>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Annulla</Button>
          <Button onClick={save} disabled={busy} className="bg-rose-600 hover:bg-rose-700" data-testid="insoluto-save">Registra insoluto</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const Effetti = ({ did, reload }) => {
  const [d, setD] = useState(null);
  const [ins, setIns] = useState(null);
  const load = useCallback(() => { api.get(`/riba/distinte/${did}`).then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e))); }, [did]);
  useEffect(() => { load(); }, [load]);
  if (!d) return <tr><td colSpan={7} className="px-4 py-3 text-xs text-slate-500">Caricamento…</td></tr>;
  return (
    <>
      {d.effetti.map((e) => (
        <tr key={e.id} className="bg-slate-50/60 text-xs" data-testid={`riba-effetto-${e.id}`}>
          <td />
          <td className="px-4 py-2">{fmtDate(e.scadenza)}</td>
          <td className="px-4 py-2" colSpan={2}>{e.cliente.denominazione} · <span className="mono">{e.numero_display}</span>{e.rate_totali > 1 && ` rata ${e.rata_n}/${e.rate_totali}`}</td>
          <td className="px-4 py-2 text-right">{fmtEUR(e.importo)}</td>
          <td className="px-4 py-2"><span className={`rounded-full px-2 py-0.5 font-semibold ${STATO[e.stato][1]}`} data-testid={`riba-effetto-stato-${e.id}`}>{STATO[e.stato][0]}</span></td>
          <td className="px-4 py-2 text-right">{e.stato === "maturato" && <Button size="sm" variant="outline" className="h-7 text-rose-700" onClick={() => setIns(e)} data-testid={`riba-insoluto-btn-${e.id}`}>Insoluto</Button>}</td>
        </tr>
      ))}
      <InsolutoDialog effetto={ins} onOpenChange={(o) => !o && setIns(null)} onDone={() => { load(); reload(); }} />
    </>
  );
};

export const RibaDistinte = () => {
  const [rows, setRows] = useState(null);
  const [open, setOpen] = useState({});
  const load = useCallback(() => { api.get("/riba/distinte").then(({ data }) => setRows(data)).catch((e) => toast.error(errMsg(e))); }, []);
  useEffect(() => { load(); }, [load]);
  const scarica = async (d) => {
    try {
      const { data } = await api.get(`/riba/distinte/${d.id}/cbi`, { responseType: "blob" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(data);
      a.download = `RIBA_${d.anno}_${String(d.numero).padStart(4, "0")}.txt`;
      a.click();
    } catch (e) {
      const msg = e.response?.data instanceof Blob ? JSON.parse(await e.response.data.text()).detail : errMsg(e);
      toast.error(typeof msg === "string" ? msg : "Impossibile generare il flusso");
    }
  };
  const stampa = async (d) => {
    const w = window.open("", "_blank");
    try {
      const { data } = await api.get(`/riba/distinte/${d.id}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([data], { type: "application/pdf" }));
      if (w) w.location.href = url;
      else { const a = document.createElement("a"); a.href = url; a.download = `Distinta_RIBA_${d.anno}_${String(d.numero).padStart(4, "0")}.pdf`; a.click(); }
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (e) { if (w) w.close(); toast.error(errMsg(e)); }
  };
  const annulla = async (d) => {
    if (!window.confirm(`Annullare la distinta ${d.numero_display}? Le scadenze tornano da presentare.`)) return;
    try { await api.delete(`/riba/distinte/${d.id}`); toast.success("Distinta annullata"); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  if (!rows) return <p className="text-sm text-slate-500">Caricamento…</p>;
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table className="w-full text-sm" data-testid="riba-distinte-table">
        <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
          <tr><th className="w-8" /><th className="px-4 py-3 font-medium">Data</th><th className="px-4 py-3 font-medium">Distinta</th><th className="px-4 py-3 font-medium">Banca</th><th className="px-4 py-3 text-right font-medium">Totale</th><th className="px-4 py-3 font-medium">Effetti</th><th className="px-4 py-3" /></tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.length === 0 && <tr><td colSpan={7} className="px-4 py-10 text-center text-slate-500" data-testid="riba-distinte-empty">Nessuna distinta presentata</td></tr>}
          {rows.map((d) => [
            <tr key={d.id} className="hover:bg-slate-50" data-testid={`riba-distinta-${d.id}`}>
              <td className="pl-3"><button onClick={() => setOpen({ ...open, [d.id]: !open[d.id] })} data-testid={`riba-distinta-toggle-${d.id}`}>{open[d.id] ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}</button></td>
              <td className="px-4 py-3">{fmtDate(d.data)}</td>
              <td className="mono px-4 py-3 font-medium">{d.numero_display}</td>
              <td className="px-4 py-3">{d.banca_nome}<div className="text-xs text-slate-400">conto SBF {d.conto_sbf}</div></td>
              <td className="px-4 py-3 text-right font-semibold">{fmtEUR(d.totale)}</td>
              <td className="px-4 py-3 text-xs">{Object.entries(d.stati).map(([s, n]) => <span key={s} className={`mr-1 rounded-full px-2 py-0.5 font-semibold ${STATO[s][1]}`}>{n} {STATO[s][0].toLowerCase()}</span>)}</td>
              <td className="whitespace-nowrap px-4 py-3 text-right">
                <Button size="sm" variant="outline" className="mr-1" onClick={() => stampa(d)} data-testid={`riba-pdf-btn-${d.id}`}><FileText className="mr-1 h-3.5 w-3.5" />PDF</Button>
                <Button size="sm" variant="outline" onClick={() => scarica(d)} data-testid={`riba-cbi-btn-${d.id}`}><Download className="mr-1 h-3.5 w-3.5" />Flusso CBI</Button>
                {Object.keys(d.stati).every((s) => s === "presentato") && <Button size="sm" variant="ghost" className="ml-1 text-rose-600" onClick={() => annulla(d)} data-testid={`riba-annulla-btn-${d.id}`}><Trash2 className="h-3.5 w-3.5" /></Button>}
              </td>
            </tr>,
            open[d.id] && <Effetti key={`e-${d.id}`} did={d.id} reload={load} />,
          ])}
        </tbody>
      </table>
    </div>
  );
};

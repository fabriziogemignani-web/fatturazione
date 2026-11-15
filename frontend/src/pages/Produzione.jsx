import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Plus, Play, PackagePlus, Lock, Trash2, Undo2, ChevronDown, ChevronRight, Printer, Timer } from "lucide-react";
import { TempiFasi, Confronto } from "@/components/TempiFasi";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { PageHeader } from "@/components/Common";
import { SearchPicker } from "@/components/SearchPicker";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";

const today = () => new Date().toISOString().slice(0, 10);
const STATI = { pianificato: ["Pianificato", "bg-slate-100 text-slate-700"], lanciato: ["Lanciato", "bg-blue-100 text-blue-800"], in_corso: ["In corso", "bg-amber-100 text-amber-800"], completato: ["Completato", "bg-emerald-100 text-emerald-800"], chiuso: ["Chiuso", "bg-slate-200 text-slate-700"] };
const apriScheda = async (o) => {
  const w = window.open("", "_blank");
  try {
    const { data } = await api.get(`/produzione/ordini/${o.id}/pdf`, { responseType: "blob" });
    const url = URL.createObjectURL(new Blob([data], { type: "application/pdf" }));
    if (w) w.location.href = url; else { const a = document.createElement("a"); a.href = url; a.download = `Scheda_lavoro_OP_${o.numero}.pdf`; a.click(); }
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch (e) { if (w) w.close(); toast.error(errMsg(e)); }
};
const ORIG = { manuale: "manuale", ordine_cliente: "da ordine cliente", mrp: "da MRP / sottoscorta" };

const NuovoOp = ({ open, onClose, onDone }) => {
  const [arts, setArts] = useState([]);
  const [f, setF] = useState({ article_id: "", quantita: 1, data: today(), data_consegna: "", note: "" });
  useEffect(() => { if (open) api.get("/produzione/distinte").then(({ data }) => setArts(data)); }, [open]);
  const items = useMemo(() => arts.map((d) => ({ key: d.article_id, label: `${d.codice} · ${d.descrizione}` })), [arts]);
  const save = async () => { try { const { data } = await api.post("/produzione/ordini", { ...f, quantita: Number(f.quantita) }); toast.success(`${data.numero_display} creato`); onDone(); onClose(); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="bg-white sm:max-w-xl" data-testid="op-new-dialog">
        <DialogHeader><DialogTitle>Nuovo ordine di produzione</DialogTitle></DialogHeader>
        <label className="text-xs text-slate-600">Prodotto (con distinta base)<SearchPicker items={items} value={items.find((i) => i.key === f.article_id)?.label} onPick={(i) => setF({ ...f, article_id: i.key })} onClear={() => setF({ ...f, article_id: "" })} placeholder="Cerca prodotto" testId="op-prodotto" className="w-full" /></label>
        <div className="grid grid-cols-3 gap-3">
          <label className="text-xs text-slate-600">Quantità<Input type="number" min={0} value={f.quantita} onChange={(e) => setF({ ...f, quantita: e.target.value })} data-testid="op-quantita" /></label>
          <label className="text-xs text-slate-600">Data<Input type="date" value={f.data} onChange={(e) => setF({ ...f, data: e.target.value })} data-testid="op-data" /></label>
          <label className="text-xs text-slate-600">Consegna<Input type="date" value={f.data_consegna} onChange={(e) => setF({ ...f, data_consegna: e.target.value })} data-testid="op-consegna" /></label>
        </div>
        <Input placeholder="Note" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} data-testid="op-note" />
        <DialogFooter><Button variant="outline" onClick={onClose}>Annulla</Button><Button onClick={save} disabled={!f.article_id || !(Number(f.quantita) > 0)} data-testid="op-save">Crea ordine</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const Versa = ({ o, onClose, onDone }) => {
  const [f, setF] = useState({ data: today(), quantita: String(Math.max(o.quantita - o.prodotta, 0)), chiudi: false });
  const send = async (forza = false) => {
    try { await api.post(`/produzione/ordini/${o.id}/versa`, { ...f, quantita: Number(f.quantita), forza }); toast.success("Produzione versata: componenti scaricati e prodotto caricato a magazzino"); onDone(); onClose(); } catch (e) {
      const det = e.response?.data?.detail;
      if (e.response?.status === 409 && det?.carenze) { if (window.confirm(`${det.message}:\n${det.carenze.map((c) => `${c.codice}: servono ${c.richiesta}, in giacenza ${c.disponibile}`).join("\n")}\n\nVersare comunque?`)) send(true); } else toast.error(errMsg(e));
    }
  };
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="bg-white sm:max-w-lg" data-testid="op-versa-dialog">
        <DialogHeader><DialogTitle>Versa produzione · {o.numero_display}</DialogTitle></DialogHeader>
        <p className="text-sm text-slate-600">{o.codice} {o.descrizione} · prodotti {o.prodotta} su {o.quantita}</p>
        <div className="grid grid-cols-2 gap-3">
          <label className="text-xs text-slate-600">Data<Input type="date" value={f.data} onChange={(e) => setF({ ...f, data: e.target.value })} data-testid="versa-data" /></label>
          <label className="text-xs text-slate-600">Quantità prodotta<Input type="number" min={0} value={f.quantita} onChange={(e) => setF({ ...f, quantita: e.target.value })} data-testid="versa-quantita" /></label>
        </div>
        <ul className="text-xs text-slate-600">{o.componenti.map((c) => <li key={c.article_id}>Scarico {c.codice}: {Math.round(c.quantita * (Number(f.quantita) || 0) * 10000) / 10000} {c.unita_misura}</li>)}</ul>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.chiudi} onChange={(e) => setF({ ...f, chiudi: e.target.checked })} data-testid="versa-chiudi" />Chiudi l'ordine anche se la quantità è inferiore</label>
        <DialogFooter><Button variant="outline" onClick={onClose}>Annulla</Button><Button onClick={() => send()} disabled={!(Number(f.quantita) > 0)} data-testid="versa-conferma">Versa</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const Dettaglio = ({ o, act }) => (
  <tr className="bg-slate-50/60"><td /><td colSpan={7} className="px-4 pb-3 text-xs" data-testid={`op-dettaglio-${o.id}`}>
    <div className="grid gap-4 md:grid-cols-4">
      <div><b>Componenti</b>{o.componenti.map((c) => <div key={c.article_id}>{c.codice} · {c.quantita} × {o.quantita} = {Math.round(c.quantita * o.quantita * 10000) / 10000} {c.unita_misura}</div>)}</div>
      <div><b>Ciclo</b>{o.fasi.map((x, i) => <div key={i}>{(i + 1) * 10} {x.descrizione} · {x.centro} · {x.minuti_previsti} min prev.{x.minuti_effettivi ? ` · ${x.minuti_effettivi} eff.` : ""}</div>)}{!o.fasi.length && <div>—</div>}</div>
      <div><b>Versamenti</b> · costo standard {fmtEUR(o.costo_standard.materiali + o.costo_standard.lavorazioni)}/pz
        {o.versamenti.map((v) => <div key={v.id} className={v.annullato ? "text-slate-400 line-through" : ""}>{fmtDate(v.data)} · {v.quantita} pz · mat. {fmtEUR(v.costo_materiali)} + lav. {fmtEUR(v.costo_lavorazioni)} = {fmtEUR(v.costo_unitario)}/pz{v.forzato ? " (forzato)" : ""}
          {!v.annullato && <button className="ml-1 text-rose-600 hover:underline" onClick={() => act(o, `versamenti/${v.id}/annulla`, "Annullare il versamento? Carico e scarichi vengono stornati.")} data-testid={`op-versa-annulla-${v.id}`}><Undo2 className="inline h-3 w-3" /> annulla</button>}</div>)}</div>
      <div><b>Standard / effettivo</b><Confronto c={o.consuntivo} /></div>
    </div>
  </td></tr>
);

export default function Produzione() {
  const [rows, setRows] = useState(null);
  const [nuovo, setNuovo] = useState(false);
  const [versa, setVersa] = useState(null);
  const [tempi, setTempi] = useState(null);
  const [open, setOpen] = useState({});
  const load = () => api.get("/produzione/ordini").then(({ data }) => setRows(data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, []);
  const act = async (o, path, conf, method = "post") => {
    if (conf && !window.confirm(conf)) return;
    try { await api[method](`/produzione/ordini/${o.id}${path ? `/${path}` : ""}`); toast.success("Fatto"); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div data-testid="produzione-page">
      <PageHeader eyebrow="Produzione" title="Ordini di produzione" subtitle="Pianifica, lancia e versa: i componenti si scaricano al versamento e il prodotto entra a magazzino al costo di materiali e lavorazioni">
        <Button onClick={() => setNuovo(true)} data-testid="op-new-btn"><Plus className="mr-2 h-4 w-4" />Nuovo ordine</Button>
      </PageHeader>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm" data-testid="op-table">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500"><tr><th className="w-8" /><th className="px-4 py-3">Ordine</th><th className="px-4 py-3">Prodotto</th><th className="px-4 py-3">Origine</th><th className="px-4 py-3">Consegna</th><th className="px-4 py-3 text-right">Prodotti</th><th className="px-4 py-3">Stato</th><th /></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {rows?.length === 0 && <tr><td colSpan={8} className="px-4 py-10 text-center text-slate-500" data-testid="op-empty">Nessun ordine di produzione</td></tr>}
            {rows?.map((o) => [
              <tr key={o.id} data-testid={`op-row-${o.id}`}>
                <td className="pl-2"><button onClick={() => setOpen({ ...open, [o.id]: !open[o.id] })} data-testid={`op-toggle-${o.id}`}>{open[o.id] ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}</button></td>
                <td className="px-4 py-3"><div className="mono text-xs font-semibold">{o.numero_display}</div><div className="text-xs text-slate-500">{fmtDate(o.data)}</div></td>
                <td className="px-4 py-3"><span className="mono text-xs">{o.codice}</span> {o.descrizione}</td>
                <td className="px-4 py-3 text-xs">{ORIG[o.origine]}{o.ordine_cliente && <div>{o.ordine_cliente} · {o.cliente}</div>}</td>
                <td className="px-4 py-3">{o.data_consegna ? fmtDate(o.data_consegna) : "—"}</td>
                <td className="px-4 py-3 text-right font-semibold" data-testid={`op-prodotta-${o.id}`}>{o.prodotta} / {o.quantita}</td>
                <td className="px-4 py-3"><span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${STATI[o.status][1]}`} data-testid={`op-stato-${o.id}`}>{STATI[o.status][0]}</span></td>
                <td className="whitespace-nowrap px-4 py-3 text-right">
                  <Button size="sm" variant="outline" className="mr-1" title="Stampa scheda di lavoro" onClick={() => apriScheda(o)} data-testid={`op-pdf-${o.id}`}><Printer className="h-3.5 w-3.5" /></Button>
                  {o.status !== "pianificato" && o.fasi.length > 0 && <Button size="sm" variant="outline" className="mr-1" title="Tempi effettivi" onClick={() => setTempi(o)} data-testid={`op-tempi-${o.id}`}><Timer className="h-3.5 w-3.5" /></Button>}
                  {o.status === "pianificato" && <Button size="sm" onClick={() => act(o, "stato/lanciato")} data-testid={`op-lancia-${o.id}`}><Play className="mr-1 h-3.5 w-3.5" />Lancia</Button>}
                  {["lanciato", "in_corso"].includes(o.status) && <Button size="sm" onClick={() => setVersa(o)} data-testid={`op-versa-${o.id}`}><PackagePlus className="mr-1 h-3.5 w-3.5" />Versa</Button>}
                  {["pianificato", "lanciato", "in_corso"].includes(o.status) && <Button size="sm" variant="outline" className="ml-1" title="Chiudi" onClick={() => act(o, "stato/chiuso", "Chiudere l'ordine? Il residuo non verrà prodotto.")} data-testid={`op-chiudi-${o.id}`}><Lock className="h-3.5 w-3.5" /></Button>}
                  {!o.versamenti.some((v) => !v.annullato) && <Button size="sm" variant="outline" className="ml-1 text-rose-600" onClick={() => act(o, "", `Eliminare ${o.numero_display}?`, "delete")} data-testid={`op-elimina-${o.id}`}><Trash2 className="h-3.5 w-3.5" /></Button>}
                </td>
              </tr>,
              open[o.id] && <Dettaglio key={`${o.id}-d`} o={o} act={act} />,
            ])}
          </tbody>
        </table>
      </div>
      <NuovoOp open={nuovo} onClose={() => setNuovo(false)} onDone={load} />
      {versa && <Versa o={versa} onClose={() => setVersa(null)} onDone={load} />}
      {tempi && <TempiFasi o={tempi} onClose={() => setTempi(null)} onDone={load} />}
    </div>
  );
}

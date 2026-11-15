import { useState } from "react";
import { toast } from "sonner";
import { Trash2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";

const today = () => new Date().toISOString().slice(0, 10);

const Fase = ({ o, f, i, onChange }) => {
  const [v, setV] = useState({ data: today(), minuti: "", operatore: "", note: "" });
  const add = async () => {
    try { const { data } = await api.post(`/produzione/ordini/${o.id}/fasi/${i}/tempi`, { ...v, minuti: Number(v.minuti) }); setV({ ...v, minuti: "", note: "" }); onChange(data); toast.success("Tempo registrato"); } catch (e) { toast.error(errMsg(e)); }
  };
  const del = async (tid) => { try { const { data } = await api.delete(`/produzione/ordini/${o.id}/fasi/${i}/tempi/${tid}`); onChange(data); } catch (e) { toast.error(errMsg(e)); } };
  const eff = f.minuti_effettivi || 0;
  const prev = f.setup_min + f.minuti_pezzo * o.consuntivo.base;
  return (
    <div className="rounded-lg border border-slate-200 p-3" data-testid={`tempi-fase-${i}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
        <b>{(i + 1) * 10} · {f.descrizione} <span className="font-normal text-slate-500">· {f.centro} · {fmtEUR(f.costo_orario)}/h</span></b>
        <span className={eff > prev ? "text-rose-600" : "text-emerald-700"} data-testid={`tempi-fase-tot-${i}`}>{eff} min effettivi su {Math.round(prev * 100) / 100} previsti</span>
      </div>
      {(f.tempi || []).map((x) => (
        <div key={x.id} className="flex items-center gap-2 text-xs text-slate-600">{fmtDate(x.data)} · {x.minuti} min{x.operatore && ` · ${x.operatore}`}{x.note && ` · ${x.note}`}
          <button className="text-rose-600" onClick={() => del(x.id)} data-testid={`tempi-del-${x.id}`}><Trash2 className="h-3 w-3" /></button></div>
      ))}
      <div className="mt-2 grid grid-cols-[8.5rem_6rem_1fr_1fr_auto] gap-2">
        <Input type="date" value={v.data} onChange={(e) => setV({ ...v, data: e.target.value })} data-testid={`tempi-data-${i}`} />
        <Input type="number" min={0} placeholder="Minuti" value={v.minuti} onChange={(e) => setV({ ...v, minuti: e.target.value })} data-testid={`tempi-minuti-${i}`} />
        <Input placeholder="Operatore" value={v.operatore} onChange={(e) => setV({ ...v, operatore: e.target.value })} data-testid={`tempi-operatore-${i}`} />
        <Input placeholder="Note" value={v.note} onChange={(e) => setV({ ...v, note: e.target.value })} data-testid={`tempi-note-${i}`} />
        <Button size="sm" onClick={add} disabled={!(Number(v.minuti) > 0)} data-testid={`tempi-add-${i}`}>Registra</Button>
      </div>
    </div>
  );
};

export const Confronto = ({ c }) => (
  <table className="mt-1 w-full text-xs" data-testid="op-consuntivo">
    <thead className="text-slate-500"><tr><th className="text-left">su {c.base} pz</th><th className="text-right">Standard</th><th className="text-right">Effettivo</th></tr></thead>
    <tbody>
      <tr><td>Materiali</td><td className="text-right">{fmtEUR(c.std_materiali)}</td><td className="text-right">{fmtEUR(c.eff_materiali)}</td></tr>
      <tr><td>Lavorazioni</td><td className="text-right">{fmtEUR(c.std_lavorazioni)}</td><td className="text-right">{fmtEUR(c.eff_lavorazioni)}</td></tr>
      <tr className="font-semibold"><td>Totale</td><td className="text-right">{fmtEUR(c.std_totale)}</td><td className="text-right" data-testid="op-consuntivo-eff">{fmtEUR(c.eff_totale)}</td></tr>
      <tr><td>Unitario</td><td className="text-right">{fmtEUR(c.std_unitario)}</td><td className="text-right">{fmtEUR(c.eff_unitario)}</td></tr>
      <tr className={c.scostamento > 0 ? "text-rose-600" : "text-emerald-700"}><td>Scostamento</td><td /><td className="text-right" data-testid="op-consuntivo-scost">{c.scostamento > 0 ? "+" : ""}{fmtEUR(c.scostamento)} ({c.scostamento_pct}%)</td></tr>
    </tbody>
    {c.fasi_mancanti > 0 && <caption className="caption-bottom pt-1 text-left text-amber-700">{c.fasi_mancanti} fasi senza tempi registrati</caption>}
  </table>
);

export const TempiFasi = ({ o, onClose, onDone }) => {
  const [cur, setCur] = useState(o);
  return (
    <Dialog open onOpenChange={(v) => { if (!v) { onDone(); onClose(); } }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto bg-white sm:max-w-3xl" data-testid="tempi-dialog">
        <DialogHeader><DialogTitle>Tempi effettivi · {cur.numero_display}</DialogTitle></DialogHeader>
        <p className="text-sm text-slate-600">{cur.codice} {cur.descrizione} · registra i minuti realmente impiegati per ogni fase (anche più volte: si sommano)</p>
        <div className="space-y-3">{cur.fasi.map((f, i) => <Fase key={i} o={cur} f={f} i={i} onChange={setCur} />)}</div>
        <Confronto c={cur.consuntivo} />
        <DialogFooter><Button onClick={() => { onDone(); onClose(); }} data-testid="tempi-chiudi">Chiudi</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

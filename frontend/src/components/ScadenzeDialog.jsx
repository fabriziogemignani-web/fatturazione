import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Plus, Trash2 } from "lucide-react";

export const ScadenzeDialog = ({ open, onOpenChange, doc, kind, onDone }) => {
  const [rate, setRate] = useState([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open && doc) setRate(doc.rate.map((r) => ({ scadenza: r.scadenza, importo: r.importo }))); }, [open, doc]);
  if (!doc) return null;
  const tot = Math.round(rate.reduce((s, r) => s + (Number(r.importo) || 0), 0) * 100) / 100;
  const set = (i, k, v) => setRate(rate.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  const save = async () => {
    setBusy(true);
    try {
      await api.put(`/scadenze/${kind}/${doc.id}`, { rate: rate.map((r) => ({ scadenza: r.scadenza, importo: Number(r.importo) })) });
      toast.success("Scadenze aggiornate");
      onDone();
      onOpenChange(false);
    } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white sm:max-w-lg" data-testid="scadenze-dialog">
        <DialogHeader><DialogTitle>Modifica scadenze · {doc.numero_display}</DialogTitle></DialogHeader>
        <p className="text-xs text-slate-500">{doc.cliente} · netto da pagare {fmtEUR(doc.netto)}. Le modifiche valgono per scadenzario e solleciti; il file XML della fattura non cambia.</p>
        <div className="space-y-2">
          {rate.map((r, i) => (
            <div key={i} className="flex items-center gap-2" data-testid={`scadenze-rata-${i}`}>
              <span className="w-14 text-xs text-slate-500">Rata {i + 1}</span>
              <Input type="date" value={r.scadenza} onChange={(e) => set(i, "scadenza", e.target.value)} className="w-40" data-testid={`scadenze-data-${i}`} />
              <Input type="number" step="0.01" value={r.importo} onChange={(e) => set(i, "importo", e.target.value)} className="w-32 text-right" data-testid={`scadenze-importo-${i}`} />
              {rate.length > 1 && <button onClick={() => setRate(rate.filter((_, j) => j !== i))} className="text-rose-600" data-testid={`scadenze-remove-${i}`}><Trash2 className="h-4 w-4" /></button>}
            </div>
          ))}
        </div>
        <div className="flex items-center justify-between text-sm">
          <Button size="sm" variant="outline" onClick={() => setRate([...rate, { scadenza: rate[rate.length - 1]?.scadenza || doc.data, importo: 0 }])} data-testid="scadenze-add"><Plus className="mr-1 h-3.5 w-3.5" />Aggiungi rata</Button>
          <span className={Math.abs(tot - doc.netto) > 0.009 ? "font-semibold text-rose-600" : "text-slate-600"} data-testid="scadenze-totale">Totale {fmtEUR(tot)}</span>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Annulla</Button>
          <Button onClick={save} disabled={busy} data-testid="scadenze-save">Salva scadenze</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

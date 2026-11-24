import { useEffect, useState } from "react";
import { ArrowDown, ArrowUp, Plus, X, RotateCcw } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

export const WidgetPicker = ({ open, onClose, attivi, disponibili, onSave, onReset }) => {
  const [list, setList] = useState(attivi);
  useEffect(() => { if (open) setList(attivi); }, [open, attivi]);
  if (!open) return null;
  const byId = Object.fromEntries(disponibili.map((w) => [w.id, w]));
  const sposta = (i, d) => { const l = [...list]; [l[i], l[i + d]] = [l[i + d], l[i]]; setList(l); };
  const altri = disponibili.filter((w) => !list.includes(w.id));
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto bg-white sm:max-w-2xl [&>*]:min-w-0" data-testid="widget-picker">
        <DialogHeader><DialogTitle>Personalizza la dashboard</DialogTitle></DialogHeader>
        <p className="text-xs text-slate-500">Scegli i riquadri e il loro ordine. La configurazione è salvata per il tuo utente in questa azienda.</p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <div className="mb-2 text-xs font-semibold uppercase text-slate-500">In dashboard</div>
            <ul className="space-y-1.5" data-testid="widget-attivi">
              {list.filter((id) => byId[id]).map((id, i, arr) => (
                <li key={id} className="flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 px-2 py-1.5 text-sm" data-testid={`widget-on-${id}`}>
                  <span className="min-w-0 flex-1 truncate">{byId[id].label}</span>
                  <button disabled={i === 0} onClick={() => sposta(list.indexOf(id), list.indexOf(arr[i - 1]) - list.indexOf(id))} className="p-1 text-slate-400 hover:text-slate-800 disabled:opacity-30" data-testid={`widget-up-${id}`}><ArrowUp className="h-3.5 w-3.5" /></button>
                  <button disabled={i === arr.length - 1} onClick={() => sposta(list.indexOf(id), list.indexOf(arr[i + 1]) - list.indexOf(id))} className="p-1 text-slate-400 hover:text-slate-800 disabled:opacity-30" data-testid={`widget-down-${id}`}><ArrowDown className="h-3.5 w-3.5" /></button>
                  <button onClick={() => setList(list.filter((x) => x !== id))} className="p-1 text-slate-400 hover:text-rose-600" data-testid={`widget-remove-${id}`}><X className="h-3.5 w-3.5" /></button>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Aggiungi</div>
            <ul className="space-y-1.5" data-testid="widget-disponibili">
              {altri.length === 0 && <li className="text-xs text-slate-400">Tutti i riquadri sono già in dashboard.</li>}
              {altri.map((w) => (
                <li key={w.id}><button onClick={() => setList([...list, w.id])} className="flex w-full items-center gap-2 rounded-lg border border-dashed border-slate-300 px-2 py-1.5 text-left text-sm hover:border-blue-400 hover:bg-blue-50" data-testid={`widget-add-${w.id}`}><Plus className="h-3.5 w-3.5 text-blue-600" />{w.label}</button></li>
              ))}
            </ul>
          </div>
        </div>
        <DialogFooter className="gap-2">
          <Button variant="ghost" onClick={() => { onReset(); onClose(); }} data-testid="widget-reset"><RotateCcw className="mr-1 h-3.5 w-3.5" />Ripristina predefinita</Button>
          <Button variant="outline" onClick={onClose} data-testid="widget-cancel">Annulla</Button>
          <Button onClick={() => { onSave(list); onClose(); }} data-testid="widget-save">Salva</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

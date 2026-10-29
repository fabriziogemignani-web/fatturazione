import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { computeTotals, fmtEUR } from "@/lib/fe";

const MODES = [["tutto", "Tutta la fattura"], ["righe", "Solo alcune righe"], ["perc", "Una percentuale"]];
const PRESETS = [10, 25, 50];

export const partialLines = (lines, righe, perc) => {
  const sel = righe ? lines.filter((_, i) => righe.includes(i)) : lines;
  const k = perc ? Number(perc) / 100 : 1;
  return sel.map((l) => ({ ...l, prezzo_unitario: Math.round(Number(l.prezzo_unitario) * k * 100) / 100 }));
};

export const CreditNoteDialog = ({ open, onOpenChange, inv }) => {
  const navigate = useNavigate();
  const [mode, setMode] = useState("tutto");
  const [righe, setRighe] = useState([]);
  const [perc, setPerc] = useState(50);

  useEffect(() => {
    if (open) { setMode("tutto"); setRighe(inv.lines.map((_, i) => i)); setPerc(50); }
  }, [open, inv]);

  const lines = useMemo(() => partialLines(inv.lines, mode === "righe" ? righe : null, mode === "perc" ? perc : null), [inv, mode, righe, perc]);
  const total = computeTotals(lines, inv.cassa, inv.ritenuta).totale;
  const over = total > inv.residuo_stornabile + 0.005;
  const invalid = (mode === "righe" && righe.length === 0) || (mode === "perc" && !(perc > 0 && perc <= 100));

  const go = () => {
    const q = new URLSearchParams({ da: inv.id });
    if (mode === "righe") q.set("righe", righe.join(","));
    if (mode === "perc") q.set("perc", String(perc));
    onOpenChange(false);
    navigate(`/fatture/nuova?${q.toString()}`);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white sm:max-w-lg" data-testid="credit-note-dialog">
        <DialogHeader><DialogTitle>Storno fattura N. {inv.numero_display}</DialogTitle></DialogHeader>
        <div className="grid grid-cols-3 rounded-lg border border-slate-200 p-1 text-xs font-semibold">
          {MODES.map(([k, l]) => (
            <button key={k} onClick={() => setMode(k)} data-testid={`storno-mode-${k}`}
              className={`rounded-md py-2 transition-colors ${mode === k ? "bg-violet-600 text-white" : "text-slate-600 hover:bg-slate-50"}`}>{l}</button>
          ))}
        </div>
        {mode === "righe" && (
          <div className="max-h-56 space-y-2 overflow-y-auto rounded-lg border border-slate-200 p-3" data-testid="storno-lines">
            {inv.lines.map((l, i) => (
              <label key={i} className="flex items-center gap-3 text-sm">
                <Checkbox checked={righe.includes(i)} onCheckedChange={(v) => setRighe((r) => (v ? [...r, i].sort((a, b) => a - b) : r.filter((x) => x !== i)))} data-testid={`storno-line-${i}`} />
                <span className="flex-1 truncate text-slate-800">{l.descrizione}</span>
                <span className="font-semibold text-slate-900">{fmtEUR(l.prezzo_totale)}</span>
              </label>
            ))}
          </div>
        )}
        {mode === "perc" && (
          <div className="flex flex-wrap items-center gap-2" data-testid="storno-perc">
            {PRESETS.map((p) => (
              <button key={p} onClick={() => setPerc(p)} data-testid={`storno-perc-${p}`}
                className={`rounded-full border px-3 py-1.5 text-xs font-semibold ${Number(perc) === p ? "border-violet-600 bg-violet-600 text-white" : "border-slate-200 text-slate-600 hover:border-slate-400"}`}>{p}%</button>
            ))}
            <div className="flex items-center gap-1">
              <Input type="number" min="1" max="100" step="0.01" className="w-24" value={perc} onChange={(e) => setPerc(e.target.value)} data-testid="storno-perc-input" />
              <span className="text-sm text-slate-500">%</span>
            </div>
          </div>
        )}
        <div className="space-y-1 rounded-lg bg-violet-50 p-4 text-sm">
          <div className="flex justify-between"><span className="text-slate-600">Totale nota di credito</span><b className="text-violet-800" data-testid="storno-preview-total">{fmtEUR(total)}</b></div>
          <div className="flex justify-between text-xs"><span className="text-slate-500">Residuo stornabile</span><span data-testid="storno-residuo">{fmtEUR(inv.residuo_stornabile)}</span></div>
          {over && <p className="pt-1 text-xs font-semibold text-rose-700" data-testid="storno-over-warning">Supera il residuo: riduci righe o percentuale.</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="storno-cancel-btn">Annulla</Button>
          <Button className="bg-violet-600 hover:bg-violet-700" disabled={invalid || over} onClick={go} data-testid="storno-confirm-btn">Crea nota di credito</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

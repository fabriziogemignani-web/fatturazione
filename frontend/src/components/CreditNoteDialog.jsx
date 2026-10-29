import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Zap } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useAuth, canSend } from "@/context/AuthContext";
import { Switch } from "@/components/ui/switch";
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
  const [invia, setInvia] = useState(false);
  const [busy, setBusy] = useState(false);
  const { user } = useAuth();
  const full = inv.residuo_stornabile >= inv.totale - 0.005;

  const auto = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/invoices/${inv.id}/storno-totale`, { invia });
      toast.success(`Nota di credito ${data.numero_display} creata${invia ? " e trasmessa allo SDI (simulato)" : ""}`);
      onOpenChange(false);
      navigate(`/fatture/${data.id}`);
    } catch (e) { toast.error(errMsg(e)); }
    finally { setBusy(false); }
  };

  useEffect(() => {
    if (open) { setMode("tutto"); setRighe(inv.lines.map((_, i) => i)); setPerc(50); setInvia(false); }
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
        {mode === "tutto" && full && (
          <div className="rounded-lg border border-violet-200 p-4" data-testid="storno-auto-section">
            <div className="flex items-start gap-3">
              <Zap className="mt-0.5 h-4 w-4 text-violet-600" />
              <div className="text-sm text-slate-700"><b>Storno totale automatico</b>: crea in un clic la nota di credito con tutte le righe, cassa e ritenuta della fattura, datata oggi.</div>
            </div>
            {canSend(user) && (
              <label className="mt-3 flex items-center justify-between gap-4 text-sm text-slate-700">
                Invia subito allo SDI
                <Switch checked={invia} onCheckedChange={setInvia} data-testid="storno-auto-send-switch" />
              </label>
            )}
            <Button className="mt-3 w-full bg-violet-600 hover:bg-violet-700" disabled={busy} onClick={auto} data-testid="storno-auto-btn">
              <Zap className="mr-2 h-4 w-4" />{busy ? "Creazione…" : invia ? "Storna e invia ora" : "Storna tutto ora"}
            </Button>
          </div>
        )}
        <div className="space-y-1 rounded-lg bg-violet-50 p-4 text-sm">
          <div className="flex justify-between"><span className="text-slate-600">Totale nota di credito</span><b className="text-violet-800" data-testid="storno-preview-total">{fmtEUR(total)}</b></div>
          <div className="flex justify-between text-xs"><span className="text-slate-500">Residuo stornabile</span><span data-testid="storno-residuo">{fmtEUR(inv.residuo_stornabile)}</span></div>
          {over && <p className="pt-1 text-xs font-semibold text-rose-700" data-testid="storno-over-warning">Supera il residuo: riduci righe o percentuale.</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="storno-cancel-btn">Annulla</Button>
          <Button variant="outline" className="border-violet-300 text-violet-700" disabled={invalid || over} onClick={go} data-testid="storno-confirm-btn">{mode === "tutto" ? "Apri e modifica prima" : "Crea nota di credito"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

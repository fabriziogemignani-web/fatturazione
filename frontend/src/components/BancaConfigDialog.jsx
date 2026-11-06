import { useState } from "react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";

export const BancaConfigDialog = ({ cfg, open, onClose, onSaved }) => {
  const [f, setF] = useState({ ambiente: cfg?.ambiente || "sandbox", email: cfg?.email || "", password: "", auto: cfg?.auto ?? true });
  const [busy, setBusy] = useState(false);
  const save = async () => {
    if (f.ambiente === "production" && !window.confirm("Con l'ambiente reale il programma legge i movimenti veri dei conti collegati. Continuare?")) return;
    setBusy(true);
    try { await api.put("/banca/config", { ...f, password: f.password || null }); toast.success("Collegamento salvato"); onSaved(); onClose(); } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };
  const amb = (v, l) => (
    <button type="button" onClick={() => setF({ ...f, ambiente: v })} data-testid={`banca-ambiente-${v}`}
      className={`flex-1 rounded-md border px-3 py-2 text-sm font-semibold ${f.ambiente === v ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 text-slate-600"}`}>{l}</button>
  );
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-white sm:max-w-md" data-testid="banca-config-dialog">
        <DialogHeader>
          <DialogTitle>A-Cube Open Banking</DialogTitle>
          <DialogDescription>{cfg?.usa_sdi ? "Ora vengono usate le credenziali A-Cube del collegamento SDI. Compila qui solo se vuoi un account diverso." : "Credenziali dell'account A-Cube con il servizio Open Banking attivo. La password viene salvata cifrata."}</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="flex gap-2">{amb("sandbox", "Ambiente di prova")}{amb("production", "Ambiente reale")}</div>
          <label className="block text-sm text-slate-600">Email A-Cube<Input value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} data-testid="banca-email-input" /></label>
          <label className="block text-sm text-slate-600">Password A-Cube<Input type="password" autoComplete="new-password" placeholder={cfg?.has_password ? "•••••••• (lascia vuoto per non cambiarla)" : ""} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} data-testid="banca-password-input" /></label>
          <label className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700">
            Scarica movimenti e riconcilia in automatico ogni 6 ore
            <Switch checked={f.auto} onCheckedChange={(v) => setF({ ...f, auto: v })} data-testid="banca-auto-switch" />
          </label>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Annulla</Button>
          <Button onClick={save} disabled={busy} data-testid="banca-config-save-btn">{busy ? "Salvataggio…" : "Salva"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

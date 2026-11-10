import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";

export const ConsConfigDialog = ({ open, onClose, onSaved }) => {
  const [c, setC] = useState(null);
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setPw(""); api.get("/conservazione/config").then(({ data }) => setC(data)).catch((e) => toast.error(errMsg(e))); } }, [open]);
  const save = async (test) => {
    setBusy(true);
    try {
      await api.put("/conservazione/config", { usa_sdi: c.usa_sdi, ambiente: c.ambiente, email: c.email, password: pw || null });
      if (test) { const { data } = await api.post("/conservazione/config/test"); toast.success(data.message); } else toast.success("Collegamento salvato");
      onSaved(); onClose();
    } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="bg-white sm:max-w-lg" data-testid="cons-config-dialog">
        <DialogHeader>
          <DialogTitle>Conservatore A-Cube</DialogTitle>
          <DialogDescription>Credenziali dell'account A-Cube di questa azienda. Prima prova in ambiente di prova: in ambiente reale ogni documento inviato è a pagamento.</DialogDescription>
        </DialogHeader>
        {c && (
          <div className="space-y-4">
            {c.sdi_acube && (
              <label className="flex items-center justify-between gap-4 rounded-lg border border-slate-200 p-3">
                <span className="text-sm text-slate-700">Usa le stesse credenziali A-Cube del collegamento SDI</span>
                <Switch checked={c.usa_sdi} onCheckedChange={(v) => setC({ ...c, usa_sdi: v })} data-testid="cons-usa-sdi-switch" />
              </label>
            )}
            {!c.usa_sdi && (
              <>
                <label className="block text-xs text-slate-600">Ambiente
                  <Select value={c.ambiente} onValueChange={(v) => setC({ ...c, ambiente: v })}>
                    <SelectTrigger data-testid="cons-ambiente-select"><SelectValue /></SelectTrigger>
                    <SelectContent className="bg-white"><SelectItem value="sandbox">Prova (sandbox)</SelectItem><SelectItem value="production">Reale (a pagamento)</SelectItem></SelectContent>
                  </Select>
                </label>
                <label className="block text-xs text-slate-600">Email account A-Cube<Input value={c.email} onChange={(e) => setC({ ...c, email: e.target.value })} data-testid="cons-email-input" /></label>
                <label className="block text-xs text-slate-600">Password<Input type="password" value={pw} placeholder={c.has_password ? "•••••••• (lascia vuoto per non cambiarla)" : ""} onChange={(e) => setPw(e.target.value)} data-testid="cons-password-input" /></label>
              </>
            )}
            {c.legal_entity && <p className="text-xs text-emerald-700" data-testid="cons-legal-entity">Azienda registrata presso il conservatore (P.IVA {c.legal_entity})</p>}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose} data-testid="cons-config-cancel">Annulla</Button>
          <Button variant="outline" onClick={() => save(true)} disabled={busy || !c} data-testid="cons-config-test">Salva e prova</Button>
          <Button onClick={() => save(false)} disabled={busy || !c} data-testid="cons-config-save">Salva</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

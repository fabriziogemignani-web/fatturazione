import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Zap } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR } from "@/lib/fe";
import { useAuth, canSend } from "@/context/AuthContext";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";

export const QuickStornoDialog = ({ inv, onOpenChange, onDone }) => {
  const { user } = useAuth();
  const [invia, setInvia] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { setInvia(false); }, [inv]);

  const confirm = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/invoices/${inv.id}/storno-totale`, { invia });
      toast.success(`Documento nota di credito ${data.numero_display} creato${invia ? " e trasmesso allo SDI (simulato)" : ""}`);
      onOpenChange(false);
      onDone(data);
    } catch (e) { toast.error(errMsg(e)); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={!!inv} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white sm:max-w-md" data-testid="quick-storno-dialog">
        <DialogHeader><DialogTitle>Storno totale fattura N. {inv?.numero_display}</DialogTitle></DialogHeader>
        <p className="text-sm text-slate-600">
          Verrà creato il documento <b>nota di credito (TD04)</b> nel registro NC, datato oggi, per <b className="text-violet-700">{fmtEUR(inv?.totale)}</b> intestato a <b>{inv?.cliente?.denominazione}</b>, con le stesse righe, cassa e ritenuta della fattura e collegato a essa (file XML e stampa PDF disponibili). Al termine si apre il documento creato.
        </p>
        {canSend(user) && (
          <label className="flex items-center justify-between gap-4 rounded-lg bg-violet-50 p-3 text-sm text-slate-700">
            Invia subito allo SDI
            <Switch checked={invia} onCheckedChange={setInvia} data-testid="quick-storno-send-switch" />
          </label>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="quick-storno-cancel-btn">Annulla</Button>
          <Button className="bg-violet-600 hover:bg-violet-700" disabled={busy} onClick={confirm} data-testid="quick-storno-confirm-btn">
            <Zap className="mr-2 h-4 w-4" />{busy ? "Creazione…" : invia ? "Storna e invia" : "Storna tutto"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

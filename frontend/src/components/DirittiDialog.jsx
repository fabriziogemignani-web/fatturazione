import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";

export const DIRITTI = [
  ["dati_azienda", "Dati azienda", "anagrafica azienda e predefiniti per le nuove fatture"],
  ["banche", "Banche aziendali", "banche, IBAN, ABI e CAB"],
  ["tabelle_contabili", "Tabelle contabili", "piano dei conti, causali, codici IVA e parametri contabili"],
  ["articoli_magazzino", "Articoli e magazzino", "anagrafica articoli, carichi e scarichi"],
  ["testi_comunicazioni", "Testi delle comunicazioni", "modelli di cortesia, promemoria e solleciti"],
];

export const dirSummary = (u) => {
  const n = DIRITTI.filter(([k]) => u?.diritti?.[k]).length;
  return n === DIRITTI.length ? "Tutti" : n ? `${n} su ${DIRITTI.length}` : "Nessuno";
};

export const DirittiDialog = ({ target, onClose, onSaved }) => {
  const [d, setD] = useState({});
  const [busy, setBusy] = useState(false);
  useEffect(() => { setD(target?.diritti || {}); }, [target]);
  const save = async () => {
    setBusy(true);
    try { await api.put(`/users/${target.user_id}/diritti`, Object.fromEntries(DIRITTI.map(([k]) => [k, !!d[k]]))); toast.success("Diritti aggiornati"); await onSaved(); onClose(); }
    catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };
  return (
    <Dialog open={!!target} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="bg-white sm:max-w-lg" data-testid="diritti-dialog">
        <DialogHeader>
          <DialogTitle>Diritti di modifica · {target?.name || target?.email}</DialogTitle>
          <DialogDescription>Le sezioni spente non sono visibili a questo utente, in tutte le sue aziende.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          {DIRITTI.map(([k, label, desc]) => (
            <label key={k} className="flex items-start justify-between gap-4 rounded-lg border border-slate-200 p-3">
              <span><span className="block text-sm font-semibold text-slate-800">{label}</span><span className="block text-xs text-slate-500">{desc}</span></span>
              <Switch checked={!!d[k]} onCheckedChange={(v) => setD({ ...d, [k]: v })} data-testid={`diritto-switch-${k}`} />
            </label>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} data-testid="diritti-cancel-btn">Annulla</Button>
          <Button onClick={save} disabled={busy} data-testid="diritti-save-btn">{busy ? "Salvataggio…" : "Salva"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

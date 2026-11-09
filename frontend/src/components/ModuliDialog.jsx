import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { mods } from "@/lib/moduli";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";

const AREE = [
  ["fatturazione", "Fatturazione", "Emissione e ricezione fatture, IVA, scadenzari", [
    ["fatture_attive", "Fatture attive", "fatture emesse, numerazione, scadenzario clienti, registro IVA vendite"],
    ["fatture_passive", "Fatture passive", "fatture ricevute, registro IVA acquisti, scadenzario fornitori"],
    ["corrispettivi", "Corrispettivi", "corrispettivi giornalieri dal cassetto fiscale"],
    ["contabilita", "Contabilità generale", "piano dei conti, prima nota in partita doppia, mastrini e bilancio di verifica"],
  ]],
  ["archivio", "Archivio fatture", "Importazione e consultazione di fatture XML, P7M e ZIP", []],
];

const Row = ({ k, label, desc, m, setM, disabled, sub }) => (
  <label className={`flex items-start justify-between gap-4 rounded-lg border p-3 ${sub ? "ml-6 border-slate-100" : "border-slate-200"} ${disabled ? "opacity-50" : ""}`}>
    <span><span className="block text-sm font-semibold text-slate-800">{label}</span><span className="block text-xs text-slate-500">{desc}</span></span>
    <Switch checked={m[k]} disabled={disabled} onCheckedChange={(v) => setM({ ...m, [k]: v })} data-testid={`modulo-switch-${k}`} />
  </label>
);

export const ModuliDialog = ({ company, onClose, onSaved, endpoint, desc }) => {
  const [m, setM] = useState(mods(company));
  const [busy, setBusy] = useState(false);
  useEffect(() => { setM(mods(company)); }, [company]);
  const save = async () => {
    setBusy(true);
    try { await api.put(endpoint || `/companies/${company.id}/moduli`, m); toast.success("Moduli aggiornati"); await onSaved(); onClose(); } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };

  return (
    <Dialog open={!!company} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="bg-white sm:max-w-lg" data-testid="moduli-dialog">
        <DialogHeader>
          <DialogTitle>Moduli attivi · {company?.denominazione}</DialogTitle>
          <DialogDescription>{desc || "Scegli le aree e le funzioni disponibili per questa azienda: quelle spente spariscono dal menu."}</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          {AREE.map(([k, label, desc, subs]) => (
            <div key={k} className="space-y-2">
              <Row k={k} label={label} desc={desc} m={m} setM={setM} />
              {subs.map(([sk, sl, sd]) => <Row key={sk} k={sk} label={sl} desc={sd} m={m} setM={setM} disabled={!m[k]} sub />)}
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} data-testid="moduli-cancel-btn">Annulla</Button>
          <Button onClick={save} disabled={busy} data-testid="moduli-save-btn">{busy ? "Salvataggio…" : "Salva"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

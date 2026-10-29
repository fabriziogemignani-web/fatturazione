import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Field, FieldErrors, useFieldErrors } from "@/components/Common";
import { api, errMsg } from "@/lib/api";

const EMPTY = { denominazione: "", partita_iva: "", codice_fiscale: "", indirizzo: "", cap: "", comune: "", provincia: "", nazione: "IT", regime_fiscale: "RF01" };
const FIELDS = [
  ["denominazione", "Ragione sociale", "sm:col-span-2"],
  ["partita_iva", "Partita IVA"],
  ["codice_fiscale", "Codice fiscale"],
  ["indirizzo", "Indirizzo", "sm:col-span-2"],
  ["cap", "CAP"],
  ["comune", "Comune"],
  ["provincia", "Provincia (sigla)"],
];

export const CompanyDialog = ({ open, onOpenChange, onSaved }) => {
  const [f, setF] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const { fail, reset, value } = useFieldErrors();
  useEffect(() => { if (open) { setF(EMPTY); reset(); } }, [open, reset]);

  const save = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/companies", f);
      toast.success("Azienda creata");
      onSaved(data);
      onOpenChange(false);
    } catch (e) { fail(e); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white sm:max-w-xl" data-testid="company-dialog">
        <DialogHeader><DialogTitle>Nuova azienda</DialogTitle></DialogHeader>
        <FieldErrors value={value}>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {FIELDS.map(([k, label, cls]) => (
            <Field key={k} name={k} label={label} className={cls}>
              <Input value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} data-testid={`new-company-${k.replace(/_/g, "-")}-input`} />
            </Field>
          ))}
        </div>
        </FieldErrors>
        <p className="text-xs text-slate-500">Regime fiscale, IBAN, cassa e ritenuta predefinite si completano poi in "Dati azienda".</p>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="new-company-cancel-btn">Annulla</Button>
          <Button onClick={save} disabled={busy} data-testid="new-company-save-btn">{busy ? "Salvataggio…" : "Crea azienda"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

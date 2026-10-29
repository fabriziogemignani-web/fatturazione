import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/Common";
import { api, errMsg } from "@/lib/api";

const EMPTY = {
  denominazione: "", partita_iva: "", codice_fiscale: "", codice_destinatario: "0000000", pec: "",
  email: "", telefono: "", indirizzo: "", cap: "", comune: "", provincia: "", nazione: "IT",
};

const FIELDS = [
  ["denominazione", "Ragione sociale / Nome", "sm:col-span-2"],
  ["partita_iva", "Partita IVA"],
  ["codice_fiscale", "Codice fiscale"],
  ["codice_destinatario", "Codice destinatario SDI"],
  ["pec", "PEC"],
  ["email", "Email"],
  ["telefono", "Telefono"],
  ["indirizzo", "Indirizzo", "sm:col-span-2"],
  ["cap", "CAP"],
  ["comune", "Comune"],
  ["provincia", "Provincia (sigla)"],
  ["nazione", "Nazione"],
];

export const PartyDialog = ({ open, onOpenChange, tipo, party, onSaved }) => {
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) setForm(party ? { ...EMPTY, ...party } : EMPTY);
  }, [open, party]);

  const save = async () => {
    setSaving(true);
    try {
      const body = { ...form, tipo: party?.tipo || tipo };
      const { data } = party ? await api.put(`/parties/${party.id}`, body) : await api.post("/parties", body);
      toast.success(party ? "Anagrafica aggiornata" : "Anagrafica creata");
      onSaved(data);
      onOpenChange(false);
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto bg-white sm:max-w-2xl" data-testid="party-dialog">
        <DialogHeader>
          <DialogTitle>{party ? "Modifica anagrafica" : `Nuovo ${tipo === "fornitore" ? "fornitore" : "cliente"}`}</DialogTitle>
        </DialogHeader>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {FIELDS.map(([k, label, cls]) => (
            <Field key={k} label={label} className={cls}>
              <Input data-testid={`party-${k.replace(/_/g, "-")}-input`} value={form[k] || ""} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
            </Field>
          ))}
        </div>
        <p className="text-xs text-slate-500">Usa 0000000 come codice destinatario se il cliente riceve via PEC o è un privato.</p>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="party-cancel-btn">Annulla</Button>
          <Button onClick={save} disabled={saving} data-testid="party-save-btn">{saving ? "Salvataggio…" : "Salva"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

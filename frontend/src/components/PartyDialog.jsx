import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { PaSearch } from "@/components/PaSearch";
import { Field } from "@/components/Common";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { NATURE } from "@/lib/fe";
import { api, errMsg } from "@/lib/api";

const EMPTY = {
  denominazione: "", partita_iva: "", codice_fiscale: "", codice_destinatario: "0000000", pec: "",
  email: "", telefono: "", indirizzo: "", cap: "", comune: "", provincia: "", nazione: "IT",
  natura_default: "", riferimento_normativo: "", intento_protocollo: "", intento_data: "",
  pubblica_amministrazione: false, split_payment: false,
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
        {(party?.tipo || tipo) === "cliente" && (
          <div className="space-y-3 rounded-lg border border-sky-200 bg-sky-50 p-4" data-testid="party-pa-section">
            <label className="flex items-center justify-between gap-3 text-sm font-semibold text-slate-800">
              Pubblica Amministrazione (fattura FPA12)
              <Switch checked={!!form.pubblica_amministrazione} data-testid="party-pa-switch"
                onCheckedChange={(v) => setForm({ ...form, pubblica_amministrazione: v, split_payment: v ? form.split_payment : false, codice_destinatario: v ? (form.codice_destinatario === "0000000" ? "" : form.codice_destinatario) : (form.codice_destinatario || "0000000") })} />
            </label>
            {form.pubblica_amministrazione && (
              <label className="flex items-center justify-between gap-3 text-sm text-slate-700">
                Scissione dei pagamenti (split payment, art. 17-ter)
                <Switch checked={!!form.split_payment} onCheckedChange={(v) => setForm({ ...form, split_payment: v })} data-testid="party-split-switch" />
              </label>
            )}
            {form.pubblica_amministrazione && (
              <PaSearch onPick={(r) => {
                setForm((f) => ({ ...f, denominazione: f.denominazione || r.ente, codice_fiscale: r.codice_fiscale || f.codice_fiscale, codice_destinatario: r.codice_uo,
                  indirizzo: r.indirizzo || f.indirizzo, cap: r.cap || f.cap, pec: r.pec || f.pec, nazione: "IT" }));
                toast.success(`Codice ufficio ${r.codice_uo} inserito`);
              }} />
            )}
          </div>
        )}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {FIELDS.map(([k, label, cls]) => (
            <Field key={k} label={k === "codice_destinatario" && form.pubblica_amministrazione ? "Codice univoco ufficio PA (6 caratteri)" : label} className={cls}>
              <Input data-testid={`party-${k.replace(/_/g, "-")}-input`} value={form[k] || ""} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
            </Field>
          ))}
        </div>
        <p className="text-xs text-slate-500">{form.pubblica_amministrazione ? "Il codice univoco ufficio (6 caratteri) si trova sull'Indice delle PA (indicepa.gov.it)." : "Usa 0000000 come codice destinatario se il cliente riceve via PEC o è un privato."}</p>
        <div className="space-y-4 rounded-lg border border-slate-200 bg-slate-50 p-4" data-testid="party-iva-section">
          <div className="text-sm font-semibold text-slate-800">Regime IVA del cliente</div>
          <Field label="Codice IVA / esenzione applicata">
            <Select value={form.natura_default || "ORD"} onValueChange={(v) => setForm({ ...form, natura_default: v === "ORD" ? "" : v })}>
              <SelectTrigger className="bg-white" data-testid="party-natura-select"><SelectValue /></SelectTrigger>
              <SelectContent className="bg-white max-h-72">
                <SelectItem value="ORD">Ordinario (IVA dell'articolo)</SelectItem>
                {NATURE.map(([k, l]) => <SelectItem key={k} value={k}>{`Esente/non imponibile ${l}`}</SelectItem>)}
              </SelectContent>
            </Select>
          </Field>
          {form.natura_default && form.natura_default !== "N3.5" && (
            <Field label="Riferimento normativo (opzionale)">
              <Input value={form.riferimento_normativo || ""} onChange={(e) => setForm({ ...form, riferimento_normativo: e.target.value })} placeholder="es. Esente art. 10 n. 18 DPR 633/72" data-testid="party-riferimento-input" />
            </Field>
          )}
          {form.natura_default === "N3.5" && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2" data-testid="party-intento-fields">
              <Field label="Protocollo dichiarazione d'intento *">
                <Input value={form.intento_protocollo || ""} onChange={(e) => setForm({ ...form, intento_protocollo: e.target.value })} placeholder="12345678901234567-000001" className="mono" data-testid="party-intento-protocollo-input" />
              </Field>
              <Field label="Data protocollo *">
                <Input type="date" value={form.intento_data || ""} onChange={(e) => setForm({ ...form, intento_data: e.target.value })} data-testid="party-intento-data-input" />
              </Field>
              <p className="text-xs text-slate-500 sm:col-span-2">Dati presenti nella ricevuta telematica dell'Agenzia delle Entrate (17 cifre + trattino + 6 cifre). Verranno riportati in fattura in AltriDatiGestionali (INTENTO).</p>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="party-cancel-btn">Annulla</Button>
          <Button onClick={save} disabled={saving} data-testid="party-save-btn">{saving ? "Salvataggio…" : "Salva"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

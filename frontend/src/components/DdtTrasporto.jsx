import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export const CAUSALI_DDT = ["Vendita", "Conto visione", "Conto lavorazione", "Reso a fornitore", "Omaggio", "Sostituzione in garanzia", "Altro"];

const S = ({ label, value, onChange, options, disabled, testId }) => (
  <label className="block text-xs text-slate-600">{label}
    <Select disabled={disabled} value={value} onValueChange={onChange}>
      <SelectTrigger data-testid={testId}><SelectValue /></SelectTrigger>
      <SelectContent className="bg-white">{options.map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent>
    </Select>
  </label>
);

const I = ({ label, value, onChange, disabled, testId, type = "text", className = "" }) => (
  <label className={`block text-xs text-slate-600 ${className}`}>{label}
    <Input disabled={disabled} type={type} value={value ?? ""} onChange={(e) => onChange(e.target.value)} data-testid={testId} />
  </label>
);

export const DdtTrasporto = ({ f, set, disabled }) => {
  const sub = (k, sk, v) => set(k, { ...(f[k] || {}), [sk]: v });
  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-4">
        <S label="Causale del trasporto" value={f.causale} onChange={(v) => set("causale", v)} options={CAUSALI_DDT.map((c) => [c, c])} disabled={disabled} testId="ddt-causale-select" />
        <S label="Porto" value={f.porto} onChange={(v) => set("porto", v)} options={[["franco", "Franco"], ["assegnato", "Assegnato"]]} disabled={disabled} testId="ddt-porto-select" />
        <S label="Trasporto a cura del" value={f.trasporto_a_cura} onChange={(v) => set("trasporto_a_cura", v)} options={[["mittente", "Mittente"], ["destinatario", "Destinatario"], ["vettore", "Vettore"]]} disabled={disabled} testId="ddt-acura-select" />
        <I label="Inizio trasporto" type="datetime-local" value={f.inizio_trasporto} onChange={(v) => set("inizio_trasporto", v)} disabled={disabled} testId="ddt-inizio-input" />
      </div>
      {f.trasporto_a_cura === "vettore" && (
        <div className="grid gap-3 sm:grid-cols-3" data-testid="ddt-vettore-fields">
          <I label="Vettore" value={f.vettore?.denominazione} onChange={(v) => sub("vettore", "denominazione", v)} disabled={disabled} testId="ddt-vettore-nome" />
          <I label="P.IVA vettore" value={f.vettore?.partita_iva} onChange={(v) => sub("vettore", "partita_iva", v)} disabled={disabled} testId="ddt-vettore-piva" />
          <I label="Indirizzo vettore" value={f.vettore?.indirizzo} onChange={(v) => sub("vettore", "indirizzo", v)} disabled={disabled} testId="ddt-vettore-indirizzo" />
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-4">
        <I label="N. colli" type="number" value={f.colli} onChange={(v) => set("colli", v)} disabled={disabled} testId="ddt-colli-input" />
        <I label="Peso kg" type="number" value={f.peso_kg} onChange={(v) => set("peso_kg", v)} disabled={disabled} testId="ddt-peso-input" />
        <I label="Aspetto esteriore dei beni" className="sm:col-span-2" value={f.aspetto_beni} onChange={(v) => set("aspetto_beni", v)} disabled={disabled} testId="ddt-aspetto-input" />
      </div>
      <div>
        <label className="flex items-center gap-3 text-sm text-slate-700"><Switch disabled={disabled} checked={!!f.destinazione} onCheckedChange={(v) => set("destinazione", v ? { denominazione: "", indirizzo: "", cap: "", comune: "", provincia: "" } : null)} data-testid="ddt-destinazione-switch" />Luogo di destinazione diverso dalla sede del cliente</label>
        {f.destinazione && (
          <div className="mt-3 grid gap-3 sm:grid-cols-6" data-testid="ddt-destinazione-fields">
            <I label="Presso" className="sm:col-span-2" value={f.destinazione.denominazione} onChange={(v) => sub("destinazione", "denominazione", v)} disabled={disabled} testId="ddt-dest-nome" />
            <I label="Indirizzo" className="sm:col-span-2" value={f.destinazione.indirizzo} onChange={(v) => sub("destinazione", "indirizzo", v)} disabled={disabled} testId="ddt-dest-indirizzo" />
            <I label="CAP" value={f.destinazione.cap} onChange={(v) => sub("destinazione", "cap", v)} disabled={disabled} testId="ddt-dest-cap" />
            <I label="Prov." value={f.destinazione.provincia} onChange={(v) => sub("destinazione", "provincia", v.toUpperCase().slice(0, 2))} disabled={disabled} testId="ddt-dest-prov" />
            <I label="Comune" className="sm:col-span-2" value={f.destinazione.comune} onChange={(v) => sub("destinazione", "comune", v)} disabled={disabled} testId="ddt-dest-comune" />
          </div>
        )}
      </div>
      <label className="flex items-center gap-3 text-sm text-slate-700"><Switch disabled={disabled} checked={!!f.prezzi_in_stampa} onCheckedChange={(v) => set("prezzi_in_stampa", v)} data-testid="ddt-prezzi-switch" />Mostra i prezzi nella stampa del DDT</label>
    </div>
  );
};

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { REGIMI, CASSE, RITENUTE, CAUSALI, ALIQUOTE } from "@/lib/fe";
import { Switch } from "@/components/ui/switch";
import { useAuth, isAdmin } from "@/context/AuthContext";
import { PageHeader, Field, FieldErrors, useFieldErrors } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const EMPTY = { denominazione: "", partita_iva: "", codice_fiscale: "", regime_fiscale: "RF01", indirizzo: "", cap: "", comune: "", provincia: "", nazione: "IT", iban: "", email: "", pec: "", telefono: "", cassa_tipo: "", cassa_aliquota: 4, cassa_aliquota_iva: 22, cassa_ritenuta: false, ritenuta_tipo: "", ritenuta_aliquota: 20, ritenuta_causale: "A" };

const DSel = ({ label, value, onChange, options, disabled, testId, none, name }) => (
  <Field label={label} name={name}>
    <Select disabled={disabled} value={value || "-"} onValueChange={(v) => onChange(v === "-" ? "" : v)}>
      <SelectTrigger data-testid={testId}><SelectValue /></SelectTrigger>
      <SelectContent className="bg-white max-h-72">{none && <SelectItem value="-">{none}</SelectItem>}{options.map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent>
    </Select>
  </Field>
);

const FIELDS = [
  ["denominazione", "Ragione sociale", "sm:col-span-2"],
  ["partita_iva", "Partita IVA"],
  ["codice_fiscale", "Codice fiscale"],
  ["indirizzo", "Indirizzo", "sm:col-span-2"],
  ["cap", "CAP"],
  ["comune", "Comune"],
  ["provincia", "Provincia (sigla)"],
  ["nazione", "Nazione"],
  ["iban", "IBAN", "sm:col-span-2"],
  ["pec", "PEC"],
  ["email", "Email"],
  ["telefono", "Telefono"],
];

export default function Settings() {
  const { user } = useAuth();
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  const admin = isAdmin(user);
  const { fail, reset, value } = useFieldErrors();

  useEffect(() => {
    api.get("/company").then(({ data }) => setForm({ ...EMPTY, ...data }));
  }, []);

  const save = async () => {
    setSaving(true);
    reset();
    try { await api.put("/company", { ...form, cassa_aliquota: Number(form.cassa_aliquota || 0), cassa_aliquota_iva: Number(form.cassa_aliquota_iva || 0), ritenuta_aliquota: Number(form.ritenuta_aliquota || 0) }); toast.success("Dati azienda salvati"); }
    catch (e) { fail(e); }
    finally { setSaving(false); }
  };

  return (
    <FieldErrors value={value}>
    <div>
      <PageHeader eyebrow="Cedente / Prestatore" title="Dati azienda">
        {admin && <Button onClick={save} disabled={saving} data-testid="company-save-btn">{saving ? "Salvataggio…" : "Salva"}</Button>}
      </PageHeader>
      {!admin && <p className="mb-4 text-sm text-slate-500" data-testid="company-readonly-note">Solo un amministratore può modificare questi dati.</p>}
      <div className="max-w-3xl rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {FIELDS.map(([k, label, cls]) => (
            <Field key={k} name={k} label={label} className={cls}>
              <Input disabled={!admin} value={form[k] || ""} onChange={(e) => setForm({ ...form, [k]: e.target.value })} data-testid={`company-${k.replace(/_/g, "-")}-input`} />
            </Field>
          ))}
          <Field label="Regime fiscale" name="regime_fiscale">
            <Select disabled={!admin} value={form.regime_fiscale} onValueChange={(v) => setForm({ ...form, regime_fiscale: v })}>
              <SelectTrigger data-testid="company-regime-select"><SelectValue /></SelectTrigger>
              <SelectContent className="bg-white">{REGIMI.map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent>
            </Select>
          </Field>
        </div>
      </div>
      <div className="mt-6 max-w-3xl rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm" data-testid="company-defaults-card">
        <h3 className="text-lg font-semibold text-slate-800">Predefiniti per le nuove fatture</h3>
        <p className="mb-4 text-xs text-slate-500">Se imposti una cassa o una ritenuta, verranno attivate automaticamente su ogni nuova fattura (modificabili).</p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <DSel label="Cassa previdenziale" value={form.cassa_tipo} onChange={(v) => setForm({ ...form, cassa_tipo: v })} options={CASSE} disabled={!admin} testId="company-cassa-select" none="Nessuna" name="cassa_tipo" />
          <Field label="Aliquota cassa %" name="cassa_aliquota"><Input disabled={!admin} type="number" step="0.01" value={form.cassa_aliquota ?? ""} onChange={(e) => setForm({ ...form, cassa_aliquota: e.target.value })} data-testid="company-cassa-aliquota-input" /></Field>
          <DSel label="IVA sul contributo" value={String(form.cassa_aliquota_iva ?? 22)} onChange={(v) => setForm({ ...form, cassa_aliquota_iva: Number(v) })} options={ALIQUOTE.map((a) => [String(a), `IVA ${a}%`])} disabled={!admin} testId="company-cassa-iva-select" name="cassa_aliquota_iva" />
          <label className="flex items-center justify-between gap-4 self-end pb-2"><span className="text-sm text-slate-700">Contributo soggetto a ritenuta</span><Switch disabled={!admin} checked={!!form.cassa_ritenuta} onCheckedChange={(v) => setForm({ ...form, cassa_ritenuta: v })} data-testid="company-cassa-ritenuta-switch" /></label>
          <DSel label="Ritenuta d'acconto" value={form.ritenuta_tipo} onChange={(v) => setForm({ ...form, ritenuta_tipo: v })} options={RITENUTE} disabled={!admin} testId="company-ritenuta-select" none="Nessuna" name="ritenuta_tipo" />
          <Field label="Aliquota ritenuta %" name="ritenuta_aliquota"><Input disabled={!admin} type="number" step="0.01" value={form.ritenuta_aliquota ?? ""} onChange={(e) => setForm({ ...form, ritenuta_aliquota: e.target.value })} data-testid="company-ritenuta-aliquota-input" /></Field>
          <div className="sm:col-span-2"><DSel label="Causale pagamento" value={form.ritenuta_causale || "A"} onChange={(v) => setForm({ ...form, ritenuta_causale: v || "A" })} options={CAUSALI} disabled={!admin} testId="company-ritenuta-causale-select" name="ritenuta_causale" /></div>
        </div>
      </div>
    </div>
    </FieldErrors>
  );
}

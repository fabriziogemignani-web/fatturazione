import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { REGIMI } from "@/lib/fe";
import { useAuth, isAdmin } from "@/context/AuthContext";
import { PageHeader, Field } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const EMPTY = { denominazione: "", partita_iva: "", codice_fiscale: "", regime_fiscale: "RF01", indirizzo: "", cap: "", comune: "", provincia: "", nazione: "IT", iban: "", email: "", pec: "", telefono: "" };

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

  useEffect(() => {
    api.get("/company").then(({ data }) => setForm({ ...EMPTY, ...data }));
  }, []);

  const save = async () => {
    setSaving(true);
    try { await api.put("/company", form); toast.success("Dati azienda salvati"); }
    catch (e) { toast.error(errMsg(e)); }
    finally { setSaving(false); }
  };

  return (
    <div>
      <PageHeader eyebrow="Cedente / Prestatore" title="Dati azienda">
        {admin && <Button onClick={save} disabled={saving} data-testid="company-save-btn">{saving ? "Salvataggio…" : "Salva"}</Button>}
      </PageHeader>
      {!admin && <p className="mb-4 text-sm text-slate-500" data-testid="company-readonly-note">Solo un amministratore può modificare questi dati.</p>}
      <div className="max-w-3xl rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {FIELDS.map(([k, label, cls]) => (
            <Field key={k} label={label} className={cls}>
              <Input disabled={!admin} value={form[k] || ""} onChange={(e) => setForm({ ...form, [k]: e.target.value })} data-testid={`company-${k.replace(/_/g, "-")}-input`} />
            </Field>
          ))}
          <Field label="Regime fiscale">
            <Select disabled={!admin} value={form.regime_fiscale} onValueChange={(v) => setForm({ ...form, regime_fiscale: v })}>
              <SelectTrigger data-testid="company-regime-select"><SelectValue /></SelectTrigger>
              <SelectContent className="bg-white">{REGIMI.map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent>
            </Select>
          </Field>
        </div>
      </div>
    </div>
  );
}

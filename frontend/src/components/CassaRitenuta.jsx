import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Field } from "@/components/Common";
import { ALIQUOTE, NATURE, CASSE, RITENUTE, CAUSALI } from "@/lib/fe";

const Sel = ({ value, onChange, options, testId, disabled }) => (
  <Select value={value} onValueChange={onChange} disabled={disabled}>
    <SelectTrigger className="bg-white" data-testid={testId}><SelectValue /></SelectTrigger>
    <SelectContent className="bg-white max-h-72">{options.map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent>
  </Select>
);

export const defaultCassa = (c = {}) => ({ tipo: c.cassa_tipo || "TC22", aliquota: c.cassa_aliquota ?? 4, aliquota_iva: c.cassa_aliquota_iva ?? 22, natura: null, ritenuta: !!c.cassa_ritenuta });
export const defaultRitenuta = (c = {}) => ({ tipo: c.ritenuta_tipo || "RT01", aliquota: c.ritenuta_aliquota ?? 20, causale: c.ritenuta_causale || "A" });

const Toggle = ({ label, checked, onChange, disabled, testId }) => (
  <label className="flex items-center justify-between gap-4">
    <span className="text-sm font-semibold text-slate-800">{label}</span>
    <Switch checked={checked} onCheckedChange={onChange} disabled={disabled} data-testid={testId} />
  </label>
);

export const CassaFields = ({ cassa, onChange, disabled, ritenutaOn }) => {
  const set = (k, v) => onChange({ ...cassa, [k]: v });
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <Field label="Tipo cassa" name="cassa.tipo" className="sm:col-span-2"><Sel disabled={disabled} value={cassa.tipo} onChange={(v) => set("tipo", v)} options={CASSE} testId="cassa-tipo-select" /></Field>
      <Field label="Aliquota contributo %" name="cassa.aliquota"><Input disabled={disabled} type="number" step="0.01" value={cassa.aliquota} onChange={(e) => set("aliquota", e.target.value)} data-testid="cassa-aliquota-input" /></Field>
      <Field label="IVA sul contributo" name="cassa.aliquota_iva"><Sel disabled={disabled} value={String(cassa.aliquota_iva)} onChange={(v) => onChange({ ...cassa, aliquota_iva: Number(v), natura: Number(v) === 0 ? cassa.natura || "N2.2" : null })} options={ALIQUOTE.map((a) => [String(a), `IVA ${a}%`])} testId="cassa-iva-select" /></Field>
      {Number(cassa.aliquota_iva) === 0 && <Field label="Natura IVA contributo" name="cassa.natura" className="sm:col-span-2"><Sel disabled={disabled} value={cassa.natura || "N2.2"} onChange={(v) => set("natura", v)} options={NATURE} testId="cassa-natura-select" /></Field>}
      {ritenutaOn && <div className="sm:col-span-2"><Toggle label="Contributo soggetto a ritenuta" checked={!!cassa.ritenuta} onChange={(v) => set("ritenuta", v)} disabled={disabled} testId="cassa-ritenuta-switch" /></div>}
    </div>
  );
};

export const RitenutaFields = ({ ritenuta, onChange, disabled }) => {
  const set = (k, v) => onChange({ ...ritenuta, [k]: v });
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <Field label="Tipo ritenuta" name="ritenuta.tipo"><Sel disabled={disabled} value={ritenuta.tipo} onChange={(v) => set("tipo", v)} options={RITENUTE} testId="ritenuta-tipo-select" /></Field>
      <Field label="Aliquota ritenuta %" name="ritenuta.aliquota"><Input disabled={disabled} type="number" step="0.01" value={ritenuta.aliquota} onChange={(e) => set("aliquota", e.target.value)} data-testid="ritenuta-aliquota-input" /></Field>
      <Field label="Causale pagamento (770)" name="ritenuta.causale" className="sm:col-span-2"><Sel disabled={disabled} value={ritenuta.causale} onChange={(v) => set("causale", v)} options={CAUSALI} testId="ritenuta-causale-select" /></Field>
    </div>
  );
};

export const CassaRitenutaCard = ({ form, setForm, disabled, company, client }) => (
  <div className="space-y-6 rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm" data-testid="cassa-ritenuta-card">
    <h3 className="text-lg font-semibold text-slate-800">Cassa professionisti e ritenuta d'acconto</h3>
    <Toggle label="Cassa previdenziale" checked={!!form.cassa} disabled={disabled} testId="cassa-switch"
      onChange={(v) => setForm((f) => ({ ...f, cassa: v ? { ...defaultCassa(company), ...(client?.natura_default ? { aliquota_iva: 0, natura: client.natura_default } : {}) } : null }))} />
    {form.cassa && <CassaFields cassa={form.cassa} disabled={disabled} ritenutaOn={!!form.ritenuta} onChange={(c) => setForm((f) => ({ ...f, cassa: c }))} />}
    <div className="border-t border-slate-100" />
    <Toggle label="Ritenuta d'acconto" checked={!!form.ritenuta} disabled={disabled} testId="ritenuta-switch"
      onChange={(v) => setForm((f) => ({ ...f, ritenuta: v ? defaultRitenuta(company) : null }))} />
    {form.ritenuta && <RitenutaFields ritenuta={form.ritenuta} disabled={disabled} onChange={(r) => setForm((f) => ({ ...f, ritenuta: r }))} />}
  </div>
);

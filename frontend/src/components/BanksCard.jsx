import { Plus, Trash2, Landmark } from "lucide-react";
import { Field } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const NEW_BANK = { nome: "", iban: "", abi: "", cab: "", bic: "", predefinita: false };
const COLS = [["nome", "Banca", "col-span-2"], ["iban", "IBAN", "col-span-2 sm:col-span-4"], ["abi", "ABI", "sm:col-span-2"], ["cab", "CAB", "sm:col-span-2"], ["bic", "BIC / SWIFT", "col-span-2"]];

export const fromIban = (b) => {
  const s = (b.iban || "").replace(/\s+/g, "").toUpperCase();
  return s.startsWith("IT") && s.length === 27 ? { ...b, iban: s, abi: s.slice(5, 10), cab: s.slice(10, 15) } : { ...b, iban: s };
};

const BankRow = ({ b, i, disabled, onChange, onDefault, onRemove }) => (
  <div className="rounded-lg border border-slate-200 p-4" data-testid={`bank-row-${i}`}>
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-6">
      {COLS.map(([k, label, cls]) => (
        <Field key={k} name={`banche.${i}.${k}`} label={label} className={cls}>
          <Input disabled={disabled} value={b[k] || ""} className={k === "iban" ? "mono" : ""} placeholder={k === "abi" || k === "cab" ? "dall'IBAN" : ""}
            onChange={(e) => onChange({ ...b, [k]: e.target.value })} onBlur={() => k === "iban" && onChange(fromIban(b))} data-testid={`bank-${k}-input-${i}`} />
        </Field>
      ))}
    </div>
    <div className="mt-3 flex items-center justify-between">
      <label className="flex items-center gap-2 text-xs text-slate-600">
        <input type="radio" name="bank-default" disabled={disabled} checked={!!b.predefinita} onChange={onDefault} data-testid={`bank-default-radio-${i}`} />
        Banca predefinita per le nuove fatture
      </label>
      {!disabled && <Button size="sm" variant="ghost" className="text-rose-600" onClick={onRemove} data-testid={`bank-remove-btn-${i}`}><Trash2 className="mr-1 h-3.5 w-3.5" />Rimuovi</Button>}
    </div>
  </div>
);

export const BanksCard = ({ banche, onChange, disabled }) => {
  const list = banche || [];
  const update = (i, b) => onChange(list.map((x, j) => (j === i ? b : x)));
  const setDefault = (i) => onChange(list.map((x, j) => ({ ...x, predefinita: j === i })));
  const add = () => onChange([...list, { ...NEW_BANK, predefinita: list.length === 0 }]);
  const remove = (i) => {
    const rest = list.filter((_, j) => j !== i);
    onChange(rest.length && !rest.some((x) => x.predefinita) ? rest.map((x, j) => ({ ...x, predefinita: j === 0 })) : rest);
  };

  return (
    <div className="mt-6 max-w-3xl rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm" data-testid="banks-card">
      <div className="mb-1 flex items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-lg font-semibold text-slate-800"><Landmark className="h-5 w-5 text-blue-600" />Banche aziendali</h3>
        {!disabled && <Button size="sm" variant="outline" onClick={add} data-testid="bank-add-btn"><Plus className="mr-1 h-4 w-4" />Aggiungi banca</Button>}
      </div>
      <p className="mb-4 text-xs text-slate-500">Conti su cui ricevere i pagamenti. In fattura scegli la banca: nome, IBAN, ABI e CAB vengono riportati nella copia di cortesia e nel file XML. Per gli IBAN italiani ABI e CAB si compilano da soli.</p>
      {list.length === 0 && <p className="rounded-lg border border-dashed border-slate-200 p-6 text-center text-sm text-slate-500" data-testid="banks-empty">Nessuna banca inserita</p>}
      <div className="space-y-3">
        {list.map((b, i) => <BankRow key={b.id || `new-${i}`} b={b} i={i} disabled={disabled} onChange={(nb) => update(i, nb)} onDefault={() => setDefault(i)} onRemove={() => remove(i)} />)}
      </div>
      <p className="mt-3 text-xs text-slate-500">Ricorda di premere <b>Salva</b> in alto per memorizzare le modifiche.</p>
    </div>
  );
};

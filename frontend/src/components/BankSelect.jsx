import { Link } from "react-router-dom";
import { Field } from "@/components/Common";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export const BankSelect = ({ form, set, company, locked, inv }) => {
  const banche = company.banche || [];
  const def = banche.find((b) => b.predefinita) || banche[0];
  const value = banche.some((b) => b.id === form.banca_id) ? form.banca_id : def?.id;
  const shown = banche.find((b) => b.id === value) || (locked ? inv?.banca : null);

  if (locked) {
    return (
      <Field label="Banca d'appoggio" name="banca_id">
        <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm" data-testid="invoice-bank-locked">{inv?.banca?.iban ? <>{inv.banca.nome} · <span className="mono">{inv.banca.iban}</span></> : "—"}</div>
      </Field>
    );
  }
  if (!banche.length) {
    return (
      <Field label="Banca d'appoggio" name="banca_id">
        <p className="pt-2 text-xs text-amber-700" data-testid="invoice-bank-empty">Nessuna banca aziendale: <Link to="/impostazioni" className="font-semibold underline">aggiungila in Dati azienda</Link>.</p>
      </Field>
    );
  }
  return (
    <Field label="Banca d'appoggio" name="banca_id" className="sm:col-span-2">
      <Select value={value} onValueChange={(v) => set("banca_id", v)}>
        <SelectTrigger className="bg-white" data-testid="invoice-bank-select"><SelectValue /></SelectTrigger>
        <SelectContent className="bg-white">
          {banche.map((b) => <SelectItem key={b.id} value={b.id} data-testid={`invoice-bank-option-${b.id}`}>{b.nome} · {b.iban}{b.predefinita ? " (predefinita)" : ""}</SelectItem>)}
        </SelectContent>
      </Select>
      {shown && <p className="mt-1 text-xs text-slate-500" data-testid="invoice-bank-details">ABI {shown.abi || "—"} · CAB {shown.cab || "—"}{shown.bic ? ` · BIC ${shown.bic}` : ""}</p>}
    </Field>
  );
};

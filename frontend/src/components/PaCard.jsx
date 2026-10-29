import { Landmark } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/Common";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const RIF = [["ordine", "Ordine d'acquisto"], ["contratto", "Contratto"], ["convenzione", "Convenzione"]];

export const PaCard = ({ form, set, disabled, client }) => (
  <div className="rounded-xl border border-sky-200 bg-sky-50/60 p-6 shadow-sm" data-testid="pa-card">
    <h3 className="mb-1 flex items-center gap-2 text-lg font-semibold text-slate-800"><Landmark className="h-5 w-5 text-sky-700" />Dati Pubblica Amministrazione</h3>
    <p className="mb-4 text-xs text-sky-800">
      Formato FPA12 · Codice univoco ufficio <span className="mono font-semibold">{client.codice_destinatario}</span>
      {client.split_payment && " · Scissione dei pagamenti (art. 17-ter DPR 633/72)"}
    </p>
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      <Field label="Riferimento" name="rif_tipo">
        <Select disabled={disabled} value={form.rif_tipo || "ordine"} onValueChange={(v) => set("rif_tipo", v)}>
          <SelectTrigger className="bg-white" data-testid="pa-rif-tipo-select"><SelectValue /></SelectTrigger>
          <SelectContent className="bg-white">{RIF.map(([k, l]) => <SelectItem key={k} value={k} data-testid={`pa-rif-tipo-${k}`}>{l}</SelectItem>)}</SelectContent>
        </Select>
      </Field>
      <Field label="N. documento" name="rif_documento"><Input disabled={disabled} className="bg-white" maxLength={20} value={form.rif_documento || ""} onChange={(e) => set("rif_documento", e.target.value)} data-testid="pa-rif-documento-input" /></Field>
      <Field label="Data documento" name="rif_data"><Input disabled={disabled} className="bg-white" type="date" value={form.rif_data || ""} onChange={(e) => set("rif_data", e.target.value)} data-testid="pa-rif-data-input" /></Field>
      <Field label="Codice CIG (10 car.)" name="cig"><Input disabled={disabled} className="mono bg-white uppercase" maxLength={10} value={form.cig || ""} onChange={(e) => set("cig", e.target.value.toUpperCase())} data-testid="pa-cig-input" /></Field>
      <Field label="Codice CUP (15 car.)" name="cup" className="sm:col-span-2"><Input disabled={disabled} className="mono bg-white uppercase" maxLength={15} value={form.cup || ""} onChange={(e) => set("cup", e.target.value.toUpperCase())} data-testid="pa-cup-input" /></Field>
    </div>
  </div>
);

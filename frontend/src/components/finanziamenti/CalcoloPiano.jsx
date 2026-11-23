import { useState } from "react";
import { toast } from "sonner";
import { Calculator } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { NSelect } from "@/components/ui/nselect";
import { api, errMsg } from "@/lib/api";

const PER = [[1, "Mensile"], [2, "Bimestrale"], [3, "Trimestrale"], [6, "Semestrale"], [12, "Annuale"]];
const L = ({ label, children }) => <label className="block text-xs font-medium text-slate-600">{label}{children}</label>;

export const CalcoloPiano = ({ f, onRate }) => {
  const [c, setC] = useState({ n_rate: 60, periodicita: 1, prima_scadenza: "", maxicanone: 0, riscatto: 0 });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setC({ ...c, [k]: e.target.value });
  const run = async () => {
    setBusy(true);
    try {
      const body = { tipo: f.tipo, importo: Number(f.importo), tasso: Number(f.tasso || 0), n_rate: Number(c.n_rate), periodicita: Number(c.periodicita), prima_scadenza: c.prima_scadenza, maxicanone: Number(c.maxicanone || 0), riscatto: Number(c.riscatto || 0), data: f.data };
      const { data } = await api.post("/finanziamenti/calcola", body);
      onRate(data.rate);
      toast.success(`Piano calcolato: ${data.rate.length} rate`);
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <div className="rounded-lg border border-blue-100 bg-blue-50/50 p-3" data-testid="fin-calcolo">
      <div className="mb-2 text-xs font-semibold uppercase text-blue-900">Calcolo automatico (rata costante alla francese)</div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        <L label="Numero rate"><Input type="number" min={1} value={c.n_rate} onChange={set("n_rate")} className="h-8" data-testid="fin-calc-n" /></L>
        <L label="Periodicità"><NSelect value={c.periodicita} onChange={set("periodicita")} className="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-sm" data-testid="fin-calc-per">{PER.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</NSelect></L>
        <L label="Prima scadenza"><Input type="date" value={c.prima_scadenza} onChange={set("prima_scadenza")} className="h-8" data-testid="fin-calc-prima" /></L>
        {f.tipo === "leasing" && <>
          <L label="Maxicanone"><Input type="number" step="0.01" min={0} value={c.maxicanone} onChange={set("maxicanone")} className="h-8" data-testid="fin-calc-maxi" /></L>
          <L label="Riscatto"><Input type="number" step="0.01" min={0} value={c.riscatto} onChange={set("riscatto")} className="h-8" data-testid="fin-calc-riscatto" /></L>
        </>}
      </div>
      <Button size="sm" className="mt-3" onClick={run} disabled={busy || !f.importo || !c.prima_scadenza} data-testid="fin-calc-btn"><Calculator className="mr-1 h-3.5 w-3.5" />Calcola le rate</Button>
      <span className="ml-3 text-xs text-slate-500">Usa importo e tasso indicati sopra; il risultato sostituisce le rate in tabella.</span>
    </div>
  );
};

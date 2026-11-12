import { lineTotal, fmtEUR } from "@/lib/fe";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const NATURE = ["N2.1", "N2.2", "N3.5", "N3.6", "N4"];
export const BOLLO_LINE = { descrizione: "Imposta di bollo assolta in modo virtuale (art. 6 DM 17/06/2014)", quantita: 1, prezzo_unitario: 2, aliquota: 0, natura: "N1", sconto: "", bollo: true };

export const bolloState = (lines, scelta, client) => {
  const esenti = Math.round(lines.filter((l) => Number(l.aliquota) === 0 && NATURE.includes(l.natura)).reduce((s, l) => s + lineTotal(l), 0) * 100) / 100;
  const dovuto = esenti > 77.47;
  const on = scelta === null || scelta === undefined ? dovuto : scelta;
  return { esenti, dovuto, on, add: on && !!client?.bollo_addebito };
};

const VAL = { auto: null, si: true, no: false };
const key = (v) => (v === true ? "si" : v === false ? "no" : "auto");

export const BolloCard = ({ state, scelta, onChange, disabled }) => (
  <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs" data-testid="bollo-card">
    <div className="flex items-center justify-between gap-2">
      <span className="font-semibold text-slate-800">Bollo virtuale 2 €</span>
      <Select disabled={disabled} value={key(scelta)} onValueChange={(v) => onChange(VAL[v])}>
        <SelectTrigger className="h-8 w-40 bg-white" data-testid="bollo-select"><SelectValue /></SelectTrigger>
        <SelectContent className="bg-white">
          <SelectItem value="auto" data-testid="bollo-opt-auto">Automatico</SelectItem>
          <SelectItem value="si" data-testid="bollo-opt-si">Applica sempre</SelectItem>
          <SelectItem value="no" data-testid="bollo-opt-no">Non applicare</SelectItem>
        </SelectContent>
      </Select>
    </div>
    <p className="mt-2 text-slate-600" data-testid="bollo-status">
      Importi esenti/non imponibili: {fmtEUR(state.esenti)} {state.dovuto ? "(oltre 77,47 €: bollo dovuto)" : "(sotto 77,47 €)"}.{" "}
      {state.on ? (state.add ? <b className="text-slate-800">Bollo applicato e addebitato al cliente.</b> : <b className="text-slate-800">Bollo applicato, a carico tuo.</b>) : "Bollo non applicato."}
    </p>
  </div>
);

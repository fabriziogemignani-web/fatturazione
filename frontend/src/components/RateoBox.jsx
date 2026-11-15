import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

export const NOMI_RR = { acquisto: { risconto: "Risconto attivo", rateo: "Rateo passivo" }, vendita: { risconto: "Risconto passivo", rateo: "Rateo attivo" } };

export const proponiRR = (dataReg, dal, al) => {
  const y = (dataReg || "").slice(0, 4);
  if (!dal || !al || !y) return null;
  if (al > `${y}-12-31`) return "risconto";
  if (dal < `${y}-01-01`) return "rateo";
  return null;
};

export const rateoBody = (rr) => (rr?.attivo ? { competenza_dal: rr.dal, competenza_al: rr.al, tipo: rr.tipo || "risconto", note: rr.note || "" } : null);
export const rateoInvalido = (rr) => rr?.attivo && (!rr.dal || !rr.al || rr.al < rr.dal || !rr.tipo);

export const RateoBox = ({ rr, setRr, dataReg, origine }) => {
  const upd = (patch) => {
    const n = { ...rr, ...patch };
    if (("dal" in patch || "al" in patch) && !n.tipoManuale) n.tipo = proponiRR(dataReg, n.dal, n.al) || n.tipo;
    setRr(n);
  };
  const prop = proponiRR(dataReg, rr.dal, rr.al);
  return (
    <div className="rounded-lg border border-violet-200 bg-violet-50/50 p-3 text-xs text-slate-600" data-testid="rateo-box">
      <label className="flex items-center justify-between gap-3 text-sm font-semibold text-slate-800">
        Esiste un rateo o risconto su questo documento?
        <Switch checked={!!rr.attivo} onCheckedChange={(v) => setRr({ ...rr, attivo: v })} data-testid="rateo-switch" />
      </label>
      {rr.attivo && (
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <label>Competenza dal<Input type="date" value={rr.dal || ""} onChange={(e) => upd({ dal: e.target.value })} className="w-40 bg-white" data-testid="rateo-dal" /></label>
          <label>Competenza al<Input type="date" value={rr.al || ""} onChange={(e) => upd({ al: e.target.value })} className="w-40 bg-white" data-testid="rateo-al" /></label>
          <label>Tipo
            <select value={rr.tipo || ""} onChange={(e) => setRr({ ...rr, tipo: e.target.value, tipoManuale: true })} className="block h-9 rounded-md border border-slate-200 bg-white px-2 text-sm" data-testid="rateo-tipo">
              <option value="">Scegli…</option>
              {["risconto", "rateo"].map((k) => <option key={k} value={k}>{NOMI_RR[origine][k]}</option>)}
            </select>
          </label>
          <Input placeholder="Note" value={rr.note || ""} onChange={(e) => setRr({ ...rr, note: e.target.value })} className="w-48 bg-white" data-testid="rateo-note" />
          <span className="pb-2" data-testid="rateo-proposta">
            {rr.dal && rr.al ? (prop ? `Proposto: ${NOMI_RR[origine][prop]}${rr.tipo && rr.tipo !== prop ? " (hai scelto un tipo diverso)" : ""}` : "La competenza è tutta nell'esercizio di registrazione: non serve rateo né risconto") : "Inserisci le date di competenza"}
          </span>
        </div>
      )}
    </div>
  );
};

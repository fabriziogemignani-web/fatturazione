import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Percent } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR } from "@/lib/fe";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export const DetraibilitaCard = ({ d, edit, onSaved }) => {
  const cur = d.detraibilita_iva ?? 100;
  const [v, setV] = useState(cur);
  useEffect(() => { setV(cur); }, [cur]);
  const pct = Math.min(Math.max(Number(v || 0), 0), 100);
  const det = Math.round((d.iva || 0) * pct) / 100;
  const save = async () => {
    try { await api.put(`/passive/${d.id}/detraibilita`, { percentuale: pct }); toast.success("Detraibilità IVA aggiornata"); onSaved(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm" data-testid="passive-detraibilita-card">
      <h3 className="mb-1 flex items-center gap-2 text-lg font-semibold text-slate-800"><Percent className="h-4 w-4" />IVA detraibile</h3>
      <p className="mb-3 text-xs text-slate-500">Proposta dal fornitore (es. carburante 40%, telefonia 50%). La parte indetraibile va a costo in contabilità e non entra nella liquidazione IVA.</p>
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-xs text-slate-600">Detraibile %<Input type="number" min={0} max={100} step="1" value={v} onChange={(e) => setV(e.target.value)} disabled={!edit} className="w-24" data-testid="passive-detraibilita-input" /></label>
        <div className="text-sm" data-testid="passive-detraibilita-importi">Detraibile <b>{fmtEUR(det)}</b> · indetraibile <b className="text-rose-700">{fmtEUR((d.iva || 0) - det)}</b></div>
        {edit && Number(v) !== cur && <Button size="sm" onClick={save} data-testid="passive-detraibilita-save">Salva</Button>}
      </div>
    </div>
  );
};

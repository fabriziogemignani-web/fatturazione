import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { fmtEUR } from "@/lib/fe";
import { Button } from "@/components/ui/button";

export const AmmortamentiPanel = ({ edit, onChange }) => {
  const [anno, setAnno] = useState(new Date().getFullYear());
  const [a, setA] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => { api.get(`/cespiti/ammortamenti/${anno}`).then(({ data }) => setA(data)).catch((e) => toast.error(errMsg(e))); }, [anno]);
  useEffect(() => { load(); }, [load]);
  const run = async (del) => {
    if (!window.confirm(del ? `Annullare gli ammortamenti ${anno} e la loro registrazione in prima nota?` : `Registrare gli ammortamenti ${anno} al 31/12/${anno}?`)) return;
    setBusy(true);
    try {
      const { data } = await (del ? api.delete(`/cespiti/ammortamenti/${anno}`) : api.post(`/cespiti/ammortamenti/${anno}`));
      setA(data);
      toast.success(del ? "Ammortamenti annullati" : `Ammortamenti ${anno} registrati${data.coge_rif ? ` · ${data.coge_rif}` : ""}`);
      onChange();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <section className="mb-6 rounded-xl border border-slate-200 bg-white shadow-sm" data-testid="amm-panel">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <div className="flex items-center gap-2">
          <h3 className="font-semibold text-slate-900">Ammortamenti di fine anno</h3>
          <select value={anno} onChange={(e) => setAnno(Number(e.target.value))} className="h-8 rounded-md border border-slate-200 px-2 text-sm" data-testid="amm-anno">
            {[0, 1, 2, 3, 4].map((i) => new Date().getFullYear() - i).map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
        {a && <div className="flex items-center gap-3 text-sm">
          <span>Totale <b data-testid="amm-totale">{fmtEUR(a.totale)}</b></span>
          {a.registrato ? <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800" data-testid="amm-registrato">Registrati{a.coge_rif ? ` · ${a.coge_rif}` : ""}</span> : null}
          {edit && !a.registrato && <Button size="sm" onClick={() => run(false)} disabled={busy || !a.voci.length} data-testid="amm-registra">Registra ammortamenti {anno}</Button>}
          {edit && a.registrato && <Button size="sm" variant="outline" onClick={() => run(true)} disabled={busy} data-testid="amm-annulla">Annulla</Button>}
        </div>}
      </div>
      {a && (a.voci.length === 0 ? <p className="px-5 py-6 text-sm text-slate-500">Nessuna quota di ammortamento per il {anno}.</p> : (
        <div className="grid grid-cols-1 gap-4 p-5 lg:grid-cols-3">
          <div className="max-h-72 overflow-auto lg:col-span-2">
            <table className="w-full text-sm" data-testid="amm-voci">
              <thead className="text-left text-xs uppercase text-slate-500"><tr><th className="py-1">Cespite</th><th className="py-1 text-right">Costo</th><th className="py-1 text-right">%</th><th className="py-1 text-right">Quota {anno}</th></tr></thead>
              <tbody className="divide-y divide-slate-100">{a.voci.map((v) => <tr key={v.id} data-testid={`amm-voce-${v.id}`}><td className="py-1.5">{v.descrizione}<div className="text-xs text-slate-400">{v.categoria}</div></td><td className="py-1.5 text-right">{fmtEUR(v.costo)}</td><td className="py-1.5 text-right">{v.aliquota}</td><td className="py-1.5 text-right font-semibold">{fmtEUR(v.quota)}</td></tr>)}</tbody>
            </table>
          </div>
          <div className="rounded-lg bg-slate-50 p-3 text-xs" data-testid="amm-anteprima">
            <div className="mb-2 font-semibold uppercase text-slate-500">Prima nota al 31/12/{anno}</div>
            {a.righe.map((r, i) => <div key={i} className="flex justify-between py-0.5"><span className="mono">{r.conto}</span><span>{r.dare ? `Dare ${fmtEUR(r.dare)}` : `Avere ${fmtEUR(r.avere)}`}</span></div>)}
          </div>
        </div>
      ))}
    </section>
  );
};

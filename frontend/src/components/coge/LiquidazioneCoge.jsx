import { useEffect, useState } from "react";
import { toast } from "sonner";
import { BookCheck, Undo2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR } from "@/lib/fe";
import { Button } from "@/components/ui/button";
import { useAuth, canSend } from "@/context/AuthContext";

export const LiquidazioneCoge = ({ anno, per }) => {
  const { user } = useAuth();
  const canEdit = canSend(user);
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState(null);
  const load = () => api.get("/contabilita/liquidazioni", { params: { anno, periodicita: per } }).then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, [anno, per]); // eslint-disable-line react-hooks/exhaustive-deps
  const run = async (x, fn, ok) => {
    setBusy(x.periodo);
    try { await fn(); toast.success(ok); load(); } catch (e) { toast.error(errMsg(e)); }
    setBusy(null);
  };
  const registra = (x) => run(x, () => api.post("/contabilita/liquidazioni", { anno, periodicita: per, periodo: x.periodo }), `Liquidazione ${x.label} registrata in contabilità`);
  const annulla = (x) => window.confirm(`Annullare la registrazione della liquidazione ${x.label} ${anno}?`) && run(x, () => api.delete(`/contabilita/liquidazioni/${x.registrazione.id}`), "Registrazione annullata");
  if (!d) return null;

  return (
    <div className="mt-6 rounded-xl border border-slate-200 bg-white shadow-sm print:hidden" data-testid="liq-coge-card">
      <div className="border-b border-slate-100 p-5">
        <h3 className="font-semibold text-slate-800">Registrazione in contabilità generale</h3>
        <p className="text-xs text-slate-500">Giroconto dei saldi di IVA vendite e IVA acquisti del periodo su Erario c/IVA, calcolato dalle registrazioni contabili. {d.chiuso && <b className="text-rose-700">Esercizio {anno} chiuso: nessuna modifica possibile.</b>}</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm" data-testid="liq-coge-table">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr><th className="px-4 py-2.5">Periodo</th><th className="px-4 py-2.5 text-right">IVA vendite</th><th className="px-4 py-2.5 text-right">IVA acquisti</th><th className="px-4 py-2.5 text-right">Saldo</th>{per === "trimestrale" && <th className="px-4 py-2.5 text-right">Interessi 1%</th>}<th className="px-4 py-2.5">Stato</th><th /></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {d.periodi.map((x) => (
              <tr key={x.periodo} data-testid={`liq-coge-row-${x.periodo}`}>
                <td className="px-4 py-2.5 font-medium">{x.label}</td>
                <td className="px-4 py-2.5 text-right">{fmtEUR(x.iva_vendite)}</td>
                <td className="px-4 py-2.5 text-right">{fmtEUR(x.iva_acquisti)}</td>
                <td className={`px-4 py-2.5 text-right font-semibold ${x.saldo > 0 ? "text-rose-700" : x.saldo < 0 ? "text-emerald-700" : ""}`} data-testid={`liq-coge-saldo-${x.periodo}`}>{fmtEUR(Math.abs(x.saldo))} {x.saldo > 0 ? "a debito" : x.saldo < 0 ? "a credito" : ""}</td>
                {per === "trimestrale" && <td className="px-4 py-2.5 text-right">{x.interessi ? fmtEUR(x.interessi) : "—"}</td>}
                <td className="px-4 py-2.5 text-xs" data-testid={`liq-coge-stato-${x.periodo}`}>
                  {x.registrazione ? <span className="rounded-full bg-emerald-50 px-2 py-0.5 font-semibold text-emerald-700">Registrata n. {x.registrazione.numero}/{x.registrazione.anno}</span>
                    : x.bloccato ? <span className="text-amber-700">{x.bloccato}</span> : <span className="text-slate-500">Da registrare</span>}
                </td>
                <td className="whitespace-nowrap px-4 py-2.5 text-right">
                  {canEdit && !d.chiuso && (x.registrazione
                    ? <Button size="sm" variant="outline" disabled={busy === x.periodo} onClick={() => annulla(x)} data-testid={`liq-coge-annulla-${x.periodo}`}><Undo2 className="mr-1 h-3.5 w-3.5" />Annulla</Button>
                    : !x.bloccato && (x.iva_vendite || x.iva_acquisti) ? <Button size="sm" disabled={busy === x.periodo} onClick={() => registra(x)} data-testid={`liq-coge-registra-${x.periodo}`}><BookCheck className="mr-1 h-3.5 w-3.5" />Registra</Button> : null)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

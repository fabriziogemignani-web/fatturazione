import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, ArrowLeftRight } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate, METODI_INCASSO } from "@/lib/fe";
import { useAuth, canSend } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { PaymentDialog, RataBadge } from "@/components/PaymentDialog";

const METODO = Object.fromEntries(METODI_INCASSO);

const Sum = ({ label, value, testId, tone = "text-slate-900" }) => (
  <div><div className="text-xs text-slate-500">{label}</div><div className={`font-semibold ${tone}`} data-testid={testId}>{value}</div></div>
);

export const PaymentsPanel = ({ invoiceId }) => {
  const { user } = useAuth();
  const [d, setD] = useState(null);
  const [dlg, setDlg] = useState(null);
  const load = useCallback(() => { api.get(`/invoices/${invoiceId}/pagamenti`).then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e))); }, [invoiceId]);
  useEffect(() => { load(); }, [load]);

  if (!d?.scadenzario) return null;
  const s = d.scadenzario;
  const credits = d.crediti.filter((c) => c.party_id === s.party_id);
  const remove = async (p) => {
    if (!window.confirm(`Eliminare ${p.metodo === "compensazione" ? "la compensazione" : "l'incasso"} di ${fmtEUR(p.importo)}?`)) return;
    try { await api.delete(`/pagamenti/${p.id}`); toast.success("Eliminato"); load(); } catch (e) { toast.error(errMsg(e)); }
  };

  return (
    <div className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm" data-testid="payments-panel">
      <h3 className="mb-4 text-lg font-semibold text-slate-800">Scadenzario e incassi</h3>
      <div className="mb-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <Sum label="Netto a pagare" value={fmtEUR(s.netto)} testId="pp-netto" />
        <Sum label="Incassato" value={fmtEUR(s.incassato)} testId="pp-incassato" tone="text-emerald-700" />
        <Sum label="Compensato con NC" value={fmtEUR(s.compensato)} testId="pp-compensato" tone="text-violet-700" />
        <Sum label="Residuo" value={fmtEUR(s.residuo)} testId="pp-residuo" tone={s.residuo > 0 ? "text-rose-700" : "text-emerald-700"} />
      </div>
      <div className="divide-y divide-slate-100 rounded-lg border border-slate-100">
        {s.rate.map((r) => (
          <div key={r.n} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm" data-testid={`pp-rata-${r.n}`}>
            <span className="text-slate-600">Rata {r.n}/{r.di} · {fmtDate(r.scadenza)}</span>
            <span className="flex items-center gap-3"><span className="font-semibold">{fmtEUR(r.importo)}</span><RataBadge r={r} testId={`pp-rata-stato-${r.n}`} /></span>
          </div>
        ))}
      </div>
      {s.compensato_auto > 0 && <p className="mt-2 text-xs text-violet-700" data-testid="pp-auto-nc">Include {fmtEUR(s.compensato_auto)} compensati automaticamente dalle note di credito collegate.</p>}
      {d.pagamenti.length > 0 && (
        <div className="mt-4 space-y-1" data-testid="pp-payments">
          {d.pagamenti.map((p) => (
            <div key={p.id} className="flex items-center justify-between gap-2 rounded-md bg-slate-50 px-3 py-2 text-xs" data-testid={`pp-payment-${p.id}`}>
              <span>{fmtDate(p.data)} · {METODO[p.metodo]}{p.nc_numero && ` ${p.nc_numero}`}{p.note && ` · ${p.note}`}</span>
              <span className="flex items-center gap-2 font-semibold">{fmtEUR(p.importo)}
                {canSend(user) && <button onClick={() => remove(p)} className="text-slate-400 hover:text-rose-600" data-testid={`pp-delete-${p.id}`}><Trash2 className="h-3.5 w-3.5" /></button>}
              </span>
            </div>
          ))}
        </div>
      )}
      {canSend(user) && s.residuo > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          <Button size="sm" onClick={() => setDlg({ compensa: false })} data-testid="pp-add-payment-btn"><Plus className="mr-1.5 h-4 w-4" />Registra incasso</Button>
          {credits.length > 0 && <Button size="sm" variant="outline" className="border-violet-300 text-violet-700" onClick={() => setDlg({ compensa: true })} data-testid="pp-compensate-btn"><ArrowLeftRight className="mr-1.5 h-4 w-4" />Compensa con NC</Button>}
        </div>
      )}
      <PaymentDialog open={!!dlg} onOpenChange={(o) => !o && setDlg(null)} doc={s} crediti={d.crediti} compensa={dlg?.compensa} onDone={load} />
    </div>
  );
};

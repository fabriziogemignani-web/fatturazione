import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Wallet, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { Button } from "@/components/ui/button";
import { useAuth, canSend } from "@/context/AuthContext";

export const PagamentiPanel = () => {
  const [d, setD] = useState(null);
  const { user } = useAuth();
  useEffect(() => { api.get("/pagamenti-fornitori/riepilogo").then(({ data }) => setD(data)).catch(() => {}); }, []);
  if (!d) return null;
  const righe = d.in_scadenza;
  return (
    <div className="mt-6 rounded-xl border border-slate-200 bg-white shadow-sm" data-testid="pagamenti-panel">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <div className="flex items-center gap-2"><Wallet className="h-4 w-4 text-blue-600" /><h3 className="font-semibold text-slate-900">Fatture fornitori in scadenza nei prossimi 10 giorni</h3></div>
        <div className="flex items-center gap-3">
          <b data-testid="pagamenti-panel-totale">{fmtEUR(d.in_scadenza_totale)}</b>
          {canSend(user) && righe.length > 0 && (
            <Button asChild size="sm" data-testid="pagamenti-panel-prepara-btn"><Link to={`/pagamenti-fornitori?dal=${d.dal}&al=${d.al}&prepara=1`}>Prepara pagamento</Link></Button>
          )}
        </div>
      </div>
      <div className="px-5 py-4">
        {righe.length === 0 ? <p className="text-xs text-slate-500" data-testid="pagamenti-panel-empty">Nessuna fattura fornitore in scadenza nei prossimi 10 giorni.</p> : (
          <ul className="space-y-1 text-xs">
            {righe.slice(0, 8).map((x) => (
              <li key={x.key} className="flex justify-between gap-2" data-testid={`pagamenti-panel-row-${x.key}`}>
                <span className="truncate">{fmtDate(x.scadenza)} · {x.fornitore} · <span className="mono">{x.numero_display}</span>{x.rate_totali > 1 && ` rata ${x.rata_n}/${x.rate_totali}`}
                  {x.manca_iban && <span className="ml-1 inline-flex items-center gap-0.5 text-amber-700"><AlertTriangle className="h-3 w-3" />IBAN mancante</span>}</span>
                <span className="font-medium">{fmtEUR(x.residuo)}</span>
              </li>
            ))}
            {righe.length > 8 && <li className="text-slate-400">e altre {righe.length - 8}…</li>}
          </ul>
        )}
        {d.scadute_n > 0 && <p className="mt-3 text-xs font-medium text-rose-700" data-testid="pagamenti-panel-scadute">Ci sono anche {d.scadute_n} rate già scadute da pagare per {fmtEUR(d.scadute_totale)}.</p>}
      </div>
    </div>
  );
};

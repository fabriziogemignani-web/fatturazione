import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Mail, CheckCircle2, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { fmtEUR } from "@/lib/fe";

const CLS = { cortesia: "bg-blue-50 text-blue-700", promemoria: "bg-amber-50 text-amber-700", sollecito: "bg-rose-50 text-rose-700" };

export const ComLog = ({ limit = 8, compact = false }) => {
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/comunicazioni/log", { params: { limit } }).then(({ data }) => setD(data)).catch(() => {}); }, [limit]);
  if (!d) return null;
  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm" data-testid={compact ? "com-panel" : "com-log"}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-5 py-4">
        <div className="flex items-center gap-2"><Mail className="h-4 w-4 text-slate-500" /><h3 className="font-semibold text-slate-900">Comunicazioni inviate ai clienti</h3></div>
        <div className="flex flex-wrap gap-2 text-xs" data-testid="com-stats">
          {Object.entries(d.tipi).map(([k, l]) => <span key={k} className={`rounded-full px-2 py-0.5 font-semibold ${CLS[k]}`}>{d.settimana[k]} {l.toLowerCase()}</span>)}
          {d.errori > 0 && <span className="rounded-full bg-rose-600 px-2 py-0.5 font-semibold text-white">{d.errori} non inviate</span>}
          <span className="text-slate-400">ultimi 7 giorni</span>
          {compact && <Link to="/comunicazioni" className="font-semibold text-blue-600 hover:underline" data-testid="com-panel-link">Gestisci</Link>}
        </div>
      </div>
      {d.log.length === 0 ? <p className="px-5 py-8 text-center text-sm text-slate-500" data-testid="com-log-empty">Nessuna comunicazione inviata finora</p> : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm"><tbody className="divide-y divide-slate-100">
            {d.log.map((x) => (
              <tr key={x.id} data-testid={`com-log-row-${x.id}`}>
                <td className="whitespace-nowrap px-4 py-2.5 text-xs text-slate-500">{new Date(x.created_at).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" })}</td>
                <td className="px-4 py-2.5"><span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${CLS[x.tipo]}`}>{d.tipi[x.tipo]}{x.livello ? ` ${x.livello}° livello` : ""}</span></td>
                <td className="px-4 py-2.5"><div className="font-medium">{x.cliente}</div><div className="text-xs text-slate-500">{x.to || "nessun indirizzo"} · {x.documenti.join(", ")}</div></td>
                <td className="whitespace-nowrap px-4 py-2.5 text-right font-semibold">{fmtEUR(x.importo || 0)}</td>
                <td className="px-4 py-2.5 text-xs">{x.esito === "ok" ? <span className="flex items-center gap-1 text-emerald-700"><CheckCircle2 className="h-3.5 w-3.5" />Inviata{x.auto ? "" : " a mano"}</span>
                  : <span className="flex items-center gap-1 text-rose-700" title={x.errore}><XCircle className="h-3.5 w-3.5" />{x.errore}</span>}</td>
              </tr>
            ))}
          </tbody></table>
        </div>
      )}
    </div>
  );
};

export const ComunicazioniPanel = () => <div className="mt-6"><ComLog limit={6} compact /></div>;

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, CalendarRange } from "lucide-react";
import { api } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";

const Riga = ({ x, scaduta }) => (
  <li className="flex items-center justify-between gap-3 px-5 py-2 text-sm" data-testid={`rat-avviso-${x.piano_id}-${x.n}`}>
    <span className="min-w-0 truncate"><b className={scaduta ? "text-rose-700" : "text-amber-700"}>{fmtDate(x.scadenza)}</b> · <Link to={x.link} className="hover:underline">{x.label || `Rata ${x.n}/${x.di} ${x.ente} ${x.numero}`}</Link></span>
    <span className="whitespace-nowrap font-semibold">{fmtEUR(x.totale)}</span>
  </li>
);

export const RateizzazioniPanel = () => {
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/rateizzazioni-avvisi").then(({ data }) => setD(data)).catch(() => {}); }, []);
  if (!d || (!d.scadute.length && !d.in_scadenza.length)) return null;
  return (
    <div className="mt-6 rounded-xl border border-amber-200 bg-white shadow-sm" data-testid="rateizzazioni-panel">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-amber-100 px-5 py-4">
        <div>
          <h3 className="flex items-center gap-2 font-semibold text-slate-900"><CalendarRange className="h-4 w-4 text-amber-600" />Rate in scadenza: rateizzazioni, finanziamenti e leasing</h3>
          <p className="text-xs text-slate-500">Scadute e in scadenza nei prossimi {d.giorni} giorni</p>
        </div>
        {d.scadute.length > 0 && <span className="flex items-center gap-1 rounded-full bg-rose-50 px-3 py-1 text-xs font-semibold text-rose-700" data-testid="rat-avvisi-scadute"><AlertTriangle className="h-3.5 w-3.5" />{d.scadute.length} scadute · {fmtEUR(d.totale_scaduto)}</span>}
      </div>
      <ul className="divide-y divide-slate-100">
        {d.scadute.map((x) => <Riga key={`${x.piano_id}-${x.n}`} x={x} scaduta />)}
        {d.in_scadenza.map((x) => <Riga key={`${x.piano_id}-${x.n}`} x={x} />)}
      </ul>
      {d.scadute.length > 0 && <p className="px-5 pb-2 text-[11px] text-rose-700">Attenzione: il mancato pagamento delle rate può far decadere il piano o il contratto.</p>}
      <div className="px-5 pb-4 pt-2"><Link to="/rateizzazioni" className="text-xs font-semibold text-blue-600 hover:underline" data-testid="rat-avvisi-link">Vai alle rateizzazioni</Link></div>
    </div>
  );
};

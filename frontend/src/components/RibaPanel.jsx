import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Banknote } from "lucide-react";
import { api } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";

const Gruppo = ({ id, titolo, tono, righe, totale, vuoto, data }) => (
  <div className="px-5 py-4" data-testid={`riba-panel-${id}`}>
    <div className="mb-2 flex items-center justify-between text-sm">
      <span className={`font-semibold ${tono}`}>{titolo} · {righe.length}</span>
      <b data-testid={`riba-panel-${id}-totale`}>{fmtEUR(totale)}</b>
    </div>
    {righe.length === 0 ? <p className="text-xs text-slate-500">{vuoto}</p> : (
      <ul className="space-y-1 text-xs">
        {righe.slice(0, 6).map((x) => (
          <li key={x.id || x.key} className="flex justify-between gap-2" data-testid={`riba-panel-${id}-row`}>
            <span className="truncate">{fmtDate(data(x))} · {x.cliente} · <span className="mono">{x.numero_display}</span></span>
            <span className="font-medium">{fmtEUR(x.importo)}</span>
          </li>
        ))}
        {righe.length > 6 && <li className="text-slate-400">e altri {righe.length - 6}…</li>}
      </ul>
    )}
  </div>
);

export const RibaPanel = () => {
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/riba/riepilogo").then(({ data }) => setD(data)).catch(() => {}); }, []);
  if (!d) return null;
  return (
    <div className="mt-6 rounded-xl border border-slate-200 bg-white shadow-sm" data-testid="riba-panel">
      <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
        <div className="flex items-center gap-2"><Banknote className="h-4 w-4 text-blue-600" /><h3 className="font-semibold text-slate-900">Effetti Ri.Ba.</h3></div>
        <Link to="/riba" className="text-xs font-semibold text-blue-700 hover:underline" data-testid="riba-panel-link">Apri Ri.Ba.</Link>
      </div>
      <div className="grid divide-y divide-slate-100 md:grid-cols-3 md:divide-x md:divide-y-0">
        <Gruppo id="insoluti" titolo="Insoluti del mese" tono="text-rose-700" righe={d.insoluti} totale={d.insoluti_totale} vuoto="Nessun insoluto questo mese." data={(x) => x.insoluto?.data} />
        <Gruppo id="in-scadenza" titolo="Presentate in scadenza (10 gg)" tono="text-blue-800" righe={d.in_scadenza} totale={d.in_scadenza_totale} vuoto="Nessun effetto in scadenza." data={(x) => x.scadenza} />
        <Gruppo id="da-presentare" titolo="Da presentare entro 10 gg" tono="text-amber-700" righe={d.da_presentare} totale={d.da_presentare_totale} vuoto="Nessuna Ri.Ba. da presentare." data={(x) => x.scadenza} />
      </div>
    </div>
  );
};

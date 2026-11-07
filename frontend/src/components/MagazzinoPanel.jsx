import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Warehouse } from "lucide-react";
import { api } from "@/lib/api";
import { fmtEUR } from "@/lib/fe";
import { ScortaBadge } from "@/components/Sottoscorta";

export const MagazzinoPanel = () => {
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/magazzino/riepilogo").then(({ data }) => setD(data)).catch(() => {}); }, []);
  if (!d || !d.articoli) return null;
  return (
    <section className="mt-6 rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm" data-testid="magazzino-panel">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-lg font-semibold text-slate-800"><Warehouse className="h-5 w-5 text-blue-600" />Magazzino</h3>
        <Link to="/magazzino" className="text-xs font-semibold text-blue-700 hover:underline" data-testid="magazzino-panel-link">Apri il magazzino →</Link>
      </div>
      <div className="mb-4 grid grid-cols-3 gap-3">
        <div><div className="text-xs text-slate-500">Valore</div><div className="text-lg font-bold" data-testid="magazzino-panel-valore">{fmtEUR(d.valore_totale)}</div></div>
        <div><div className="text-xs text-slate-500">Articoli</div><div className="text-lg font-bold">{d.articoli}</div></div>
        <div><div className="text-xs text-amber-700">Sottoscorta</div><div className="text-lg font-bold text-amber-800" data-testid="magazzino-panel-sottoscorta">{d.sottoscorta}{d.esauriti ? ` (${d.esauriti} esauriti)` : ""}</div></div>
      </div>
      {d.elenco.length > 0 && (
        <div className="divide-y divide-slate-100 text-sm">
          {d.elenco.map((a) => (
            <div key={a.id} className="flex items-center justify-between gap-2 py-2" data-testid={`magazzino-panel-row-${a.id}`}>
              <span className="truncate"><span className="mono text-xs">{a.codice}</span> · {a.descrizione} <ScortaBadge s={a.stato_scorta} /></span>
              <span className="whitespace-nowrap text-xs text-slate-600">{a.giacenza} / min {a.scorta_minima} · ordina <b>{a.da_ordinare}</b> {a.unita_misura}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
};

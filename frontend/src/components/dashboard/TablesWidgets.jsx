import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { User } from "lucide-react";
import { api } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { Button } from "@/components/ui/button";
import { DCard } from "@/components/dashboard/Card";

const TH = "px-3 py-2 text-left text-xs font-medium text-slate-500";

export const SottoscortaWidget = () => {
  const [rows, setRows] = useState(null);
  const navigate = useNavigate();
  useEffect(() => { api.get("/magazzino/sottoscorta").then(({ data }) => setRows(data)).catch(() => setRows([])); }, []);
  return (
    <DCard title="Alert scorte magazzino" sub="Articoli sotto la scorta minima" testId="dash-sottoscorta"
      action={<Link to="/magazzino" className="text-xs font-semibold text-blue-700 hover:underline">Magazzino</Link>}>
      <div className="-mx-5 max-h-72 overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-slate-50"><tr><th className={TH}>Articolo</th><th className={`${TH} text-right`}>Giacenza</th><th className={`${TH} text-right`}>Minima</th><th className={TH}>Stato</th><th /></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {!rows ? <tr><td colSpan={5} className="px-5 py-6 text-slate-500">Caricamento…</td></tr>
              : rows.length === 0 ? <tr><td colSpan={5} className="px-5 py-8 text-center text-slate-500" data-testid="dash-sottoscorta-empty">Nessun articolo sottoscorta.</td></tr>
              : rows.slice(0, 20).map((a) => (
                <tr key={a.id} data-testid={`dash-scorta-${a.id}`}>
                  <td className="px-3 py-2.5 pl-5"><div className="font-medium text-slate-900">{a.descrizione}</div><div className="mono text-xs text-slate-400">{a.codice}</div></td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{a.giacenza}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{a.scorta_minima}</td>
                  <td className="px-3 py-2.5"><span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${a.stato_scorta === "esaurito" ? "bg-rose-100 text-rose-700" : "bg-amber-100 text-amber-800"}`}>{a.stato_scorta === "esaurito" ? "Esaurito" : "Sottoscorta"}</span></td>
                  <td className="px-3 py-2.5 pr-5 text-right"><Button size="sm" variant="outline" onClick={() => navigate("/magazzino?riordina=1")} data-testid={`dash-riordina-${a.id}`}>Riordina</Button></td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </DCard>
  );
};

export const ScadenzeWidget = () => {
  const [rows, setRows] = useState(null);
  useEffect(() => { api.get("/scadenzario").then(({ data }) => setRows(data.rate.filter((r) => r.residuo > 0.005))).catch(() => setRows([])); }, []);
  const oggi = new Date().toISOString().slice(0, 10);
  return (
    <DCard title="Scadenze fatture imminenti" sub="Incassi da clienti in ordine di scadenza" testId="dash-scadenze"
      action={<Link to="/scadenzario" className="text-xs font-semibold text-blue-700 hover:underline">Scadenzario</Link>}>
      <div className="-mx-5 max-h-72 overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-slate-50"><tr><th className={`${TH} pl-5`}>Cliente</th><th className={TH}>Fattura</th><th className={`${TH} text-right`}>Importo</th><th className={`${TH} pr-5`}>Scadenza</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {!rows ? <tr><td colSpan={4} className="px-5 py-6 text-slate-500">Caricamento…</td></tr>
              : rows.length === 0 ? <tr><td colSpan={4} className="px-5 py-8 text-center text-slate-500" data-testid="dash-scadenze-empty">Nessuna scadenza aperta.</td></tr>
              : rows.slice(0, 20).map((r) => (
                <tr key={`${r.invoice_id}-${r.n}`} data-testid={`dash-scad-${r.invoice_id}-${r.n}`}>
                  <td className="px-3 py-2.5 pl-5"><span className="flex items-center gap-2"><span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-100"><User className="h-3.5 w-3.5 text-slate-500" /></span><span className="min-w-0 truncate font-medium text-slate-900">{r.cliente}</span></span></td>
                  <td className="px-3 py-2.5"><Link to={`/fatture/${r.invoice_id}`} className="mono text-xs text-slate-600 hover:underline">{r.numero_display}</Link></td>
                  <td className="px-3 py-2.5 text-right font-semibold tabular-nums">{fmtEUR(r.residuo)}</td>
                  <td className={`px-3 py-2.5 pr-5 tabular-nums ${r.scadenza < oggi ? "font-semibold text-rose-700" : "text-slate-700"}`}>{fmtDate(r.scadenza)}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </DCard>
  );
};

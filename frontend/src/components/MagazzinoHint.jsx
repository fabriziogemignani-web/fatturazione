import { AlertTriangle, PackageOpen } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";

const fmt = (n) => Number(n || 0).toLocaleString("it-IT", { maximumFractionDigits: 3 });

const qtyBy = (lines, arts) => lines.reduce((m, l) => (arts[l.article_id] ? { ...m, [l.article_id]: (m[l.article_id] || 0) + Math.abs(Number(l.quantita) || 0) } : m), {});

export const MagazzinoHint = ({ form, inv, articles, isNC, locked, set }) => {
  const arts = Object.fromEntries(articles.filter((a) => a.gestione_magazzino).map((a) => [a.id, a]));
  const req = qtyBy(form.lines, arts);
  if (locked || !Object.keys(req).length) return null;
  if (isNC) {
    return (
      <label className="mt-3 flex cursor-pointer items-start gap-2.5 rounded-lg border border-sky-200 bg-sky-50 px-3 py-2.5 text-sm text-sky-900" data-testid="reso-merce-box">
        <Checkbox checked={!!form.reso_merce} onCheckedChange={(v) => set("reso_merce", !!v)} className="mt-0.5" data-testid="reso-merce-checkbox" />
        <span><PackageOpen className="mr-1 inline h-4 w-4" /><b>Reso di merce</b>: la merce torna in magazzino e le quantità degli articoli vengono ricaricate. Lascia vuoto per note di credito di solo importo (sconti, abbuoni, errori di prezzo).</span>
      </label>
    );
  }
  if (inv?.ddt_rif || inv?.accompagnatoria_ddt_id) return null;
  const gia = inv && !["TD04"].includes(inv.tipo_documento) ? qtyBy(inv.lines || [], arts) : {};
  const short = Object.entries(req).map(([aid, q]) => ({ a: arts[aid], q, g: (arts[aid].giacenza || 0) + (gia[aid] || 0) })).filter((x) => x.q > x.g);
  if (!short.length) return null;
  return (
    <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2.5 text-sm text-amber-900" data-testid="giacenza-warning">
      <p className="flex items-center gap-1.5 font-medium"><AlertTriangle className="h-4 w-4" />Merce non sufficiente in magazzino</p>
      <ul className="mt-1 space-y-0.5 text-xs">
        {short.map(({ a, q, g }) => <li key={a.id} data-testid={`giacenza-warning-${a.codice}`}>{a.codice} · {a.descrizione}: richiesti {fmt(q)}, in giacenza {fmt(g)} {a.unita_misura || ""}</li>)}
      </ul>
      <p className="mt-1 text-xs">Puoi salvare comunque: la giacenza andrà sotto zero finché non registri il carico.</p>
    </div>
  );
};

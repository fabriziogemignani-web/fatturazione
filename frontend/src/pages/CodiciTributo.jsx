import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Search } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { PageHeader } from "@/components/Common";
import { Input } from "@/components/ui/input";

export default function CodiciTributo() {
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const [d, setD] = useState(null);
  useEffect(() => {
    const h = setTimeout(() => api.get("/codici-tributo", { params: { q: q || undefined, categoria: cat || undefined } }).then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e))), 200);
    return () => clearTimeout(h);
  }, [q, cat]);
  return (
    <div>
      <PageHeader eyebrow="Fisco e IVA" title="Codici tributo F24" />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-sm"><Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cerca codice o descrizione" className="bg-white pl-9" data-testid="ct-search" /></div>
        <select value={cat} onChange={(e) => setCat(e.target.value)} className="h-9 rounded-md border border-slate-200 bg-white px-2 text-sm" data-testid="ct-categoria">
          <option value="">Tutte le categorie</option>{Object.entries(d?.categorie || {}).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
      </div>
      <p className="mb-3 text-xs text-slate-500">Principali codici tributo della sezione Erario dell'F24 usati dal programma (ritenute, IVA, bollo, imposte dirette). L'elenco completo è pubblicato dall'Agenzia delle Entrate.</p>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm" data-testid="ct-table">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500"><tr><th className="px-4 py-3 font-medium">Codice</th><th className="px-4 py-3 font-medium">Descrizione</th><th className="px-4 py-3 font-medium">Categoria</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {d?.codici.length === 0 && <tr><td colSpan={3} className="px-4 py-8 text-center text-slate-500" data-testid="ct-empty">Nessun codice trovato</td></tr>}
            {d?.codici.map((c) => (
              <tr key={c.codice} data-testid={`ct-row-${c.codice}`}><td className="mono px-4 py-2.5 font-semibold">{c.codice}</td><td className="px-4 py-2.5">{c.descrizione}</td><td className="px-4 py-2.5 text-xs text-slate-500">{c.categoria_label}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

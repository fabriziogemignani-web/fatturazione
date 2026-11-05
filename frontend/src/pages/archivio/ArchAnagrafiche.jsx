import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Search, ArrowUpDown } from "lucide-react";
import { api } from "@/lib/api";
import { fmtEUR } from "@/lib/fe";
import { PageHeader } from "@/components/Common";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const RUOLI = [["cliente", "Clienti"], ["fornitore", "Fornitori"]];
const COLS = [["denominazione", "Ragione sociale"], ["n_fatture", "Documenti"], ["totale_fatture", "Importo"]];

export default function ArchAnagrafiche() {
  const [ruolo, setRuolo] = useState("cliente");
  const [q, setQ] = useState("");
  const [anno, setAnno] = useState("all");
  const [anni, setAnni] = useState([]);
  const [rows, setRows] = useState(null);
  const [sort, setSort] = useState(["denominazione", 1]);
  useEffect(() => { api.get("/archivio/years").then(({ data }) => setAnni(data)); }, []);
  useEffect(() => {
    const h = setTimeout(() => { api.get("/archivio/anagrafiche", { params: { ruolo, q: q || undefined, anno: anno === "all" ? undefined : anno } }).then(({ data }) => setRows(data)); }, 250);
    return () => clearTimeout(h);
  }, [ruolo, q, anno]);
  const sorted = useMemo(() => [...(rows || [])].sort((a, b) => {
    const [k, dir] = sort;
    return dir * (typeof a[k] === "number" ? a[k] - b[k] : String(a[k] || "").localeCompare(String(b[k] || "")));
  }), [rows, sort]);
  const tot = (rows || []).reduce((s, r) => [s[0] + r.n_fatture, s[1] + r.totale_fatture], [0, 0]);

  return (
    <div>
      <PageHeader eyebrow="Archivio fatture" title="Anagrafiche archivio" />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="inline-flex rounded-lg border border-slate-200 bg-white p-1 text-xs font-semibold">
          {RUOLI.map(([k, l]) => <button key={k} onClick={() => setRuolo(k)} className={`rounded-md px-3 py-1.5 ${ruolo === k ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-50"}`} data-testid={`arch-ruolo-${k}`}>{l}</button>)}
        </div>
        <div className="relative"><Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" /><Input className="w-64 bg-white pl-9" placeholder="Nome, P.IVA, comune…" value={q} onChange={(e) => setQ(e.target.value)} data-testid="arch-anag-search" /></div>
        <Select value={String(anno)} onValueChange={setAnno}>
          <SelectTrigger className="w-36 bg-white" data-testid="arch-anag-year-select"><SelectValue /></SelectTrigger>
          <SelectContent className="bg-white"><SelectItem value="all">Tutti gli anni</SelectItem>{anni.map((y) => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}</SelectContent>
        </Select>
        <span className="ml-auto text-xs text-slate-600" data-testid="arch-anag-summary">{rows?.length || 0} anagrafiche · {tot[0]} documenti · <b>{fmtEUR(tot[1])}</b></span>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200/80 bg-white shadow-sm">
        <table className="w-full text-sm" data-testid="arch-anag-table">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr>{COLS.map(([k, l], i) => <th key={k} className={`px-4 py-3 font-medium ${i ? "text-right" : ""}`}><button className="inline-flex items-center gap-1 uppercase hover:text-slate-900" onClick={() => setSort([k, sort[0] === k ? -sort[1] : 1])} data-testid={`arch-anag-sort-${k}`}>{l}<ArrowUpDown className="h-3 w-3" /></button></th>)}<th className="px-4 py-3 font-medium">P.IVA / CF</th><th className="px-4 py-3 font-medium">Comune</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows && rows.length === 0 && <tr><td colSpan={5} className="px-4 py-10 text-center text-slate-500" data-testid="arch-anag-empty">Nessuna anagrafica</td></tr>}
            {sorted.map((a) => (
              <tr key={a.id} className="hover:bg-slate-50" data-testid={`arch-anag-row-${a.id}`}>
                <td className="px-4 py-2.5 font-semibold"><Link to={`/archivio/anagrafiche/${a.id}`} className="text-blue-700 hover:underline">{a.denominazione || a.chiave}</Link></td>
                <td className="px-4 py-2.5 text-right">{a.n_fatture}</td><td className="px-4 py-2.5 text-right">{fmtEUR(a.totale_fatture)}</td>
                <td className="mono px-4 py-2.5 text-xs">{a.chiave}</td><td className="px-4 py-2.5">{a.comune}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

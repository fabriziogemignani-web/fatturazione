import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Plus, Printer } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { openPdf } from "@/pages/DdtEditor";

const STATI = { bozza: ["Bozza", "bg-slate-200 text-slate-800"], confermato: ["Confermato", "bg-blue-100 text-blue-800"], fatturato: ["Fatturato", "bg-emerald-100 text-emerald-800"], annullato: ["Annullato", "bg-rose-100 text-rose-700"] };

export const DdtStato = ({ d }) => {
  const [l, c] = STATI[d.status] || [d.status, ""];
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${c}`} data-testid={`ddt-stato-${d.id}`}>{l}</span>;
};

export default function Ddt() {
  const nav = useNavigate();
  const [rows, setRows] = useState([]);
  const [stato, setStato] = useState("");
  const [q, setQ] = useState("");
  useEffect(() => { api.get("/ddt", { params: stato ? { stato } : {} }).then(({ data }) => setRows(data)).catch((e) => toast.error(errMsg(e))); }, [stato]);
  const list = useMemo(() => rows.filter((r) => `${r.numero_display || ""} ${r.cliente?.denominazione || ""}`.toLowerCase().includes(q.toLowerCase())), [rows, q]);
  return (
    <div>
      <PageHeader eyebrow="Vendite" title="Documenti di trasporto">
        <Button onClick={() => nav("/ddt/nuovo")} data-testid="ddt-new-btn"><Plus className="mr-2 h-4 w-4" />Nuovo DDT</Button>
      </PageHeader>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cerca numero o cliente" className="w-64 bg-white" data-testid="ddt-search-input" />
        {[["", "Tutti"], ...Object.entries(STATI).map(([k, [l]]) => [k, l])].map(([k, l]) => (
          <button key={k || "all"} onClick={() => setStato(k)} className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${stato === k ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`} data-testid={`ddt-filter-${k || "tutti"}`}>{l}</button>
        ))}
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr><th className="px-4 py-2 font-medium">Numero</th><th className="px-4 py-2 font-medium">Data</th><th className="px-4 py-2 font-medium">Cliente</th><th className="px-4 py-2 font-medium">Causale</th><th className="px-4 py-2 text-right font-medium">Imponibile</th><th className="px-4 py-2 font-medium">Stato</th><th className="px-4 py-2 font-medium">Fattura</th><th /></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {list.map((r) => (
              <tr key={r.id} className="cursor-pointer hover:bg-slate-50" onClick={() => nav(`/ddt/${r.id}`)} data-testid={`ddt-row-${r.id}`}>
                <td className="px-4 py-2 font-semibold text-slate-900">{r.numero_display || "—"}</td>
                <td className="px-4 py-2 text-slate-600">{fmtDate(r.data)}</td>
                <td className="px-4 py-2 text-slate-800">{r.cliente?.denominazione}</td>
                <td className="px-4 py-2 text-slate-600">{r.causale}</td>
                <td className="px-4 py-2 text-right tabular-nums">{fmtEUR(r.imponibile)}</td>
                <td className="px-4 py-2"><DdtStato d={r} /></td>
                <td className="px-4 py-2" onClick={(e) => e.stopPropagation()}>{r.invoice_id ? <Link className="text-blue-700 hover:underline" to={`/fatture/${r.invoice_id}`}>{r.invoice_numero}</Link> : ""}</td>
                <td className="px-4 py-2" onClick={(e) => e.stopPropagation()}><button title="Stampa" onClick={() => openPdf(`/ddt/${r.id}/pdf`)} className="rounded p-1.5 text-slate-500 hover:bg-slate-100" data-testid={`ddt-row-pdf-${r.id}`}><Printer className="h-4 w-4" /></button></td>
              </tr>
            ))}
            {list.length === 0 && <tr><td colSpan={8} className="px-4 py-10 text-center text-slate-500" data-testid="ddt-empty">Nessun DDT</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

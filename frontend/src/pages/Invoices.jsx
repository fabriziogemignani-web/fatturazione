import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Plus, Search, Download, Zap } from "lucide-react";
import { api } from "@/lib/api";
import { fmtEUR, fmtDate, STATUS } from "@/lib/fe";
import { PageHeader, StatusBadge } from "@/components/Common";
import { downloadXml } from "@/components/XmlDialog";
import { QuickStornoDialog } from "@/components/QuickStornoDialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const FILTERS = [["", "Tutte"], ...Object.entries(STATUS).map(([k, v]) => [k, v.label])];
const SENT = ["inviata", "consegnata", "mancata_consegna"];

export default function Invoices() {
  const [items, setItems] = useState([]);
  const [params, setParams] = useSearchParams();
  const status = params.get("status") || "";
  const setStatus = (s) => setParams(s ? { status: s } : {});
  const [q, setQ] = useState("");
  const [tipo, setTipo] = useState("");
  const navigate = useNavigate();
  const [storno, setStorno] = useState(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    api.get("/invoices", { params: status ? { status } : {} }).then(({ data }) => setItems(data));
  }, [status, reload]);

  const shown = useMemo(() => {
    const s = q.toLowerCase();
    return items.filter((i) => (!tipo || (tipo === "nc" ? i.tipo_documento === "TD04" : i.tipo_documento !== "TD04")) && (!s || i.cliente?.denominazione?.toLowerCase().includes(s) || i.numero_display.toLowerCase().includes(s)));
  }, [items, q, tipo]);

  return (
    <div>
      <PageHeader eyebrow="Ciclo attivo" title="Fatture e note di credito">
        <Button asChild variant="outline" data-testid="create-credit-note-list-btn"><Link to="/fatture/nuova?tipo=TD04"><Plus className="mr-2 h-4 w-4" />Nuova nota di credito</Link></Button>
        <Button asChild data-testid="create-invoice-btn"><Link to="/fatture/nuova"><Plus className="mr-2 h-4 w-4" />Nuova fattura</Link></Button>
      </PageHeader>
      <div className="mb-3 inline-flex rounded-lg border border-slate-200 bg-white p-1 text-xs font-semibold">
        {[["", "Tutti i documenti"], ["fatture", "Fatture"], ["nc", "Note di credito"]].map(([k, l]) => (
          <button key={k || "all"} onClick={() => setTipo(k)} data-testid={`filter-tipo-${k || "all"}`}
            className={`rounded-md px-3 py-1.5 transition-colors ${tipo === k ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-50"}`}>{l}</button>
        ))}
      </div>
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap gap-2">
          {FILTERS.map(([k, label]) => (
            <button
              key={k || "all"}
              data-testid={`filter-status-${k || "all"}`}
              onClick={() => setStatus(k)}
              className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${status === k ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 bg-white text-slate-600 hover:border-slate-400"}`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="relative sm:w-72">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input data-testid="invoice-search-input" className="bg-white pl-9" placeholder="Cerca cliente o numero" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm" data-testid="invoices-table">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr>
              <th className="px-4 py-3 font-medium">Numero</th>
              <th className="px-4 py-3 font-medium">Data</th>
              <th className="px-4 py-3 font-medium">Cliente</th>
              <th className="px-4 py-3 text-right font-medium">Totale</th>
              <th className="px-4 py-3 font-medium">Stato SDI</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {shown.map((i) => (
              <tr key={i.id} className="cursor-pointer transition-colors hover:bg-slate-50" onClick={() => navigate(`/fatture/${i.id}`)} data-testid={`invoice-row-${i.id}`}>
                <td className="mono px-4 py-3 font-medium text-slate-900">{i.numero_display}<span className={`ml-2 text-[10px] ${i.tipo_documento === "TD04" ? "rounded bg-violet-100 px-1.5 py-0.5 font-semibold text-violet-700" : "text-slate-400"}`}>{i.tipo_documento === "TD04" ? "NC" : i.tipo_documento}</span></td>
                <td className="px-4 py-3 text-slate-600">{fmtDate(i.data)}</td>
                <td className="px-4 py-3 font-medium text-slate-800">{i.cliente?.denominazione}</td>
                <td className={`px-4 py-3 text-right font-semibold ${i.tipo_documento === "TD04" ? "text-violet-700" : "text-slate-900"}`}>{i.tipo_documento === "TD04" ? `- ${fmtEUR(i.totale)}` : fmtEUR(i.totale)}</td>
                <td className="px-4 py-3"><StatusBadge status={i.status} testId={`invoice-status-${i.id}`} /></td>
                <td className="whitespace-nowrap px-4 py-3 text-right">
                  {i.tipo_documento !== "TD04" && SENT.includes(i.status) && !i.has_nc && (
                    <button data-testid={`invoice-quick-storno-${i.id}`} title="Storno totale" onClick={(e) => { e.stopPropagation(); setStorno(i); }} className="rounded-md p-1.5 text-violet-500 hover:bg-violet-50 hover:text-violet-700">
                      <Zap className="h-4 w-4" />
                    </button>
                  )}
                  {i.has_nc && <span className="mr-1 rounded bg-violet-50 px-1.5 py-0.5 text-[10px] font-semibold text-violet-600" data-testid={`invoice-stornata-${i.id}`}>stornata</span>}
                  <button data-testid={`invoice-download-xml-${i.id}`} title="Scarica XML" onClick={(e) => { e.stopPropagation(); downloadXml(i.id); }} className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-900">
                    <Download className="h-4 w-4" />
                  </button>
                </td>
              </tr>
            ))}
            {shown.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-12 text-center text-slate-500" data-testid="invoices-empty">Nessun documento trovato</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <QuickStornoDialog inv={storno} onOpenChange={(o) => { if (!o) setStorno(null); }} onDone={(nc) => { setReload((r) => r + 1); navigate(`/fatture/${nc.id}`); }} />
    </div>
  );
}

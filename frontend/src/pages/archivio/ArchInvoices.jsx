import { useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { Download, ArrowUp, ArrowDown, Search } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { DocBadge, TD_LABEL, downloadBlob } from "@/lib/archivio";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const LIMIT = 50;

const Filters = ({ tipo, f, setF }) => {
  const [anni, setAnni] = useState([]);
  const [docs, setDocs] = useState([]);
  useEffect(() => { api.get("/archivio/years", { params: { tipo } }).then(({ data }) => setAnni(data)); }, [tipo]);
  useEffect(() => { api.get("/archivio/doc-types", { params: { tipo, anno: f.anno === "all" ? undefined : f.anno } }).then(({ data }) => setDocs(data)); }, [tipo, f.anno]);
  return (
    <div className="mb-4 flex flex-wrap items-center gap-3">
      <div className="relative"><Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
        <Input className="w-72 bg-white pl-9" placeholder="Numero, cliente/fornitore, P.IVA, descrizione…" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value, page: 1 })} data-testid="arch-search-input" /></div>
      <Select value={String(f.anno)} onValueChange={(v) => setF({ ...f, anno: v, page: 1, td: "all" })}>
        <SelectTrigger className="w-36 bg-white" data-testid="arch-year-select"><SelectValue /></SelectTrigger>
        <SelectContent className="bg-white"><SelectItem value="all">Tutti gli anni</SelectItem>{anni.map((y) => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}</SelectContent>
      </Select>
      <Select value={f.td} onValueChange={(v) => setF({ ...f, td: v, page: 1 })}>
        <SelectTrigger className="w-56 bg-white" data-testid="arch-doctype-select"><SelectValue /></SelectTrigger>
        <SelectContent className="bg-white"><SelectItem value="all">Tutti i tipi documento</SelectItem>{docs.map((d) => <SelectItem key={d.code} value={d.code}>{d.code} · {TD_LABEL[d.code] || ""} ({d.n})</SelectItem>)}</SelectContent>
      </Select>
    </div>
  );
};

export default function ArchInvoices() {
  const { tipo } = useParams();
  const [f, setF] = useState({ q: "", anno: "all", td: "all", order: "asc", page: 1 });
  const [d, setD] = useState(null);
  const params = { tipo, q: f.q || undefined, anno: f.anno === "all" ? undefined : f.anno, tipo_documento: f.td === "all" ? undefined : f.td, order: f.order };
  const key = JSON.stringify(params) + f.page;
  useEffect(() => { setF((x) => ({ ...x, q: "", anno: "all", td: "all", page: 1 })); }, [tipo]);
  useEffect(() => {
    const h = setTimeout(() => { api.get("/archivio/invoices", { params: { ...params, page: f.page, limit: LIMIT } }).then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e))); }, 250);
    return () => clearTimeout(h);
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  const pages = d ? Math.max(1, Math.ceil(d.total / LIMIT)) : 1;
  const exportCsv = () => downloadBlob("/archivio/export", params, "archivio.csv").catch((e) => toast.error(errMsg(e)));
  if (!["attiva", "passiva"].includes(tipo)) return <Navigate to="/archivio" replace />;

  return (
    <div>
      <PageHeader eyebrow="Archivio fatture" title={tipo === "attiva" ? "Fatture attive" : "Fatture passive"}>
        <Button variant="outline" onClick={exportCsv} data-testid="arch-export-btn"><Download className="mr-2 h-4 w-4" />Esporta CSV</Button>
      </PageHeader>
      <Filters tipo={tipo} f={f} setF={setF} />
      <div className="overflow-x-auto rounded-xl border border-slate-200/80 bg-white shadow-sm">
        <table className="w-full text-sm" data-testid="arch-invoices-table">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr>
              <th className="px-4 py-3 font-medium">Anno</th>
              <th className="px-4 py-3 font-medium"><button className="inline-flex items-center gap-1 uppercase hover:text-slate-900" onClick={() => setF({ ...f, order: f.order === "asc" ? "desc" : "asc" })} data-testid="arch-sort-btn">Protocollo {f.order === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />}</button></th>
              <th className="px-4 py-3 font-medium">Data</th><th className="px-4 py-3 font-medium">Tipo doc.</th>
              <th className="px-4 py-3 font-medium">{tipo === "attiva" ? "Cliente" : "Fornitore"}</th>
              <th className="px-4 py-3 text-right font-medium">Imponibile</th><th className="px-4 py-3 text-right font-medium">IVA</th><th className="px-4 py-3 text-right font-medium">Totale</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {d && d.items.length === 0 && <tr><td colSpan={8} className="px-4 py-10 text-center text-slate-500" data-testid="arch-empty">Nessuna fattura. <Link to="/archivio/carica" className="font-semibold text-blue-600">Carica fatture</Link></td></tr>}
            {d?.items.map((r) => (
              <tr key={r.id} className="hover:bg-slate-50" data-testid={`arch-row-${r.id}`}>
                <td className="px-4 py-2.5 text-slate-500">{r.anno}</td>
                <td className="px-4 py-2.5 font-semibold"><Link to={`/archivio/fatture/${r.id}`} className="text-blue-700 hover:underline">{r.numero}</Link></td>
                <td className="px-4 py-2.5">{fmtDate(r.data)}</td>
                <td className="px-4 py-2.5"><DocBadge code={r.tipo_documento} /></td>
                <td className="px-4 py-2.5"><Link to={`/archivio/anagrafiche/${r.controparte_id}`} className="hover:underline">{r.controparte_nome}</Link><div className="mono text-[11px] text-slate-500">{r.controparte_piva}</div></td>
                <td className="px-4 py-2.5 text-right">{fmtEUR(r.imponibile)}</td><td className="px-4 py-2.5 text-right">{fmtEUR(r.imposta)}</td>
                <td className="px-4 py-2.5 text-right font-semibold">{fmtEUR(r.totale)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {d && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-slate-600">
          <span data-testid="arch-total">{d.total} fatture · totale <b>{fmtEUR(d.somma_totale)}</b></span>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" disabled={f.page <= 1} onClick={() => setF({ ...f, page: f.page - 1 })} data-testid="arch-prev-btn">Precedente</Button>
            <span data-testid="arch-page">Pagina {f.page} di {pages}</span>
            <Button size="sm" variant="outline" disabled={f.page >= pages} onClick={() => setF({ ...f, page: f.page + 1 })} data-testid="arch-next-btn">Successiva</Button>
          </div>
        </div>
      )}
    </div>
  );
}

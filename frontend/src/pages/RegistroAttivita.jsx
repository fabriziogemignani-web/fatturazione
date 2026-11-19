import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Search, ChevronLeft, ChevronRight } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { PageHeader } from "@/components/Common";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { NSelect } from "@/components/ui/nselect";

const TONO = { POST: "bg-blue-100 text-blue-800", PUT: "bg-amber-100 text-amber-800", PATCH: "bg-amber-100 text-amber-800", DELETE: "bg-rose-100 text-rose-800" };
const quando = (s) => new Date(s).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "medium" });

const Riga = ({ r }) => {
  const [open, setOpen] = useState(false);
  return (
    <>
      <tr className="cursor-pointer hover:bg-slate-50" onClick={() => setOpen(!open)} data-testid={`audit-row-${r.id}`}>
        <td className="mono whitespace-nowrap px-4 py-2.5 text-xs text-slate-600">{quando(r.at)}</td>
        <td className="px-4 py-2.5 text-sm text-slate-800">{r.utente}</td>
        <td className="px-4 py-2.5"><span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${TONO[r.method] || "bg-slate-100"}`}>{r.azione}</span></td>
        <td className="px-4 py-2.5 text-sm text-slate-700">{r.area}</td>
        <td className="mono px-4 py-2.5 text-xs text-slate-500">{r.path}</td>
      </tr>
      {open && (
        <tr className="bg-slate-50" data-testid={`audit-detail-${r.id}`}>
          <td colSpan={5} className="px-4 py-3">
            <div className="mb-1 text-xs text-slate-500">IP {r.ip || "—"} · esito {r.esito} · {r.email}</div>
            <pre className="max-h-72 overflow-auto rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-700">{r.dati ? JSON.stringify(r.dati, null, 2) : "Nessun dato inviato"}</pre>
          </td>
        </tr>
      )}
    </>
  );
};

export default function RegistroAttivita() {
  const [f, setF] = useState({ dal: "", al: "", utente: "", area: "", q: "" });
  const [pagina, setPagina] = useState(1);
  const [data, setData] = useState(null);

  const load = useCallback(() => {
    const params = Object.fromEntries(Object.entries({ ...f, pagina }).filter(([, v]) => v));
    api.get("/registro-attivita", { params }).then(({ data: d }) => setData(d)).catch((e) => toast.error(errMsg(e)));
  }, [f, pagina]);
  useEffect(() => { load(); }, [load]);
  const set = (k) => (e) => { setPagina(1); setF({ ...f, [k]: e.target.value }); };

  return (
    <div>
      <PageHeader eyebrow="Sicurezza" title="Registro attività" />
      <p className="mb-4 max-w-3xl text-sm text-slate-600">Ogni creazione, modifica, invio, registrazione ed eliminazione fatta in questa azienda, con chi l'ha fatta e quando. Il registro non si può modificare né cancellare. Password e chiavi non vengono mai salvate.</p>
      <div className="mb-4 grid grid-cols-1 gap-2 sm:grid-cols-5">
        <Input type="date" value={f.dal} onChange={set("dal")} className="bg-white" data-testid="audit-dal" />
        <Input type="date" value={f.al} onChange={set("al")} className="bg-white" data-testid="audit-al" />
        <NSelect value={f.utente} onChange={set("utente")} className="h-9 rounded-md border border-slate-200 bg-white px-2 text-sm" data-testid="audit-utente">
          <option value="">Tutti gli utenti</option>
          {(data?.utenti || []).map((u) => <option key={u.id} value={u.id}>{u.nome}</option>)}
        </NSelect>
        <NSelect value={f.area} onChange={set("area")} className="h-9 rounded-md border border-slate-200 bg-white px-2 text-sm" data-testid="audit-area">
          <option value="">Tutte le aree</option>
          {(data?.aree || []).map((a) => <option key={a} value={a}>{a}</option>)}
        </NSelect>
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
          <Input value={f.q} onChange={set("q")} placeholder="Cerca percorso, utente, id" className="bg-white pl-8" data-testid="audit-search" />
        </div>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm" data-testid="audit-table">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr><th className="px-4 py-3 font-medium">Quando</th><th className="px-4 py-3 font-medium">Utente</th><th className="px-4 py-3 font-medium">Azione</th><th className="px-4 py-3 font-medium">Area</th><th className="px-4 py-3 font-medium">Dettaglio</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data?.righe.map((r) => <Riga key={r.id} r={r} />)}
            {data && !data.righe.length && <tr><td colSpan={5} className="px-4 py-8 text-center text-sm text-slate-500" data-testid="audit-empty">Nessuna attività registrata</td></tr>}
          </tbody>
        </table>
      </div>
      {data && (
        <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
          <span data-testid="audit-total">{data.totale} attività</span>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" disabled={pagina <= 1} onClick={() => setPagina(pagina - 1)} data-testid="audit-prev"><ChevronLeft className="h-4 w-4" /></Button>
            <span>Pagina {data.pagina} di {data.pagine}</span>
            <Button size="sm" variant="outline" disabled={pagina >= data.pagine} onClick={() => setPagina(pagina + 1)} data-testid="audit-next"><ChevronRight className="h-4 w-4" /></Button>
          </div>
        </div>
      )}
    </div>
  );
}

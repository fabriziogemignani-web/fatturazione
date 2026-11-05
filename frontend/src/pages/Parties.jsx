import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Plus, Pencil, Trash2, FileText, AlertTriangle } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { PageHeader } from "@/components/Common";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { PartyDialog } from "@/components/PartyDialog";
import { downloadEstratto } from "@/components/SollecitoDialog";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCompany } from "@/context/CompanyContext";
import { mods } from "@/lib/moduli";

export default function Parties() {
  const attive = mods(useCompany().company).fatture_attive;
  const [tipo, setTipo] = useState("cliente");
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [saldi, setSaldi] = useState({});
  const [late, setLate] = useState(false);

  const load = () => {
    api.get("/parties", { params: { tipo } }).then(({ data }) => setItems(data));
    if (tipo === "cliente" && attive) api.get("/scadenzario").then(({ data }) => setSaldi(Object.fromEntries(data.clienti.map((c) => [c.party_id, c])))).catch(() => setSaldi({}));
  };
  useEffect(() => { load(); }, [tipo]); // eslint-disable-line react-hooks/exhaustive-deps
  const isCli = tipo === "cliente";
  const nLate = items.filter((p) => saldi[p.id]?.scaduto > 0).length;
  const shown = isCli && late ? items.filter((p) => saldi[p.id]?.scaduto > 0) : items;

  const remove = async (p) => {
    if (!window.confirm(`Eliminare ${p.denominazione}?`)) return;
    try { await api.delete(`/parties/${p.id}`); toast.success("Eliminato"); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };

  return (
    <div>
      <PageHeader eyebrow="Anagrafica" title="Clienti e fornitori">
        <Button onClick={() => { setEditing(null); setOpen(true); }} data-testid="new-party-btn"><Plus className="mr-2 h-4 w-4" />Nuovo {tipo}</Button>
      </PageHeader>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
      <Tabs value={tipo} onValueChange={setTipo}>
        <TabsList className="bg-white border border-slate-200">
          <TabsTrigger value="cliente" data-testid="tab-clienti">Clienti</TabsTrigger>
          <TabsTrigger value="fornitore" data-testid="tab-fornitori">Fornitori</TabsTrigger>
        </TabsList>
      </Tabs>
      {isCli && nLate > 0 && (
        <button onClick={() => setLate(!late)} data-testid="parties-late-filter"
          className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${late ? "border-rose-600 bg-rose-600 text-white" : "border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100"}`}>
          <AlertTriangle className="h-3.5 w-3.5" />{nLate} {nLate === 1 ? "cliente in ritardo" : "clienti in ritardo"}{late ? " · mostra tutti" : ""}
        </button>
      )}
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm" data-testid="parties-table">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr><th className="px-4 py-3 font-medium">Denominazione</th><th className="px-4 py-3 font-medium">P.IVA / C.F.</th><th className="px-4 py-3 font-medium">Cod. SDI</th><th className="px-4 py-3 font-medium">PEC</th><th className="px-4 py-3 font-medium">Comune</th>{isCli && <><th className="px-4 py-3 text-right font-medium">Saldo aperto</th><th className="px-4 py-3 text-right font-medium">Scaduto</th></>}<th className="px-4 py-3" /></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {shown.map((p) => {
              const s = saldi[p.id];
              const ritardo = isCli && s?.scaduto > 0;
              return (
              <tr key={p.id} className={ritardo ? "bg-rose-50/60 hover:bg-rose-50" : "hover:bg-slate-50"} data-testid={`party-row-${p.id}`}>
                <td className={`px-4 py-3 font-semibold text-slate-900 ${ritardo ? "border-l-4 border-rose-500" : ""}`}>{p.denominazione}{p.pubblica_amministrazione && <span className="ml-2 rounded bg-sky-100 px-1.5 py-0.5 text-[10px] font-semibold text-sky-800" data-testid={`party-pa-badge-${p.id}`}>PA</span>}
                  {ritardo && <span className="ml-2 inline-flex items-center gap-1 rounded bg-rose-100 px-1.5 py-0.5 text-[10px] font-semibold text-rose-800" data-testid={`party-late-badge-${p.id}`}><AlertTriangle className="h-3 w-3" />In ritardo · {s.rate_scadute} {s.rate_scadute === 1 ? "rata" : "rate"}</span>}
                  {isCli && s?.aperto > 0 && <div className="mt-1 text-xs font-normal text-slate-600 md:hidden" data-testid={`party-saldo-mobile-${p.id}`}>Aperto {fmtEUR(s.aperto)}{ritardo && <span className="font-semibold text-rose-700"> · scaduto {fmtEUR(s.scaduto)}</span>}</div>}
                </td>
                <td className="mono px-4 py-3 text-xs text-slate-600">{p.partita_iva || p.codice_fiscale || "—"}</td>
                <td className="px-4 py-3"><span className="mono rounded-md border border-slate-200 bg-slate-100 px-2 py-0.5 text-xs">{p.codice_destinatario}</span></td>
                <td className="px-4 py-3 text-slate-600">{p.pec || "—"}</td>
                <td className="px-4 py-3 text-slate-600">{p.comune} {p.provincia && `(${p.provincia})`}</td>
                {isCli && <>
                  <td className="whitespace-nowrap px-4 py-3 text-right" data-testid={`party-saldo-${p.id}`}>
                    {s?.aperto ? <Link to={`/scadenzario?cliente=${p.id}`} className="font-semibold text-slate-900 hover:text-blue-700 hover:underline">{fmtEUR(s.aperto)}</Link> : <span className="text-slate-400">—</span>}
                    {s?.prossima && <div className="text-[11px] text-slate-500">prossima {fmtDate(s.prossima)}</div>}
                    {s?.crediti > 0 && <div className="text-[11px] text-violet-700">crediti NC {fmtEUR(s.crediti)}</div>}
                  </td>
                  <td className={`whitespace-nowrap px-4 py-3 text-right font-bold ${ritardo ? "text-rose-700" : "text-slate-400"}`} data-testid={`party-scaduto-${p.id}`}>{ritardo ? fmtEUR(s.scaduto) : "—"}</td>
                </>}
                <td className="whitespace-nowrap px-4 py-3 text-right">
                  {tipo === "cliente" && attive && <button onClick={() => downloadEstratto(p.id, p.denominazione)} title="Estratto conto PDF" className="rounded p-1.5 text-slate-500 hover:bg-blue-50 hover:text-blue-700" data-testid={`party-estratto-${p.id}`}><FileText className="h-4 w-4" /></button>}
                  <button onClick={() => { setEditing(p); setOpen(true); }} className="rounded p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-900" data-testid={`party-edit-${p.id}`}><Pencil className="h-4 w-4" /></button>
                  <button onClick={() => remove(p)} className="rounded p-1.5 text-slate-500 hover:bg-rose-50 hover:text-rose-600" data-testid={`party-delete-${p.id}`}><Trash2 className="h-4 w-4" /></button>
                </td>
              </tr>
              );
            })}
            {shown.length === 0 && <tr><td colSpan={isCli ? 8 : 6} className="px-4 py-12 text-center text-slate-500" data-testid="parties-empty">Nessuna anagrafica</td></tr>}
          </tbody>
        </table>
      </div>
      <PartyDialog open={open} onOpenChange={setOpen} tipo={tipo} party={editing} onSaved={load} />
    </div>
  );
}

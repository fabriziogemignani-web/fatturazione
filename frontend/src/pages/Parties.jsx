import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Pencil, Trash2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { PageHeader } from "@/components/Common";
import { PartyDialog } from "@/components/PartyDialog";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default function Parties() {
  const [tipo, setTipo] = useState("cliente");
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);

  const load = () => api.get("/parties", { params: { tipo } }).then(({ data }) => setItems(data));
  useEffect(() => { load(); }, [tipo]); // eslint-disable-line react-hooks/exhaustive-deps

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
      <Tabs value={tipo} onValueChange={setTipo} className="mb-4">
        <TabsList className="bg-white border border-slate-200">
          <TabsTrigger value="cliente" data-testid="tab-clienti">Clienti</TabsTrigger>
          <TabsTrigger value="fornitore" data-testid="tab-fornitori">Fornitori</TabsTrigger>
        </TabsList>
      </Tabs>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm" data-testid="parties-table">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr><th className="px-4 py-3 font-medium">Denominazione</th><th className="px-4 py-3 font-medium">P.IVA / C.F.</th><th className="px-4 py-3 font-medium">Cod. SDI</th><th className="px-4 py-3 font-medium">PEC</th><th className="px-4 py-3 font-medium">Comune</th><th className="px-4 py-3" /></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items.map((p) => (
              <tr key={p.id} className="hover:bg-slate-50" data-testid={`party-row-${p.id}`}>
                <td className="px-4 py-3 font-semibold text-slate-900">{p.denominazione}</td>
                <td className="mono px-4 py-3 text-xs text-slate-600">{p.partita_iva || p.codice_fiscale || "—"}</td>
                <td className="px-4 py-3"><span className="mono rounded-md border border-slate-200 bg-slate-100 px-2 py-0.5 text-xs">{p.codice_destinatario}</span></td>
                <td className="px-4 py-3 text-slate-600">{p.pec || "—"}</td>
                <td className="px-4 py-3 text-slate-600">{p.comune} {p.provincia && `(${p.provincia})`}</td>
                <td className="whitespace-nowrap px-4 py-3 text-right">
                  <button onClick={() => { setEditing(p); setOpen(true); }} className="rounded p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-900" data-testid={`party-edit-${p.id}`}><Pencil className="h-4 w-4" /></button>
                  <button onClick={() => remove(p)} className="rounded p-1.5 text-slate-500 hover:bg-rose-50 hover:text-rose-600" data-testid={`party-delete-${p.id}`}><Trash2 className="h-4 w-4" /></button>
                </td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={6} className="px-4 py-12 text-center text-slate-500" data-testid="parties-empty">Nessuna anagrafica</td></tr>}
          </tbody>
        </table>
      </div>
      <PartyDialog open={open} onOpenChange={setOpen} tipo={tipo} party={editing} onSaved={load} />
    </div>
  );
}

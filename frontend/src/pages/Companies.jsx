import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Plus, Trash2, ArrowRight } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useCompany } from "@/context/CompanyContext";
import { PageHeader } from "@/components/Common";
import { CompanyDialog } from "@/components/CompanyDialog";
import { Button } from "@/components/ui/button";

export default function Companies() {
  const { companies, current, setCurrent, reload } = useCompany();
  const [users, setUsers] = useState([]);
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => { api.get("/users").then(({ data }) => setUsers(data)); }, []);
  const assigned = (cid) => users.filter((u) => (u.company_ids || []).includes(cid));

  const remove = async (c) => {
    if (!window.confirm(`Eliminare l'azienda ${c.denominazione}? Verranno eliminati anche clienti, fornitori e articoli.`)) return;
    try { await api.delete(`/companies/${c.id}`); toast.success("Azienda eliminata"); await reload(); }
    catch (e) { toast.error(errMsg(e)); }
  };

  const open_ = (c) => { setCurrent(c.id); navigate("/impostazioni"); };

  return (
    <div>
      <PageHeader eyebrow="Amministrazione" title="Aziende">
        <Button onClick={() => setOpen(true)} data-testid="new-company-btn"><Plus className="mr-2 h-4 w-4" />Nuova azienda</Button>
      </PageHeader>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3" data-testid="companies-grid">
        {(companies || []).map((c) => (
          <div key={c.id} className={`rounded-xl border bg-white p-6 shadow-sm transition-shadow hover:shadow-md ${c.id === current ? "border-blue-500 ring-1 ring-blue-500" : "border-slate-200"}`} data-testid={`company-card-${c.id}`}>
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate text-lg font-bold text-slate-900">{c.denominazione}</div>
                <div className="mono text-xs text-slate-500">P.IVA {c.partita_iva} · {c.comune}</div>
              </div>
              {c.id === current && <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-semibold uppercase text-blue-700">Attiva</span>}
            </div>
            <div className="mt-4 text-xs text-slate-600" data-testid={`company-users-${c.id}`}>
              <span className="font-semibold">Utenti assegnati:</span> {assigned(c.id).map((u) => u.name || u.email).join(", ") || "nessuno (solo admin)"}
            </div>
            <div className="mt-5 flex gap-2">
              <Button size="sm" variant="outline" onClick={() => open_(c)} data-testid={`company-open-${c.id}`}>Apri <ArrowRight className="ml-1 h-3.5 w-3.5" /></Button>
              <Button size="sm" variant="ghost" className="text-rose-600 hover:bg-rose-50" onClick={() => remove(c)} data-testid={`company-delete-${c.id}`}><Trash2 className="h-4 w-4" /></Button>
            </div>
          </div>
        ))}
      </div>
      <p className="mt-6 text-xs text-slate-500">Gli amministratori vedono tutte le aziende. Contabili e operatori vedono solo quelle assegnate in Gestione utenti.</p>
      <CompanyDialog open={open} onOpenChange={setOpen} onSaved={async (c) => { await reload(); setCurrent(c.id); navigate("/impostazioni"); }} />
    </div>
  );
}

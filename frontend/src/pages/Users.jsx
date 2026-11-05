import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Plus, Search, Pencil, Mail, Trash2, ToggleRight } from "lucide-react";
import { ModuliDialog } from "@/components/ModuliDialog";
import { modSummary } from "@/lib/moduli";
import { api, errMsg } from "@/lib/api";
import { ROLES, fmtDate } from "@/lib/fe";
import { PageHeader } from "@/components/Common";
import { UserDialog } from "@/components/UserDialog";
import { useCompany } from "@/context/CompanyContext";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const STAT = {
  approved: ["Approvato", "bg-emerald-100 text-emerald-800 border-emerald-300"],
  pending: ["In attesa", "bg-amber-100 text-amber-800 border-amber-300"],
  rejected: ["Rifiutato", "bg-rose-100 text-rose-800 border-rose-300"],
};

export default function Users() {
  const { user: me } = useAuth();
  const { companies } = useCompany();
  const cname = (id) => companies?.find((c) => c.id === id)?.denominazione;
  const [users, setUsers] = useState([]);
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("");
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [modU, setModU] = useState(null);
  const load = () => api.get("/users").then(({ data }) => setUsers(data));
  useEffect(() => { load(); }, []);

  const shown = useMemo(() => users.filter((u) => (!filter || u.status === filter) && (!q || `${u.name} ${u.email}`.toLowerCase().includes(q.toLowerCase()))), [users, q, filter]);
  const count = (s) => users.filter((u) => u.status === s).length;

  const sendReset = async (u) => {
    try { await api.post(`/users/${u.user_id}/send-reset`); toast.success(`Link password inviato a ${u.email}`); }
    catch (e) { toast.error(errMsg(e)); }
  };

  const remove = async (u) => {
    if (!window.confirm(`Eliminare definitivamente l'utente ${u.email}?`)) return;
    try { await api.delete(`/users/${u.user_id}`); toast.success("Utente eliminato"); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };

  const patch = async (u, body) => {
    try { await api.patch(`/users/${u.user_id}`, body); toast.success("Utente aggiornato"); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };

  return (
    <div>
      <PageHeader eyebrow="Amministrazione" title="Gestione utenti">
        <Button onClick={() => { setEditing(null); setOpen(true); }} data-testid="new-user-btn"><Plus className="mr-2 h-4 w-4" />Nuovo utente</Button>
      </PageHeader>
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap gap-2">
          {[["", `Tutti (${users.length})`], ["pending", `In attesa (${count("pending")})`], ["approved", `Approvati (${count("approved")})`], ["rejected", `Rifiutati (${count("rejected")})`]].map(([k, l]) => (
            <button key={k || "all"} onClick={() => setFilter(k)} data-testid={`users-filter-${k || "all"}`}
              className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${filter === k ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 bg-white text-slate-600 hover:border-slate-400"}`}>{l}</button>
          ))}
        </div>
        <div className="relative sm:w-72">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input className="bg-white pl-9" placeholder="Cerca nome o email" value={q} onChange={(e) => setQ(e.target.value)} data-testid="users-search-input" />
        </div>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm" data-testid="users-table">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr><th className="px-4 py-3 font-medium">Utente</th><th className="px-4 py-3 font-medium">Registrato</th><th className="px-4 py-3 font-medium">Accesso</th><th className="px-4 py-3 font-medium">Aziende</th><th className="px-4 py-3 font-medium">Moduli</th><th className="px-4 py-3 font-medium">Stato</th><th className="px-4 py-3 font-medium">Ruolo</th><th className="px-4 py-3" /></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {shown.map((u) => {
              const [lbl, cls] = STAT[u.status] || STAT.pending;
              const self = u.user_id === me?.user_id;
              const locked = self || u.is_owner;
              return (
                <tr key={u.user_id} data-testid={`user-row-${u.user_id}`}>
                  <td className="px-4 py-3"><div className="font-semibold text-slate-900">{u.name}</div><div className="text-xs text-slate-500">{u.email}</div></td>
                  <td className="px-4 py-3 text-slate-600">{fmtDate(u.created_at)}</td>
                  <td className="px-4 py-3 text-xs text-slate-600" data-testid={`user-access-${u.user_id}`}>{u.has_password ? "Email e password" : "Invito in attesa"}</td>
                  <td className="max-w-[220px] px-4 py-3 text-xs text-slate-600" data-testid={`user-companies-${u.user_id}`}>{u.role === "admin" ? "Tutte (admin)" : (u.company_ids || []).map(cname).filter(Boolean).join(", ") || <span className="text-amber-700">Nessuna</span>}</td>
                  <td className="px-4 py-3 text-xs text-slate-600" data-testid={`user-moduli-${u.user_id}`}>
                    {u.role === "admin" ? "Tutti (admin)" : (
                      <button disabled={locked} onClick={() => setModU(u)} className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-2 py-1 hover:border-slate-400 hover:text-slate-900 disabled:opacity-50" data-testid={`user-moduli-btn-${u.user_id}`}>
                        <ToggleRight className="h-3.5 w-3.5" />{u.moduli ? modSummary(u) : "Tutti"}
                      </button>
                    )}
                  </td>
                  <td className="px-4 py-3"><span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${cls}`} data-testid={`user-status-${u.user_id}`}>{lbl}</span></td>
                  <td className="px-4 py-3">
                    <Select disabled={locked} value={u.role} onValueChange={(v) => patch(u, { role: v })}>
                      <SelectTrigger className="w-36" data-testid={`user-role-select-${u.user_id}`}><SelectValue /></SelectTrigger>
                      <SelectContent className="bg-white">{ROLES.map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent>
                    </Select>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right">
                    {self && <span className="text-xs text-slate-400">Tu</span>}
                    {!self && u.is_owner && <span className="text-xs text-slate-400">Titolare</span>}
                    {!locked && u.status !== "approved" && <Button size="sm" className="mr-2 bg-emerald-600 hover:bg-emerald-700" onClick={() => patch(u, { status: "approved" })} data-testid={`user-approve-${u.user_id}`}>Approva</Button>}
                    {!locked && u.status !== "rejected" && <Button size="sm" variant="outline" className="mr-2 text-rose-600" onClick={() => patch(u, { status: "rejected" })} data-testid={`user-reject-${u.user_id}`}>{u.status === "approved" ? "Revoca" : "Rifiuta"}</Button>}
                    {!locked && (
                      <>
                        <button title="Modifica" onClick={() => { setEditing(u); setOpen(true); }} className="rounded p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-900" data-testid={`user-edit-${u.user_id}`}><Pencil className="h-4 w-4" /></button>
                        <button title="Invia link per impostare la password" onClick={() => sendReset(u)} className="rounded p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-900" data-testid={`user-send-reset-${u.user_id}`}><Mail className="h-4 w-4" /></button>
                        <button title="Elimina" onClick={() => remove(u)} className="rounded p-1.5 text-slate-500 hover:bg-rose-50 hover:text-rose-600" data-testid={`user-delete-${u.user_id}`}><Trash2 className="h-4 w-4" /></button>
                      </>
                    )}
                  </td>
                </tr>
              );
            })}
            {shown.length === 0 && <tr><td colSpan={8} className="px-4 py-12 text-center text-slate-500" data-testid="users-empty">Nessun utente trovato</td></tr>}
          </tbody>
        </table>
      </div>
      <UserDialog open={open} onOpenChange={setOpen} user={editing} onSaved={load} />
      <ModuliDialog company={modU && { ...modU, id: modU.user_id, denominazione: modU.name }} onClose={() => setModU(null)} onSaved={load}
        endpoint={modU && `/users/${modU.user_id}/moduli`}
        desc="Scegli quali aree e funzioni può usare questo utente. Vale per tutte le sue aziende, e solo se il modulo è attivo anche per l'azienda." />
    </div>
  );
}

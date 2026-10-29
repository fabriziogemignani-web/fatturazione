import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { ROLES, fmtDate } from "@/lib/fe";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const STAT = {
  approved: ["Approvato", "bg-emerald-100 text-emerald-800 border-emerald-300"],
  pending: ["In attesa", "bg-amber-100 text-amber-800 border-amber-300"],
  rejected: ["Rifiutato", "bg-rose-100 text-rose-800 border-rose-300"],
};

export default function Users() {
  const [users, setUsers] = useState([]);
  const load = () => api.get("/users").then(({ data }) => setUsers(data));
  useEffect(() => { load(); }, []);

  const patch = async (u, body) => {
    try { await api.patch(`/users/${u.user_id}`, body); toast.success("Utente aggiornato"); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };

  return (
    <div>
      <PageHeader eyebrow="Amministrazione" title="Utenti" />
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm" data-testid="users-table">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr><th className="px-4 py-3 font-medium">Utente</th><th className="px-4 py-3 font-medium">Registrato</th><th className="px-4 py-3 font-medium">Stato</th><th className="px-4 py-3 font-medium">Ruolo</th><th className="px-4 py-3" /></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {users.map((u) => {
              const [lbl, cls] = STAT[u.status] || STAT.pending;
              return (
                <tr key={u.user_id} data-testid={`user-row-${u.user_id}`}>
                  <td className="px-4 py-3"><div className="font-semibold text-slate-900">{u.name}</div><div className="text-xs text-slate-500">{u.email}</div></td>
                  <td className="px-4 py-3 text-slate-600">{fmtDate(u.created_at)}</td>
                  <td className="px-4 py-3"><span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${cls}`} data-testid={`user-status-${u.user_id}`}>{lbl}</span></td>
                  <td className="px-4 py-3">
                    <Select value={u.role} onValueChange={(v) => patch(u, { role: v })}>
                      <SelectTrigger className="w-36" data-testid={`user-role-select-${u.user_id}`}><SelectValue /></SelectTrigger>
                      <SelectContent className="bg-white">{ROLES.map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent>
                    </Select>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right">
                    {u.status !== "approved" && <Button size="sm" className="mr-2 bg-emerald-600 hover:bg-emerald-700" onClick={() => patch(u, { status: "approved" })} data-testid={`user-approve-${u.user_id}`}>Approva</Button>}
                    {u.status !== "rejected" && <Button size="sm" variant="outline" className="text-rose-600" onClick={() => patch(u, { status: "rejected" })} data-testid={`user-reject-${u.user_id}`}>{u.status === "approved" ? "Revoca" : "Rifiuta"}</Button>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Field } from "@/components/Common";
import { api, errMsg } from "@/lib/api";
import { ROLES } from "@/lib/fe";
import { useCompany } from "@/context/CompanyContext";
import { Checkbox } from "@/components/ui/checkbox";

export const UserDialog = ({ open, onOpenChange, user, onSaved }) => {
  const [f, setF] = useState({ name: "", email: "", role: "operatore", send_invite: true, company_ids: [] });
  const [busy, setBusy] = useState(false);
  const { companies, current } = useCompany();
  useEffect(() => {
    if (open) setF(user ? { name: user.name || "", email: user.email, role: user.role, send_invite: false, company_ids: user.company_ids || [] } : { name: "", email: "", role: "operatore", send_invite: true, company_ids: current ? [current] : [] });
  }, [open, user, current]);
  const toggle = (id, on) => setF((x) => ({ ...x, company_ids: on ? [...x.company_ids, id] : x.company_ids.filter((c) => c !== id) }));

  const save = async () => {
    setBusy(true);
    try {
      if (user) await api.patch(`/users/${user.user_id}`, { name: f.name, role: f.role, company_ids: f.company_ids });
      else await api.post("/users", f);
      toast.success(user ? "Utente aggiornato" : f.send_invite ? "Utente creato, invito inviato via email" : "Utente creato");
      onSaved();
      onOpenChange(false);
    } catch (e) { toast.error(errMsg(e)); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white sm:max-w-md" data-testid="user-dialog">
        <DialogHeader><DialogTitle>{user ? "Modifica utente" : "Nuovo utente"}</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <Field label="Nome e cognome"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} data-testid="user-name-input" /></Field>
          <Field label="Email"><Input type="email" disabled={!!user} value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} data-testid="user-email-input" /></Field>
          <Field label="Ruolo">
            <Select value={f.role} onValueChange={(v) => setF({ ...f, role: v })}>
              <SelectTrigger data-testid="user-role-input"><SelectValue /></SelectTrigger>
              <SelectContent className="bg-white">{ROLES.map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent>
            </Select>
          </Field>
          <Field label="Aziende assegnate">
            <div className="max-h-40 space-y-2 overflow-y-auto rounded-lg border border-slate-200 p-3" data-testid="user-companies-list">
              {(companies || []).map((c) => (
                <label key={c.id} className="flex items-center gap-2 text-sm text-slate-700">
                  <Checkbox checked={f.company_ids.includes(c.id)} onCheckedChange={(v) => toggle(c.id, !!v)} data-testid={`user-company-${c.id}`} />
                  {c.denominazione}
                </label>
              ))}
            </div>
            {f.role === "admin" && <span className="text-xs text-slate-500">Gli admin accedono comunque a tutte le aziende.</span>}
          </Field>
          {!user && (
            <label className="flex items-center justify-between gap-4 rounded-lg bg-slate-50 p-3">
              <span className="text-sm text-slate-700">Invia email di invito per impostare la password (link valido 72 ore)</span>
              <Switch checked={f.send_invite} onCheckedChange={(v) => setF({ ...f, send_invite: v })} data-testid="user-invite-switch" />
            </label>
          )}
          {!user && <p className="text-xs text-slate-500">L'utente viene creato già approvato. Potrà entrare anche con Google usando la stessa email.</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="user-cancel-btn">Annulla</Button>
          <Button onClick={save} disabled={busy} data-testid="user-save-btn">{busy ? "Salvataggio…" : "Salva"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

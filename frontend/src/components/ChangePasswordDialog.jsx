import { useState } from "react";
import { toast } from "sonner";
import { KeyRound } from "lucide-react";
import { api } from "@/lib/api";
import { Field, FieldErrors, useFieldErrors } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";

const EMPTY = { current_password: "", new_password: "", confirm: "" };
const FIELDS = [["current_password", "Password attuale", "current-password"], ["new_password", "Nuova password (almeno 8 caratteri)", "new-password"], ["confirm", "Ripeti la nuova password", "new-password"]];

export const ChangePasswordDialog = ({ open, onOpenChange }) => {
  const [f, setF] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [mismatch, setMismatch] = useState(false);
  const { fail, reset, value } = useFieldErrors();
  const close = (v) => { if (!v) { setF(EMPTY); reset(); setMismatch(false); } onOpenChange(v); };

  const submit = async (e) => {
    e.preventDefault();
    reset();
    if (f.new_password !== f.confirm) { setMismatch(true); return; }
    setMismatch(false);
    setBusy(true);
    try {
      await api.post("/auth/change-password", { current_password: f.current_password, new_password: f.new_password });
      toast.success("Password aggiornata. Le altre sessioni aperte sono state chiuse.");
      close(false);
    } catch (err) { fail(err); }
    setBusy(false);
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="bg-white sm:max-w-md" data-testid="change-password-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><KeyRound className="h-5 w-5 text-blue-600" />Cambia password</DialogTitle>
          <DialogDescription>Inserisci la password attuale e scegli quella nuova.</DialogDescription>
        </DialogHeader>
        <FieldErrors value={value}>
          <form onSubmit={submit} className="space-y-4">
            {FIELDS.map(([k, label, ac]) => (
              <Field key={k} name={k} label={label}>
                <Input type="password" autoComplete={ac} required value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })}
                  className={k === "confirm" && mismatch ? "border-rose-500 ring-1 ring-rose-500" : ""} data-testid={`change-password-${k.replace(/_/g, "-")}-input`} />
                {k === "confirm" && mismatch && <p className="mt-1 text-xs text-rose-600" data-testid="change-password-mismatch">Le due password non coincidono</p>}
              </Field>
            ))}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => close(false)} data-testid="change-password-cancel-btn">Annulla</Button>
              <Button type="submit" disabled={busy} data-testid="change-password-submit-btn">{busy ? "Salvataggio…" : "Aggiorna password"}</Button>
            </DialogFooter>
          </form>
        </FieldErrors>
      </DialogContent>
    </Dialog>
  );
};

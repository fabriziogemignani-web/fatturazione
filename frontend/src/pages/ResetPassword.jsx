import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/Common";
import { AuthShell } from "@/pages/ForgotPassword";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (pw !== pw2) { toast.error("Le password non coincidono"); return; }
    setBusy(true);
    try {
      await api.post("/auth/reset-password", { token: params.get("token") || "", password: pw });
      toast.success("Password aggiornata: ora puoi accedere");
      navigate("/login", { replace: true });
    } catch (err) { toast.error(errMsg(err)); }
    finally { setBusy(false); }
  };

  return (
    <AuthShell title="Nuova password">
      <form onSubmit={submit} className="mt-6 space-y-4">
        <Field label="Nuova password"><Input required minLength={8} type="password" value={pw} onChange={(e) => setPw(e.target.value)} data-testid="reset-password-input" /></Field>
        <Field label="Conferma password"><Input required minLength={8} type="password" value={pw2} onChange={(e) => setPw2(e.target.value)} data-testid="reset-password-confirm-input" /></Field>
        <Button type="submit" disabled={busy} className="w-full" data-testid="reset-submit-btn">{busy ? "Salvataggio…" : "Imposta password"}</Button>
      </form>
    </AuthShell>
  );
}

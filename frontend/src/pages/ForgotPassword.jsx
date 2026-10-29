import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { MailCheck } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/Common";

export const AuthShell = ({ title, children }) => (
  <div className="grid min-h-screen place-items-center bg-slate-50 p-6">
    <div className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-8 shadow-sm fade-up">
      <div className="text-xs font-medium uppercase tracking-wider text-slate-500">Area riservata</div>
      <h1 className="mt-2 text-2xl font-extrabold tracking-tight text-slate-900">{title}</h1>
      {children}
      <Link to="/login" className="mt-6 block text-center text-sm font-medium text-blue-600 hover:text-blue-700" data-testid="back-to-login-link">Torna all'accesso</Link>
    </div>
  </div>
);

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try { await api.post("/auth/forgot-password", { email }); setSent(true); }
    catch (err) { toast.error(errMsg(err)); }
    finally { setBusy(false); }
  };

  return (
    <AuthShell title="Recupera password">
      {sent ? (
        <div className="mt-6 rounded-lg bg-emerald-50 p-4 text-sm text-emerald-800" data-testid="forgot-success">
          <MailCheck className="mb-2 h-5 w-5" />
          Se l'email è registrata, riceverai a breve un link per reimpostare la password (valido 1 ora). Controlla anche lo spam.
        </div>
      ) : (
        <form onSubmit={submit} className="mt-6 space-y-4">
          <Field label="Email"><Input required type="email" value={email} onChange={(e) => setEmail(e.target.value)} data-testid="forgot-email-input" /></Field>
          <Button type="submit" disabled={busy} className="w-full" data-testid="forgot-submit-btn">{busy ? "Invio…" : "Invia link di recupero"}</Button>
        </form>
      )}
    </AuthShell>
  );
}

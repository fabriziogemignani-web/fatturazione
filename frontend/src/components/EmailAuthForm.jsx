import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Field, FieldErrors, useFieldErrors } from "@/components/Common";

export const EmailAuthForm = () => {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [busy, setBusy] = useState(false);
  const { setUser } = useAuth();
  const navigate = useNavigate();
  const { fail, reset, value } = useFieldErrors();
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    reset();
    try {
      const body = mode === "login" ? { email: form.email, password: form.password } : form;
      const { data } = await api.post(`/auth/${mode}`, body);
      setUser(data);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <FieldErrors value={value}>
    <form onSubmit={submit} className="space-y-4" data-testid="email-auth-form">
      <div className="grid grid-cols-2 rounded-lg border border-slate-200 bg-white p-1 text-sm font-semibold">
        {[["login", "Accedi"], ["register", "Registrati"]].map(([k, l]) => (
          <button type="button" key={k} onClick={() => setMode(k)} data-testid={`auth-mode-${k}`}
            className={`rounded-md py-2 transition-colors ${mode === k ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-50"}`}>{l}</button>
        ))}
      </div>
      {mode === "register" && (
        <Field label="Nome e cognome" name="name"><Input required value={form.name} onChange={set("name")} data-testid="register-name-input" /></Field>
      )}
      <Field label="Email" name="email"><Input required type="email" value={form.email} onChange={set("email")} data-testid="login-email-input" /></Field>
      <Field label="Password" name="password"><Input required type="password" minLength={mode === "register" ? 8 : undefined} value={form.password} onChange={set("password")} data-testid="login-password-input" /></Field>
      <Button type="submit" disabled={busy} className="w-full" data-testid="login-submit-button">
        {busy ? "Attendere…" : mode === "login" ? "Accedi con email" : "Crea account"}
      </Button>
      {mode === "login" ? (
        <Link to="/password-dimenticata" className="block text-center text-sm font-medium text-blue-600 hover:text-blue-700" data-testid="login-forgot-password-link">Password dimenticata?</Link>
      ) : (
        <p className="text-xs text-slate-500">Minimo 8 caratteri. Il tuo account dovrà essere approvato da un amministratore.</p>
      )}
    </form>
    </FieldErrors>
  );
};

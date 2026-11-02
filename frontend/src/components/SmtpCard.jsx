import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Mail, Send, Trash2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Field, FieldErrors, useFieldErrors } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const EMPTY = { host: "", port: 587, security: "starttls", username: "", password: "", from_email: "", from_name: "", reply_to: "" };
const SECURITY = [["starttls", "STARTTLS (porta 587)"], ["ssl", "SSL/TLS (porta 465)"], ["none", "Nessuna (porta 25)"]];
const PORTS = { starttls: 587, ssl: 465, none: 25 };
const TEXT = [["host", "Server SMTP", "smtp.miodominio.it"], ["port", "Porta", ""], ["username", "Utente", "di solito l'indirizzo email"], ["from_email", "Email mittente", "fatture@miodominio.it"], ["from_name", "Nome mittente", "vuoto = ragione sociale"], ["reply_to", "Rispondi a (facoltativo)", ""]];

export const SmtpCard = () => {
  const [form, setForm] = useState(EMPTY);
  const [info, setInfo] = useState(null);
  const [to, setTo] = useState("");
  const [busy, setBusy] = useState("");
  const { fail, reset, value } = useFieldErrors();
  const load = () => api.get("/company/smtp").then(({ data }) => { setInfo(data); setForm({ ...EMPTY, ...Object.fromEntries(Object.entries(data).filter(([, v]) => v != null)), password: "" }); }).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, []);

  const save = async () => {
    setBusy("save"); reset();
    try { await api.put("/company/smtp", { ...form, port: Number(form.port), password: form.password ? form.password : null }); toast.success("Configurazione email salvata"); load(); }
    catch (e) { fail(e); }
    setBusy("");
  };
  const test = async () => {
    setBusy("test");
    try { await api.post("/company/smtp/test", { to }); toast.success(`Email di prova inviata a ${to}`); } catch (e) { toast.error(errMsg(e)); }
    setBusy("");
  };
  const remove = async () => {
    if (!window.confirm("Rimuovere la configurazione email di questa azienda?")) return;
    try { await api.delete("/company/smtp"); toast.success("Configurazione rimossa"); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  if (!info) return null;

  return (
    <FieldErrors value={value}>
      <div className="mt-6 max-w-3xl rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm" data-testid="smtp-card">
        <div className="mb-1 flex items-center justify-between gap-3">
          <h3 className="flex items-center gap-2 text-lg font-semibold text-slate-800"><Mail className="h-5 w-5 text-blue-600" />Email in uscita (SMTP)</h3>
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${info.configured ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`} data-testid="smtp-status">{info.configured ? "Configurato" : "Non configurato"}</span>
        </div>
        <p className="mb-4 text-xs text-slate-500">Server di posta usato da questa azienda per solleciti, inviti e recupero password. La password viene salvata cifrata e non viene mai mostrata.</p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {TEXT.map(([k, label, ph]) => (
            <Field key={k} name={k} label={label}>
              <Input type={k === "port" ? "number" : "text"} placeholder={ph} value={form[k] ?? ""} onChange={(e) => setForm({ ...form, [k]: e.target.value })} data-testid={`smtp-${k.replace(/_/g, "-")}-input`} />
            </Field>
          ))}
          <Field label="Sicurezza" name="security">
            <Select value={form.security} onValueChange={(v) => setForm({ ...form, security: v, port: PORTS[v] })}>
              <SelectTrigger data-testid="smtp-security-select"><SelectValue /></SelectTrigger>
              <SelectContent className="bg-white">{SECURITY.map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent>
            </Select>
          </Field>
          <Field label="Password" name="password">
            <Input type="password" autoComplete="new-password" placeholder={info.has_password ? "•••••••• (lascia vuoto per non cambiarla)" : ""} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} data-testid="smtp-password-input" />
          </Field>
        </div>
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Button onClick={save} disabled={busy === "save"} data-testid="smtp-save-btn">{busy === "save" ? "Salvataggio…" : "Salva configurazione"}</Button>
          {info.configured && <Button variant="ghost" className="text-rose-600" onClick={remove} data-testid="smtp-delete-btn"><Trash2 className="mr-2 h-4 w-4" />Rimuovi</Button>}
        </div>
        {info.configured && (
          <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-4">
            <Input className="max-w-xs" placeholder="email destinatario della prova" value={to} onChange={(e) => setTo(e.target.value)} data-testid="smtp-test-to-input" />
            <Button variant="outline" onClick={test} disabled={!to || busy === "test"} data-testid="smtp-test-btn"><Send className="mr-2 h-4 w-4" />{busy === "test" ? "Invio…" : "Invia email di prova"}</Button>
          </div>
        )}
      </div>
    </FieldErrors>
  );
};

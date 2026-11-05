import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Radio, PlugZap } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Field, FieldErrors, useFieldErrors } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { fmtDateTime } from "@/lib/fe";

const PROVIDERS = [["simulato", "Simulato (nessun invio reale)"], ["openapi", "Openapi.it"], ["acube", "A-Cube"]];
const AMBIENTI = [["sandbox", "Ambiente di prova"], ["production", "Ambiente reale"]];
const HINT = {
  openapi: "Token creato nella console Openapi (sezione Authentication) per il servizio SDI. Per ricevere le fatture passive registrate il codice destinatario JKKZDGR nel portale Fatture e Corrispettivi.",
  acube: "Email e password dell'account A-Cube. Per ricevere le fatture passive registrate nel portale Fatture e Corrispettivi il codice destinatario indicato da A-Cube.",
};

const Secret = ({ name, label, has, form, setForm }) => (
  <Field name={name} label={label}>
    <Input type="password" autoComplete="new-password" placeholder={has ? "•••••••• (lascia vuoto per non cambiarlo)" : ""} value={form[name]} onChange={(e) => setForm({ ...form, [name]: e.target.value })} data-testid={`sdi-${name}-input`} />
  </Field>
);

const Choice = ({ name, label, opts, form, setForm }) => (
  <Field name={name} label={label}>
    <Select value={form[name]} onValueChange={(v) => setForm({ ...form, [name]: v })}>
      <SelectTrigger data-testid={`sdi-${name}-select`}><SelectValue /></SelectTrigger>
      <SelectContent className="bg-white">{opts.map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent>
    </Select>
  </Field>
);

const Status = ({ info }) => (
  <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${info.provider === "simulato" ? "bg-amber-50 text-amber-700" : info.ambiente === "sandbox" ? "bg-blue-50 text-blue-700" : "bg-emerald-50 text-emerald-700"}`} data-testid="sdi-status">
    {info.provider === "simulato" ? "Simulato" : `${info.label} · ${info.ambiente === "sandbox" ? "prova" : "reale"}`}
  </span>
);

export const SdiCard = () => {
  const [info, setInfo] = useState(null);
  const [form, setForm] = useState({ provider: "simulato", ambiente: "sandbox", email: "", token: "", password: "" });
  const [busy, setBusy] = useState("");
  const { fail, reset, value } = useFieldErrors();
  const load = () => api.get("/company/sdi").then(({ data }) => { setInfo(data); setForm({ provider: data.provider, ambiente: data.ambiente, email: data.email, token: "", password: "" }); }).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, []);

  const save = async () => {
    if (form.provider !== "simulato" && form.ambiente === "production" && !window.confirm("Con l'ambiente reale ogni fattura inviata arriva davvero allo SDI e al cliente. Continuare?")) return;
    setBusy("save"); reset();
    try { await api.put("/company/sdi", { ...form, token: form.token || null, password: form.password || null }); toast.success("Collegamento SDI salvato"); load(); } catch (e) { fail(e); }
    setBusy("");
  };
  const test = async () => {
    setBusy("test");
    try { const { data } = await api.post("/company/sdi/test"); toast.success(data.message); } catch (e) { toast.error(errMsg(e)); }
    setBusy("");
  };
  if (!info) return null;
  const same = info.provider === form.provider;

  return (
    <FieldErrors value={value}>
      <div className="mt-6 max-w-3xl rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm" data-testid="sdi-card">
        <div className="mb-1 flex items-center justify-between gap-3">
          <h3 className="flex items-center gap-2 text-lg font-semibold text-slate-800"><Radio className="h-5 w-5 text-blue-600" />Collegamento SDI</h3>
          <Status info={info} />
        </div>
        <p className="mb-4 text-xs text-slate-500">Intermediario usato da questa azienda per inviare le fatture e ricevere notifiche e fatture passive. Le credenziali vengono salvate cifrate e non vengono mai mostrate. Esiti e fatture ricevute vengono controllati in automatico ogni 15 minuti.</p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Choice name="provider" label="Intermediario" opts={PROVIDERS} form={form} setForm={setForm} />
          {form.provider !== "simulato" && <Choice name="ambiente" label="Ambiente" opts={AMBIENTI} form={form} setForm={setForm} />}
          {form.provider === "openapi" && <div className="sm:col-span-2"><Secret name="token" label="Token Openapi" has={same && info.has_token} form={form} setForm={setForm} /></div>}
          {form.provider === "acube" && <>
            <Field name="email" label="Email account A-Cube"><Input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="sdi-email-input" /></Field>
            <Secret name="password" label="Password A-Cube" has={same && info.has_password} form={form} setForm={setForm} />
          </>}
        </div>
        {HINT[form.provider] && <p className="mt-3 text-xs text-slate-500" data-testid="sdi-hint">{HINT[form.provider]}</p>}
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Button onClick={save} disabled={busy === "save"} data-testid="sdi-save-btn">{busy === "save" ? "Salvataggio…" : "Salva collegamento"}</Button>
          {info.provider !== "simulato" && <Button variant="outline" onClick={test} disabled={busy === "test"} data-testid="sdi-test-btn"><PlugZap className="mr-2 h-4 w-4" />{busy === "test" ? "Verifica…" : "Prova collegamento"}</Button>}
        </div>
        {info.last_sync_at && (
          <p className={`mt-4 text-xs ${info.last_sync_error ? "text-rose-600" : "text-slate-500"}`} data-testid="sdi-last-sync">
            Ultimo controllo automatico: {fmtDateTime(info.last_sync_at)}{info.last_sync_error ? ` · errore: ${info.last_sync_error}` : " · ok"}
          </p>
        )}
      </div>
    </FieldErrors>
  );
};

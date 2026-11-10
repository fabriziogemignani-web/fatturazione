import { useEffect, useState } from "react";
import { toast } from "sonner";
import { HardDriveUpload, PlugZap, UploadCloud, CheckCircle2, AlertTriangle } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Field, FieldErrors, useFieldErrors } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

const EMPTY = { attivo: false, host: "", porta: 21, utente: "", password: "", cartella: "", tls: true, ora: "02:00" };
const dt = (s) => new Date(s).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
const kb = (n) => (n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

const Esito = ({ u }) => (
  <div className={`mt-4 flex items-start gap-2 rounded-lg p-3 text-xs ${u.ok ? "bg-emerald-50 text-emerald-800" : "bg-rose-50 text-rose-800"}`} data-testid="ftp-ultimo-esito">
    {u.ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /> : <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />}
    <span>Ultimo invio {dt(u.data)}: {u.ok ? <>riuscito · <b>{u.file}</b> ({kb(u.dimensione)}, {u.documenti} documenti)</> : <>non riuscito – {u.errore}</>}</span>
  </div>
);

export const FtpBackupCard = () => {
  const [form, setForm] = useState(EMPTY);
  const [info, setInfo] = useState(null);
  const [busy, setBusy] = useState("");
  const { fail, reset, value } = useFieldErrors();
  const load = () => api.get("/company/ftp-backup").then(({ data }) => { setInfo(data); setForm({ ...EMPTY, ...Object.fromEntries(Object.entries(data).filter(([, v]) => v != null)), password: "" }); }).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, []);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const save = async () => {
    setBusy("save"); reset();
    try { await api.put("/company/ftp-backup", { ...form, porta: Number(form.porta), password: form.password || null }); toast.success("Configurazione FTP salvata"); load(); } catch (e) { fail(e); }
    setBusy("");
  };
  const act = async (k, url, ok) => {
    setBusy(k);
    try { const { data } = await api.post(url); toast.success(ok(data)); } catch (e) { toast.error(errMsg(e)); }
    setBusy(""); load();
  };
  if (!info) return null;
  return (
    <FieldErrors value={value}>
      <div className="mt-6 max-w-3xl rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm" data-testid="ftp-backup-card">
        <div className="mb-1 flex items-center justify-between gap-3">
          <h3 className="flex items-center gap-2 text-lg font-semibold text-slate-800"><HardDriveUpload className="h-5 w-5 text-blue-600" />Backup su FTP</h3>
          <label className="flex items-center gap-2 text-sm text-slate-600">Invio notturno<Switch checked={form.attivo} onCheckedChange={(v) => setForm({ ...form, attivo: v })} data-testid="ftp-attivo-switch" /></label>
        </div>
        <p className="mb-4 text-xs text-slate-500">Ogni notte, all'ora scelta, il programma esporta solo i dati di questa azienda (anagrafiche, fatture, contabilità, configurazioni) in un file compresso e lo invia al vostro FTP. La password viene salvata cifrata.</p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
          <div className="sm:col-span-3"><Field name="host" label="Server FTP"><Input placeholder="ftp.miodominio.it" value={form.host} onChange={set("host")} data-testid="ftp-host-input" /></Field></div>
          <Field name="porta" label="Porta"><Input type="number" value={form.porta} onChange={set("porta")} data-testid="ftp-porta-input" /></Field>
          <div className="sm:col-span-2"><Field name="utente" label="Utente"><Input value={form.utente} onChange={set("utente")} autoComplete="off" data-testid="ftp-utente-input" /></Field></div>
          <div className="sm:col-span-2"><Field name="password" label="Password"><Input type="password" autoComplete="new-password" placeholder={info.has_password ? "•••••••• (lascia vuoto per non cambiarla)" : ""} value={form.password} onChange={set("password")} data-testid="ftp-password-input" /></Field></div>
          <div className="sm:col-span-2"><Field name="cartella" label="Cartella sul server (creata se manca)"><Input placeholder="backup/azienda" value={form.cartella} onChange={set("cartella")} data-testid="ftp-cartella-input" /></Field></div>
          <Field name="ora" label="Ora di invio"><Input type="time" value={form.ora} onChange={set("ora")} data-testid="ftp-ora-input" /></Field>
          <label className="flex items-end gap-2 pb-2 text-sm text-slate-600"><Switch checked={form.tls} onCheckedChange={(v) => setForm({ ...form, tls: v })} data-testid="ftp-tls-switch" />Connessione cifrata (FTPS)</label>
        </div>
        {!form.tls && <p className="mt-2 text-xs text-amber-700" data-testid="ftp-tls-warning">Senza cifratura password e dati viaggiano in chiaro: usatelo solo se il server non supporta FTPS.</p>}
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Button onClick={save} disabled={busy === "save"} data-testid="ftp-save-btn">{busy === "save" ? "Salvataggio…" : "Salva configurazione"}</Button>
          {info.host && <Button variant="outline" onClick={() => act("test", "/company/ftp-backup/test", (d) => `Connessione riuscita (cartella ${d.cartella})`)} disabled={!!busy} data-testid="ftp-test-btn"><PlugZap className="mr-2 h-4 w-4" />{busy === "test" ? "Verifica…" : "Prova connessione"}</Button>}
          {info.host && <Button variant="outline" onClick={() => act("run", "/company/ftp-backup/run", (d) => `Backup inviato: ${d.file}`)} disabled={!!busy} data-testid="ftp-run-btn"><UploadCloud className="mr-2 h-4 w-4" />{busy === "run" ? "Invio…" : "Invia backup ora"}</Button>}
        </div>
        {info.ultimo && <Esito u={info.ultimo} />}
      </div>
    </FieldErrors>
  );
};

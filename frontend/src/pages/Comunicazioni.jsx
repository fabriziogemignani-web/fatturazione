import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Play, Save } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useAuth, canSend, can } from "@/context/AuthContext";
import { ComLog } from "@/components/ComunicazioniPanel";

const TESTI = [["cortesia", "Fattura di cortesia"], ["promemoria", "Promemoria scadenza"], ["sollecito1", "1° sollecito"], ["sollecito2", "2° sollecito"], ["sollecito3", "3° sollecito / diffida"]];

const Toggle = ({ label, desc, checked, onChange, testId, disabled, children }) => (
  <div className="rounded-xl border border-slate-200 bg-white p-4">
    <div className="flex items-start justify-between gap-4">
      <div><div className="font-semibold text-slate-800">{label}</div><div className="text-xs text-slate-500">{desc}</div></div>
      <Switch checked={checked} onCheckedChange={onChange} disabled={disabled} data-testid={testId} />
    </div>
    {children && <div className="mt-3 flex flex-wrap items-end gap-3">{children}</div>}
  </div>
);

export default function Comunicazioni() {
  const { user } = useAuth();
  const edit = canSend(user);
  const testi = can(user, "testi_comunicazioni");
  const [d, setD] = useState(null);
  const [tab, setTab] = useState("cortesia");
  const [busy, setBusy] = useState(false);
  const [logKey, setLogKey] = useState(0);
  useEffect(() => { api.get("/comunicazioni/config").then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e))); }, []);
  if (!d) return <div className="text-sm text-slate-500">Caricamento…</div>;
  const c = d.config;
  const set = (p) => setD({ ...d, config: { ...c, ...p } });
  const setT = (k, p) => set({ testi: { ...c.testi, [k]: { ...c.testi[k], ...p } } });
  const save = async () => {
    try { await api.put("/comunicazioni/config", { ...c, livelli: c.livelli.map(Number), promemoria_giorni: Number(c.promemoria_giorni), ora: Number(c.ora) }); toast.success("Impostazioni salvate"); } catch (e) { toast.error(errMsg(e)); }
  };
  const esegui = async () => {
    if (!window.confirm("Invio subito promemoria e solleciti dovuti oggi (quelli già inviati non vengono ripetuti). Continuare?")) return;
    setBusy(true);
    try { const { data } = await api.post("/comunicazioni/esegui"); toast.success(`Inviati ${data.promemoria} promemoria e ${data.solleciti} solleciti${data.errori ? ` · ${data.errori} non inviati` : ""}`); setLogKey((k) => k + 1); setD((x) => ({ ...x, ultimo: { ...data, auto: false, at: new Date().toISOString() } })); } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };

  return (
    <div>
      <PageHeader eyebrow="Vendite" title="Comunicazioni ai clienti">
        {edit && <Button variant="outline" onClick={esegui} disabled={busy} data-testid="com-esegui-btn"><Play className="mr-2 h-4 w-4" />Invia ora promemoria e solleciti</Button>}
        {(edit || testi) && <Button onClick={save} data-testid="com-save-btn"><Save className="mr-2 h-4 w-4" />Salva</Button>}
      </PageHeader>
      <p className="mb-4 text-sm text-slate-600">Le email partono dal server di posta dell'azienda (Dati azienda → Email). Invio automatico ogni giorno dalle ore {c.ora}:00; ogni rata riceve ogni comunicazione una sola volta.</p>
      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Toggle label="Fattura di cortesia" desc="Email con il PDF appena lo SDI consegna la fattura" checked={c.cortesia_auto} onChange={(v) => set({ cortesia_auto: v })} disabled={!edit} testId="com-cortesia-switch" />
        <Toggle label="Promemoria scadenza" desc="Avviso ai clienti per le rate in scadenza" checked={c.promemoria_auto} onChange={(v) => set({ promemoria_auto: v })} disabled={!edit} testId="com-promemoria-switch">
          <label className="text-xs text-slate-600">Giorni prima<Input type="number" min={1} max={30} value={c.promemoria_giorni} onChange={(e) => set({ promemoria_giorni: e.target.value })} className="w-24" disabled={!edit} data-testid="com-promemoria-giorni" /></label>
          <label className="text-xs text-slate-600">Ora invio<Input type="number" min={6} max={20} value={c.ora} onChange={(e) => set({ ora: e.target.value })} className="w-20" disabled={!edit} data-testid="com-ora" /></label>
        </Toggle>
        <Toggle label="Solleciti a livelli" desc="Giorni di ritardo dopo cui parte ogni livello" checked={c.solleciti_auto} onChange={(v) => set({ solleciti_auto: v })} disabled={!edit} testId="com-solleciti-switch">
          {c.livelli.map((g, i) => (
            <label key={i} className="text-xs text-slate-600">{i + 1}° livello<Input type="number" min={1} value={g} onChange={(e) => set({ livelli: c.livelli.map((x, k) => (k === i ? e.target.value : x)) })} className="w-20" disabled={!edit} data-testid={`com-livello-${i + 1}`} /></label>
          ))}
        </Toggle>
      </div>
      {testi && <div className="mb-6 rounded-xl border border-slate-200 bg-white p-5" data-testid="com-testi-card">
        <h3 className="mb-3 font-semibold text-slate-800">Testi delle email</h3>
        <div className="mb-4 flex flex-wrap gap-2">
          {TESTI.map(([k, l]) => <button key={k} onClick={() => setTab(k)} className={`rounded-full px-3 py-1 text-xs font-semibold ${tab === k ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`} data-testid={`com-testo-tab-${k}`}>{l}</button>)}
        </div>
        <label className="text-xs text-slate-600">Oggetto<Input value={c.testi[tab].oggetto} onChange={(e) => setT(tab, { oggetto: e.target.value })} data-testid="com-testo-oggetto" /></label>
        <label className="mt-3 block text-xs text-slate-600">Testo<Textarea rows={10} value={c.testi[tab].corpo} onChange={(e) => setT(tab, { corpo: e.target.value })} data-testid="com-testo-corpo" /></label>
        <p className="mt-2 text-xs text-slate-500">Campi disponibili: {d.segnaposto.join(" ")} · {"{elenco}"} inserisce la tabella delle rate.</p>
      </div>}
      {d.ultimo && <p className="mb-2 text-xs text-slate-500" data-testid="com-ultimo">Ultimo invio {d.ultimo.auto === false ? "manuale" : "pianificato"}: {new Date(d.ultimo.at).toLocaleString("it-IT")} · {d.ultimo.promemoria} promemoria, {d.ultimo.solleciti} solleciti{d.ultimo.errori ? `, ${d.ultimo.errori} non inviati` : ""}</p>}
      <ComLog key={logKey} limit={100} />
    </div>
  );
}

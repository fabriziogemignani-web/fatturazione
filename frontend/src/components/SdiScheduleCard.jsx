import { useEffect, useState } from "react";
import { toast } from "sonner";
import { CalendarClock, Plus, X } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { fmtDateTime } from "@/lib/fe";

export const GIORNI = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"];
const PRESET = [[15, "15 min"], [30, "30 min"], [60, "1 ora"], [120, "2 ore"], [240, "4 ore"]];

const Chip = ({ on, onClick, children, testId }) => (
  <button type="button" onClick={onClick} data-testid={testId}
    className={`rounded-full border px-3 py-1 text-xs font-semibold transition-colors ${on ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 bg-white text-slate-600 hover:border-slate-400"}`}>{children}</button>
);

const Orari = ({ s, set }) => {
  const [n, setN] = useState("");
  const add = () => { if (/^\d{2}:\d{2}$/.test(n) && !s.orari.includes(n)) set({ orari: [...s.orari, n].sort() }); setN(""); };
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="schedule-orari">
      {s.orari.map((o) => (
        <span key={o} className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700" data-testid={`schedule-orario-${o}`}>
          {o}<button type="button" onClick={() => set({ orari: s.orari.filter((x) => x !== o) })} data-testid={`schedule-orario-remove-${o}`}><X className="h-3 w-3" /></button>
        </span>
      ))}
      <Input type="time" className="w-32" value={n} onChange={(e) => setN(e.target.value)} data-testid="schedule-orario-input" />
      <Button type="button" variant="outline" size="sm" onClick={add} data-testid="schedule-orario-add-btn"><Plus className="mr-1 h-3.5 w-3.5" />Aggiungi</Button>
    </div>
  );
};

const Intervallo = ({ s, set }) => (
  <div className="space-y-3">
    <div className="flex flex-wrap items-center gap-2">
      {PRESET.map(([v, l]) => <Chip key={v} on={s.ogni_minuti === v} onClick={() => set({ ogni_minuti: v })} testId={`schedule-ogni-${v}`}>{l}</Chip>)}
      <span className="text-xs text-slate-500">oppure ogni</span>
      <Input type="number" min={5} max={1440} className="w-24" value={s.ogni_minuti} onChange={(e) => set({ ogni_minuti: Number(e.target.value) })} data-testid="schedule-ogni-input" />
      <span className="text-xs text-slate-500">minuti</span>
    </div>
    <div className="flex items-center gap-2 text-sm text-slate-600">
      dalle <Input type="time" className="w-32" value={s.dalle} onChange={(e) => set({ dalle: e.target.value })} data-testid="schedule-dalle-input" />
      alle <Input type="time" className="w-32" value={s.alle} onChange={(e) => set({ alle: e.target.value })} data-testid="schedule-alle-input" />
    </div>
  </div>
);

const Check = ({ k, label, s, set }) => (
  <label className="flex items-center gap-2 text-sm text-slate-700">
    <input type="checkbox" checked={s[k]} onChange={(e) => set({ [k]: e.target.checked })} data-testid={`schedule-${k}-checkbox`} />{label}
  </label>
);

export const SdiScheduleCard = () => {
  const [s, setS] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.get("/company/sdi-schedule").then(({ data }) => setS(data)).catch((e) => toast.error(errMsg(e))); }, []);
  if (!s) return null;
  const set = (p) => setS({ ...s, ...p });
  const toggleDay = (d) => set({ giorni: s.giorni.includes(d) ? s.giorni.filter((x) => x !== d) : [...s.giorni, d].sort() });
  const save = async () => {
    setBusy(true);
    try { const { data } = await api.put("/company/sdi-schedule", s); setS(data); toast.success("Pianificazione salvata"); } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };

  return (
    <div className="mt-6 max-w-3xl rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm" data-testid="sdi-schedule-card">
      <div className="mb-1 flex items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-lg font-semibold text-slate-800"><CalendarClock className="h-5 w-5 text-blue-600" />Ricezione pianificata dallo SDI</h3>
        <Switch checked={s.enabled} onCheckedChange={(v) => set({ enabled: v })} data-testid="schedule-enabled-switch" />
      </div>
      <p className="mb-4 text-xs text-slate-500">Scegli quando il programma scarica da solo le fatture passive e le notifiche delle fatture inviate. Orari secondo l'ora italiana.</p>
      <div className={`space-y-4 ${s.enabled ? "" : "pointer-events-none opacity-50"}`}>
        <div className="flex gap-2">
          <Chip on={s.modo === "intervallo"} onClick={() => set({ modo: "intervallo" })} testId="schedule-modo-intervallo">Ogni tot minuti od ore</Chip>
          <Chip on={s.modo === "orari"} onClick={() => set({ modo: "orari" })} testId="schedule-modo-orari">A orari fissi</Chip>
        </div>
        {s.modo === "orari" ? <Orari s={s} set={set} /> : <Intervallo s={s} set={set} />}
        <div className="flex flex-wrap gap-2">{GIORNI.map((g, i) => <Chip key={g} on={s.giorni.includes(i)} onClick={() => toggleDay(i)} testId={`schedule-giorno-${i}`}>{g}</Chip>)}</div>
        <div className="flex flex-wrap gap-6"><Check k="passive" label="Fatture passive" s={s} set={set} /><Check k="notifiche" label="Notifiche delle fatture inviate" s={s} set={set} /></div>
      </div>
      {s.provider === "simulato" && <p className="mt-4 text-xs text-amber-700" data-testid="schedule-sim-note">Collegamento SDI simulato: la pianificazione aggiorna solo gli esiti simulati; le fatture passive arrivano quando colleghi l'intermediario.</p>}
      <div className="mt-5 flex flex-wrap items-center gap-4">
        <Button onClick={save} disabled={busy} data-testid="schedule-save-btn">{busy ? "Salvataggio…" : "Salva pianificazione"}</Button>
        <span className="text-xs text-slate-500" data-testid="schedule-next-run">{s.next_run_at ? `Prossima esecuzione: ${fmtDateTime(s.next_run_at)}` : s.descrizione}</span>
      </div>
    </div>
  );
};

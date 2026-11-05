import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { RefreshCw, CalendarClock, CheckCircle2, AlertCircle } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { fmtDateTime } from "@/lib/fe";
import { useAuth, canSend } from "@/context/AuthContext";

const Stat = ({ label, value, testId }) => (
  <div>
    <div className="text-xs text-slate-500">{label}</div>
    <div className="mt-0.5 text-sm font-semibold text-slate-900" data-testid={testId}>{value}</div>
  </div>
);

const LastRun = ({ r }) => {
  if (!r) return <p className="text-sm text-slate-500" data-testid="schedule-panel-never">Nessuna esecuzione ancora.</p>;
  return (
    <div className={`flex items-start gap-2 rounded-lg px-3 py-2 text-sm ${r.error ? "bg-rose-50 text-rose-700" : "bg-emerald-50 text-emerald-800"}`} data-testid="schedule-panel-last">
      {r.error ? <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" /> : <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />}
      <span>
        {fmtDateTime(r.at)} · {r.manual_by ? `eseguita da ${r.manual_by}` : "pianificata"}
        {r.error ? ` · errore: ${r.error}` : ` · ${r.fatture} fatture ricevute, ${r.notifiche} notifiche${r.simulato ? " (simulato)" : ""}`}
      </span>
    </div>
  );
};

export const SdiSchedulePanel = () => {
  const { user } = useAuth();
  const [s, setS] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.get("/company/sdi-schedule").then(({ data }) => setS(data)).catch(() => {}); }, []);
  if (!s) return null;
  const run = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/company/sdi-schedule/run");
      setS(data.schedule);
      if (data.run.error) toast.error(`Ricezione non riuscita: ${data.run.error}`);
      else toast.success(`Ricezione completata: ${data.run.fatture} fatture, ${data.run.notifiche} notifiche`);
    } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };

  return (
    <section className="mt-6 rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm" data-testid="schedule-panel">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="flex items-center gap-2 text-lg font-semibold text-slate-800"><CalendarClock className="h-5 w-5 text-blue-600" />Ricezione dallo SDI</h3>
          <p className="text-xs text-slate-500" data-testid="schedule-panel-desc">{s.descrizione}{s.provider === "simulato" ? " · collegamento simulato" : ""}</p>
        </div>
        {canSend(user) && <Button variant="outline" onClick={run} disabled={busy} data-testid="schedule-run-now-btn"><RefreshCw className={`mr-2 h-4 w-4 ${busy ? "animate-spin" : ""}`} />{busy ? "Ricezione…" : "Esegui ora"}</Button>}
      </div>
      <div className="mb-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat label="Prossima esecuzione" value={s.next_run_at ? fmtDateTime(s.next_run_at) : "—"} testId="schedule-panel-next" />
        <Stat label="Ultima esecuzione" value={s.last_run ? fmtDateTime(s.last_run.at) : "—"} testId="schedule-panel-last-at" />
        <Stat label="Fatture ricevute (ultima)" value={s.last_run?.fatture ?? 0} testId="schedule-panel-fatture" />
        <Stat label="Notifiche (ultima)" value={s.last_run?.notifiche ?? 0} testId="schedule-panel-notifiche" />
      </div>
      <LastRun r={s.last_run} />
      <Link to="/impostazioni" className="mt-3 inline-block text-xs font-semibold text-blue-700 hover:underline" data-testid="schedule-panel-settings-link">Modifica la pianificazione →</Link>
    </section>
  );
};

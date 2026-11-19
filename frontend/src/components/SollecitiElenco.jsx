import { useEffect, useState } from "react";
import { toast } from "sonner";
import { RefreshCw, Send, Clock } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { fmtEUR, fmtDate } from "@/lib/fe";

const COSA = [["fatture", "Fatture aperte (PDF)"], ["promemoria", "Promemoria rate in scadenza"], ["scadenze", "Sollecito rate scadute"]];
const TIPO = { cortesia: "Fattura", promemoria: "Promemoria", sollecito: "Sollecito" };
const quando = (s) => { const d = new Date(s); return `${d.toLocaleDateString("it-IT")} ore ${d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })}`; };

const Riga = ({ r, sel, onSel }) => (
  <tr className={`${r.scaduto > 0 ? "" : "bg-amber-50/30"} hover:bg-slate-50`} data-testid={`sollecito-row-${r.party_id}`}>
    <td className="px-3 py-2.5"><Checkbox checked={sel} onCheckedChange={onSel} data-testid={`sollecito-check-${r.party_id}`} /></td>
    <td className="px-3 py-2.5">
      <div className="font-semibold text-slate-800">{r.cliente}</div>
      <div className={`text-xs ${r.email ? "text-slate-500" : "text-rose-600"}`}>{r.email || "senza email/PEC"}</div>
      <div className="mt-1 inline-flex items-center gap-1 rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600" data-testid={`sollecito-agg-${r.party_id}`}>
        <Clock className="h-3 w-3" />Aggiornamento {r.auto ? "automatico" : "manuale"} del {quando(r.aggiornato_il)}
      </div>
    </td>
    <td className="mono px-3 py-2.5 text-right">{r.scaduto > 0 ? <span className="font-bold text-rose-700">{fmtEUR(r.scaduto)}</span> : "—"}<div className="text-xs text-slate-500">{r.n_scadute ? `${r.n_scadute} rate · ${r.max_ritardo} gg` : ""}</div></td>
    <td className="px-3 py-2.5 text-center">{r.livello ? <span className="rounded-full bg-rose-100 px-2 py-0.5 text-xs font-semibold text-rose-800">{r.livello}°</span> : "—"}</td>
    <td className="mono px-3 py-2.5 text-right">{r.in_scadenza > 0 ? fmtEUR(r.in_scadenza) : "—"}<div className="text-xs text-slate-500">{r.prossima_scadenza ? `dal ${fmtDate(r.prossima_scadenza)}` : ""}</div></td>
    <td className="px-3 py-2.5 text-center text-sm">{r.fatture_aperte}</td>
    <td className="px-3 py-2.5 text-xs text-slate-600">{r.ultimo_invio ? <>{TIPO[r.ultimo_invio.tipo] || r.ultimo_invio.tipo}{r.ultimo_invio.livello ? ` ${r.ultimo_invio.livello}°` : ""}<div>{quando(r.ultimo_invio.at)}</div></> : "mai"}</td>
  </tr>
);

const esito = (d) => {
  const ok = `Inviati: ${d.fatture} fatture, ${d.promemoria} promemoria, ${d.solleciti} solleciti`;
  if (d.errori.length) toast.error(`${ok}. Non inviati: ${d.errori.map((e) => `${e.cliente} (${e.errore})`).join("; ")}`, { duration: 10000 });
  else toast.success(ok);
  if (d.saltati.length) toast.info(`Saltati: ${d.saltati.map((s) => `${s.cliente} – ${s.motivo}`).join("; ")}`, { duration: 8000 });
};

export const SollecitiElenco = ({ edit, onSent }) => {
  const [d, setD] = useState(null);
  const [sel, setSel] = useState([]);
  const [cosa, setCosa] = useState(["scadenze"]);
  const [busy, setBusy] = useState(false);
  const load = () => api.get("/comunicazioni/elenco").then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, []);
  const aggiorna = async () => { setBusy(true); try { await api.post("/comunicazioni/elenco/aggiorna"); await load(); toast.success("Elenco aggiornato"); } catch (e) { toast.error(errMsg(e)); } setBusy(false); };
  const invia = async () => {
    if (!window.confirm(`Invio a ${sel.length} clienti: ${COSA.filter(([k]) => cosa.includes(k)).map(([, l]) => l.toLowerCase()).join(", ")}. Continuare?`)) return;
    setBusy(true);
    try { const { data } = await api.post("/comunicazioni/elenco/invia", { party_ids: sel, cosa }); esito(data); setSel([]); await load(); onSent?.(); } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };
  if (!d) return null;
  const all = d.righe.length > 0 && sel.length === d.righe.length;

  return (
    <div className="mb-6 rounded-xl border border-slate-200 bg-white" data-testid="solleciti-elenco">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
        <div>
          <h3 className="font-semibold text-slate-800">Clienti da sollecitare</h3>
          <p className="text-xs text-slate-500" data-testid="solleciti-stato">Rate scadute o in scadenza · aggiornato ogni giorno in automatico · ultimo aggiornamento {d.stato.auto ? "automatico" : "manuale"} del {quando(d.stato.at)}</p>
        </div>
        {edit && <Button variant="outline" size="sm" onClick={aggiorna} disabled={busy} data-testid="solleciti-aggiorna-btn"><RefreshCw className={`mr-1.5 h-4 w-4 ${busy ? "animate-spin" : ""}`} />Aggiorna ora</Button>}
      </div>
      {edit && (
        <div className="flex flex-wrap items-center gap-4 border-b border-slate-100 bg-slate-50 px-5 py-3">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Cosa inviare</span>
          {COSA.map(([k, l]) => (
            <label key={k} className="flex items-center gap-2 text-sm text-slate-700">
              <Checkbox checked={cosa.includes(k)} onCheckedChange={(v) => setCosa(v ? [...cosa, k] : cosa.filter((x) => x !== k))} data-testid={`solleciti-cosa-${k}`} />{l}
            </label>
          ))}
          <Button size="sm" className="ml-auto" onClick={invia} disabled={busy || !sel.length || !cosa.length} data-testid="solleciti-invia-btn"><Send className="mr-1.5 h-4 w-4" />Invia ai selezionati ({sel.length})</Button>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm" data-testid="solleciti-table">
          <thead className="text-left text-xs uppercase tracking-wider text-slate-500">
            <tr className="border-b border-slate-200">
              <th className="px-3 py-2.5"><Checkbox checked={all} onCheckedChange={(v) => setSel(v ? d.righe.map((r) => r.party_id) : [])} data-testid="solleciti-check-all" /></th>
              <th className="px-3 py-2.5 font-medium">Cliente</th><th className="px-3 py-2.5 text-right font-medium">Scaduto</th><th className="px-3 py-2.5 text-center font-medium">Livello</th>
              <th className="px-3 py-2.5 text-right font-medium">In scadenza</th><th className="px-3 py-2.5 text-center font-medium">Fatture</th><th className="px-3 py-2.5 font-medium">Ultimo invio</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {d.righe.map((r) => <Riga key={r.party_id} r={r} sel={sel.includes(r.party_id)} onSel={(v) => setSel(v ? [...sel, r.party_id] : sel.filter((x) => x !== r.party_id))} />)}
            {!d.righe.length && <tr><td colSpan={7} className="px-4 py-8 text-center text-sm text-slate-500" data-testid="solleciti-empty">Nessun cliente con rate scadute o in scadenza</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
};

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Download, FileCheck2, ShieldCheck, Paperclip, Send } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate, fmtDateTime } from "@/lib/fe";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";

const STATO = {
  to_be_stored: ["Caricato", "bg-amber-100 text-amber-800"], sent: ["Inviato", "bg-amber-100 text-amber-800"],
  sent_metadata: ["In conservazione", "bg-blue-100 text-blue-800"], stored: ["Conservato", "bg-emerald-100 text-emerald-800"],
};

export const scarica = async (url, name) => {
  try {
    const { data } = await api.get(url, { responseType: "blob" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(data);
    a.download = name;
    a.click();
    URL.revokeObjectURL(a.href);
  } catch (e) { toast.error(errMsg(e)); }
};

const toggle = (set, id) => set((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

export const ConsCandidati = ({ tipo, anno, canEdit, onDone }) => {
  const [items, setItems] = useState([]);
  const [sel, setSel] = useState([]);
  const [busy, setBusy] = useState(false);
  const load = (alive = () => true) => api.get("/conservazione/candidati", { params: { tipo, anno } }).then(({ data }) => { if (alive()) setItems(data.items.filter((i) => !i.archiviato)); }).catch((e) => toast.error(errMsg(e)));
  useEffect(() => {
    let on = true;
    setSel([]); setItems([]); load(() => on);
    return () => { on = false; };
  }, [tipo, anno]); // eslint-disable-line react-hooks/exhaustive-deps
  const archivia = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/conservazione/archivia", { tipo, anno, rif: sel });
      toast.success(`${data.archiviati === 1 ? "Archiviato 1 documento" : `Archiviati ${data.archiviati} documenti`}${data.gia_presenti ? ` · ${data.gia_presenti} già presenti` : ""}`);
      data.errori.forEach((x) => toast.error(x.errore));
      setSel([]); load(); onDone();
    } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };
  return (
    <div className="mb-6 rounded-xl border border-slate-200 bg-white p-5" data-testid="cons-candidati">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h3 className="font-semibold text-slate-800">Da archiviare ({items.length})</h3>
        {canEdit && items.length > 0 && (
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => setSel(items.filter((i) => !i.nota).map((i) => i.rif))} data-testid="cons-sel-tutti">Seleziona tutti</Button>
            <Button size="sm" onClick={archivia} disabled={busy || !sel.length} data-testid="cons-archivia-btn"><FileCheck2 className="mr-2 h-4 w-4" />Archivia ({sel.length})</Button>
          </div>
        )}
      </div>
      {items.length === 0 ? <p className="text-sm text-slate-500" data-testid="cons-candidati-vuoto">Tutto archiviato per questo anno.</p> : (
        <div className="max-h-72 divide-y divide-slate-100 overflow-y-auto">
          {items.map((i) => (
            <label key={i.rif} className="flex items-center gap-3 py-2 text-sm" data-testid={`cons-cand-${i.rif}`}>
              {canEdit && <Checkbox checked={sel.includes(i.rif)} disabled={!!i.nota} onCheckedChange={() => toggle(setSel, i.rif)} data-testid={`cons-cand-check-${i.rif}`} />}
              <span className="flex-1 text-slate-800">{i.label}</span>
              <span className="text-xs text-slate-500">{i.nota || fmtDate(i.data)}</span>
              {i.importo != null && <span className="w-28 text-right tabular-nums text-slate-700">{fmtEUR(i.importo)}</span>}
            </label>
          ))}
        </div>
      )}
    </div>
  );
};

const Azioni = ({ d, onVerifica }) => (
  <div className="flex items-center justify-end gap-1">
    <button title="Scarica il documento" onClick={() => scarica(`/conservazione/${d.id}/file`, d.file_name)} className="rounded p-1.5 text-slate-500 hover:bg-slate-100" data-testid={`cons-file-${d.id}`}><Download className="h-4 w-4" /></button>
    {d.allegati.map((a, i) => (
      <button key={a.file_name} title={a.file_name} onClick={() => scarica(`/conservazione/${d.id}/file?allegato=${i}`, a.file_name)} className="rounded p-1.5 text-slate-500 hover:bg-slate-100" data-testid={`cons-allegato-${d.id}-${i}`}><Paperclip className="h-4 w-4" /></button>
    ))}
    <button title="Verifica che il file non sia stato modificato" onClick={() => onVerifica(d)} className="rounded p-1.5 text-slate-500 hover:bg-slate-100" data-testid={`cons-verifica-${d.id}`}><ShieldCheck className="h-4 w-4" /></button>
    {d.acube?.receipt_at && <button title="Ricevuta del conservatore" onClick={() => scarica(`/conservazione/${d.id}/ricevuta`, `Ricevuta_conservazione_${d.file_name.replace(/\.[^.]+$/, "")}.pdf`)} className="rounded p-1.5 text-emerald-600 hover:bg-emerald-50" data-testid={`cons-ricevuta-${d.id}`}><FileCheck2 className="h-4 w-4" /></button>}
  </div>
);

const Stato = ({ d }) => {
  if (!d.conservatore) return <span className="text-xs text-slate-500">Solo archivio interno</span>;
  if (!d.acube) return <span className="text-xs text-slate-500">Da inviare</span>;
  const [l, cls] = STATO[d.acube.status] || ["Inviato", "bg-amber-100 text-amber-800"];
  return (
    <div>
      <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${cls}`} data-testid={`cons-stato-${d.id}`}>{l}</span>
      {d.acube.error && <div className="mt-1 max-w-xs text-xs text-rose-600" data-testid={`cons-errore-${d.id}`}>{d.acube.error}</div>}
    </div>
  );
};

export const ConsArchivio = ({ docs, canEdit, collegato, onChanged }) => {
  const [sel, setSel] = useState([]);
  const [busy, setBusy] = useState(false);
  const inviabili = docs.filter((d) => d.conservatore && !d.acube?.sent_metadata_at);
  useEffect(() => { setSel([]); }, [docs]);
  const invia = async () => {
    if (!window.confirm(`Invio ${sel.length} documenti al conservatore A-Cube. In ambiente reale ogni invio è a pagamento. Continuare?`)) return;
    setBusy(true);
    try {
      const { data } = await api.post("/conservazione/invia", { ids: sel });
      toast.success(`Inviati ${data.inviati} documenti${data.errori.length ? ` · ${data.errori.length} con errore` : ""}`);
      onChanged();
    } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };
  const verifica = async (d) => {
    try { const { data } = await api.post(`/conservazione/${d.id}/verifica`); data.ok ? toast.success("Documento integro: l'impronta coincide") : toast.error("Attenzione: il documento risulta modificato"); onChanged(); }
    catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div className="rounded-xl border border-slate-200 bg-white" data-testid="cons-archivio">
      <div className="flex flex-wrap items-center justify-between gap-3 p-5">
        <h3 className="font-semibold text-slate-800">In archivio ({docs.length})</h3>
        {canEdit && collegato && inviabili.length > 0 && (
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => setSel(inviabili.map((d) => d.id))} data-testid="cons-sel-inviabili">Seleziona da inviare</Button>
            <Button size="sm" onClick={invia} disabled={busy || !sel.length} data-testid="cons-invia-btn"><Send className="mr-2 h-4 w-4" />Invia al conservatore ({sel.length})</Button>
          </div>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-y border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr><th className="w-8 px-4 py-2" /><th className="px-4 py-2 font-medium">Documento</th><th className="px-4 py-2 font-medium">Archiviato</th><th className="px-4 py-2 font-medium">Conservare fino al</th><th className="px-4 py-2 font-medium">Impronta</th><th className="px-4 py-2 font-medium">Conservatore</th><th className="px-4 py-2" /></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {docs.map((d) => (
              <tr key={d.id} data-testid={`cons-doc-${d.id}`}>
                <td className="px-4 py-2">{canEdit && collegato && inviabili.includes(d) && <Checkbox checked={sel.includes(d.id)} onCheckedChange={() => toggle(setSel, d.id)} data-testid={`cons-doc-check-${d.id}`} />}</td>
                <td className="px-4 py-2 text-slate-800">{d.titolo}<div className="text-xs text-slate-500">{d.file_name} · {(d.size / 1024).toFixed(1)} KB</div></td>
                <td className="px-4 py-2 text-xs text-slate-600">{fmtDateTime(d.created_at)}<div>{d.created_by}</div></td>
                <td className="px-4 py-2 text-xs text-slate-600">{fmtDate(d.conserva_fino)}</td>
                <td className="px-4 py-2 font-mono text-[11px] text-slate-500" title={d.sha256}>{d.sha256.slice(0, 12)}…{d.verifica && <div className={d.verifica.ok ? "text-emerald-600" : "text-rose-600"}>{d.verifica.ok ? "integro" : "modificato"} {fmtDate(d.verifica.at)}</div>}</td>
                <td className="px-4 py-2"><Stato d={d} /></td>
                <td className="px-4 py-2"><Azioni d={d} onVerifica={verifica} /></td>
              </tr>
            ))}
            {docs.length === 0 && <tr><td colSpan={7} className="px-4 py-10 text-center text-slate-500" data-testid="cons-archivio-vuoto">Nessun documento archiviato</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
};

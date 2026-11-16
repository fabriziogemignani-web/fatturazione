import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const today = () => new Date().toISOString().slice(0, 10);

const Parametri = ({ f, setF }) => {
  const fld = (k, label, type = "number", cls = "w-36") => (
    <label className="text-xs text-slate-600">{label}<Input type={type} step={k === "giorni" ? 1 : 0.01} min={0} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} className={cls} data-testid={`blocco-${k}`} /></label>
  );
  return (
    <>
      {fld("dal", "Scadenze dal", "date", "w-40")}
      {fld("al", "al", "date", "w-40")}
      {fld("data", "Data insoluto", "date", "w-40")}
      {fld("giorni", "Nuova scadenza tra (giorni)", "number", "w-28")}
      {fld("spese_banca", "Spese banca per effetto € (vuoto = da banca)")}
      {fld("spese_cliente", "Spese al cliente € (vuoto = da anagrafica)")}
    </>
  );
};

export const RibaInsolutiBlocco = ({ onDone }) => {
  const [rows, setRows] = useState(null);
  const [sel, setSel] = useState({});
  const [f, setF] = useState({ dal: "", al: "", data: today(), giorni: 30, spese_banca: "", spese_cliente: "", avvisa: true });
  const [busy, setBusy] = useState(false);
  const [v, setV] = useState(0);
  const load = useCallback(() => { api.get("/riba/scaduti", { params: { in_scadenza: true } }).then(({ data }) => setRows(data)).catch((e) => toast.error(errMsg(e))); }, []);
  useEffect(() => { load(); }, [load]);
  const shown = useMemo(() => (rows || []).filter((r) => (!f.dal || r.scadenza >= f.dal) && (!f.al || r.scadenza <= f.al)), [rows, f.dal, f.al]);
  const scelti = shown.filter((r) => sel[r.id] && r.stato === "maturato");
  const scadute = shown.filter((r) => r.stato === "maturato");
  const num = (v) => (v === "" || v === null ? null : Number(v));
  const registra = async () => {
    if (!window.confirm(`Registrare ${scelti.length} effetti come insoluti? Per ognuno la partita viene riaperta con nuova scadenza e viene fatta la registrazione in prima nota.`)) return;
    setBusy(true);
    try {
      const { data } = await api.post("/riba/insoluti", { effetti: scelti.map((r) => r.id), data: f.data, giorni: Number(f.giorni) || 0, spese_banca: num(f.spese_banca), spese_cliente: num(f.spese_cliente), avvisa: f.avvisa });
      if (data.registrati) toast.success(`${data.registrati} insoluti registrati · nuova scadenza ${fmtDate(data.nuova_scadenza)}${f.avvisa ? ` · ${data.avvisi} avvisi email inviati` : ""}`);
      data.errori.forEach((x) => toast.error(`${rows.find((r) => r.id === x.id)?.numero_display || ""}: ${x.errore}`));
      setSel({});
      load();
      setV((x) => x + 1);
      onDone?.();
    } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };
  if (!rows) return <p className="text-sm text-slate-500">Caricamento…</p>;
  return (
    <div data-testid="riba-blocco">
      <div className="mb-4 flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <Parametri f={f} setF={setF} />
        <label className="flex items-center gap-2 pb-2 text-xs text-slate-600"><input type="checkbox" checked={f.avvisa} onChange={(e) => setF({ ...f, avvisa: e.target.checked })} data-testid="blocco-avvisa" />Invia avviso email al cliente</label>
        <div className="ml-auto text-right text-sm">
          <div className="text-xs text-slate-500" data-testid="blocco-selezione">{scelti.length} effetti selezionati</div>
          <div className="font-bold" data-testid="blocco-totale">{fmtEUR(scelti.reduce((s, r) => s + r.importo, 0))}</div>
        </div>
        <Button onClick={registra} disabled={!scelti.length || busy} className="bg-rose-600 hover:bg-rose-700" data-testid="blocco-registra-btn">{busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Registra insoluti</Button>
        <p className="w-full text-xs text-slate-500">Per ogni effetto: storno in banca (addebito al cliente), spese insoluto della banca su oneri bancari e riaddebito al cliente se previsto in anagrafica; la rata torna aperta nello scadenzario con la nuova scadenza. Gli effetti non ancora scaduti sono solo da consultare.</p>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm" data-testid="blocco-table">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr>
              <th className="px-4 py-3"><input type="checkbox" checked={scadute.length > 0 && scelti.length === scadute.length} onChange={(e) => setSel(e.target.checked ? Object.fromEntries(scadute.map((r) => [r.id, true])) : {})} data-testid="blocco-select-all" /></th>
              <th className="px-4 py-3 font-medium">Scadenza</th><th className="px-4 py-3 font-medium">Cliente</th><th className="px-4 py-3 font-medium">Documento</th><th className="px-4 py-3 font-medium">Distinta</th><th className="px-4 py-3 font-medium">Stato</th><th className="px-4 py-3 text-right font-medium">Importo</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {shown.length === 0 && <tr><td colSpan={7} className="px-4 py-10 text-center text-slate-500" data-testid="blocco-empty">Nessun effetto in scadenza nel periodo</td></tr>}
            {shown.map((r) => (
              <tr key={r.id} className={`hover:bg-slate-50 ${sel[r.id] ? "bg-rose-50/40" : ""}`} data-testid={`blocco-row-${r.id}`}>
                <td className="px-4 py-3"><input type="checkbox" disabled={r.stato !== "maturato"} checked={!!sel[r.id] && r.stato === "maturato"} onChange={(e) => setSel({ ...sel, [r.id]: e.target.checked })} data-testid={`blocco-check-${r.id}`} /></td>
                <td className="px-4 py-3 font-medium">{fmtDate(r.scadenza)}</td>
                <td className="px-4 py-3">{r.cliente.denominazione}</td>
                <td className="mono px-4 py-3">{r.numero_display}</td>
                <td className="mono px-4 py-3 text-xs">{r.distinta_numero || ""}</td>
                <td className="px-4 py-3"><span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${r.stato === "maturato" ? "bg-amber-100 text-amber-800" : "bg-sky-100 text-sky-800"}`} data-testid={`blocco-stato-${r.id}`}>{r.stato === "maturato" ? "Scaduto" : "In scadenza"}</span></td>
                <td className="px-4 py-3 text-right font-semibold">{fmtEUR(r.importo)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <InsolutiRegistrati key={v} />
    </div>
  );
};

const InsolutiRegistrati = () => {
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(null);
  const load = useCallback(() => { api.get("/riba/insoluti-registrati").then(({ data }) => setRows(data)).catch(() => {}); }, []);
  useEffect(() => { load(); }, [load]);
  const invia = async (r) => {
    setBusy(r.id);
    try { const { data } = await api.post(`/riba/effetti/${r.id}/avviso`); toast.success(`Avviso inviato a ${data.to}`); load(); } catch (e) { toast.error(errMsg(e)); }
    setBusy(null);
  };
  if (!rows.length) return null;
  return (
    <div className="mt-6 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm" data-testid="insoluti-registrati">
      <div className="border-b border-slate-200 px-4 py-3 text-sm font-semibold">Insoluti registrati · avvisi ai clienti</div>
      <table className="w-full text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
          <tr><th className="px-4 py-2">Insoluto</th><th className="px-4 py-2">Cliente</th><th className="px-4 py-2">Documento</th><th className="px-4 py-2 text-right">Importo + spese</th><th className="px-4 py-2">Nuova scadenza</th><th className="px-4 py-2">Avviso</th></tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r) => (
            <tr key={r.id} data-testid={`ins-row-${r.id}`}>
              <td className="px-4 py-2 text-xs">{fmtDate(r.insoluto.data)}</td>
              <td className="px-4 py-2">{r.cliente.denominazione}</td>
              <td className="mono px-4 py-2 text-xs">{r.numero_display}</td>
              <td className="px-4 py-2 text-right text-xs">{fmtEUR(r.importo)}{r.insoluto.spese_cliente ? ` + ${fmtEUR(r.insoluto.spese_cliente)}` : ""}</td>
              <td className="px-4 py-2 text-xs">{fmtDate(r.insoluto.nuova_scadenza)}</td>
              <td className="px-4 py-2 text-xs">
                {r.avviso && <span className="mr-2 text-emerald-700" data-testid={`ins-avviso-${r.id}`}>Inviato il {fmtDate(r.avviso.inviato_il.slice(0, 10))}</span>}
                <Button size="sm" variant="outline" disabled={busy === r.id} onClick={() => invia(r)} data-testid={`ins-avviso-btn-${r.id}`}>{r.avviso ? "Reinvia" : "Invia avviso"}</Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Send, Loader2, CheckCircle2, XCircle } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate, STATUS } from "@/lib/fe";
import { useCompany } from "@/context/CompanyContext";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const iso = (d) => d.toISOString().slice(0, 10);
const inizioMese = () => { const d = new Date(); return iso(new Date(Date.UTC(d.getFullYear(), d.getMonth(), 1))); };
const tipoDoc = (r) => (r.autofattura ? `Autofattura ${r.tipo_documento}` : r.tipo_documento === "TD04" ? "Nota di credito" : "Fattura");

const Esiti = ({ res, onClose }) => (
  <div className="mb-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm" data-testid="invio-esiti">
    <div className="mb-2 flex items-center justify-between">
      <b className="text-sm">Esito invio: {res.inviate} {res.inviate === 1 ? "inviata" : "inviate"}{res.errori ? `, ${res.errori} con errori` : ""}</b>
      <button onClick={onClose} className="text-xs text-slate-500 hover:underline" data-testid="invio-esiti-chiudi">Chiudi</button>
    </div>
    <ul className="space-y-1 text-xs">
      {res.risultati.map((r) => (
        <li key={r.id} className="flex items-start gap-2" data-testid={`invio-esito-${r.id}`}>
          {r.ok ? <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" /> : <XCircle className="h-4 w-4 shrink-0 text-rose-600" />}
          <span><Link to={`/fatture/${r.id}`} className="mono font-medium text-blue-700 hover:underline">{r.numero_display}</Link> {r.ok ? "trasmessa allo SDI" : <span className="text-rose-700">{r.errore}</span>}</span>
        </li>
      ))}
    </ul>
  </div>
);

const Riga = ({ r, on, toggle }) => (
  <tr onClick={toggle} className={`cursor-pointer transition-colors ${on ? "bg-blue-50" : "hover:bg-slate-50"}`} data-testid={`invio-row-${r.id}`}>
    <td className="px-4 py-3"><input type="checkbox" checked={on} onChange={toggle} onClick={(e) => e.stopPropagation()} className="h-4 w-4 cursor-pointer" data-testid={`invio-check-${r.id}`} /></td>
    <td className="whitespace-nowrap px-4 py-3">{fmtDate(r.data)}</td>
    <td className="px-4 py-3"><span className="mono font-medium">{r.numero_display}</span><div className="text-xs text-slate-400">{tipoDoc(r)}</div></td>
    <td className="px-4 py-3">{r.cliente?.denominazione}</td>
    <td className="px-4 py-3"><span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${STATUS[r.status]?.cls}`}>{STATUS[r.status]?.label}</span></td>
    <td className="px-4 py-3 text-right font-semibold">{fmtEUR(r.totale)}</td>
  </tr>
);

export default function InvioSdi() {
  const { company } = useCompany();
  const [dal, setDal] = useState(inizioMese());
  const [al, setAl] = useState(iso(new Date()));
  const [rows, setRows] = useState(null);
  const [sel, setSel] = useState(new Set());
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const load = useCallback(() => {
    api.get("/invio-sdi/da-inviare", { params: { dal: dal || undefined, al: al || undefined } }).then(({ data }) => { setRows(data); setSel(new Set()); }).catch((e) => toast.error(errMsg(e)));
  }, [dal, al]);
  useEffect(() => { load(); }, [load, company?.id]);
  const tot = useMemo(() => (rows || []).filter((r) => sel.has(r.id)).reduce((s, r) => s + r.totale, 0), [rows, sel]);
  const toggle = (id) => { const n = new Set(sel); if (n.has(id)) n.delete(id); else n.add(id); setSel(n); };
  const tutte = rows?.length > 0 && sel.size === rows.length;
  const invia = async () => {
    if (!window.confirm(`Inviare allo SDI ${sel.size} ${sel.size === 1 ? "documento" : "documenti"} per ${fmtEUR(tot)}? Dopo l'invio non saranno più modificabili.`)) return;
    setBusy(true);
    try {
      const { data } = await api.post("/invio-sdi", { ids: [...sel] });
      setRes(data);
      if (data.inviate) toast.success(`${data.inviate} ${data.inviate === 1 ? "documento trasmesso" : "documenti trasmessi"} allo SDI`);
      if (data.errori) toast.error(`${data.errori} non ${data.errori === 1 ? "inviato" : "inviati"}: vedi il dettaglio`);
      load();
    } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };
  return (
    <div>
      <PageHeader eyebrow="Vendite" title="Invio massivo allo SDI" />
      <div className="mb-4 flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <label className="text-xs text-slate-600">Dal<Input type="date" value={dal} onChange={(e) => setDal(e.target.value)} className="w-40" data-testid="invio-dal" /></label>
        <label className="text-xs text-slate-600">Al<Input type="date" value={al} onChange={(e) => setAl(e.target.value)} className="w-40" data-testid="invio-al" /></label>
        <Button variant="outline" onClick={() => setSel(tutte ? new Set() : new Set(rows.map((r) => r.id)))} disabled={!rows?.length} data-testid="invio-seleziona-tutte">{tutte ? "Deseleziona tutte" : "Seleziona tutte"}</Button>
        <div className="ml-auto text-right">
          <div className="text-xs text-slate-500" data-testid="invio-selezione">{sel.size} di {rows?.length || 0} selezionate</div>
          <div className="text-lg font-bold" data-testid="invio-totale">{fmtEUR(tot)}</div>
        </div>
        <Button onClick={invia} disabled={!sel.size || busy} className="bg-blue-600 hover:bg-blue-700" data-testid="invio-invia-btn">
          {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}Invia allo SDI ({sel.size})
        </Button>
        <p className="w-full text-xs text-slate-500">Sono elencate solo le fatture, note di credito e autofatture ancora da inviare (bozze e scartate da reinviare) con data nel periodo. Clicca una riga per selezionarla. I documenti vengono inviati in ordine di data e numero.</p>
      </div>
      {res && <Esiti res={res} onClose={() => setRes(null)} />}
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm" data-testid="invio-table">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr><th className="w-10 px-4 py-3" /><th className="px-4 py-3 font-medium">Data</th><th className="px-4 py-3 font-medium">Documento</th><th className="px-4 py-3 font-medium">Cliente</th><th className="px-4 py-3 font-medium">Stato</th><th className="px-4 py-3 text-right font-medium">Totale</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {!rows && <tr><td colSpan={6} className="px-4 py-10 text-center text-slate-500">Caricamento…</td></tr>}
            {rows?.length === 0 && <tr><td colSpan={6} className="px-4 py-10 text-center text-slate-500" data-testid="invio-empty">Nessuna fattura da inviare nel periodo</td></tr>}
            {rows?.map((r) => <Riga key={r.id} r={r} on={sel.has(r.id)} toggle={() => toggle(r.id)} />)}
          </tbody>
        </table>
      </div>
    </div>
  );
}

import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { FileUp, AlertTriangle, Loader2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { useCompany } from "@/context/CompanyContext";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { InsolutoDialog, RibaDistinte } from "@/components/RibaDistinte";
import { RibaInsolutiBlocco } from "@/components/RibaInsolutiBlocco";

const today = () => new Date().toISOString().slice(0, 10);
const TABS = [["presentare", "Da presentare"], ["distinte", "Distinte"], ["insoluti", "Insoluti in blocco"]];

const DaPresentare = ({ onCreated }) => {
  const { company } = useCompany();
  const [rows, setRows] = useState(null);
  const [sel, setSel] = useState({});
  const [fino, setFino] = useState("");
  const [banche, setBanche] = useState([]);
  const [iban, setIban] = useState("");
  const [data, setData] = useState(today());
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => { api.get("/riba/da-presentare").then(({ data: d }) => setRows(d)).catch((e) => toast.error(errMsg(e))); }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api.get("/company").then(({ data: c }) => { setBanche(c.banche || []); setIban((c.banche || []).find((b) => b.predefinita)?.iban || c.banche?.[0]?.iban || ""); }).catch(() => {});
  }, [company?.id]);
  const shown = useMemo(() => (rows || []).filter((r) => !fino || r.scadenza <= fino), [rows, fino]);
  const scelti = shown.filter((r) => sel[r.key]);
  const tot = scelti.reduce((s, r) => s + r.importo, 0);
  const crea = async () => {
    setBusy(true);
    try {
      const { data: d } = await api.post("/riba/distinte", { banca_iban: iban, data, effetti: scelti.map((r) => r.key) });
      toast.success(`Distinta ${d.numero_display} creata: ${d.n_effetti} effetti per ${fmtEUR(d.totale)}`);
      setSel({});
      load();
      onCreated();
    } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };
  if (!rows) return <p className="text-sm text-slate-500">Caricamento…</p>;
  const b = banche.find((x) => x.iban === iban);
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <label className="text-xs text-slate-600">Scadenze fino al<Input type="date" value={fino} onChange={(e) => setFino(e.target.value)} className="w-40" data-testid="riba-fino-input" /></label>
        <label className="text-xs text-slate-600">Banca di presentazione
          <Select value={iban} onValueChange={setIban}>
            <SelectTrigger className="w-64 bg-white" data-testid="riba-banca-select"><SelectValue placeholder="Scegli la banca" /></SelectTrigger>
            <SelectContent className="bg-white">{banche.map((x) => <SelectItem key={x.iban} value={x.iban}>{x.nome}</SelectItem>)}</SelectContent>
          </Select>
        </label>
        <label className="text-xs text-slate-600">Data distinta<Input type="date" value={data} onChange={(e) => setData(e.target.value)} className="w-40" data-testid="riba-data-input" /></label>
        <div className="ml-auto text-right text-sm">
          <div className="text-xs text-slate-500" data-testid="riba-selezione">{scelti.length} effetti selezionati</div>
          <div className="font-bold" data-testid="riba-totale">{fmtEUR(tot)}</div>
        </div>
        <Button onClick={crea} disabled={!scelti.length || !iban || busy} data-testid="riba-crea-btn">{busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Crea distinta</Button>
        {b && !b.sia && <p className="w-full text-xs text-amber-700" data-testid="riba-sia-warning">Per il flusso CBI inserisci il codice SIA della banca {b.nome} in Dati azienda → Banche.</p>}
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm" data-testid="riba-presentare-table">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr>
              <th className="px-4 py-3"><input type="checkbox" checked={shown.length > 0 && scelti.length === shown.length} onChange={(e) => setSel(e.target.checked ? Object.fromEntries(shown.map((r) => [r.key, true])) : {})} data-testid="riba-select-all" /></th>
              <th className="px-4 py-3 font-medium">Scadenza</th><th className="px-4 py-3 font-medium">Cliente</th><th className="px-4 py-3 font-medium">Documento</th><th className="px-4 py-3 font-medium">Banca d'appoggio</th><th className="px-4 py-3 text-right font-medium">Importo</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {shown.length === 0 && <tr><td colSpan={6} className="px-4 py-10 text-center text-slate-500" data-testid="riba-presentare-empty">Nessuna scadenza con pagamento Ri.Ba. (MP12) da presentare</td></tr>}
            {shown.map((r) => (
              <tr key={r.key} className="hover:bg-slate-50" data-testid={`riba-row-${r.key}`}>
                <td className="px-4 py-3"><input type="checkbox" checked={!!sel[r.key]} onChange={(e) => setSel({ ...sel, [r.key]: e.target.checked })} data-testid={`riba-check-${r.key}`} /></td>
                <td className="px-4 py-3 font-medium">{fmtDate(r.scadenza)}</td>
                <td className="px-4 py-3">{r.cliente.denominazione}</td>
                <td className="mono px-4 py-3">{r.numero_display}{r.rate_totali > 1 && <span className="ml-1 text-xs text-slate-400">rata {r.rata_n}/{r.rate_totali}</span>}</td>
                <td className="px-4 py-3 text-xs">{r.manca_appoggio ? <span className="inline-flex items-center gap-1 text-amber-700"><AlertTriangle className="h-3.5 w-3.5" />ABI/CAB mancanti in anagrafica</span> : `${r.cliente.appoggio_banca || ""} ABI ${r.cliente.appoggio_abi} CAB ${r.cliente.appoggio_cab}`}</td>
                <td className="px-4 py-3 text-right font-semibold">{fmtEUR(r.importo)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const Esiti = ({ onDone }) => {
  const [res, setRes] = useState(null);
  const [ins, setIns] = useState(null);
  const upload = async (e) => {
    const f = e.target.files[0];
    e.target.value = "";
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f);
    try { const { data } = await api.post("/riba/esiti", fd); setRes(data); } catch (err) { toast.error(errMsg(err)); }
  };
  return (
    <div className="mb-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm" data-testid="riba-esiti">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><b className="text-sm">Esiti insoluti dalla banca</b><p className="text-xs text-slate-500">Carica il file CBI degli insoluti: gli effetti vengono abbinati per numero ricevuta, importo e scadenza.</p></div>
        <label className="inline-flex cursor-pointer items-center rounded-md border border-slate-200 px-3 py-2 text-sm hover:bg-slate-50"><FileUp className="mr-2 h-4 w-4" />Carica file esiti<input type="file" accept=".txt,.cbi,.dat,text/plain" className="hidden" onChange={upload} data-testid="riba-esiti-input" /></label>
      </div>
      {res && (
        <div className="mt-3 divide-y divide-slate-100 text-sm" data-testid="riba-esiti-result">
          {res.map((x, i) => (
            <div key={i} className="flex items-center justify-between py-2" data-testid={`riba-esito-${i}`}>
              <span>{fmtDate(x.riga.scadenza)} · {fmtEUR(x.riga.importo)} {x.effetto ? `· ${x.effetto.cliente.denominazione} · ${x.effetto.numero_display}` : ""}</span>
              {x.effetto ? (x.effetto.stato === "insoluto" ? <span className="text-xs text-slate-500">Registrato</span>
                : x.effetto.stato === "presentato" ? <span className="text-xs text-slate-500" data-testid={`riba-esito-non-scaduto-${i}`}>Non ancora scaduto</span>
                : <Button size="sm" variant="outline" className="text-rose-700" onClick={() => setIns(x.effetto)} data-testid={`riba-esito-insoluto-${i}`}>Registra insoluto</Button>)
                : <span className="text-xs text-amber-700">Nessun effetto corrispondente</span>}
            </div>
          ))}
        </div>
      )}
      <InsolutoDialog effetto={ins} onOpenChange={(o) => !o && setIns(null)} onDone={(e) => { setRes(res.map((x) => (x.effetto?.id === e.id ? { ...x, effetto: e } : x))); onDone(); }} />
    </div>
  );
};

export default function Riba() {
  const [tab, setTab] = useState("presentare");
  const [v, setV] = useState(0);
  return (
    <div>
      <PageHeader eyebrow="Contabilità generale" title="Effetti Ri.Ba." />
      <div className="mb-4 inline-flex rounded-lg border border-slate-200 bg-white p-1 text-xs font-semibold">
        {TABS.map(([k, l]) => <button key={k} onClick={() => setTab(k)} className={`rounded-md px-3 py-1.5 transition-colors ${tab === k ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-50"}`} data-testid={`riba-tab-${k}`}>{l}</button>)}
      </div>
      {tab === "presentare" ? <DaPresentare onCreated={() => setTab("distinte")} /> : tab === "insoluti" ? <RibaInsolutiBlocco /> : <><Esiti onDone={() => setV(v + 1)} /><RibaDistinte key={v} /></>}
    </div>
  );
}

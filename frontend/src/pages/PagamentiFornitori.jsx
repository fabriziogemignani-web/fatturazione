import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { AlertTriangle, Download, FileText, Loader2, Trash2, ChevronDown, ChevronRight } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { useCompany } from "@/context/CompanyContext";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const iso = (d) => d.toISOString().slice(0, 10);
const today = () => iso(new Date());
const fineMese = () => { const d = new Date(); return iso(new Date(Date.UTC(d.getFullYear(), d.getMonth() + 1, 0))); };
const num = (v) => Number(String(v).replace(",", ".")) || 0;
const TABS = [["pagare", "Scadenze da pagare"], ["distinte", "Distinte di pagamento"]];

const useBanche = () => {
  const { company } = useCompany();
  const [banche, setBanche] = useState([]);
  useEffect(() => { api.get("/company").then(({ data: c }) => setBanche(c.banche || [])).catch(() => {}); }, [company?.id]);
  return banche;
};

const Filtri = ({ dal, al, setDal, setAl, banche, iban, setIban, data, setData }) => (
  <>
    <label className="text-xs text-slate-600">Scadenze dal<Input type="date" value={dal} onChange={(e) => setDal(e.target.value)} className="w-40" data-testid="pf-dal-input" /></label>
    <label className="text-xs text-slate-600">al<Input type="date" value={al} onChange={(e) => setAl(e.target.value)} className="w-40" data-testid="pf-al-input" /></label>
    <label className="text-xs text-slate-600">Banca di pagamento
      <Select value={iban} onValueChange={setIban}>
        <SelectTrigger className="w-60 bg-white" data-testid="pf-banca-select"><SelectValue placeholder="Scegli la banca" /></SelectTrigger>
        <SelectContent className="bg-white">{banche.map((x) => <SelectItem key={x.iban} value={x.iban} data-testid={`pf-banca-${x.iban}`}>{x.nome}</SelectItem>)}</SelectContent>
      </Select>
    </label>
    <label className="text-xs text-slate-600">Data pagamento<Input type="date" value={data} onChange={(e) => setData(e.target.value)} className="w-40" data-testid="pf-data-input" /></label>
  </>
);

const IbanCell = ({ r, value, onChange }) => {
  if (r.banche.length > 1) return (
    <select value={value} onChange={(e) => onChange(e.target.value)} className="mono mt-1 h-7 max-w-[260px] rounded border border-slate-200 bg-white px-1 text-[11px]" data-testid={`pf-iban-select-${r.key}`}>
      {r.banche.map((b) => <option key={b.iban} value={b.iban}>{(b.nome ? `${b.nome} · ` : "") + b.iban}</option>)}
    </select>
  );
  if (r.banche.length === 1) return <div className="mono text-[11px] text-slate-400">{r.iban}</div>;
  return (
    <div className="mt-1">
      <Input value={value} onChange={(e) => onChange(e.target.value.replace(/\s+/g, "").toUpperCase())} placeholder="Inserisci IBAN" className={`mono h-7 max-w-[260px] text-[11px] ${value ? "" : "border-amber-400"}`} data-testid={`pf-iban-input-${r.key}`} />
      <div className="mt-0.5 inline-flex items-center gap-1 text-[10px] text-amber-700"><AlertTriangle className="h-3 w-3" />{r.iban ? "IBAN letto dalla fattura: " : "IBAN mancante: "}verrà salvato in anagrafica</div>
    </div>
  );
};

const Riga = ({ r, imp, onToggle, onImp, iban, onIban }) => (
  <tr className={`hover:bg-slate-50 ${imp !== undefined ? "bg-blue-50/40" : ""}`} data-testid={`pf-row-${r.key}`}>
    <td className="px-4 py-3"><input type="checkbox" checked={imp !== undefined} onChange={(e) => onToggle(e.target.checked)} data-testid={`pf-check-${r.key}`} /></td>
    <td className={`px-4 py-3 font-medium ${r.scaduta ? "text-rose-700" : ""}`}>{fmtDate(r.scadenza)}{r.scaduta && <div className="text-[11px] font-normal">scaduta</div>}</td>
    <td className="px-4 py-3">{r.fornitore}<IbanCell r={r} value={iban} onChange={onIban} /></td>
    <td className="mono px-4 py-3">{r.numero_display}<div className="text-xs text-slate-400">del {fmtDate(r.data_doc)}{r.rate_totali > 1 ? ` · rata ${r.rata_n}/${r.rate_totali}` : ""}</div></td>
    <td className="px-4 py-3 text-right">{fmtEUR(r.residuo)}</td>
    <td className="px-4 py-3 text-right">
      {imp !== undefined ? <Input value={imp} onChange={(e) => onImp(e.target.value)} className="ml-auto h-8 w-28 text-right" data-testid={`pf-importo-${r.key}`} /> : <span className="text-slate-300">—</span>}
    </td>
  </tr>
);

const DaPagare = ({ onCreated }) => {
  const banche = useBanche();
  const [qs, setQs] = useSearchParams();
  const [rows, setRows] = useState(null);
  const [dal, setDal] = useState(qs.get("dal") || "");
  const [al, setAl] = useState(qs.get("al") || fineMese());
  const [sel, setSel] = useState({});
  const [ibf, setIbf] = useState({});
  const ibanOf = (r) => ibf[r.party_id] ?? r.iban;
  useEffect(() => {
    if (!rows || !qs.get("prepara")) return;
    const win = rows.filter((r) => (!dal || r.scadenza >= dal) && (!al || r.scadenza <= al));
    setSel(Object.fromEntries(win.filter((r) => r.iban).map((r) => [r.key, String(r.residuo)])));
    const senza = win.filter((r) => !r.iban).length;
    if (senza) toast.warning(`${senza} ${senza === 1 ? "scadenza non selezionata" : "scadenze non selezionate"}: manca l'IBAN del fornitore, inseriscilo nella riga`);
    setQs({}, { replace: true });
  }, [rows]); // eslint-disable-line react-hooks/exhaustive-deps
  const [iban, setIban] = useState("");
  const [data, setData] = useState(today());
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => { api.get("/pagamenti-fornitori/scadenze").then(({ data: d }) => setRows(d)).catch((e) => toast.error(errMsg(e))); }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (!iban && banche.length) setIban((banche.find((b) => b.predefinita) || banche[0]).iban); }, [banche, iban]);
  const shown = useMemo(() => (rows || []).filter((r) => (!dal || r.scadenza >= dal) && (!al || r.scadenza <= al)), [rows, dal, al]);
  const scelti = shown.filter((r) => sel[r.key] !== undefined);
  const tot = scelti.reduce((s, r) => s + num(sel[r.key]), 0);
  const toggle = (r, on) => { const n = { ...sel }; if (on) n[r.key] = String(r.residuo); else delete n[r.key]; setSel(n); };
  const crea = async () => {
    const senza = scelti.find((r) => !ibanOf(r));
    if (senza) { toast.error(`Inserisci l'IBAN di ${senza.fornitore} nella riga della scadenza`); return; }
    setBusy(true);
    try {
      const { data: d } = await api.post("/pagamenti-fornitori/distinte", { banca_iban: iban, data, voci: scelti.map((r) => ({ key: r.key, importo: num(sel[r.key]), iban: ibanOf(r) })) });
      toast.success(`Distinta ${d.numero_display} registrata: ${d.n_partite} partite, ${fmtEUR(d.totale)}${d.coge_rif ? ` · ${d.coge_rif}` : ""}${d.iban_salvati ? ` · ${d.iban_salvati} IBAN salvati in anagrafica` : ""}`);
      setSel({});
      setIbf({});
      load();
      onCreated();
    } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };
  if (!rows) return <p className="text-sm text-slate-500">Caricamento…</p>;
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <Filtri {...{ dal, al, setDal, setAl, banche, iban, setIban, data, setData }} />
        <div className="ml-auto text-right text-sm">
          <div className="text-xs text-slate-500" data-testid="pf-selezione">{scelti.length} partite selezionate</div>
          <div className="text-lg font-bold" data-testid="pf-totale">{fmtEUR(tot)}</div>
        </div>
        <Button onClick={crea} disabled={!scelti.length || !iban || busy} data-testid="pf-registra-btn">{busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Registra pagamento</Button>
        {!banche.length && <p className="w-full text-xs text-amber-700" data-testid="pf-no-banche">Aggiungi una banca in <Link to="/impostazioni" className="underline">Dati azienda → Banche</Link>.</p>}
        <p className="w-full text-xs text-slate-500">Con "Registra pagamento" il movimento va in prima nota (Dare fornitori / Avere banca), le partite si chiudono e lo scadenzario si aggiorna. Poi scarica il flusso CBI dalla distinta.</p>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm" data-testid="pf-scadenze-table">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr>
              <th className="px-4 py-3"><input type="checkbox" checked={shown.length > 0 && scelti.length === shown.length} onChange={(e) => setSel(e.target.checked ? Object.fromEntries(shown.map((r) => [r.key, String(r.residuo)])) : {})} data-testid="pf-select-all" /></th>
              <th className="px-4 py-3 font-medium">Scadenza</th><th className="px-4 py-3 font-medium">Fornitore</th><th className="px-4 py-3 font-medium">Documento</th>
              <th className="px-4 py-3 text-right font-medium">Da pagare</th><th className="px-4 py-3 text-right font-medium">Importo pagamento</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {shown.length === 0 && <tr><td colSpan={6} className="px-4 py-10 text-center text-slate-500" data-testid="pf-empty">Nessuna scadenza fornitore aperta nel periodo: allarga le date "dal / al" per vedere le altre</td></tr>}
            {shown.map((r) => <Riga key={r.key} r={r} imp={sel[r.key]} onToggle={(on) => toggle(r, on)} onImp={(v) => setSel({ ...sel, [r.key]: v })} iban={ibanOf(r)} onIban={(v) => setIbf({ ...ibf, [r.party_id]: v })} />)}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const scarica = async (d) => {
  try {
    const { data } = await api.get(`/pagamenti-fornitori/distinte/${d.id}/cbi`, { responseType: "blob" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(data);
    a.download = `BONIFICI_${d.anno}_${String(d.numero).padStart(4, "0")}.xml`;
    a.click();
  } catch (e) {
    const msg = e.response?.data instanceof Blob ? JSON.parse(await e.response.data.text()).detail : errMsg(e);
    toast.error(typeof msg === "string" ? msg : "Impossibile generare il flusso");
  }
};

const stampa = async (d) => {
  const w = window.open("", "_blank");
  try {
    const { data } = await api.get(`/pagamenti-fornitori/distinte/${d.id}/pdf`, { responseType: "blob" });
    const url = URL.createObjectURL(new Blob([data], { type: "application/pdf" }));
    if (w) w.location.href = url;
    else { const a = document.createElement("a"); a.href = url; a.download = `Distinta_bonifici_${d.anno}_${String(d.numero).padStart(4, "0")}.pdf`; a.click(); }
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch (e) { if (w) w.close(); toast.error(errMsg(e)); }
};

const Dettaglio = ({ d }) => (
  <tr className="bg-slate-50/60" data-testid={`pf-dettaglio-${d.id}`}>
    <td colSpan={7} className="px-10 py-3 text-xs">
      {d.partite.map((p, i) => (
        <div key={i} className="flex justify-between border-b border-slate-100 py-1 last:border-0">
          <span>{p.fornitore} · <span className="mono">{p.numero_display}</span>{p.rate_totali > 1 ? ` rata ${p.rata_n}/${p.rate_totali}` : ""} · scad. {fmtDate(p.scadenza)}</span><b>{fmtEUR(p.importo)}</b>
        </div>
      ))}
    </td>
  </tr>
);

const Distinte = () => {
  const [rows, setRows] = useState(null);
  const [open, setOpen] = useState({});
  const load = useCallback(() => { api.get("/pagamenti-fornitori/distinte").then(({ data }) => setRows(data)).catch((e) => toast.error(errMsg(e))); }, []);
  useEffect(() => { load(); }, [load]);
  const annulla = async (d) => {
    if (!window.confirm(`Annullare la distinta ${d.numero_display}? Il movimento di prima nota viene eliminato e le partite tornano aperte.`)) return;
    try { await api.delete(`/pagamenti-fornitori/distinte/${d.id}`); toast.success("Distinta annullata"); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  if (!rows) return <p className="text-sm text-slate-500">Caricamento…</p>;
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table className="w-full text-sm" data-testid="pf-distinte-table">
        <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
          <tr><th className="w-8" /><th className="px-4 py-3 font-medium">Data</th><th className="px-4 py-3 font-medium">Distinta</th><th className="px-4 py-3 font-medium">Banca</th><th className="px-4 py-3 font-medium">Prima nota</th><th className="px-4 py-3 text-right font-medium">Totale</th><th className="px-4 py-3" /></tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.length === 0 && <tr><td colSpan={7} className="px-4 py-10 text-center text-slate-500" data-testid="pf-distinte-empty">Nessuna distinta di pagamento</td></tr>}
          {rows.map((d) => [
            <tr key={d.id} className="hover:bg-slate-50" data-testid={`pf-distinta-${d.id}`}>
              <td className="pl-3"><button onClick={() => setOpen({ ...open, [d.id]: !open[d.id] })} data-testid={`pf-distinta-toggle-${d.id}`}>{open[d.id] ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}</button></td>
              <td className="px-4 py-3">{fmtDate(d.data)}</td>
              <td className="mono px-4 py-3 font-medium">{d.numero_display}<div className="text-xs font-normal text-slate-400">{d.n_partite} partite · {d.n_bonifici} bonifici</div></td>
              <td className="px-4 py-3">{d.banca_nome}{d.conto_banca && <div className="text-xs text-slate-400">conto {d.conto_banca}</div>}</td>
              <td className="px-4 py-3 text-xs">{d.coge_rif || <span className="text-slate-400">contabilità non attiva</span>}{d.modificata_prima_nota && <span className="ml-1 rounded-full bg-amber-50 px-2 py-0.5 font-semibold text-amber-700" data-testid={`pf-modificata-${d.id}`}>modificata: riscarica il CBI</span>}</td>
              <td className="px-4 py-3 text-right font-semibold">{fmtEUR(d.totale)}</td>
              <td className="whitespace-nowrap px-4 py-3 text-right">
                <Button size="sm" variant="outline" className="mr-1" onClick={() => stampa(d)} data-testid={`pf-pdf-btn-${d.id}`}><FileText className="mr-1 h-3.5 w-3.5" />PDF</Button>
                <Button size="sm" variant="outline" onClick={() => scarica(d)} data-testid={`pf-cbi-btn-${d.id}`}><Download className="mr-1 h-3.5 w-3.5" />Flusso CBI</Button>
                <Button size="sm" variant="ghost" className="ml-1 text-rose-600" onClick={() => annulla(d)} data-testid={`pf-annulla-btn-${d.id}`}><Trash2 className="h-3.5 w-3.5" /></Button>
              </td>
            </tr>,
            open[d.id] && <Dettaglio key={`d-${d.id}`} d={d} />,
          ])}
        </tbody>
      </table>
    </div>
  );
};

export default function PagamentiFornitori() {
  const [tab, setTab] = useState("pagare");
  return (
    <div>
      <PageHeader eyebrow="Acquisti" title="Pagamenti fornitori" />
      <div className="mb-4 inline-flex rounded-lg border border-slate-200 bg-white p-1 text-xs font-semibold">
        {TABS.map(([k, l]) => <button key={k} onClick={() => setTab(k)} className={`rounded-md px-3 py-1.5 transition-colors ${tab === k ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-50"}`} data-testid={`pf-tab-${k}`}>{l}</button>)}
      </div>
      {tab === "pagare" ? <DaPagare onCreated={() => setTab("distinte")} /> : <Distinte />}
    </div>
  );
}

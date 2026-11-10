import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowLeftRight, Wallet, FileDown, Mail, ArrowUp, ArrowDown } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { useAuth, canSend } from "@/context/AuthContext";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PaymentDialog, RataBadge } from "@/components/PaymentDialog";
import { SollecitoDialog, downloadEstratto } from "@/components/SollecitoDialog";
import { SearchPicker } from "@/components/SearchPicker";

const TABS = [["aperte", "Da incassare"], ["scadute", "Scadute"], ["pagate", "Pagate"], ["tutte", "Tutte"]];
const TABS_PASSIVE = [["aperte", "Da pagare"], ["scadute", "Scadute"], ["pagate", "Pagate"], ["tutte", "Tutte"]];
const FILTER = { aperte: (r) => r.residuo > 0, scadute: (r) => r.scaduta, pagate: (r) => r.stato === "pagata", tutte: () => true };

const iso = (dt) => `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}`;
const plus = (n) => { const x = new Date(); x.setDate(x.getDate() + n); return iso(x); };
const monthEnd = (y, m) => iso(new Date(y, m + 1, 0));
const PERIODI = [["tutto", "Qualsiasi data"], ["7", "Prossimi 7 giorni"], ["30", "Prossimi 30 giorni"], ["60", "Prossimi 60 giorni"], ["90", "Prossimi 90 giorni"], ["mese", "Questo mese"], ["mese_prox", "Mese prossimo"], ["custom", "Periodo personalizzato"]];
const periodRange = (p, dal, al) => {
  const n = new Date();
  if (/^\d+$/.test(p)) return [iso(n), plus(Number(p))];
  if (p === "mese") return [iso(new Date(n.getFullYear(), n.getMonth(), 1)), monthEnd(n.getFullYear(), n.getMonth())];
  if (p === "mese_prox") return [iso(new Date(n.getFullYear(), n.getMonth() + 1, 1)), monthEnd(n.getFullYear(), n.getMonth() + 1)];
  if (p === "custom") return [dal || "", al || ""];
  return ["", ""];
};
const toIt = (s) => (s ? `${s.slice(8, 10)}/${s.slice(5, 7)}/${s.slice(0, 4)}` : "");
const fromIt = (t) => { const m = t.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/); if (!m) return null; const v = `${m[3]}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}`; return iso(new Date(`${v}T00:00:00`)) === v ? v : null; };

const DataManuale = ({ value, onChange, testId }) => {
  const [txt, setTxt] = useState(toIt(value));
  useEffect(() => { setTxt(toIt(value)); }, [value]);
  const commit = () => { const v = txt.trim() ? fromIt(txt.trim()) : ""; if (v === null) { toast.error("Data non valida: usa gg/mm/aaaa"); setTxt(toIt(value)); } else onChange(v); };
  return <input type="text" inputMode="numeric" placeholder="gg/mm/aaaa" maxLength={10} className="w-28 rounded-md border border-slate-200 bg-white px-2 py-1.5 text-sm" value={txt}
    onChange={(e) => setTxt(e.target.value.replace(/[^\d/]/g, ""))} onBlur={commit} onKeyDown={(e) => { if (e.key === "Enter") commit(); }} data-testid={testId} />;
};

const monthLabel = (s) => new Date(`${s.slice(0, 7)}-01T00:00:00`).toLocaleDateString("it-IT", { month: "long", year: "numeric" });

const Kpi = ({ label, value, testId, tone }) => (
  <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
    <div className="text-xs uppercase tracking-wider text-slate-500">{label}</div>
    <div className={`mt-1 text-xl font-bold ${tone}`} data-testid={testId}>{value}</div>
  </div>
);

export default function Scadenzario({ passive = false }) {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const cliente = params.get("cliente") || "all";
  const [tab, setTab] = useState("aperte");
  const [periodo, setPeriodo] = useState("tutto");
  const [dal, setDal] = useState("");
  const [al, setAl] = useState("");
  const [asc, setAsc] = useState(true);
  const [d, setD] = useState(null);
  const [dlg, setDlg] = useState(null);
  const [soll, setSoll] = useState(false);
  const [parties, setParties] = useState([]);
  useEffect(() => { api.get("/parties", { params: { tipo: passive ? "fornitore" : "cliente" } }).then(({ data }) => setParties(data)).catch(() => {}); }, [passive]);
  const load = useCallback(() => { api.get(passive ? "/scadenzario-passivo" : "/scadenzario").then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e))); }, [passive]);
  const docUrl = (id) => (passive ? `/passive/${id}` : `/fatture/${id}`);
  useEffect(() => { load(); }, [load]);

  const rows = useMemo(() => {
    if (!d) return [];
    const [from, to] = periodRange(periodo, dal, al);
    const out = d.rate.filter((r) => (cliente === "all" || r.party_id === cliente) && FILTER[tab](r) && (!from || r.scadenza >= from) && (!to || r.scadenza <= to));
    return [...out].sort((a, b) => (asc ? 1 : -1) * (a.scadenza.localeCompare(b.scadenza) || a.numero_display.localeCompare(b.numero_display)));
  }, [d, cliente, tab, periodo, dal, al, asc]);
  if (!d) return <div className="text-sm text-slate-500">Caricamento…</div>;
  const tot = cliente === "all" ? d.totali : (d.clienti.find((c) => c.party_id === cliente) || { aperto: 0, scaduto: 0, entro_30: 0, crediti: 0 });
  const crediti = d.crediti.filter((c) => cliente === "all" || c.party_id === cliente);
  const hasCredit = (pid) => d.crediti.some((c) => c.party_id === pid);
  const clienti = [...new Map([...d.rate, ...d.crediti].map((r) => [r.party_id, r.cliente])).entries()];
  const pinfo = Object.fromEntries(parties.map((p) => [p.id, p]));
  const docName = Object.fromEntries(clienti);
  const pickItems = [...new Map([...clienti.map(([id, n]) => [id, n]), ...parties.map((p) => [p.id, p.denominazione])]).entries()]
    .sort((a, b) => (a[1] || "").localeCompare(b[1] || ""))
    .map(([id, n]) => ({ key: id, label: n || "", sub: pinfo[id]?.partita_iva || pinfo[id]?.codice_fiscale || "", search: `${pinfo[id]?.codice_fiscale || ""} ${docName[id] || ""}` }));
  const clienteName = pickItems.find((i) => i.key === cliente)?.label || "";
  const open = (r, compensa) => setDlg({ doc: { id: r.invoice_id, numero_display: r.numero_display, cliente: r.cliente, party_id: r.party_id, residuo: r.residuo_documento }, importo: Math.min(r.residuo, r.residuo_documento), compensa });

  return (
    <div>
      <PageHeader eyebrow={passive ? "Debiti verso fornitori" : "Crediti verso clienti"} title={passive ? "Scadenzario fornitori" : "Scadenzario clienti"}>
        {!passive && cliente !== "all" && (
          <>
            <Button variant="outline" onClick={() => downloadEstratto(cliente, clienteName)} data-testid="scad-estratto-btn"><FileDown className="mr-2 h-4 w-4" />Estratto conto</Button>
            {canSend(user) && tot.scaduto > 0 && <Button onClick={() => setSoll(true)} className="bg-rose-600 hover:bg-rose-700" data-testid="scad-sollecito-btn"><Mail className="mr-2 h-4 w-4" />Sollecito</Button>}
          </>
        )}
      </PageHeader>
      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Kpi label="Scaduto" value={fmtEUR(tot.scaduto)} testId="scad-kpi-scaduto" tone="text-rose-700" />
        <Kpi label="In scadenza 30 gg" value={fmtEUR(tot.entro_30)} testId="scad-kpi-entro30" tone="text-amber-700" />
        <Kpi label={passive ? "Totale da pagare" : "Totale da incassare"} value={fmtEUR(tot.aperto)} testId="scad-kpi-aperto" tone="text-slate-900" />
        <Kpi label={passive ? "Crediti da note di credito ricevute" : "Crediti da note di credito"} value={fmtEUR(tot.crediti)} testId="scad-kpi-crediti" tone="text-violet-700" />
      </div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="inline-flex rounded-lg border border-slate-200 bg-white p-1 text-xs font-semibold">
          {(passive ? TABS_PASSIVE : TABS).map(([k, l]) => <button key={k} onClick={() => setTab(k)} className={`rounded-md px-3 py-1.5 transition-colors ${tab === k ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-50"}`} data-testid={`scad-tab-${k}`}>{l}</button>)}
        </div>
        <SearchPicker items={pickItems} value={cliente === "all" ? "" : clienteName} onPick={(i) => setParams({ cliente: i.key })} onClear={() => setParams({})}
          placeholder={passive ? "Cerca fornitore (nome o P.IVA)…" : "Cerca cliente (nome o P.IVA)…"} testId="scad-client-search" className="w-full sm:w-72" />
        <Select value={periodo} onValueChange={(p) => { setPeriodo(p); if (p !== "custom") { const [f, t] = periodRange(p); setDal(f); setAl(t); } }}>
          <SelectTrigger className="w-52 bg-white" data-testid="scad-periodo-select"><SelectValue /></SelectTrigger>
          <SelectContent className="bg-white">{PERIODI.map(([k, l]) => <SelectItem key={k} value={k} data-testid={`scad-periodo-${k}`}>{l}</SelectItem>)}</SelectContent>
        </Select>
        <div className="flex items-center gap-2 text-xs text-slate-600">
          Da <DataManuale value={dal} onChange={(v) => { setDal(v); setPeriodo("custom"); }} testId="scad-dal-input" />
          a <DataManuale value={al} onChange={(v) => { setAl(v); setPeriodo("custom"); }} testId="scad-al-input" />
          {(dal || al) && <button onClick={() => { setDal(""); setAl(""); setPeriodo("tutto"); }} className="text-blue-600 hover:underline" data-testid="scad-date-reset">Azzera</button>}
        </div>
        <span className="ml-auto text-xs text-slate-600" data-testid="scad-filtered-total">{rows.length} scadenze · residuo <b>{fmtEUR(rows.reduce((s, r) => s + r.residuo, 0))}</b></span>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm" data-testid="scad-table">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr><th className="px-4 py-3 font-medium"><button onClick={() => setAsc(!asc)} className="inline-flex items-center gap-1 uppercase hover:text-slate-900" title="Cambia ordine" data-testid="scad-sort-btn">Scadenza {asc ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />}</button></th><th className="px-4 py-3 font-medium">{passive ? "Fornitore" : "Cliente"}</th><th className="px-4 py-3 font-medium">Documento</th><th className="px-4 py-3 text-right font-medium">Importo</th><th className="px-4 py-3 text-right font-medium">Residuo</th><th className="px-4 py-3 font-medium">Stato</th><th className="px-4 py-3" /></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.length === 0 && <tr><td colSpan={7} className="px-4 py-10 text-center text-slate-500" data-testid="scad-empty">Nessuna scadenza nel periodo</td></tr>}
            {rows.map((r, i) => [
              (i === 0 || rows[i - 1].scadenza.slice(0, 7) !== r.scadenza.slice(0, 7)) && (
                <tr key={`m-${r.scadenza.slice(0, 7)}`} className="bg-slate-50/70" data-testid={`scad-month-${r.scadenza.slice(0, 7)}`}>
                  <td colSpan={7} className="px-4 py-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">{monthLabel(r.scadenza)} · {fmtEUR(rows.filter((x) => x.scadenza.slice(0, 7) === r.scadenza.slice(0, 7)).reduce((s, x) => s + x.residuo, 0))}</td>
                </tr>
              ),
              <tr key={`${r.invoice_id}-${r.n}`} className="hover:bg-slate-50" data-testid={`scad-row-${r.invoice_id}-${r.n}`}>
                <td className="px-4 py-3 font-medium text-slate-800">{fmtDate(r.scadenza)}</td>
                <td className="px-4 py-3 text-slate-700">{r.cliente}</td>
                <td className="px-4 py-3"><Link to={docUrl(r.invoice_id)} className="mono text-blue-600 hover:underline">{r.numero_display}</Link>{r.di > 1 && <span className="ml-1 text-xs text-slate-400">rata {r.n}/{r.di}</span>}</td>
                <td className="px-4 py-3 text-right">{fmtEUR(r.importo)}</td>
                <td className="px-4 py-3 text-right font-semibold" data-testid={`scad-residuo-${r.invoice_id}-${r.n}`}>{fmtEUR(r.residuo)}</td>
                <td className="px-4 py-3"><RataBadge r={r} passive={passive} testId={`scad-stato-${r.invoice_id}-${r.n}`} /></td>
                <td className="whitespace-nowrap px-4 py-3 text-right">
                  {canSend(user) && r.residuo > 0 && <>
                    <Button size="sm" variant="outline" onClick={() => open(r, false)} data-testid={`scad-pay-${r.invoice_id}-${r.n}`}><Wallet className="mr-1 h-3.5 w-3.5" />{passive ? "Paga" : "Incassa"}</Button>
                    {hasCredit(r.party_id) && <Button size="sm" variant="ghost" className="ml-1 text-violet-700" onClick={() => open(r, true)} title="Compensa con nota di credito" data-testid={`scad-comp-${r.invoice_id}-${r.n}`}><ArrowLeftRight className="h-3.5 w-3.5" /></Button>}
                  </>}
                </td>
              </tr>,
            ])}
          </tbody>
        </table>
      </div>
      {crediti.length > 0 && (
        <div className="mt-6 rounded-xl border border-violet-200 bg-violet-50/50 p-5" data-testid="scad-crediti">
          <h3 className="mb-2 font-semibold text-violet-900">Note di credito da compensare</h3>
          {crediti.map((c) => (
            <div key={c.id} className="flex justify-between py-1 text-sm" data-testid={`scad-credito-${c.id}`}>
              <span><Link to={docUrl(c.id)} className="mono text-violet-700 hover:underline">{c.numero_display}</Link> · {c.cliente} · {fmtDate(c.data)}</span>
              <span className="font-semibold text-violet-800">{fmtEUR(c.residuo)} <span className="text-xs font-normal">di {fmtEUR(c.netto)}</span></span>
            </div>
          ))}
          <p className="mt-2 text-xs text-violet-700">Le note collegate a una fattura la compensano in automatico; il credito restante si compensa con il pulsante ⇄ su un'altra scadenza dello stesso {passive ? "fornitore" : "cliente"}.</p>
        </div>
      )}
      <SollecitoDialog open={soll} onOpenChange={setSoll} partyId={cliente} cliente={clienteName} />
      <PaymentDialog open={!!dlg} onOpenChange={(o) => !o && setDlg(null)} doc={dlg?.doc} importo={dlg?.importo} compensa={dlg?.compensa} crediti={d.crediti} onDone={load} kind={passive ? "passive" : "invoices"} />
    </div>
  );
}

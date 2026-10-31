import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowLeftRight, Wallet, FileDown, Mail } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { useAuth, canSend } from "@/context/AuthContext";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PaymentDialog, RataBadge } from "@/components/PaymentDialog";
import { SollecitoDialog, downloadEstratto } from "@/components/SollecitoDialog";

const TABS = [["aperte", "Da incassare"], ["scadute", "Scadute"], ["pagate", "Pagate"], ["tutte", "Tutte"]];
const TABS_PASSIVE = [["aperte", "Da pagare"], ["scadute", "Scadute"], ["pagate", "Pagate"], ["tutte", "Tutte"]];
const FILTER = { aperte: (r) => r.residuo > 0, scadute: (r) => r.scaduta, pagate: (r) => r.stato === "pagata", tutte: () => true };

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
  const [d, setD] = useState(null);
  const [dlg, setDlg] = useState(null);
  const [soll, setSoll] = useState(false);
  const load = useCallback(() => { api.get(passive ? "/scadenzario-passivo" : "/scadenzario").then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e))); }, [passive]);
  const docUrl = (id) => (passive ? `/passive/${id}` : `/fatture/${id}`);
  useEffect(() => { load(); }, [load]);

  const rows = useMemo(() => (d ? d.rate.filter((r) => (cliente === "all" || r.party_id === cliente) && FILTER[tab](r)) : []), [d, cliente, tab]);
  if (!d) return <div className="text-sm text-slate-500">Caricamento…</div>;
  const tot = cliente === "all" ? d.totali : (d.clienti.find((c) => c.party_id === cliente) || { aperto: 0, scaduto: 0, entro_30: 0, crediti: 0 });
  const crediti = d.crediti.filter((c) => cliente === "all" || c.party_id === cliente);
  const hasCredit = (pid) => d.crediti.some((c) => c.party_id === pid);
  const clienti = [...new Map([...d.rate, ...d.crediti].map((r) => [r.party_id, r.cliente])).entries()].sort((a, b) => a[1].localeCompare(b[1]));
  const clienteName = clienti.find(([id]) => id === cliente)?.[1] || "";
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
        <Select value={cliente} onValueChange={(v) => setParams(v === "all" ? {} : { cliente: v })}>
          <SelectTrigger className="w-64 bg-white" data-testid="scad-client-select"><SelectValue /></SelectTrigger>
          <SelectContent className="bg-white">
            <SelectItem value="all" data-testid="scad-client-all">{passive ? "Tutti i fornitori" : "Tutti i clienti"}</SelectItem>
            {clienti.map(([id, n]) => <SelectItem key={id} value={id} data-testid={`scad-client-${id}`}>{n}</SelectItem>)}
          </SelectContent>
        </Select>
      </PageHeader>
      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Kpi label="Scaduto" value={fmtEUR(tot.scaduto)} testId="scad-kpi-scaduto" tone="text-rose-700" />
        <Kpi label="In scadenza 30 gg" value={fmtEUR(tot.entro_30)} testId="scad-kpi-entro30" tone="text-amber-700" />
        <Kpi label={passive ? "Totale da pagare" : "Totale da incassare"} value={fmtEUR(tot.aperto)} testId="scad-kpi-aperto" tone="text-slate-900" />
        <Kpi label={passive ? "Crediti da note di credito ricevute" : "Crediti da note di credito"} value={fmtEUR(tot.crediti)} testId="scad-kpi-crediti" tone="text-violet-700" />
      </div>
      <div className="mb-4 inline-flex rounded-lg border border-slate-200 bg-white p-1 text-xs font-semibold">
        {(passive ? TABS_PASSIVE : TABS).map(([k, l]) => <button key={k} onClick={() => setTab(k)} className={`rounded-md px-3 py-1.5 transition-colors ${tab === k ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-50"}`} data-testid={`scad-tab-${k}`}>{l}</button>)}
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm" data-testid="scad-table">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr><th className="px-4 py-3 font-medium">Scadenza</th><th className="px-4 py-3 font-medium">{passive ? "Fornitore" : "Cliente"}</th><th className="px-4 py-3 font-medium">Documento</th><th className="px-4 py-3 text-right font-medium">Importo</th><th className="px-4 py-3 text-right font-medium">Residuo</th><th className="px-4 py-3 font-medium">Stato</th><th className="px-4 py-3" /></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.length === 0 && <tr><td colSpan={7} className="px-4 py-10 text-center text-slate-500" data-testid="scad-empty">Nessuna scadenza</td></tr>}
            {rows.map((r) => (
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
              </tr>
            ))}
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

import { Link } from "react-router-dom";
import { ArrowLeft, Send, RefreshCw, Trash2, Download } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate, STATUS } from "@/lib/fe";
import { Button } from "@/components/ui/button";

const Party = ({ title, p }) => (
  <div>
    <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{title}</div>
    <div className="font-semibold text-slate-900">{p.denominazione}</div>
    <div className="text-xs text-slate-600">{p.indirizzo} {p.cap} {p.comune} {p.nazione}<br />{p.partita_iva && `P.IVA ${p.nazione || "IT"}${p.partita_iva}`}</div>
  </div>
);

export const AutofatturaView = ({ inv, busy, canSend, onSend, onRefresh, onDelete }) => {
  const st = STATUS[inv.status] || { label: inv.status, cls: "" };
  const xml = async () => {
    try {
      const { data } = await api.get(`/invoices/${inv.id}/xml`, { responseType: "blob" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(data);
      a.download = `Autofattura_${inv.numero_display.replace("/", "_")}.xml`;
      a.click();
    } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div data-testid="autofattura-view">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Link to="/fatture" className="inline-flex items-center gap-1 text-sm text-slate-600 hover:text-slate-900"><ArrowLeft className="h-4 w-4" />Fatture emesse</Link>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={xml} data-testid="autofattura-xml-btn"><Download className="mr-2 h-4 w-4" />XML</Button>
          {inv.passive_id && <Link to={`/passive/${inv.passive_id}`}><Button variant="outline" data-testid="autofattura-passiva-link">Fattura del fornitore</Button></Link>}
          {canSend && ["bozza", "scartata"].includes(inv.status) && <Button onClick={onSend} disabled={busy} className="bg-blue-600 hover:bg-blue-700" data-testid="autofattura-send-btn"><Send className="mr-2 h-4 w-4" />Invia allo SDI</Button>}
          {inv.status === "inviata" && <Button onClick={onRefresh} disabled={busy} className="bg-emerald-600 hover:bg-emerald-700" data-testid="autofattura-refresh-btn"><RefreshCw className="mr-2 h-4 w-4" />Aggiorna stato SDI</Button>}
          {canSend && inv.status === "bozza" && <Button variant="ghost" className="text-rose-600" onClick={onDelete} data-testid="autofattura-delete-btn"><Trash2 className="h-4 w-4" /></Button>}
        </div>
      </div>
      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-4">
          <div>
            <div className="text-xs uppercase tracking-wider text-indigo-600">Autofattura {inv.tipo_documento} · {inv.causale}</div>
            <div className="text-2xl font-extrabold" data-testid="autofattura-numero">N. {inv.numero_display}</div>
            <div className="text-xs text-slate-500">del {fmtDate(inv.data)} · rif. fattura fornitore n. {inv.fattura_collegata?.numero_display} del {fmtDate(inv.fattura_collegata?.data)}</div>
          </div>
          <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${st.cls}`} data-testid="autofattura-status">{st.label}</span>
        </div>
        <div className="grid gap-4 sm:grid-cols-2"><Party title="Cedente / Prestatore (fornitore)" p={inv.cedente} /><Party title="Cessionario / Committente (la tua azienda)" p={inv.cliente} /></div>
        <table className="mt-6 w-full text-sm">
          <thead className="border-y border-slate-200 bg-slate-50 text-left text-xs uppercase text-slate-500"><tr><th className="px-3 py-2">Descrizione</th><th className="px-3 py-2 text-right">Imponibile</th><th className="px-3 py-2 text-right">IVA</th></tr></thead>
          <tbody>{inv.lines.map((l, i) => <tr key={i} className="border-b border-slate-100"><td className="px-3 py-2">{l.descrizione}</td><td className="px-3 py-2 text-right">{fmtEUR(l.prezzo_unitario)}</td><td className="px-3 py-2 text-right">{l.aliquota}%</td></tr>)}</tbody>
        </table>
        <div className="mt-4 text-right text-sm">Imponibile {fmtEUR(inv.imponibile)} · IVA {fmtEUR(inv.iva)} · <b data-testid="autofattura-totale">Totale {fmtEUR(inv.totale)}</b></div>
        <p className="mt-4 text-xs text-slate-500">L'IVA è già registrata in contabilità e nel registro acquisti con la fattura del fornitore (reverse charge): l'autofattura non va nel registro vendite né nello scadenzario.</p>
        {inv.sdi_history?.length > 0 && <ul className="mt-4 space-y-1 text-xs text-slate-600">{inv.sdi_history.map((h, i) => <li key={i}>{fmtDate(h.at)} · {h.status} {h.message ? `· ${h.message}` : ""}</li>)}</ul>}
      </div>
    </div>
  );
};

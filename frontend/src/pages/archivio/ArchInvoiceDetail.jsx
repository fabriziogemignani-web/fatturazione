import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Download, Trash2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { DocBadge, TD_LABEL, downloadBlob } from "@/lib/archivio";
import { useAuth, canSend } from "@/context/AuthContext";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";

const Party = ({ title, p }) => (
  <div className="rounded-xl border border-slate-200/80 bg-white p-5 shadow-sm">
    <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">{title}</div>
    <div className="mt-2 font-semibold text-slate-900">{p.denominazione}</div>
    <div className="mt-1 text-sm text-slate-600">{p.piva && <>P.IVA {p.paese}{p.piva} · </>}{p.codice_fiscale && <>CF {p.codice_fiscale}</>}</div>
    <div className="text-sm text-slate-600">{[p.indirizzo, p.cap, p.comune, p.provincia && `(${p.provincia})`].filter(Boolean).join(" ")}</div>
  </div>
);

const Table = ({ head, rows }) => (
  <div className="overflow-x-auto rounded-xl border border-slate-200/80 bg-white shadow-sm">
    <table className="w-full text-sm">
      <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500"><tr>{head.map((h, i) => <th key={h} className={`px-4 py-2.5 font-medium ${i ? "text-right" : ""}`}>{h}</th>)}</tr></thead>
      <tbody className="divide-y divide-slate-100">{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className={`px-4 py-2 ${j ? "text-right" : ""}`}>{c}</td>)}</tr>)}</tbody>
    </table>
  </div>
);

export default function ArchInvoiceDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const { user } = useAuth();
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.get(`/archivio/invoices/${id}`).then(({ data }) => setD(data)).catch((e) => setErr(errMsg(e))); }, [id]);
  if (err) return <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-600" data-testid="arch-detail-error">{err}. <Link to="/archivio" className="font-semibold text-blue-600">Torna all'archivio</Link></div>;
  if (!d) return <div className="text-sm text-slate-500">Caricamento…</div>;
  const remove = async () => {
    if (!window.confirm(`Eliminare dall'archivio la fattura ${d.numero}?`)) return;
    try { await api.delete(`/archivio/invoices/${id}`); toast.success("Fattura eliminata"); nav(`/archivio/${d.tipo}`); } catch (e) { toast.error(errMsg(e)); }
  };

  return (
    <div>
      <PageHeader eyebrow={`Archivio · fattura ${d.tipo}`} title={`${TD_LABEL[d.tipo_documento] || "Documento"} n. ${d.numero} del ${fmtDate(d.data)}`}>
        <Button variant="outline" onClick={() => downloadBlob(`/archivio/invoices/${id}/xml`, {}, "fattura.xml").catch((e) => toast.error(errMsg(e)))} data-testid="arch-download-xml-btn"><Download className="mr-2 h-4 w-4" />Scarica XML</Button>
        {canSend(user) && <Button variant="ghost" className="text-rose-600" onClick={remove} data-testid="arch-delete-btn"><Trash2 className="mr-2 h-4 w-4" />Elimina</Button>}
      </PageHeader>
      <div className="mb-4 flex flex-wrap items-center gap-3 text-sm text-slate-600">
        <DocBadge code={d.tipo_documento} /><span>File: <span className="mono text-xs">{d.filename}</span></span>
        {d.allegati_rimossi && <span className="text-xs text-amber-700" data-testid="arch-attach-removed">Allegati PDF non conservati (file troppo grande)</span>}
        {d.controparte_id && <Link to={`/archivio/anagrafiche/${d.controparte_id}`} className="font-semibold text-blue-600" data-testid="arch-open-anag-link">Scheda {d.tipo === "attiva" ? "cliente" : "fornitore"} →</Link>}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Party title="Cedente / prestatore" p={d.cedente} />
        <Party title="Cessionario / committente" p={d.cessionario} />
      </div>
      {d.causale && <p className="mt-4 rounded-lg bg-slate-50 p-3 text-sm text-slate-700"><b>Causale:</b> {d.causale}</p>}
      <h3 className="mb-2 mt-6 font-semibold text-slate-800">Righe</h3>
      <Table head={["Descrizione", "Quantità", "Prezzo unitario", "IVA", "Totale"]} rows={d.righe.map((r) => [r.descrizione, r.quantita ? `${r.quantita} ${r.unita_misura}` : "", fmtEUR(r.prezzo_unitario), r.natura || `${r.aliquota_iva}%`, fmtEUR(r.prezzo_totale)])} />
      <h3 className="mb-2 mt-6 font-semibold text-slate-800">Riepilogo IVA</h3>
      <Table head={["Aliquota / natura", "Imponibile", "Imposta"]} rows={d.riepilogo.map((r) => [r.natura ? `${r.natura} ${r.riferimento_normativo}` : `${r.aliquota_iva}%`, fmtEUR(r.imponibile), fmtEUR(r.imposta)])} />
      {d.pagamenti.length > 0 && <>
        <h3 className="mb-2 mt-6 font-semibold text-slate-800">Pagamenti</h3>
        <Table head={["Modalità", "Scadenza", "IBAN", "Importo"]} rows={d.pagamenti.map((p) => [p.modalita, p.scadenza ? fmtDate(p.scadenza) : "—", p.iban || "—", fmtEUR(p.importo)])} />
      </>}
      <div className="mt-6 ml-auto max-w-sm space-y-1 rounded-xl border border-slate-200/80 bg-white p-5 text-sm shadow-sm" data-testid="arch-totals">
        <div className="flex justify-between"><span>Imponibile</span><span>{fmtEUR(d.imponibile)}</span></div>
        <div className="flex justify-between"><span>IVA</span><span>{fmtEUR(d.imposta)}</span></div>
        <div className="flex justify-between border-t border-slate-200 pt-2 text-base font-bold"><span>Totale documento</span><span>{fmtEUR(d.totale)}</span></div>
      </div>
    </div>
  );
}

import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Printer, ArrowLeft } from "lucide-react";
import { api } from "@/lib/api";
import { fmtEUR, fmtDate, TIPI_DOC, MODALITA, CASSE, RITENUTE } from "@/lib/fe";

const label = (list, k) => (list.find(([x]) => x === k) || [k, k])[1];

const Party = ({ title, p }) => (
  <div>
    <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{title}</div>
    <div className="mt-1 text-sm font-bold text-slate-900">{p.denominazione}</div>
    <div className="text-xs leading-relaxed text-slate-600">
      {p.indirizzo}<br />{p.cap} {p.comune} {p.provincia && `(${p.provincia})`} {p.nazione}<br />
      {p.partita_iva && <>P.IVA {p.partita_iva}<br /></>}
      {p.codice_fiscale && <>C.F. {p.codice_fiscale}<br /></>}
      {p.codice_destinatario && <>Cod. destinatario {p.codice_destinatario}<br /></>}
      {p.pec && <>PEC {p.pec}</>}
    </div>
  </div>
);

export default function InvoicePrint() {
  const { id } = useParams();
  const [inv, setInv] = useState(null);
  const [company, setCompany] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    Promise.all([api.get(`/invoices/${id}`), api.get("/company")]).then(([a, b]) => { setInv(a.data); setCompany(b.data); }).catch(() => setError(true));
  }, [id]);

  if (error) return <div className="p-10 text-sm text-slate-600" data-testid="print-not-found">Fattura non trovata nell'azienda attiva. Seleziona l'azienda corretta dal menu. <Link to="/fatture" className="font-medium text-blue-600">Torna alle fatture</Link></div>;
  if (!inv || !company) return <div className="p-10 text-sm text-slate-500">Caricamento…</div>;

  return (
    <div className="min-h-screen bg-slate-100 py-8">
      <div className="no-print mx-auto mb-4 flex max-w-[210mm] justify-between px-4">
        <Link to={`/fatture/${id}`} className="inline-flex items-center gap-1 text-sm text-slate-600 hover:text-slate-900" data-testid="print-back-btn"><ArrowLeft className="h-4 w-4" />Torna alla fattura</Link>
        <button onClick={() => window.print()} className="inline-flex items-center gap-2 rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800" data-testid="print-now-btn"><Printer className="h-4 w-4" />Stampa / Salva PDF</button>
      </div>
      <div className="print-sheet mx-auto max-w-[210mm] bg-white p-10 shadow-lg" data-testid="print-sheet">
        <div className="flex items-start justify-between border-b-2 border-slate-900 pb-6">
          <Party title="Cedente / Prestatore" p={company} />
          <div className="text-right">
            <div className="text-xs uppercase tracking-wider text-slate-500">{label(TIPI_DOC, inv.tipo_documento).split(" - ")[1]}</div>
            <div className="text-2xl font-extrabold text-slate-900" data-testid="print-number">N. {inv.numero_display}</div>
            <div className="text-sm text-slate-600">del {fmtDate(inv.data)}</div>
          </div>
        </div>
        <div className="mt-6 grid grid-cols-2 gap-6">
          <div />
          <div className="rounded border border-slate-200 p-4"><Party title="Cessionario / Committente" p={inv.cliente} /></div>
        </div>
        {inv.causale && <p className="mt-6 text-xs text-slate-600"><b>Causale:</b> {inv.causale}</p>}
        {inv.cliente?.intento_protocollo && inv.lines.some((l) => l.natura === "N3.5") && (
          <p className="mt-2 text-xs text-slate-600" data-testid="print-intento"><b>Dichiarazione d'intento:</b> prot. {inv.cliente.intento_protocollo} del {fmtDate(inv.cliente.intento_data)} – operazione non imponibile art. 8 c.1 lett. c DPR 633/72</p>
        )}
        <table className="mt-6 w-full text-xs">
          <thead className="border-y border-slate-300 bg-slate-50 text-left uppercase tracking-wider text-slate-500">
            <tr><th className="p-2">Descrizione</th><th className="p-2 text-right">Q.tà</th><th className="p-2 text-right">Prezzo</th><th className="p-2 text-right">IVA</th><th className="p-2 text-right">Importo</th></tr>
          </thead>
          <tbody>
            {inv.lines.map((l, i) => (
              <tr key={i} className="border-b border-slate-100">
                <td className="p-2">{l.descrizione}</td>
                <td className="p-2 text-right">{l.quantita}</td>
                <td className="p-2 text-right">{fmtEUR(l.prezzo_unitario)}</td>
                <td className="p-2 text-right">{l.aliquota ? `${l.aliquota}%` : l.natura}</td>
                <td className="p-2 text-right font-medium">{fmtEUR(l.prezzo_totale)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-6 grid grid-cols-2 gap-6">
          <table className="w-full self-start text-xs">
            <thead className="text-left uppercase tracking-wider text-slate-500"><tr><th className="py-1">Aliquota</th><th className="py-1 text-right">Imponibile</th><th className="py-1 text-right">Imposta</th></tr></thead>
            <tbody>
              {inv.riepilogo.map((r, i) => (
                <tr key={i} className="border-t border-slate-100"><td className="py-1">{r.aliquota ? `${r.aliquota}%` : r.natura}</td><td className="py-1 text-right">{fmtEUR(r.imponibile)}</td><td className="py-1 text-right">{fmtEUR(r.imposta)}</td></tr>
              ))}
            </tbody>
          </table>
          <div className="text-sm">
            <div className="flex justify-between py-1"><span>Imponibile</span><span>{fmtEUR(inv.imponibile)}</span></div>
            {inv.cassa && <div className="flex justify-between py-1 text-xs text-slate-600" data-testid="print-cassa"><span>di cui {label(CASSE, inv.cassa.tipo)} {inv.cassa.aliquota}%</span><span>{fmtEUR(inv.cassa_importo)}</span></div>}
            <div className="flex justify-between py-1"><span>IVA</span><span>{fmtEUR(inv.iva)}</span></div>
            <div className="mt-1 flex justify-between border-t-2 border-slate-900 pt-2 text-lg font-extrabold" data-testid="print-total"><span>Totale</span><span>{fmtEUR(inv.totale)}</span></div>
            {inv.ritenuta && (
              <>
                <div className="flex justify-between py-1 text-xs text-slate-600" data-testid="print-ritenuta"><span>Ritenuta d'acconto {inv.ritenuta.aliquota}% ({label(RITENUTE, inv.ritenuta.tipo).split(" - ")[1]}) su {fmtEUR(inv.ritenuta_imponibile)}</span><span className="whitespace-nowrap">- {fmtEUR(inv.ritenuta_importo)}</span></div>
                <div className="flex justify-between border-t border-slate-300 pt-2 font-bold" data-testid="print-netto"><span>Netto a pagare</span><span>{fmtEUR(inv.netto)}</span></div>
              </>
            )}
          </div>
        </div>
        <div className="mt-8 rounded border border-slate-200 p-4 text-xs text-slate-600">
          <b>Pagamento:</b> {label(MODALITA, inv.modalita_pagamento)}
          {inv.scadenza && <> · Scadenza {fmtDate(inv.scadenza)}</>}
          {inv.modalita_pagamento === "MP05" && company.iban && <> · IBAN <span className="mono">{company.iban}</span></>}
        </div>
        <p className="mt-8 text-[10px] text-slate-400">Copia di cortesia. Il documento fiscalmente valido è il file XML trasmesso tramite Sistema di Interscambio.</p>
      </div>
    </div>
  );
}

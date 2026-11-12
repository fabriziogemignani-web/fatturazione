import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Printer, ArrowLeft } from "lucide-react";
import { api } from "@/lib/api";
import { fmtEUR, fmtDate, TIPI_DOC, MODALITA, CASSE, RITENUTE } from "@/lib/fe";

const label = (list, k) => (list.find(([x]) => x === k) || [k, k])[1];

const Party = ({ title, p, on = () => true, extra = [] }) => (
  <div>
    <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{title}</div>
    <div className="mt-1 text-sm font-bold text-slate-900">{p.denominazione}</div>
    <div className="text-xs leading-relaxed text-slate-600">
      {p.indirizzo}<br />{p.cap} {p.comune} {p.provincia && `(${p.provincia})`} {p.nazione}<br />
      {p.partita_iva && <>P.IVA {p.partita_iva}<br /></>}
      {p.codice_fiscale && on("cliente_codice_fiscale") && <>C.F. {p.codice_fiscale}<br /></>}
      {p.codice_destinatario && on("cliente_codice_destinatario") && <>{p.pubblica_amministrazione ? "Cod. univoco ufficio" : "Cod. destinatario"} {p.codice_destinatario}<br /></>}
      {p.pec && on("cliente_pec") && <>PEC {p.pec}<br /></>}
      {p.email && on("cliente_email") && <>{p.email}<br /></>}
      {p.telefono && on("cliente_telefono") && <>Tel. {p.telefono}<br /></>}
      {extra.filter(Boolean).map((x) => <span key={x}>{x}<br /></span>)}
    </div>
  </div>
);

export default function InvoicePrint() {
  const { id } = useParams();
  const [inv, setInv] = useState(null);
  const [company, setCompany] = useState(null);
  const [lay, setLay] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    Promise.all([api.get(`/invoices/${id}`), api.get("/company"), api.get("/company/layout")]).then(([a, b, c]) => { setInv(a.data); setCompany(b.data); setLay(c.data); }).catch(() => setError(true));
  }, [id]);

  if (error) return <div className="p-10 text-sm text-slate-600" data-testid="print-not-found">Fattura non trovata nell'azienda attiva. Seleziona l'azienda corretta dal menu. <Link to="/fatture" className="font-medium text-blue-600">Torna alle fatture</Link></div>;
  if (!inv || !company || !lay) return <div className="p-10 text-sm text-slate-500">Caricamento…</div>;
  const on = (k) => lay.campi?.[k] !== false;
  const piede = inv.tipo_documento === "TD04" ? lay.piede_nc : lay.piede_fattura;
  const datiExtra = [lay.telefono && `Tel. ${lay.telefono}`, lay.email, lay.pec && `PEC ${lay.pec}`, lay.sito, lay.rea && `REA ${lay.rea}`, lay.capitale_sociale && `Capitale sociale ${lay.capitale_sociale}`];

  return (
    <div className="min-h-screen bg-slate-100 py-8">
      <div className="no-print mx-auto mb-4 flex max-w-[210mm] justify-between px-4">
        <Link to={`/fatture/${id}`} className="inline-flex items-center gap-1 text-sm text-slate-600 hover:text-slate-900" data-testid="print-back-btn"><ArrowLeft className="h-4 w-4" />Torna alla fattura</Link>
        <button onClick={() => window.print()} className="inline-flex items-center gap-2 rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800" data-testid="print-now-btn"><Printer className="h-4 w-4" />Stampa / Salva PDF</button>
      </div>
      <div className="print-sheet mx-auto max-w-[210mm] bg-white p-10 shadow-lg" data-testid="print-sheet">
        <div className="flex items-start justify-between border-b-2 pb-6" style={{ borderColor: lay.colore }}>
          <div>
            {lay.logo && <img src={lay.logo} alt="Logo" className="mb-3 h-16 max-w-[180px] object-contain" data-testid="print-logo" />}
            <Party title="Cedente / Prestatore" p={company} extra={datiExtra} />
          </div>
          <div className="text-right">
            <div className="text-xs uppercase tracking-wider text-slate-500">{label(TIPI_DOC, inv.tipo_documento).split(" - ")[1]}</div>
            <div className="text-2xl font-extrabold" style={{ color: lay.colore }} data-testid="print-number">N. {inv.numero_display}</div>
            <div className="text-sm text-slate-600">del {fmtDate(inv.data)}</div>
          </div>
        </div>
        <div className="mt-6 grid grid-cols-2 gap-6">
          <div />
          <div className="rounded border border-slate-200 p-4"><Party title="Cessionario / Committente" p={inv.cliente} on={on} /></div>
        </div>
        {inv.fattura_collegata && <p className="mt-6 text-xs text-slate-600" data-testid="print-linked"><b>Storno della fattura</b> n. {inv.fattura_collegata.numero_display} del {fmtDate(inv.fattura_collegata.data)}</p>}
        {inv.cliente?.pubblica_amministrazione && (inv.rif_documento || inv.cig || inv.cup) && (
          <p className="mt-6 text-xs text-slate-600" data-testid="print-pa">
            {inv.rif_documento && <><b>Rif. {inv.rif_tipo === "contratto" ? "contratto" : inv.rif_tipo === "convenzione" ? "convenzione" : "ordine d'acquisto"}:</b> n. {inv.rif_documento}{inv.rif_data && ` del ${fmtDate(inv.rif_data)}`}</>}
            {inv.cig && <> · <b>CIG:</b> <span className="mono" data-testid="print-cig">{inv.cig}</span></>}
            {inv.cup && <> · <b>CUP:</b> <span className="mono" data-testid="print-cup">{inv.cup}</span></>}
          </p>
        )}
        {inv.causale && on("causale") && <p className="mt-6 text-xs text-slate-600"><b>Causale:</b> {inv.causale}</p>}
        {inv.ddt_rif?.length > 0 && <p className="mt-2 text-xs text-slate-600" data-testid="print-ddt-rif"><b>Rif. DDT:</b> {inv.ddt_rif.map((x) => `n. ${x.numero} del ${fmtDate(x.data)}`).join(", ")}</p>}
        {inv.trasporto && (
          <p className="mt-2 text-xs text-slate-600" data-testid="print-trasporto"><b>Fattura accompagnatoria</b> · causale trasporto {inv.trasporto.causale} · porto {inv.trasporto.porto} · a cura del {inv.trasporto.trasporto_a_cura}
            {inv.trasporto.vettore?.denominazione && ` · vettore ${inv.trasporto.vettore.denominazione}`}{inv.trasporto.colli ? ` · colli ${inv.trasporto.colli}` : ""}{inv.trasporto.peso_kg ? ` · peso kg ${inv.trasporto.peso_kg}` : ""}{inv.trasporto.aspetto_beni ? ` · aspetto ${inv.trasporto.aspetto_beni}` : ""}
            {inv.trasporto.destinazione?.indirizzo && ` · destinazione ${inv.trasporto.destinazione.denominazione || ""} ${inv.trasporto.destinazione.indirizzo} ${inv.trasporto.destinazione.cap} ${inv.trasporto.destinazione.comune}`}</p>
        )}
        {inv.cliente?.intento_protocollo && inv.lines.some((l) => l.natura === "N3.5") && (
          <p className="mt-2 text-xs text-slate-600" data-testid="print-intento"><b>Dichiarazione d'intento:</b> prot. {inv.cliente.intento_protocollo} del {fmtDate(inv.cliente.intento_data)} – operazione non imponibile art. 8 c.1 lett. c DPR 633/72</p>
        )}
        <table className="mt-6 w-full text-xs">
          <thead className="border-y border-slate-300 bg-slate-50 text-left uppercase tracking-wider" style={{ color: lay.colore }}>
            <tr><th className="p-2">Descrizione</th><th className="p-2 text-right">Q.tà</th><th className="p-2 text-right">Prezzo</th><th className="p-2 text-right">IVA</th><th className="p-2 text-right">Importo</th></tr>
          </thead>
          <tbody>
            {inv.lines.map((l, i) => (
              <tr key={i} className="border-b border-slate-100">
                <td className="p-2">{l.descrizione}{l.note && on("note_righe") && <div className="mt-0.5 whitespace-pre-line text-[11px] italic text-slate-500" data-testid={`print-line-note-${i}`}>{l.note}</div>}</td>
                <td className="p-2 text-right">{l.quantita}</td>
                <td className="p-2 text-right">{fmtEUR(l.prezzo_unitario)}{l.sconto && <div className="text-[11px] text-slate-500" data-testid={`print-line-sconto-${i}`}>sc. {l.sconto}%</div>}</td>
                <td className="p-2 text-right">{l.aliquota ? `${l.aliquota}%` : l.natura}</td>
                <td className="p-2 text-right font-medium">{fmtEUR(l.prezzo_totale)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-6 grid grid-cols-2 gap-6">
          <table className={`w-full self-start text-xs ${on("riepilogo_iva") ? "" : "invisible"}`}>
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
            {inv.split_payment && <div className="flex justify-between py-1 text-xs text-slate-600" data-testid="print-split"><span>IVA da versare a cura dell'ente (scissione dei pagamenti art. 17-ter DPR 633/72)</span><span className="whitespace-nowrap">- {fmtEUR(inv.iva_split)}</span></div>}
            {(inv.ritenuta || inv.split_payment) && (
              <>
                {inv.ritenuta && <div className="flex justify-between py-1 text-xs text-slate-600" data-testid="print-ritenuta"><span>Ritenuta d'acconto {inv.ritenuta.aliquota}% ({label(RITENUTE, inv.ritenuta.tipo).split(" - ")[1]}) su {fmtEUR(inv.ritenuta_imponibile)}</span><span className="whitespace-nowrap">- {fmtEUR(inv.ritenuta_importo)}</span></div>}
                <div className="flex justify-between border-t border-slate-300 pt-2 font-bold" data-testid="print-netto"><span>Netto a pagare</span><span>{fmtEUR(inv.netto)}</span></div>
              </>
            )}
          </div>
        </div>
        {inv.bollo_virtuale && <p className="mt-4 text-xs text-slate-600" data-testid="print-bollo">Imposta di bollo di {fmtEUR(inv.bollo_importo || 2)} assolta in modo virtuale ai sensi dell'art. 6 DM 17/06/2014{inv.bollo_addebitato ? " (addebitata al cliente)" : ""}.</p>}
        <div className="mt-8 rounded border border-slate-200 p-4 text-xs text-slate-600">
          <b>Pagamento:</b> {label(MODALITA, inv.modalita_pagamento)}
          {inv.scadenza && on("scadenza") && <> · Scadenza {fmtDate(inv.scadenza)}</>}
          {on("coordinate_bancarie") && ["MP05", "MP12"].includes(inv.modalita_pagamento) && (inv.banca?.iban || company.iban) && (
            <div className="mt-1" data-testid="print-bank">
              <b>Coordinate bancarie:</b> {inv.banca?.nome && <>{inv.banca.nome} · </>}IBAN <span className="mono">{inv.banca?.iban || company.iban}</span>
              {inv.banca?.abi && <> · ABI {inv.banca.abi} · CAB {inv.banca.cab}</>}
              {inv.banca?.bic && <> · BIC {inv.banca.bic}</>}
            </div>
          )}
        </div>
        {piede && <p className="mt-8 whitespace-pre-line text-[11px] text-slate-600" data-testid="print-piede">{piede}</p>}
        <p className="mt-8 text-[10px] text-slate-400">Copia di cortesia. Il documento fiscalmente valido è il file XML trasmesso tramite Sistema di Interscambio.</p>
      </div>
    </div>
  );
}

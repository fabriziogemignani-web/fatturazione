import { useState } from "react";
import { useCompany } from "@/context/CompanyContext";

const TIPI = [["fattura", "Fattura"], ["nc", "Nota di credito"], ["ddt", "DDT"]];
const TITOLO = { fattura: "Fattura", nc: "Nota di credito", ddt: "Documento di trasporto" };

const Riga = ({ show, children }) => (show ? <div>{children}</div> : null);

export const LayoutPreview = ({ l }) => {
  const { company: c } = useCompany();
  const [tipo, setTipo] = useState("fattura");
  const on = (k) => tipo === "ddt" ? !["scadenza", "coordinate_bancarie", "riepilogo_iva"].includes(k) && l.campi?.[k] !== false : l.campi?.[k] !== false;
  const piede = { fattura: l.piede_fattura, nc: l.piede_nc, ddt: l.piede_ddt }[tipo];
  const extra = [l.telefono && `Tel. ${l.telefono}`, l.email, l.pec && `PEC ${l.pec}`, l.sito, l.rea && `REA ${l.rea}`, l.capitale_sociale && `Capitale sociale ${l.capitale_sociale}`].filter(Boolean);
  return (
    <div className="lg:sticky lg:top-4" data-testid="layout-preview">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Anteprima dal vivo</span>
        <div className="flex rounded-md border border-slate-200 p-0.5 text-xs">
          {TIPI.map(([k, lab]) => (
            <button key={k} onClick={() => setTipo(k)} className={`rounded px-2 py-1 transition-colors ${tipo === k ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"}`} data-testid={`layout-preview-tab-${k}`}>{lab}</button>
          ))}
        </div>
      </div>
      <div className="aspect-[210/297] overflow-hidden rounded-md border border-slate-200 bg-white p-4 text-[8px] leading-snug text-slate-700 shadow-sm">
        <div className="flex justify-between gap-2 border-b-2 pb-2" style={{ borderColor: l.colore }}>
          <div>
            {l.logo && <img src={l.logo} alt="Logo" className="mb-1 h-8 max-w-[90px] object-contain" data-testid="layout-preview-logo" />}
            <div className="font-bold text-slate-900">{c?.denominazione || "La tua azienda"}</div>
            <div>{c?.indirizzo} {c?.cap} {c?.comune}</div>
            <div>P.IVA {c?.partita_iva}</div>
            {extra.map((x) => <div key={x}>{x}</div>)}
          </div>
          <div className="text-right">
            <div className="uppercase text-slate-500">{TITOLO[tipo]}</div>
            <div className="text-[11px] font-extrabold" style={{ color: l.colore }} data-testid="layout-preview-numero">N. 1/2026</div>
          </div>
        </div>
        <div className="mt-2">
          <div className="text-[7px] uppercase text-slate-400">{tipo === "ddt" ? "Destinatario" : "Cessionario / Committente"}</div>
          <div className="font-bold text-slate-900">Cliente di esempio Srl</div>
          <div>Via Esempio 10, 00100 Roma</div>
          <Riga show={on("cliente_codice_fiscale")}>C.F. 01234567890</Riga>
          <Riga show={on("cliente_codice_destinatario")}>Cod. destinatario ABC1234</Riga>
          <Riga show={on("cliente_pec")}>PEC cliente@pec.it</Riga>
          <Riga show={on("cliente_email")}>cliente@esempio.it</Riga>
          <Riga show={on("cliente_telefono")}>Tel. 06 1234567</Riga>
        </div>
        <Riga show={on("causale")}><div className="mt-2"><b>Causale:</b> Vendita</div></Riga>
        <table className="mt-2 w-full">
          <thead><tr className="text-left" style={tipo === "ddt" ? { background: l.colore, color: "#fff" } : { color: l.colore }}><th className="py-0.5">Descrizione</th><th className="text-right">Q.tà</th><th className="text-right">Importo</th></tr></thead>
          <tbody>
            <tr className="border-t border-slate-100"><td className="py-0.5">Articolo di esempio{on("note_righe") && <div className="text-slate-400">Nota della riga</div>}</td><td className="text-right">2</td><td className="text-right">200,00 €</td></tr>
          </tbody>
        </table>
        {tipo !== "ddt" && <div className="mt-2 flex justify-between gap-2">
          <div>{on("riepilogo_iva") && <span>IVA 22%: imponibile 200,00 € · imposta 44,00 €</span>}</div>
          <div className="font-bold text-slate-900">Totale 244,00 €</div>
        </div>}
        <Riga show={on("scadenza")}><div className="mt-2">Scadenza 31/12/2026</div></Riga>
        <Riga show={on("coordinate_bancarie")}><div>IBAN IT60X0542811101000000123456</div></Riga>
        {piede && <p className="mt-3 whitespace-pre-line text-slate-600" data-testid="layout-preview-piede">{piede}</p>}
      </div>
    </div>
  );
};

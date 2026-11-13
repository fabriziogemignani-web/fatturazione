import { fmtEUR } from "@/lib/fe";

const Lato = ({ titolo, righe, extra, totale, id, onOpen }) => (
  <div className="flex flex-col" data-testid={`contrapposte-${id}`}>
    <div className="border-b-2 border-slate-900 px-3 py-2 text-xs font-bold uppercase tracking-wider">{titolo}</div>
    <div className="flex-1 divide-y divide-slate-100">
      {righe.map((r) => (
        <div key={r.codice} onClick={() => onOpen(r.codice)} className={`flex cursor-pointer justify-between gap-2 px-3 py-1.5 text-xs hover:bg-blue-50 ${r.livello === 1 ? "bg-slate-50 font-bold" : r.livello === 2 ? "font-semibold" : "pl-6"}`} data-testid={`contrapposte-row-${r.codice}`}>
          <span><span className="mono">{r.codice}</span> {r.descrizione}</span><span className="whitespace-nowrap">{fmtEUR(r.v)}</span>
        </div>
      ))}
      {extra && <div className={`flex justify-between px-3 py-1.5 text-xs font-bold ${extra.cls}`} data-testid={`contrapposte-${id}-risultato`}><span>{extra.label}</span><span>{fmtEUR(extra.v)}</span></div>}
    </div>
    <div className="flex justify-between border-t-2 border-slate-900 px-3 py-2 text-sm font-bold"><span>Totale</span><span data-testid={`contrapposte-${id}-totale`}>{fmtEUR(totale)}</span></div>
  </div>
);

const Prospetto = ({ titolo, sx, dx, onOpen }) => (
  <div className="mb-6 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm print:break-inside-avoid print:shadow-none">
    <div className="bg-slate-900 px-4 py-2 text-sm font-semibold text-white print:bg-white print:text-black">{titolo}</div>
    <div className="grid grid-cols-1 md:grid-cols-2 md:divide-x md:divide-slate-200 print:grid-cols-2 print:divide-x">
      <Lato {...sx} onOpen={onOpen} /><Lato {...dx} onOpen={onOpen} />
    </div>
  </div>
);

export const BilancioContrapposto = ({ d, livello, onOpen }) => {
  const sez = (tipo, sgn) => d.righe.filter((r) => r.tipo === tipo && r.livello <= livello && Math.abs(r.saldo) >= 0.005).map((r) => ({ ...r, v: sgn * r.saldo }));
  const utile = d.risultato >= 0;
  const ris = Math.abs(d.risultato);
  const lab = utile ? "Utile del periodo" : "Perdita del periodo";
  const ok = utile ? "text-emerald-700" : "text-rose-700";
  return (
    <div data-testid="bilancio-contrapposte">
      <Prospetto titolo="Stato patrimoniale" onOpen={onOpen}
        sx={{ titolo: "Attività", id: "attivita", righe: sez("attivita", 1), extra: !utile && ris ? { label: lab, v: ris, cls: ok } : null, totale: d.attivita + (!utile ? ris : 0) }}
        dx={{ titolo: "Passività e patrimonio netto", id: "passivita", righe: sez("passivita", -1), extra: utile && ris ? { label: lab, v: ris, cls: ok } : null, totale: d.passivita + (utile ? ris : 0) }} />
      <Prospetto titolo="Conto economico" onOpen={onOpen}
        sx={{ titolo: "Costi", id: "costi", righe: sez("costo", 1), extra: utile && ris ? { label: lab, v: ris, cls: ok } : null, totale: d.costi + (utile ? ris : 0) }}
        dx={{ titolo: "Ricavi", id: "ricavi", righe: sez("ricavo", -1), extra: !utile && ris ? { label: lab, v: ris, cls: ok } : null, totale: d.ricavi + (!utile ? ris : 0) }} />
    </div>
  );
};

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Printer } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCompany } from "@/context/CompanyContext";
import { SchedaConto } from "@/components/coge/SchedaConto";
import { BilancioContrapposto } from "@/components/coge/BilancioContrapposto";

const Card = ({ label, v, id, cls = "" }) => (
  <div className={`rounded-xl border border-slate-200 bg-white p-4 ${cls}`}><div className="text-xs text-slate-500">{label}</div><div className="mt-1 text-xl font-extrabold" data-testid={id}>{fmtEUR(v)}</div></div>
);

export default function Bilancio() {
  const { company } = useCompany();
  const yr = new Date().getFullYear();
  const [flt, setFlt] = useState({ dal: `${yr}-01-01`, al: `${yr}-12-31` });
  const [livello, setLivello] = useState(3);
  const [d, setD] = useState(null);
  const [scheda, setScheda] = useState(null);
  const [tick, setTick] = useState(0);
  const [vista, setVista] = useState("verifica");
  const stampa = (v) => { setVista(v); setTimeout(() => window.print(), 150); };
  useEffect(() => { api.get("/contabilita/bilancio", { params: flt }).then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e))); }, [flt, tick]);
  if (!d) return <div className="text-sm text-slate-500">Caricamento…</div>;
  const rows = d.righe.filter((r) => r.livello <= livello);
  const quadra = Math.abs(d.dare - d.avere) < 0.01;

  return (
    <div>
      <div className="print:hidden">
        <PageHeader eyebrow="Contabilità generale" title="Bilancio di verifica">
          <Button variant="outline" onClick={() => stampa("verifica")} data-testid="bilancio-print-btn"><Printer className="mr-2 h-4 w-4" />Stampa verifica</Button>
          <Button onClick={() => stampa("contrapposte")} data-testid="bilancio-print-contrapposte-btn"><Printer className="mr-2 h-4 w-4" />Stampa a sezioni contrapposte</Button>
        </PageHeader>
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <label className="text-xs text-slate-600">Dal<Input type="date" value={flt.dal} onChange={(e) => setFlt({ ...flt, dal: e.target.value })} className="w-40 bg-white" data-testid="bilancio-dal" /></label>
          <label className="text-xs text-slate-600">Al<Input type="date" value={flt.al} onChange={(e) => setFlt({ ...flt, al: e.target.value })} className="w-40 bg-white" data-testid="bilancio-al" /></label>
          <label className="text-xs text-slate-600">Dettaglio
            <select value={livello} onChange={(e) => setLivello(Number(e.target.value))} className="block h-9 rounded-md border border-slate-200 bg-white px-2 text-sm" data-testid="bilancio-livello">
              <option value={1}>Solo mastri</option><option value={2}>Mastri e conti</option><option value={3}>Fino ai sottoconti</option>
            </select>
          </label>
          <div className="inline-flex rounded-lg border border-slate-200 bg-white p-1 text-xs font-semibold">
            {[["verifica", "Verifica"], ["contrapposte", "Sezioni contrapposte"]].map(([k, l]) => <button key={k} onClick={() => setVista(k)} className={`rounded-md px-3 py-1.5 transition-colors ${vista === k ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-50"}`} data-testid={`bilancio-vista-${k}`}>{l}</button>)}
          </div>
          <span className={`ml-auto rounded-full px-3 py-1 text-xs font-semibold ${quadra ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"}`} data-testid="bilancio-quadratura">{quadra ? "Dare e avere quadrano" : "Attenzione: dare e avere non quadrano"}</span>
        </div>
        <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-5">
          <Card label="Attività" v={d.attivita} id="bilancio-attivita" />
          <Card label="Passività e netto" v={d.passivita} id="bilancio-passivita" />
          <Card label="Costi" v={d.costi} id="bilancio-costi" />
          <Card label="Ricavi" v={d.ricavi} id="bilancio-ricavi" />
          <Card label={d.risultato >= 0 ? "Utile del periodo" : "Perdita del periodo"} v={Math.abs(d.risultato)} id="bilancio-risultato" cls={d.risultato >= 0 ? "!border-emerald-200 bg-emerald-50" : "!border-rose-200 bg-rose-50"} />
        </div>
        <p className="mb-2 text-xs text-slate-500">Clicca una riga per aprire l'estratto conto del conto.</p>
      </div>
      <div className="mb-4 hidden print:block">
        <div className="text-lg font-bold">{company?.denominazione} · P.IVA {company?.partita_iva}</div>
        <div className="text-sm">{vista === "contrapposte" ? "Bilancio a sezioni contrapposte" : "Bilancio di verifica"} dal {fmtDate(flt.dal)} al {fmtDate(flt.al)} · risultato {fmtEUR(d.risultato)}</div>
      </div>
      {vista === "contrapposte" ? <BilancioContrapposto d={d} livello={livello} onOpen={setScheda} /> : (
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm print:shadow-none">
        <table className="w-full text-sm print:text-[10px]" data-testid="bilancio-table">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr><th className="px-3 py-3">Codice</th><th className="px-3 py-3">Descrizione</th><th className="px-3 py-3">Tipo</th><th className="px-3 py-3 text-right">Dare</th><th className="px-3 py-3 text-right">Avere</th><th className="px-3 py-3 text-right">Saldo dare</th><th className="px-3 py-3 text-right">Saldo avere</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.length === 0 && <tr><td colSpan={7} className="px-4 py-12 text-center text-slate-500" data-testid="bilancio-empty">Nessun movimento nel periodo</td></tr>}
            {rows.map((r) => (
              <tr key={r.codice} onClick={() => setScheda(r.codice)} title="Apri l'estratto conto" className={`cursor-pointer transition-colors hover:bg-blue-50 ${r.livello === 1 ? "bg-slate-50 font-bold" : r.livello === 2 ? "font-semibold" : ""}`} data-testid={`bilancio-row-${r.codice}`}>
                <td className={`mono px-3 py-2 text-xs ${r.livello === 3 ? "pl-8" : r.livello === 2 ? "pl-5" : ""}`}>{r.codice}</td>
                <td className="px-3 py-2 text-xs">{r.descrizione}</td>
                <td className="px-3 py-2 text-xs text-slate-500">{d.tipi[r.tipo]}</td>
                <td className="px-3 py-2 text-right text-xs">{fmtEUR(r.dare)}</td>
                <td className="px-3 py-2 text-right text-xs">{fmtEUR(r.avere)}</td>
                <td className="px-3 py-2 text-right text-xs">{r.saldo > 0 ? fmtEUR(r.saldo) : ""}</td>
                <td className="px-3 py-2 text-right text-xs">{r.saldo < 0 ? fmtEUR(-r.saldo) : ""}</td>
              </tr>
            ))}
          </tbody>
          <tfoot className="border-t-2 border-slate-900 font-bold"><tr><td colSpan={3} className="px-3 py-3">Totali</td><td className="px-3 py-3 text-right" data-testid="bilancio-tot-dare">{fmtEUR(d.dare)}</td><td className="px-3 py-3 text-right" data-testid="bilancio-tot-avere">{fmtEUR(d.avere)}</td><td colSpan={2} /></tr></tfoot>
        </table>
      </div>
      )}
      <SchedaConto conto={scheda} dal={flt.dal} al={flt.al} onClose={() => setScheda(null)} onChanged={() => setTick((x) => x + 1)} />
    </div>
  );
}

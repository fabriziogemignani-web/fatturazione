import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Printer } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCompany } from "@/context/CompanyContext";
import { useConti, ContoSelect, ORIGINE_BADGE } from "@/components/ContoSelect";

const Saldo = ({ v }) => <span className={v < 0 ? "text-rose-700" : ""}>{fmtEUR(Math.abs(v))} {v > 0 ? "D" : v < 0 ? "A" : ""}</span>;

export default function Mastrini() {
  const { company } = useCompany();
  const [conti] = useConti();
  const yr = new Date().getFullYear();
  const [flt, setFlt] = useState({ conto: "", dal: `${yr}-01-01`, al: `${yr}-12-31`, party_id: "" });
  const [d, setD] = useState(null);
  useEffect(() => {
    if (!flt.conto) { setD(null); return; }
    api.get("/contabilita/mastrino", { params: { ...flt, party_id: flt.party_id || undefined } }).then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e)));
  }, [flt]);

  return (
    <div>
      <div className="print:hidden">
        <PageHeader eyebrow="Contabilità generale" title="Schede contabili (mastrini)">
          {d && <Button variant="outline" onClick={() => window.print()} data-testid="mastrino-print-btn"><Printer className="mr-2 h-4 w-4" />Stampa</Button>}
        </PageHeader>
        <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-6">
          <label className="text-xs text-slate-600 sm:col-span-3">Conto (mastro, conto o sottoconto)
            <ContoSelect conti={conti} levels={[1, 2, 3]} value={flt.conto} onChange={(v) => setFlt({ ...flt, conto: v, party_id: "" })} testId="mastrino-conto-select" placeholder="Scegli un conto" />
          </label>
          <label className="text-xs text-slate-600">Dal<Input type="date" value={flt.dal} onChange={(e) => setFlt({ ...flt, dal: e.target.value })} className="bg-white" data-testid="mastrino-dal" /></label>
          <label className="text-xs text-slate-600">Al<Input type="date" value={flt.al} onChange={(e) => setFlt({ ...flt, al: e.target.value })} className="bg-white" data-testid="mastrino-al" /></label>
          {d?.parties?.length > 0 && (
            <label className="text-xs text-slate-600">Cliente / fornitore
              <select value={flt.party_id} onChange={(e) => setFlt({ ...flt, party_id: e.target.value })} className="block h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm" data-testid="mastrino-party-select">
                <option value="">Tutti</option>{d.parties.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
              </select>
            </label>
          )}
        </div>
      </div>
      {!d && <div className="rounded-xl border border-dashed border-slate-300 bg-white p-12 text-center text-sm text-slate-500" data-testid="mastrino-empty-hint">Scegli un conto per vedere la sua scheda con saldo progressivo.</div>}
      {d && (
        <>
          <div className="mb-4 hidden print:block">
            <div className="text-lg font-bold">{company?.denominazione}</div>
            <div className="text-sm">Scheda contabile {d.conto.codice} {d.conto.descrizione} dal {fmtDate(flt.dal)} al {fmtDate(flt.al)}</div>
          </div>
          <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4 print:hidden">
            {[["Saldo iniziale", d.saldo_iniziale, "mastrino-saldo-iniziale"], ["Totale dare", d.dare, "mastrino-dare"], ["Totale avere", -d.avere, "mastrino-avere"], ["Saldo finale", d.saldo_finale, "mastrino-saldo-finale"]].map(([l, v, id]) => (
              <div key={id} className="rounded-xl border border-slate-200 bg-white p-4"><div className="text-xs text-slate-500">{l}</div><div className="mt-1 text-xl font-extrabold" data-testid={id}>{id.endsWith("dare") || id.endsWith("avere") ? fmtEUR(Math.abs(v)) : <Saldo v={v} />}</div></div>
            ))}
          </div>
          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm print:shadow-none">
            <table className="w-full text-sm print:text-[10px]" data-testid="mastrino-table">
              <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
                <tr><th className="px-3 py-3">Data</th><th className="px-3 py-3">N.</th><th className="px-3 py-3">Descrizione</th><th className="px-3 py-3">Contropartita</th><th className="px-3 py-3 text-right">Dare</th><th className="px-3 py-3 text-right">Avere</th><th className="px-3 py-3 text-right">Saldo</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                <tr className="bg-slate-50/60 text-xs"><td colSpan={6} className="px-3 py-2 font-semibold">Saldo iniziale al {fmtDate(flt.dal)}</td><td className="px-3 py-2 text-right font-semibold"><Saldo v={d.saldo_iniziale} /></td></tr>
                {d.movimenti.map((m) => (
                  <tr key={m.id} data-testid={`mastrino-row-${m.id}`}>
                    <td className="whitespace-nowrap px-3 py-2 text-xs">{fmtDate(m.data)}</td>
                    <td className="mono px-3 py-2 text-xs">{m.numero}/{m.anno}</td>
                    <td className="px-3 py-2 text-xs">{m.causale} · {m.descrizione}{m.party_nome && <div className="text-slate-500">{m.party_nome}</div>}<span className={`ml-1 rounded px-1 text-[10px] print:hidden ${ORIGINE_BADGE[m.origine]}`}>{m.origine}</span></td>
                    <td className="px-3 py-2 text-xs text-slate-500">{m.contropartite.join(", ")}</td>
                    <td className="px-3 py-2 text-right text-xs">{m.dare ? fmtEUR(m.dare) : ""}</td>
                    <td className="px-3 py-2 text-right text-xs">{m.avere ? fmtEUR(m.avere) : ""}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-right text-xs font-semibold"><Saldo v={m.saldo} /></td>
                  </tr>
                ))}
                {d.movimenti.length === 0 && <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-500" data-testid="mastrino-no-movs">Nessun movimento nel periodo</td></tr>}
              </tbody>
              <tfoot className="border-t-2 border-slate-900 font-bold"><tr><td colSpan={4} className="px-3 py-3">Totali e saldo finale</td><td className="px-3 py-3 text-right">{fmtEUR(d.dare)}</td><td className="px-3 py-3 text-right">{fmtEUR(d.avere)}</td><td className="whitespace-nowrap px-3 py-3 text-right"><Saldo v={d.saldo_finale} /></td></tr></tfoot>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

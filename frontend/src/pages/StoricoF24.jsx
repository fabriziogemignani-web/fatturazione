import { useEffect, useState } from "react";
import { toast } from "sonner";
import { FileDown } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { useCompany } from "@/context/CompanyContext";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { F24Dialog } from "@/components/F24Dialog";
import { downloadF24Ritenute, downloadF24Bolli } from "@/components/ScadenzeFiscaliPanel";

const TIPI = { iva: ["IVA", "bg-blue-50 text-blue-700"], ritenute: ["Ritenute", "bg-violet-50 text-violet-700"], bolli: ["Bolli", "bg-teal-50 text-teal-700"] };

const Filtro = ({ value, onChange, items, testId, all }) => (
  <Select value={value} onValueChange={onChange}>
    <SelectTrigger className="w-44 bg-white" data-testid={testId}><SelectValue /></SelectTrigger>
    <SelectContent className="bg-white">
      <SelectItem value="tutti">{all}</SelectItem>
      {items.map(([k, l]) => <SelectItem key={k} value={String(k)} data-testid={`${testId}-${k}`}>{l}</SelectItem>)}
    </SelectContent>
  </Select>
);

const Totali = ({ d }) => (
  <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
    <div className="rounded-xl bg-slate-900 p-4 text-white" data-testid="f24s-totale"><div className="text-xs uppercase tracking-wider text-slate-300">Totale versato</div><div className="mt-1 text-2xl font-bold">{fmtEUR(d.totale)}</div><div className="text-xs text-slate-300">{d.versamenti.length} F24</div></div>
    {Object.entries(TIPI).map(([k, [l]]) => (
      <div key={k} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm" data-testid={`f24s-totale-${k}`}><div className="text-xs uppercase tracking-wider text-slate-500">{l}</div><div className="mt-1 text-xl font-bold">{fmtEUR(d.totali[k])}</div></div>
    ))}
  </div>
);

const Riga = ({ v, onIva }) => {
  const ristampa = () => (v.tipo === "iva" ? onIva(v.f24) : v.tipo === "bolli" ? downloadF24Bolli(v.anno, v.trimestre) : downloadF24Ritenute(v.key));
  return (
    <tr className="hover:bg-slate-50" data-testid={`f24s-row-${v.key}`}>
      <td className="whitespace-nowrap px-4 py-3">{fmtDate(v.data)}</td>
      <td className="px-4 py-3"><span className={`rounded px-2 py-0.5 text-xs font-semibold ${TIPI[v.tipo][1]}`}>{TIPI[v.tipo][0]}</span></td>
      <td className="px-4 py-3">{v.periodo_label}<div className="text-xs text-slate-400">registrato da {v.by}</div></td>
      <td className="mono px-4 py-3">{v.codice}</td>
      <td className="px-4 py-3 text-xs">{v.coge_rif || <span className="text-slate-400">—</span>}</td>
      <td className="px-4 py-3 text-right font-semibold">{fmtEUR(v.importo)}</td>
      <td className="px-4 py-3 text-right"><Button size="sm" variant="outline" onClick={ristampa} data-testid={`f24s-ristampa-${v.key}`}><FileDown className="mr-1 h-3.5 w-3.5" />Ristampa</Button></td>
    </tr>
  );
};

export default function StoricoF24() {
  const { company } = useCompany();
  const [anno, setAnno] = useState("tutti");
  const [tipo, setTipo] = useState("tutti");
  const [d, setD] = useState(null);
  const [f24, setF24] = useState(null);
  useEffect(() => {
    const params = { ...(anno !== "tutti" ? { anno } : {}), ...(tipo !== "tutti" ? { tipo } : {}) };
    api.get("/f24-storico", { params }).then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e)));
  }, [anno, tipo, company?.id]);
  return (
    <div>
      <PageHeader eyebrow="Fisco e IVA" title="Storico versamenti F24">
        <div className="flex flex-wrap gap-2">
          <Filtro value={anno} onChange={setAnno} items={(d?.anni || []).map((a) => [a, String(a)])} testId="f24s-anno" all="Tutti gli anni" />
          <Filtro value={tipo} onChange={setTipo} items={Object.entries(TIPI).map(([k, [l]]) => [k, l])} testId="f24s-tipo" all="Tutti i tributi" />
        </div>
      </PageHeader>
      {!d ? <p className="text-sm text-slate-500">Caricamento…</p> : (
        <>
          <Totali d={d} />
          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
            <table className="w-full text-sm" data-testid="f24s-table">
              <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
                <tr><th className="px-4 py-3 font-medium">Versato il</th><th className="px-4 py-3 font-medium">Tributo</th><th className="px-4 py-3 font-medium">Periodo</th><th className="px-4 py-3 font-medium">Codice</th><th className="px-4 py-3 font-medium">Prima nota</th><th className="px-4 py-3 text-right font-medium">Importo</th><th className="px-4 py-3" /></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {d.versamenti.length === 0 && <tr><td colSpan={7} className="px-4 py-10 text-center text-slate-500" data-testid="f24s-empty">Nessun F24 segnato come versato</td></tr>}
                {d.versamenti.map((v) => <Riga key={v.key} v={v} onIva={setF24} />)}
              </tbody>
            </table>
          </div>
        </>
      )}
      <F24Dialog req={f24} onClose={() => setF24(null)} />
    </div>
  );
}

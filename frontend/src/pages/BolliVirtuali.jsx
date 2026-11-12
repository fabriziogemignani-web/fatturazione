import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Printer } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { useCompany } from "@/context/CompanyContext";
import { PageHeader } from "@/components/Common";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

const scaricaF24 = async (anno, q) => {
  try {
    const { data } = await api.get("/bolli/f24", { params: { anno, trimestre: q }, responseType: "blob" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(data); a.download = `F24_bolli_${anno}_T${q}.pdf`; a.click(); URL.revokeObjectURL(a.href);
  } catch (e) {
    const msg = e.response?.data instanceof Blob ? JSON.parse(await e.response.data.text()).detail : errMsg(e);
    toast.error(typeof msg === "string" ? msg : "Impossibile preparare l'F24");
  }
};

const MESI = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"];
const TIPO = { fatture: "Fattura", note_credito: "Nota di credito", autofatture: "Autofattura" };
const TH = "px-4 py-3 font-medium";

const Trimestri = ({ d }) => (
  <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-5">
    <div className="rounded-xl border border-slate-900 bg-slate-900 p-4 text-white" data-testid="bolli-totale-anno">
      <div className="text-xs uppercase tracking-wider text-slate-300">Totale {d.anno}</div>
      <div className="mt-1 text-2xl font-bold">{fmtEUR(d.totale)}</div>
      <div className="text-xs text-slate-300">{d.n} bolli · addebitati {fmtEUR(d.addebitati)}</div>
    </div>
    {d.trimestri.map((q) => (
      <div key={q.trimestre} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm" data-testid={`bolli-trimestre-${q.trimestre}`}>
        <div className="text-xs uppercase tracking-wider text-slate-500">{q.trimestre}° trimestre</div>
        <div className="mt-1 text-xl font-bold">{fmtEUR(q.importo)}</div>
        <div className="text-xs text-slate-500">F24 cod. {q.codice_tributo} · entro {fmtDate(q.scadenza)}</div>
        {q.importo > 0 && <Button size="sm" variant="outline" className="mt-2 h-7 text-xs" onClick={() => scaricaF24(d.anno, q.trimestre)} data-testid={`bolli-f24-btn-${q.trimestre}`}><Printer className="mr-1 h-3.5 w-3.5" />Prepara F24</Button>}
      </div>
    ))}
  </div>
);

const Mesi = ({ d }) => (
  <div className="mb-6 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
    <table className="w-full text-sm" data-testid="bolli-mesi-table">
      <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
        <tr><th className={TH}>Mese</th><th className={`${TH} text-right`}>Fatture</th><th className={`${TH} text-right`}>Note credito</th><th className={`${TH} text-right`}>Autofatture</th><th className={`${TH} text-right`}>Addebitati</th><th className={`${TH} text-right`}>Da pagare</th></tr>
      </thead>
      <tbody className="divide-y divide-slate-100">
        {d.mesi.map((m) => (
          <tr key={m.mese} className={m.n ? "" : "text-slate-400"} data-testid={`bolli-mese-${m.mese}`}>
            <td className="px-4 py-2.5">{MESI[m.mese - 1]}{m.bozze > 0 && <span className="ml-2 text-xs text-amber-700">+{m.bozze} in bozza</span>}</td>
            <td className="px-4 py-2.5 text-right">{m.fatture}</td><td className="px-4 py-2.5 text-right">{m.note_credito}</td><td className="px-4 py-2.5 text-right">{m.autofatture}</td>
            <td className="px-4 py-2.5 text-right">{fmtEUR(m.addebitati)}</td><td className="px-4 py-2.5 text-right font-semibold">{fmtEUR(m.importo)}</td>
          </tr>
        ))}
      </tbody>
      <tfoot><tr className="border-t-2 border-slate-900 font-bold"><td className="px-4 py-3" colSpan={5}>Totale anno</td><td className="px-4 py-3 text-right" data-testid="bolli-mesi-totale">{fmtEUR(d.totale)}</td></tr></tfoot>
    </table>
  </div>
);

const Documenti = ({ rows }) => (
  <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
    <table className="w-full text-sm" data-testid="bolli-docs-table">
      <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
        <tr><th className={TH}>Data</th><th className={TH}>Documento</th><th className={TH}>Cliente</th><th className={`${TH} text-right`}>Esenti</th><th className={TH}>Bollo</th></tr>
      </thead>
      <tbody className="divide-y divide-slate-100">
        {rows.length === 0 && <tr><td colSpan={5} className="px-4 py-10 text-center text-slate-500" data-testid="bolli-empty">Nessun documento con bollo virtuale nell'anno</td></tr>}
        {rows.map((r) => (
          <tr key={r.id} className={r.da_pagare ? "" : "text-slate-400"} data-testid={`bolli-doc-${r.id}`}>
            <td className="px-4 py-2.5">{fmtDate(r.data)}</td>
            <td className="px-4 py-2.5"><Link to={`/fatture/${r.id}`} className="mono font-medium text-blue-700 hover:underline">{r.numero_display}</Link><div className="text-xs text-slate-400">{TIPO[r.tipo]}{!r.da_pagare && ` · ${r.status}, non conteggiato`}</div></td>
            <td className="px-4 py-2.5">{r.cliente}</td>
            <td className="px-4 py-2.5 text-right">{fmtEUR(r.esenti)}</td>
            <td className="px-4 py-2.5">{fmtEUR(r.importo)} <span className="text-xs text-slate-500">{r.addebitato ? "addebitato" : "a carico"}</span></td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

export default function BolliVirtuali() {
  const { company } = useCompany();
  const [anno, setAnno] = useState(new Date().getFullYear());
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/bolli", { params: { anno } }).then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e))); }, [anno, company?.id]);
  return (
    <div>
      <PageHeader eyebrow="Fisco e IVA" title="Bolli virtuali">
        <Input type="number" value={anno} onChange={(e) => setAnno(Number(e.target.value) || new Date().getFullYear())} className="w-28 bg-white" data-testid="bolli-anno-input" />
      </PageHeader>
      <p className="mb-4 text-xs text-slate-500">Bollo di 2 € sulle fatture con importi esenti o non imponibili oltre 77,47 €. Bozze e documenti scartati non sono conteggiati. Il versamento è trimestrale con F24.</p>
      {d ? <><Trimestri d={d} /><Mesi d={d} /><Documenti rows={d.righe} /></> : <p className="text-sm text-slate-500">Caricamento…</p>}
    </div>
  );
}

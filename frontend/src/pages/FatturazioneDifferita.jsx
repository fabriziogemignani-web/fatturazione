import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { FileStack } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate, today } from "@/lib/fe";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";

const meseScorso = () => {
  const d = new Date();
  const a = new Date(d.getFullYear(), d.getMonth() - 1, 1);
  const b = new Date(d.getFullYear(), d.getMonth(), 0);
  const iso = (x) => `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, "0")}-${String(x.getDate()).padStart(2, "0")}`;
  return [iso(a), iso(b)];
};

export default function FatturazioneDifferita() {
  const [[dal, al], setPer] = useState(meseScorso());
  const [dataFatt, setDataFatt] = useState(today());
  const [gruppi, setGruppi] = useState([]);
  const [sel, setSel] = useState([]);
  const [esito, setEsito] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = () => api.get("/ddt/fatturazione", { params: { dal, al } }).then(({ data }) => { setGruppi(data); setSel(data.map((g) => g.party_id)); }).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, [dal, al]); // eslint-disable-line react-hooks/exhaustive-deps
  const genera = async () => {
    if (!window.confirm(`Generare ${sel.length} fatture riepilogative con data ${fmtDate(dataFatt)}?`)) return;
    setBusy(true);
    try {
      const { data } = await api.post("/ddt/fatturazione", { dal, al, data_fattura: dataFatt, party_ids: sel });
      setEsito(data);
      toast.success(`Create ${data.fatture.length} fatture differite`);
      data.errori.forEach((x) => toast.error(`${x.cliente}: ${x.errore}`));
      load();
    } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };
  const tot = gruppi.filter((g) => sel.includes(g.party_id)).reduce((s, g) => s + g.imponibile, 0);
  return (
    <div>
      <PageHeader eyebrow="Vendite" title="Fatturazione differita">
        <Button onClick={genera} disabled={busy || !sel.length} data-testid="diff-genera-btn"><FileStack className="mr-2 h-4 w-4" />Genera fatture ({sel.length})</Button>
      </PageHeader>
      <div className="mb-4 flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4">
        <label className="text-xs text-slate-600">DDT dal<Input type="date" value={dal} onChange={(e) => setPer([e.target.value, al])} data-testid="diff-dal-input" /></label>
        <label className="text-xs text-slate-600">al<Input type="date" value={al} onChange={(e) => setPer([dal, e.target.value])} data-testid="diff-al-input" /></label>
        <label className="text-xs text-slate-600">Data fattura<Input type="date" value={dataFatt} onChange={(e) => setDataFatt(e.target.value)} data-testid="diff-data-input" /></label>
        <p className="max-w-md text-xs text-slate-500">Una fattura differita (TD24) per cliente con tutti i DDT di vendita confermati del periodo. La fattura va emessa entro il 15 del mese successivo ai DDT.</p>
      </div>
      {esito?.fatture.length > 0 && (
        <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900" data-testid="diff-esito">
          <div className="mb-1 font-semibold">Fatture create (in bozza, da controllare e inviare allo SDI):</div>
          {esito.fatture.map((f) => <div key={f.id}><Link to={`/fatture/${f.id}`} className="font-semibold underline" data-testid={`diff-fattura-${f.id}`}>{f.numero_display}</Link> · {f.cliente} · {f.ddt} DDT · {fmtEUR(f.totale)}</div>)}
        </div>
      )}
      <div className="rounded-xl border border-slate-200 bg-white">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3 text-sm">
          <span className="font-semibold text-slate-800">Clienti da fatturare ({gruppi.length})</span>
          <span className="text-slate-600">Imponibile selezionato <b className="text-slate-900" data-testid="diff-totale">{fmtEUR(tot)}</b></span>
        </div>
        <div className="divide-y divide-slate-100">
          {gruppi.map((g) => (
            <div key={g.party_id} className="flex gap-3 px-5 py-3" data-testid={`diff-cliente-${g.party_id}`}>
              <Checkbox checked={sel.includes(g.party_id)} onCheckedChange={() => setSel((s) => (s.includes(g.party_id) ? s.filter((x) => x !== g.party_id) : [...s, g.party_id]))} data-testid={`diff-check-${g.party_id}`} />
              <div className="flex-1">
                <div className="flex justify-between text-sm"><span className="font-semibold text-slate-900">{g.cliente}</span><span className="tabular-nums">{fmtEUR(g.imponibile)}</span></div>
                <div className="mt-1 flex flex-wrap gap-1.5">{g.ddt.map((d) => <Link key={d.id} to={`/ddt/${d.id}`} className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600 hover:bg-slate-200">DDT {d.numero_display} · {fmtDate(d.data)} · {fmtEUR(d.imponibile)}</Link>)}</div>
              </div>
            </div>
          ))}
          {gruppi.length === 0 && <p className="px-5 py-10 text-center text-sm text-slate-500" data-testid="diff-empty">Nessun DDT di vendita da fatturare nel periodo</p>}
        </div>
      </div>
    </div>
  );
}

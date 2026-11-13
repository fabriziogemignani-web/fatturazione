import { useEffect, useRef, useState } from "react";
import { Plus, Trash2, Wand2 } from "lucide-react";
import { fmtEUR } from "@/lib/fe";
import { useInvalid } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";

const addDays = (iso, d, endMonth) => {
  const x = new Date(`${iso}T00:00:00Z`);
  x.setUTCDate(x.getUTCDate() + d);
  if (endMonth) return new Date(Date.UTC(x.getUTCFullYear(), x.getUTCMonth() + 1, 0)).toISOString().slice(0, 10);
  return x.toISOString().slice(0, 10);
};

export const splitRate = (netto, n, gg, base, fm) => {
  const per = Math.floor((netto / n) * 100) / 100;
  return Array.from({ length: n }, (_, k) => ({
    scadenza: addDays(base, gg * (k + 1), fm),
    importo: k === n - 1 ? Math.round((netto - per * (n - 1)) * 100) / 100 : per,
  }));
};

export const RateCard = ({ form, setForm, netto, client }) => {
  const [n, setN] = useState(client?.pagamento_rate > 1 ? client.pagamento_rate : 3);
  const [gg, setGg] = useState(client?.pagamento_giorni ?? 30);
  const [fm, setFm] = useState(!!client?.pagamento_fine_mese);
  const auto = useRef(!form.id && client?.pagamento_rate > 1 && !(form.rate || []).length);
  const [bad, clear] = useInvalid();
  const rate = form.rate || [];
  useEffect(() => {
    if (!auto.current || netto <= 0) return undefined;
    const h = setTimeout(() => {
      if (!auto.current) return;
      const r = splitRate(netto, client.pagamento_rate, client.pagamento_giorni ?? 30, form.data, !!client.pagamento_fine_mese);
      setForm((f) => ({ ...f, rate: r, scadenza: r.reduce((m, x) => (x.scadenza > m ? x.scadenza : m), "") }));
    }, 700);
    return () => clearTimeout(h);
  }, [netto, form.data]); // eslint-disable-line react-hooks/exhaustive-deps
  const setRate = (r) => {
    auto.current = false;
    clear("rate");
    const last = r.reduce((m, x) => (x.scadenza > m ? x.scadenza : m), "");
    setForm((f) => ({ ...f, rate: r, ...(r.length ? { scadenza: last } : {}) }));
  };
  const sum = Math.round(rate.reduce((s, r) => s + Number(r.importo || 0), 0) * 100) / 100;
  const diff = Math.round((netto - sum) * 100) / 100;
  const upd = (i, k, v) => { clear(`rate.${i}.${k}`); setRate(rate.map((r, j) => (j === i ? { ...r, [k]: v } : r))); };

  return (
    <div className={`rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm ${bad("rate")}`} data-testid="rate-card">
      <h3 className="text-lg font-semibold text-slate-800">Scadenze di pagamento</h3>
      <p className="mb-4 text-xs text-slate-500">{rate.length ? `${rate.length} rate · netto a pagare ${fmtEUR(netto)}` : "Unica scadenza (campo Scadenza sopra) oppure dividi il netto in più rate."}</p>
      <div className="mb-4 flex flex-wrap items-end gap-3 rounded-lg bg-slate-50 p-3">
        <label className="text-xs text-slate-600">N. rate<Input type="number" min="2" max="36" className="mt-1 w-20 bg-white" value={n} onChange={(e) => setN(Math.max(2, Math.min(36, Number(e.target.value) || 2)))} data-testid="rate-count-input" /></label>
        <label className="text-xs text-slate-600">Ogni (giorni)<Input type="number" min="0" className="mt-1 w-24 bg-white" value={gg} onChange={(e) => setGg(Math.max(0, Number(e.target.value) || 0))} data-testid="rate-interval-input" /></label>
        <label className="flex items-center gap-2 pb-2 text-xs text-slate-600"><Checkbox checked={fm} onCheckedChange={(v) => setFm(!!v)} data-testid="rate-endmonth-checkbox" />Fine mese</label>
        <Button type="button" variant="outline" size="sm" onClick={() => setRate(splitRate(netto, n, gg, form.data, fm))} disabled={netto <= 0} data-testid="rate-generate-btn"><Wand2 className="mr-1.5 h-4 w-4" />Genera rate</Button>
      </div>
      {rate.map((r, i) => (
        <div key={i} className="mb-2 grid grid-cols-12 items-center gap-2" data-testid={`rata-row-${i}`}>
          <span className="col-span-2 text-xs font-semibold text-slate-500">Rata {i + 1}</span>
          <Input type="date" className={`col-span-5 ${bad(`rate.${i}.scadenza`)}`} value={r.scadenza} onChange={(e) => upd(i, "scadenza", e.target.value)} data-testid={`rata-date-${i}`} />
          <Input type="number" step="0.01" className={`col-span-4 ${bad(`rate.${i}.importo`)}`} value={r.importo} onChange={(e) => upd(i, "importo", e.target.value)} data-testid={`rata-amount-${i}`} />
          <Button type="button" variant="ghost" size="icon" className="col-span-1" onClick={() => setRate(rate.filter((_, j) => j !== i))} data-testid={`rata-remove-${i}`}><Trash2 className="h-4 w-4 text-slate-400" /></Button>
        </div>
      ))}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={() => setRate([...rate, { scadenza: form.data, importo: Math.max(diff, 0) }])} data-testid="rata-add-btn"><Plus className="mr-1 h-4 w-4" />Aggiungi rata</Button>
        {rate.length > 0 && Math.abs(diff) > 0.005 && (
          <>
            <span className="text-xs font-medium text-rose-600" data-testid="rate-mismatch">Somma rate {fmtEUR(sum)}: differenza {fmtEUR(diff)}</span>
            <Button type="button" variant="outline" size="sm" onClick={() => upd(rate.length - 1, "importo", Math.round((Number(rate[rate.length - 1].importo || 0) + diff) * 100) / 100)} data-testid="rate-fix-btn">Adatta ultima rata</Button>
          </>
        )}
        {rate.length > 0 && <Button type="button" variant="ghost" size="sm" className="text-rose-600" onClick={() => setRate([])} data-testid="rate-clear-btn">Rimuovi rate</Button>}
      </div>
    </div>
  );
};

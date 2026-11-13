import { useEffect, useState } from "react";
import { CASSE, RITENUTE, CAUSALI } from "@/lib/fe";
import { api } from "@/lib/api";
import { Switch } from "@/components/ui/switch";

const Sel = ({ value, onChange, items, testId, empty }) => (
  <select value={value || ""} onChange={(e) => onChange(e.target.value)} className="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm" data-testid={testId}>
    {empty && <option value="">{empty}</option>}
    {items.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
  </select>
);

const Num = ({ value, onChange, testId }) => (
  <input type="number" min={0} max={100} step="0.01" value={value ?? ""} onChange={(e) => onChange(e.target.value === "" ? 0 : Number(e.target.value))}
    className="h-9 w-full rounded-md border border-slate-200 px-2 text-sm" data-testid={testId} />
);

const L = ({ t, children }) => <label className="space-y-1 text-xs font-medium text-slate-600"><span>{t}</span>{children}</label>;

export const AssoggettamentoFornitore = ({ form, setForm }) => {
  const set = (k) => (v) => setForm({ ...form, [k]: v });
  const [codici, setCodici] = useState([]);
  useEffect(() => { api.get("/codici-tributo", { params: { categoria: "ritenute" } }).then(({ data }) => setCodici(data.codici.map((c) => [c.codice, `${c.codice} - ${c.descrizione}`]))).catch(() => {}); }, []);
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-4" data-testid="party-assoggettamento">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-slate-800">Assoggettamento fiscale (professionisti)</div>
          <p className="text-xs text-slate-500">Se la fattura ricevuta non riporta la ritenuta, viene calcolata da questi dati e registrata in contabilità (debito verso Erario c/ritenute).</p>
        </div>
        <Switch checked={!!form.soggetto_ritenuta} onCheckedChange={set("soggetto_ritenuta")} data-testid="party-soggetto-ritenuta-switch" />
      </div>
      {form.soggetto_ritenuta && (
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-4">
          <div className="sm:col-span-2"><L t="Tipo ritenuta"><Sel value={form.ritenuta_tipo} onChange={set("ritenuta_tipo")} items={RITENUTE} testId="party-ritenuta-tipo" /></L></div>
          <L t="Aliquota ritenuta %"><Num value={form.ritenuta_aliquota} onChange={set("ritenuta_aliquota")} testId="party-ritenuta-aliquota" /></L>
          <L t="Base imponibile %"><Num value={form.ritenuta_base} onChange={set("ritenuta_base")} testId="party-ritenuta-base" /></L>
          <div className="sm:col-span-4"><L t="Causale pagamento (770)"><Sel value={form.ritenuta_causale} onChange={set("ritenuta_causale")} items={CAUSALI} testId="party-ritenuta-causale" /></L></div>
          <div className="sm:col-span-4"><L t="Codice tributo F24 della ritenuta"><Sel value={form.ritenuta_codice_tributo || "1040"} onChange={set("ritenuta_codice_tributo")} items={codici.length ? codici : [["1040", "1040 - Lavoro autonomo"]]} testId="party-ritenuta-codice-tributo" /></L></div>
          <div className="sm:col-span-2"><L t="Cassa previdenziale"><Sel value={form.cassa_tipo} onChange={set("cassa_tipo")} items={CASSE} empty="Nessuna cassa" testId="party-cassa-tipo" /></L></div>
          {form.cassa_tipo && <L t="Aliquota cassa %"><Num value={form.cassa_aliquota} onChange={set("cassa_aliquota")} testId="party-cassa-aliquota" /></L>}
          {form.cassa_tipo && <label className="flex items-end gap-2 pb-2 text-xs text-slate-600"><Switch checked={!!form.cassa_ritenuta} onCheckedChange={set("cassa_ritenuta")} data-testid="party-cassa-ritenuta-switch" />Cassa soggetta a ritenuta</label>}
          <p className="text-[11px] text-slate-500 sm:col-span-4">Es. professionista: RT01, 20%, base 100%, causale A. Agente di commercio: base 50% (o 20% con dipendenti), causale Q o R.</p>
        </div>
      )}
    </div>
  );
};

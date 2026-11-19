import { NSelect } from "@/components/ui/nselect";

import { useEffect, useState } from "react";
import { CASSE, RITENUTE, CAUSALI } from "@/lib/fe";
import { api } from "@/lib/api";
import { Switch } from "@/components/ui/switch";

const Sel = ({ value, onChange, items, testId, empty }) => (
  <NSelect value={value || ""} onChange={(e) => onChange(e.target.value)} className="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm" data-testid={testId}>
    {empty && <option value="">{empty}</option>}
    {items.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
  </NSelect>
);

const Num = ({ value, onChange, testId }) => (
  <input type="number" min={0} max={100} step="0.01" value={value ?? ""} onChange={(e) => onChange(e.target.value === "" ? 0 : Number(e.target.value))}
    className="h-9 w-full rounded-md border border-slate-200 px-2 text-sm" data-testid={testId} />
);

const L = ({ t, children }) => <label className="space-y-1 text-xs font-medium text-slate-600"><span>{t}</span>{children}</label>;

const REGIMI = [["ordinario", "Regime ordinario (IVA e ritenuta)"], ["forfettario", "Forfettario / minimi (niente IVA e niente ritenuta)"], ["occasionale", "Prestazione occasionale (fuori campo IVA, ritenuta sul lordo)"]];
const TIPI_CASSA = [["privata", "Cassa privata (es. Forense, Inarcassa): fuori dalla base della ritenuta"], ["inps", "Rivalsa INPS 4% (gestione separata): dentro la base della ritenuta"]];

export const AssoggettamentoFornitore = ({ form, setForm }) => {
  const set = (k) => (v) => setForm({ ...form, [k]: v });
  const [codici, setCodici] = useState([]);
  useEffect(() => { api.get("/codici-tributo", { params: { categoria: "ritenute" } }).then(({ data }) => setCodici(data.codici.map((c) => [c.codice, `${c.codice} - ${c.descrizione}`]))).catch(() => {}); }, []);
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-4" data-testid="party-assoggettamento">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-slate-800">Assoggettamento fiscale (professionisti)</div>
          <p className="text-xs text-slate-500">Le fatture ricevute da questo fornitore vengono calcolate con questi dati (ritenuta, cassa, regime), anche se il file XML riporta valori diversi. Il bollo viene letto dal file XML.</p>
        </div>
        <Switch checked={!!form.soggetto_ritenuta} onCheckedChange={set("soggetto_ritenuta")} data-testid="party-soggetto-ritenuta-switch" />
      </div>
      {form.soggetto_ritenuta && (
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-4">
          <div className="sm:col-span-4"><L t="Regime del professionista"><Sel value={form.regime_percipiente || "ordinario"} onChange={set("regime_percipiente")} items={REGIMI} testId="party-regime-percipiente" /></L></div>
          {form.regime_percipiente === "forfettario" && <p className="rounded-md bg-amber-50 p-2 text-[11px] text-amber-800 sm:col-span-4" data-testid="party-regime-nota">Forfettario/minimi: non viene calcolata la ritenuta e l'intero importo (compreso bollo riaddebitato) va a costo. Dal 2024 non serve la CU.</p>}
          <div className="sm:col-span-2"><L t="Tipo ritenuta"><Sel value={form.ritenuta_tipo} onChange={set("ritenuta_tipo")} items={RITENUTE} testId="party-ritenuta-tipo" /></L></div>
          <L t="Aliquota ritenuta %"><Num value={form.ritenuta_aliquota} onChange={set("ritenuta_aliquota")} testId="party-ritenuta-aliquota" /></L>
          <L t="Base imponibile %"><Num value={form.ritenuta_base} onChange={set("ritenuta_base")} testId="party-ritenuta-base" /></L>
          <div className="sm:col-span-4"><L t="Causale pagamento (770)"><Sel value={form.ritenuta_causale} onChange={set("ritenuta_causale")} items={CAUSALI} testId="party-ritenuta-causale" /></L></div>
          <div className="sm:col-span-4"><L t="Codice tributo F24 della ritenuta"><Sel value={form.ritenuta_codice_tributo || "1040"} onChange={set("ritenuta_codice_tributo")} items={codici.length ? codici : [["1040", "1040 - Lavoro autonomo"]]} testId="party-ritenuta-codice-tributo" /></L></div>
          <div className="sm:col-span-2"><L t="Cassa previdenziale"><Sel value={form.cassa_tipo} onChange={set("cassa_tipo")} items={CASSE} empty="Nessuna cassa" testId="party-cassa-tipo" /></L></div>
          {form.cassa_tipo && <L t="Aliquota cassa %"><Num value={form.cassa_aliquota} onChange={set("cassa_aliquota")} testId="party-cassa-aliquota" /></L>}
          {form.cassa_tipo && <div className="sm:col-span-4"><L t="Tipo di cassa"><Sel value={form.cassa_ritenuta ? "inps" : "privata"} onChange={(v) => setForm({ ...form, cassa_ritenuta: v === "inps" })} items={TIPI_CASSA} testId="party-cassa-natura" /></L></div>}
          <p className="text-[11px] text-slate-500 sm:col-span-4">Es. professionista: RT01, 20%, base 100%, causale A. Prestazione occasionale: causale M. I rimborsi spese art. 15 (natura N1) restano fuori dalla ritenuta e vanno su "Spese anticipate da professionisti".</p>
        </div>
      )}
    </div>
  );
};

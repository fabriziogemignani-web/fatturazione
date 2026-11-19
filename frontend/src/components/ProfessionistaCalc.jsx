import { useState } from "react";
import { Calculator } from "lucide-react";
import { fmtEUR } from "@/lib/fe";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const r2 = (v) => Math.round((Number(v) || 0) * 100) / 100;
const REG = { ordinario: "regime ordinario", forfettario: "forfettario / minimi", occasionale: "prestazione occasionale" };

export const calcolaProfessionista = (p, { compenso, rimborsi, esente, bollo }) => {
  const regime = p.regime_percipiente || "ordinario";
  const c = r2(compenso);
  const cassa = p.cassa_tipo && regime !== "occasionale" ? r2(c * (Number(p.cassa_aliquota) || 0) / 100) : 0;
  const imp = r2(c + cassa);
  const senzaIva = regime !== "ordinario" || esente;
  const righe = [senzaIva ? { aliquota: 0, natura: regime === "ordinario" ? "N4" : "N2.2", totale: imp } : { aliquota: 22, natura: "", totale: r2(imp * 1.22) }];
  const conBollo = bollo && senzaIva && imp > 77.47;
  const n1 = r2((Number(rimborsi) || 0) + (conBollo ? 2 : 0));
  if (n1) righe.push({ aliquota: 0, natura: "N1", totale: n1 });
  const sog = p.soggetto_ritenuta && regime !== "forfettario";
  const base = regime === "occasionale" ? c : r2((c + (p.cassa_ritenuta ? cassa : 0)) * (Number(p.ritenuta_base) || 100) / 100);
  const rit = sog ? r2(base * (Number(p.ritenuta_aliquota) || 0) / 100) : 0;
  const totale = r2(righe.reduce((s, x) => s + x.totale, 0));
  return { righe, cassa, conBollo, rit_al: sog ? String(p.ritenuta_aliquota ?? 20) : "", rit_base: sog ? String(base) : "", rit, totale, netto: r2(totale - rit) };
};

export const ProfessionistaCalc = ({ p, onApply }) => {
  const [v, setV] = useState({ compenso: "", rimborsi: "", esente: false, bollo: true });
  const regime = p.regime_percipiente || "ordinario";
  const res = Number(v.compenso) > 0 ? calcolaProfessionista(p, v) : null;
  const set = (k) => (e) => setV({ ...v, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  return (
    <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50/50 p-4 text-xs text-slate-700" data-testid="regv-professionista">
      <div className="mb-2 flex items-center gap-2 font-semibold text-slate-800"><Calculator className="h-4 w-4 text-blue-700" />Calcolo fattura professionista · {REG[regime]}{p.cassa_tipo && regime !== "occasionale" ? ` · cassa ${p.cassa_aliquota}% ${p.cassa_ritenuta ? "rivalsa INPS" : "privata"}` : ""}</div>
      <div className="flex flex-wrap items-end gap-3">
        <label>Compenso €<Input type="number" min={0} step="0.01" value={v.compenso} onChange={set("compenso")} className="w-32 bg-white" data-testid="regv-prof-compenso" /></label>
        <label>Rimborsi spese art. 15 €<Input type="number" min={0} step="0.01" value={v.rimborsi} onChange={set("rimborsi")} className="w-32 bg-white" data-testid="regv-prof-rimborsi" /></label>
        {regime === "ordinario" && <label className="flex items-center gap-1.5 pb-2"><input type="checkbox" checked={v.esente} onChange={set("esente")} data-testid="regv-prof-esente" />Prestazione esente IVA (N4)</label>}
        {(regime !== "ordinario" || v.esente) && <label className="flex items-center gap-1.5 pb-2"><input type="checkbox" checked={v.bollo} onChange={set("bollo")} data-testid="regv-prof-bollo" />Bollo 2 € addebitato (esente art. 15)</label>}
        <Button size="sm" disabled={!res} onClick={() => onApply(res)} data-testid="regv-prof-applica">Compila righe e ritenuta</Button>
      </div>
      {res && (
        <div className="mt-2 text-slate-600" data-testid="regv-prof-riepilogo">
          Cassa {fmtEUR(res.cassa)}{res.conBollo ? " · bollo 2,00 €" : ""} · totale documento {fmtEUR(res.totale)}
          {res.rit ? ` · ritenuta ${p.ritenuta_aliquota}% su ${fmtEUR(Number(res.rit_base))} = ${fmtEUR(res.rit)}` : " · nessuna ritenuta"} · netto a pagare {fmtEUR(res.netto)}
        </div>
      )}
    </div>
  );
};

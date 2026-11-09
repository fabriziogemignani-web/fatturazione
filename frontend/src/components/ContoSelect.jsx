import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

export const useConti = (enabled = true) => {
  const [conti, setConti] = useState([]);
  const load = useCallback(() => {
    if (!enabled) return Promise.resolve();
    return api.get("/contabilita/conti").then(({ data }) => setConti(data.conti)).catch(() => {});
  }, [enabled]);
  useEffect(() => { load(); }, [load]);
  return [conti, load];
};

export const ContoSelect = ({ conti, value, onChange, tipi, testId, placeholder = "Scegli un sottoconto", allowEmpty, className = "", levels = [3], disabled }) => {
  const mastri = conti.filter((c) => c.livello === 1);
  const rows = conti.filter((c) => levels.includes(c.livello) && (!tipi || tipi.includes(c.tipo)));
  return (
    <select value={value || ""} disabled={disabled} onChange={(e) => onChange(e.target.value)} data-testid={testId}
      className={`h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${className}`}>
      <option value="">{allowEmpty || placeholder}</option>
      {mastri.map((m) => {
        const items = rows.filter((c) => c.codice.startsWith(`${m.codice}`) && (c.codice === m.codice || c.codice[2] === "."));
        if (!items.length) return null;
        return (
          <optgroup key={m.codice} label={`${m.codice} ${m.descrizione}`}>
            {items.map((c) => <option key={c.codice} value={c.codice}>{c.livello === 3 ? "" : c.livello === 2 ? "· " : ""}{c.codice} {c.descrizione}</option>)}
          </optgroup>
        );
      })}
    </select>
  );
};

export const contoLabel = (conti, codice) => {
  const c = conti.find((x) => x.codice === codice);
  return c ? `${c.codice} ${c.descrizione}` : codice;
};

export const ORIGINE_BADGE = {
  manuale: "bg-slate-100 text-slate-700", vendita: "bg-emerald-50 text-emerald-700", acquisto: "bg-amber-50 text-amber-700", banca: "bg-sky-50 text-sky-700",
};

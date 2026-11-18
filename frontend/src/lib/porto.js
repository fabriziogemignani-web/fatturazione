import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export const STATO_POSTO = {
  libero: { label: "Libero", cls: "bg-emerald-500 text-white", dot: "bg-emerald-500" },
  contratto: { label: "Contratto", cls: "bg-blue-600 text-white", dot: "bg-blue-600" },
  transito: { label: "Transito", cls: "bg-orange-500 text-white", dot: "bg-orange-500" },
  fuori_servizio: { label: "Fuori servizio", cls: "bg-slate-400 text-white", dot: "bg-slate-400" },
};

export const oggi = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
export const addDays = (s, n) => { const d = new Date(`${s}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };

export const usePortoBase = () => {
  const [d, setD] = useState({ barche: [], posti: [], pontili: [] });
  const load = () => Promise.all([api.get("/porto/barche"), api.get("/porto/posti"), api.get("/porto/pontili")])
    .then(([b, p, q]) => setD({ barche: b.data, posti: p.data, pontili: q.data })).catch(() => {});
  useEffect(() => { load(); }, []);
  return [d, load];
};

export const Legenda = () => (
  <div className="flex flex-wrap gap-3 text-xs text-slate-600" data-testid="porto-legenda">
    {Object.entries(STATO_POSTO).map(([k, v]) => <span key={k} className="flex items-center gap-1.5"><span className={`h-3 w-3 rounded ${v.dot}`} />{v.label}</span>)}
  </div>
);

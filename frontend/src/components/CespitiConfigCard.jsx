import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Boxes } from "lucide-react";
import { api, errMsg } from "@/lib/api";

const REGOLE = [["meta", "Metà aliquota nel primo anno", "come previsto ai fini fiscali"], ["giorni", "Pro rata giorni di possesso", "quota in proporzione ai giorni dall'entrata in funzione"], ["piena", "Aliquota piena", "quota intera anche nel primo anno"]];

export const CespitiConfigCard = ({ disabled }) => {
  const [v, setV] = useState(null);
  useEffect(() => { api.get("/cespiti/config").then(({ data }) => setV(data.primo_anno)).catch(() => {}); }, []);
  if (!v) return null;
  const save = (x) => api.put("/cespiti/config", { primo_anno: x }).then(() => { setV(x); toast.success("Configurazione cespiti salvata"); }).catch((e) => toast.error(errMsg(e)));
  return (
    <div className="mt-6 max-w-3xl rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm" data-testid="company-cespiti-card">
      <h3 className="flex items-center gap-2 text-lg font-semibold text-slate-800"><Boxes className="h-5 w-5 text-blue-600" />Cespiti e ammortamenti</h3>
      <p className="mb-4 text-xs text-slate-500">Regola dell'ammortamento nel primo anno, usata per tutti i cespiti dell'azienda. Si salva subito; non si può cambiare dopo aver registrato ammortamenti.{disabled ? " Modificabile solo da Admin o Contabile." : ""}</p>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        {REGOLE.map(([k, l, d]) => (
          <label key={k} className={`cursor-pointer rounded-lg border p-3 text-sm transition-colors ${v === k ? "border-blue-500 bg-blue-50" : "border-slate-200 hover:border-slate-300"}`} data-testid={`company-cespiti-${k}`}>
            <input type="radio" name="cespiti-primo-anno" className="mr-2" checked={v === k} disabled={disabled} onChange={() => save(k)} />
            <b>{l}</b><div className="mt-1 text-xs text-slate-500">{d}</div>
          </label>
        ))}
      </div>
      <p className="mt-3 text-xs text-slate-500">Coefficienti di ammortamento (DM 31/12/1988) e registro dei beni in <Link to="/contabilita/cespiti" className="text-blue-600 hover:underline">Contabilità › Cespiti e ammortamenti</Link>.</p>
    </div>
  );
};

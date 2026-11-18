import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Sparkles } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { Button } from "@/components/ui/button";

export const AiDubbiePanel = () => {
  const [rows, setRows] = useState([]);
  const load = () => api.get("/ai/passive/dubbie").then(({ data }) => setRows(data)).catch(() => {});
  useEffect(() => { load(); }, []);
  const ok = async (r) => {
    try { await api.post(`/ai/passive/${r.id}/rivista`); toast.success("Segnata come verificata"); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  if (!rows.length) return null;
  return (
    <div className="mt-6 rounded-xl border border-rose-200 bg-white shadow-sm" data-testid="ai-dubbie-panel">
      <div className="flex items-center gap-2 border-b border-rose-100 px-4 py-3">
        <Sparkles className="h-4 w-4 text-rose-600" /><h3 className="text-base font-semibold text-slate-800">Registrazioni IA da verificare</h3>
        <span className="ml-auto rounded-full bg-rose-600 px-2 py-0.5 text-xs font-bold text-white">{rows.length}</span>
      </div>
      <ul className="divide-y divide-slate-100">
        {rows.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center gap-3 px-4 py-2 text-sm" data-testid={`ai-dubbia-${r.id}`}>
            <div className="min-w-0 flex-1">
              <Link to={`/passive/${r.id}`} className="font-medium text-blue-600 hover:underline">{r.fornitore?.denominazione} · {r.numero}</Link>
              <span className="ml-2 text-xs text-slate-500">{fmtDate(r.data)} · {fmtEUR(r.totale)} · conto {r.ai_conto || "non scelto"} · sicurezza {Math.round((r.ai_analisi.confidenza || 0) * 100)}%</span>
              <div className="text-xs text-rose-700">{r.ai_analisi.motivo}</div>
            </div>
            <Button size="sm" variant="outline" onClick={() => ok(r)} data-testid={`ai-rivista-${r.id}`}>Verificata</Button>
          </li>
        ))}
      </ul>
    </div>
  );
};

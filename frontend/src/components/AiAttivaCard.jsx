import { toast } from "sonner";
import { Sparkles } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Switch } from "@/components/ui/switch";
import { useAiStato } from "@/components/AiCreditiBanner";

export const AiAttivaCard = () => {
  const [s, load] = useAiStato();
  if (!s) return null;
  const set = async (v) => {
    try { await api.put("/ai/attiva", { attiva: v }); toast.success(v ? "IA attivata" : "IA disattivata"); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div className="mt-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm" data-testid="ai-attiva-card">
      <div className="flex items-center gap-3">
        <Sparkles className="h-5 w-5 text-violet-600" />
        <div className="flex-1">
          <h3 className="text-base font-semibold text-slate-800">Intelligenza artificiale</h3>
          <p className="text-xs text-slate-500">Se attiva, l'IA propone conto e IVA delle fatture ricevute e risponde nel Consulente IA, consumando crediti. Se spenta, le fatture si registrano con le regole già impostate (conto del fornitore o contropartita acquisti).</p>
        </div>
        <Switch checked={s.attiva} onCheckedChange={set} data-testid="ai-attiva-switch" />
      </div>
      <p className="mt-2 text-xs text-slate-600">Crediti disponibili: <b data-testid="ai-attiva-crediti">{Number(s.crediti).toLocaleString("it-IT")}</b></p>
    </div>
  );
};

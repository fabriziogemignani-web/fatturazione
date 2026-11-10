import { useEffect, useState } from "react";
import { AlertTriangle, ShieldAlert, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

const TONE = { rosso: "border-rose-300 bg-rose-50 text-rose-900", giallo: "border-amber-300 bg-amber-50 text-amber-900" };

export const SistemaAvvisi = () => {
  const { user } = useAuth();
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState(false);
  const admin = user?.role === "admin";
  const load = (refresh = false) => {
    setBusy(true);
    api.get("/sistema/avvisi", { params: refresh ? { refresh: true } : {} }).then(({ data }) => setD(data)).catch(() => {}).finally(() => setBusy(false));
  };
  useEffect(() => { if (admin) load(); }, [admin]);
  if (!admin || !d?.avvisi?.length) return null;
  return (
    <div className="mb-6 space-y-2" data-testid="sistema-avvisi">
      {d.avvisi.map((a) => (
        <div key={a.id} className={`flex items-start gap-3 rounded-xl border p-4 ${TONE[a.livello]}`} data-testid={`sistema-avviso-${a.id}`}>
          {a.id === "cert" ? <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0" /> : <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />}
          <div className="flex-1 text-sm">
            <div className="font-semibold">{a.titolo}</div>
            <div className="mt-0.5 opacity-90">{a.testo}</div>
          </div>
          <button onClick={() => load(true)} disabled={busy} className="inline-flex items-center gap-1 text-xs font-semibold underline-offset-2 hover:underline" data-testid={`sistema-avviso-ricontrolla-${a.id}`}>
            <RefreshCw className={`h-3.5 w-3.5 ${busy ? "animate-spin" : ""}`} />Ricontrolla
          </button>
        </div>
      ))}
    </div>
  );
};

import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { api } from "@/lib/api";

export const AvvisoSistema = () => {
  const [a, setA] = useState(null);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const poll = () => api.get("/sistema/avviso").then(({ data }) => setA(data.avviso)).catch(() => {});
    poll();
    const p = setInterval(poll, 10000);
    const c = setInterval(() => setNow(Date.now()), 1000);
    return () => { clearInterval(p); clearInterval(c); };
  }, []);
  if (!a) return null;
  const sec = Math.max(0, Math.round((new Date(a.spegnimento_at).getTime() - now) / 1000));
  return (
    <div className="fixed inset-x-0 top-0 z-[100] flex items-center justify-center gap-3 bg-rose-600 px-4 py-3 text-sm font-semibold text-white shadow-lg print:hidden" role="alert" data-testid="avviso-sistema">
      <RefreshCw className="h-4 w-4 shrink-0 animate-spin" />
      <span>{a.messaggio}</span>
      <span className="mono rounded bg-white/20 px-2 py-0.5" data-testid="avviso-sistema-countdown">{sec > 0 ? `spegnimento tra ${sec} s` : "spegnimento in corso"}</span>
    </div>
  );
};

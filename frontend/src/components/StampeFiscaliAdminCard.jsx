import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { StampeDefinitive } from "@/pages/StampeFiscali";

export const StampeFiscaliAdminCard = () => {
  const [stampe, setStampe] = useState(null);
  const load = () => api.get("/stampe-fiscali/stampe").then(({ data }) => setStampe(data)).catch(() => setStampe([]));
  useEffect(() => { load(); }, []);
  if (!stampe) return null;
  return (
    <div className="mt-6 rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm" data-testid="sf-admin-card">
      <h3 className="text-lg font-semibold text-slate-800">Stampe fiscali definitive</h3>
      <p className="mb-4 text-xs text-slate-500">Puoi cancellare una stampa definitiva di registri IVA o libro giornale, oppure riaprire i movimenti bloccati da una stampa per correggerli (e bloccarli di nuovo dopo). Riservato agli amministratori.</p>
      <StampeDefinitive stampe={stampe} admin reload={load} />
    </div>
  );
};

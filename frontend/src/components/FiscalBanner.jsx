import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, X } from "lucide-react";
import { api } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { useCompany } from "@/context/CompanyContext";
import { mods } from "@/lib/moduli";

export const FiscalBanner = () => {
  const { company } = useCompany();
  const on = company && mods(company).fatturazione;
  const [avvisi, setAvvisi] = useState([]);
  const dk = `fisc-banner-${company?.id}-${new Date().toLocaleDateString("sv-SE")}`;
  const [hidden, setHidden] = useState(false);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const f = () => setTick((x) => x + 1);
    window.addEventListener("fisc-refresh", f);
    return () => window.removeEventListener("fisc-refresh", f);
  }, []);
  useEffect(() => {
    setHidden(!!sessionStorage.getItem(dk));
    if (!on) { setAvvisi([]); return; }
    api.get("/scadenze-fiscali").then(({ data }) => setAvvisi(data.avvisi)).catch(() => setAvvisi([]));
  }, [on, dk, tick]);
  if (!on || hidden || avvisi.length === 0) return null;
  const x = avvisi[0];
  const g = x.giorni;
  return (
    <div className="flex items-center gap-3 bg-rose-600 px-4 py-2.5 text-sm text-white print:hidden lg:px-8" data-testid="fiscal-banner">
      <AlertTriangle className="h-4 w-4 shrink-0" />
      <span className="flex-1">
        <b>F24 {x.codice}</b> {x.tipo === "iva" ? "IVA" : x.tipo === "bolli" ? "imposta di bollo" : "ritenute"} {x.periodo_label}: <b>{fmtEUR(x.importo)}</b> {g < 0 ? `scaduto il ${fmtDate(x.scadenza)}` : g === 0 ? "scade oggi" : `entro il ${fmtDate(x.scadenza)} (tra ${g} ${g === 1 ? "giorno" : "giorni"})`}
        {avvisi.length > 1 && ` · altri ${avvisi.length - 1} avvisi`}
      </span>
      <Link to="/dashboard" className="rounded-full bg-white/20 px-3 py-1 text-xs font-semibold hover:bg-white/30" data-testid="fiscal-banner-link">Vedi scadenzario</Link>
      <button onClick={() => { sessionStorage.setItem(dk, "1"); setHidden(true); }} aria-label="Nascondi" className="rounded p-1 hover:bg-white/20" data-testid="fiscal-banner-close"><X className="h-4 w-4" /></button>
    </div>
  );
};

import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Bell, Plus, Search, SlidersHorizontal } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useAuth } from "@/context/AuthContext";

export const PERIODI = [["mese", "Questo mese"], ["trimestre", "Questo trimestre"], ["anno", "Quest'anno"], ["12mesi", "Ultimi 12 mesi"]];

const AVVISI = [["scartate", "fatture scartate dallo SDI", "/fatture"], ["bozze", "bozze da inviare", "/fatture"], ["passive_da_registrare", "fatture ricevute da registrare", "/passive"],
  ["fornitori_da_verificare", "fornitori da verificare", "/passive"], ["clienti_scaduto_n", "rate clienti scadute", "/scadenzario"], ["fornitori_scaduto_n", "rate fornitori scadute", "/scadenzario-fornitori"],
  ["sottoscorta", "articoli sottoscorta", "/magazzino"], ["ordini_clienti_in_ritardo", "ordini clienti in ritardo", "/ordini-clienti"], ["ddt_da_fatturare", "DDT da fatturare", "/fatturazione-differita"]];

const Notifiche = () => {
  const [rq, setRq] = useState(null);
  useEffect(() => { api.get("/dashboard/riquadri").then(({ data }) => setRq(data)).catch(() => {}); }, []);
  const items = rq ? AVVISI.filter(([k]) => rq[k] > 0) : [];
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button className="relative flex h-10 w-10 items-center justify-center rounded-full text-slate-600 transition-colors hover:bg-slate-100" data-testid="dash-bell" title="Notifiche">
          <Bell className="h-5 w-5" />{items.length > 0 && <span className="absolute right-2 top-2 h-2.5 w-2.5 rounded-full bg-rose-500 ring-2 ring-white" data-testid="dash-bell-dot" />}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 bg-white p-0" data-testid="dash-bell-list">
        <div className="border-b border-slate-100 px-4 py-3 text-sm font-semibold">Da gestire</div>
        {items.length === 0 ? <p className="px-4 py-6 text-center text-sm text-slate-500">Tutto in ordine</p> : (
          <ul className="divide-y divide-slate-100">{items.map(([k, l, to]) => <li key={k}><Link to={to} className="flex items-center justify-between px-4 py-2.5 text-sm hover:bg-slate-50" data-testid={`dash-bell-${k}`}><span>{l}</span><b className="rounded-full bg-slate-100 px-2 text-xs">{rq[k]}</b></Link></li>)}</ul>
        )}
      </PopoverContent>
    </Popover>
  );
};

export const TopBar = ({ periodo, setPeriodo, onPersonalizza, nuova }) => {
  const [q, setQ] = useState("");
  const navigate = useNavigate();
  const { user } = useAuth();
  const ini = (user?.name || user?.email || "?").split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((x) => x[0].toUpperCase()).join("");
  return (
    <div className="mb-6 flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200/80 bg-white px-4 py-3 shadow-[0_1px_2px_rgba(15,23,42,0.04)]" data-testid="dash-topbar">
      <select value={periodo} onChange={(e) => setPeriodo(e.target.value)} className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500" data-testid="dash-periodo">
        {PERIODI.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
      </select>
      <div className="ml-auto flex flex-1 items-center justify-end gap-2 sm:flex-none">
        <form onSubmit={(e) => { e.preventDefault(); if (q.trim()) navigate(`/fatture?q=${encodeURIComponent(q.trim())}`); }} className="relative hidden md:block">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cerca fatture, clienti…" className="h-10 w-64 rounded-lg border border-slate-200 bg-white pl-9 pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" data-testid="dash-search" />
        </form>
        <Notifiche />
        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white" title={user?.name || user?.email} data-testid="dash-avatar">{ini}</span>
        <Button variant="outline" onClick={onPersonalizza} className="h-10" data-testid="dash-personalizza"><SlidersHorizontal className="h-4 w-4 sm:mr-2" /><span className="hidden sm:inline">Personalizza</span></Button>
        {nuova && <Button asChild className="h-10 bg-blue-700 hover:bg-blue-800" data-testid="dashboard-new-invoice-btn"><Link to="/fatture/nuova"><Plus className="h-4 w-4 sm:mr-2" /><span className="hidden sm:inline">Nuova fattura</span></Link></Button>}
      </div>
    </div>
  );
};

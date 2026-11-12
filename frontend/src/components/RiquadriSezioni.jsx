import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { FileText, Inbox, CalendarClock, Wallet, Banknote, Truck, Warehouse, BookText, ArrowUpRight } from "lucide-react";
import { api } from "@/lib/api";
import { fmtEUR } from "@/lib/fe";
import { useCompany } from "@/context/CompanyContext";
import { mods, vede } from "@/lib/moduli";

const TONO = {
  danger: "border-rose-200 bg-rose-50/70 text-rose-900 hover:border-rose-300",
  warn: "border-amber-200 bg-amber-50/70 text-amber-900 hover:border-amber-300",
  ok: "border-slate-200 bg-white text-slate-900 hover:border-slate-300",
};
const DOT = { danger: "bg-rose-500", warn: "bg-amber-500", ok: "bg-emerald-500" };

const tiles = (r) => [
  { id: "fatture", mod: "fatture_attive", icon: FileText, titolo: "Fatture emesse", to: "/fatture",
    ...(r.scartate ? { n: r.scartate, testo: "scartate dallo SDI", azione: "Correggi e reinvia", tono: "danger" }
      : r.bozze ? { n: r.bozze, testo: r.autofatture_bozza ? `bozze, di cui ${r.autofatture_bozza} autofatture` : "bozze da inviare", azione: "Invia allo SDI", tono: "warn" }
        : { n: 0, testo: "nessuna bozza in sospeso", azione: "Nuova fattura", to: "/fatture/nuova", tono: "ok" }) },
  { id: "passive", mod: "fatture_passive", icon: Inbox, titolo: "Fatture ricevute", to: "/passive",
    ...(r.fornitori_da_verificare ? { n: r.fornitori_da_verificare, testo: "nuovi fornitori da verificare", azione: "Verifica i dati", tono: "warn" }
      : r.passive_da_registrare ? { n: r.passive_da_registrare, testo: "da registrare", azione: "Registra", tono: "warn" }
        : { n: 0, testo: "tutte registrate", azione: "Apri", tono: "ok" }) },
  { id: "scadenzario", mod: "fatture_attive", icon: CalendarClock, titolo: "Incassi clienti", to: "/scadenzario", fmt: true,
    ...(r.clienti_scaduto_n ? { n: r.clienti_scaduto, testo: `${r.clienti_scaduto_n} rate scadute non incassate`, azione: "Sollecita", tono: "danger" }
      : { n: 0, testo: "nessun incasso scaduto", azione: "Scadenzario", tono: "ok" }) },
  { id: "scadenzario-fornitori", mod: "fatture_passive", icon: Wallet, titolo: "Pagamenti fornitori", to: "/scadenzario-fornitori", fmt: true,
    ...(r.fornitori_scaduto_n ? { n: r.fornitori_scaduto, testo: `${r.fornitori_scaduto_n} rate scadute da pagare`, azione: "Paga", tono: "danger" }
      : { n: 0, testo: "nessun pagamento scaduto", azione: "Scadenzario", tono: "ok" }) },
  { id: "riba", mod: "contabilita", icon: Banknote, titolo: "Effetti Ri.Ba.", to: "/riba",
    ...(r.riba_insoluti_mese ? { n: r.riba_insoluti_mese, testo: "insoluti questo mese", azione: "Gestisci insoluti", tono: "danger" }
      : r.riba_in_scadenza ? { n: r.riba_in_scadenza, testo: "effetti in scadenza nei 10 giorni", azione: "Controlla", tono: "warn" }
        : { n: 0, testo: "nessun effetto in scadenza", azione: "Presenta Ri.Ba.", tono: "ok" }) },
  { id: "ddt", mod: "fatture_attive", icon: Truck, titolo: "DDT", to: "/fatturazione-differita",
    ...(r.ddt_da_fatturare ? { n: r.ddt_da_fatturare, testo: "DDT confermati da fatturare", azione: "Fattura i DDT", tono: "warn" }
      : { n: 0, testo: "nessun DDT da fatturare", azione: "Nuovo DDT", to: "/ddt", tono: "ok" }) },
  { id: "magazzino", icon: Warehouse, titolo: "Magazzino", to: "/magazzino",
    ...(r.sottoscorta ? { n: r.sottoscorta, testo: "articoli sotto scorta", azione: "Riordina", tono: "danger" }
      : { n: 0, testo: "scorte sopra il minimo", azione: "Giacenze", to: "/magazzino", tono: "ok" }) },
  { id: "prima-nota", mod: "contabilita", icon: BookText, titolo: "Contabilità", to: "/contabilita/prima-nota",
    n: r.movimenti_mese, testo: r.movimenti_modificati ? `movimenti nel mese, ${r.movimenti_modificati} modificati a mano` : "movimenti nel mese", azione: "Prima nota",
    tono: r.movimenti_modificati ? "warn" : "ok" },
];

export const RiquadriSezioni = () => {
  const co = useCompany().company;
  const m = mods(co);
  const [r, setR] = useState(null);
  useEffect(() => { api.get("/dashboard/riquadri").then(({ data }) => setR(data)).catch(() => {}); }, [co?.id]);
  if (!r) return null;
  const list = tiles(r).filter((x) => (!x.mod || m[x.mod]) && vede(co, x.id));
  return (
    <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4" data-testid="riquadri-sezioni">
      {list.map((x, i) => {
        const Icon = x.icon;
        return (
          <Link key={x.id} to={x.to} className={`group relative flex aspect-[4/3] flex-col justify-between rounded-2xl border p-5 shadow-sm transition-[transform,border-color,box-shadow] duration-200 hover:-translate-y-0.5 hover:shadow-md sm:aspect-square ${TONO[x.tono]}`}
            style={{ animation: `fadeUp .4s ease-out ${i * 50}ms both` }} data-testid={`riquadro-${x.id}`}>
            <div className="flex items-start justify-between">
              <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-white/80 shadow-sm ring-1 ring-black/5"><Icon className="h-5 w-5" /></span>
              <span className={`mt-1 h-2.5 w-2.5 rounded-full ${DOT[x.tono]}`} data-testid={`riquadro-${x.id}-stato`} />
            </div>
            <div>
              <div className="text-xs font-semibold uppercase tracking-wider opacity-70">{x.titolo}</div>
              <div className="mt-1 text-3xl font-extrabold tabular-nums" data-testid={`riquadro-${x.id}-valore`}>{x.fmt ? fmtEUR(x.n) : x.n}</div>
              <div className="text-sm opacity-80">{x.testo}</div>
            </div>
            <div className="flex items-center justify-between text-sm font-semibold">
              <span data-testid={`riquadro-${x.id}-azione`}>{x.azione}</span>
              <ArrowUpRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
            </div>
          </Link>
        );
      })}
    </div>
  );
};

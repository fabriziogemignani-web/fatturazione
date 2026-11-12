import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { DndContext, closestCenter, PointerSensor, TouchSensor, KeyboardSensor, useSensor, useSensors } from "@dnd-kit/core";
import { SortableContext, useSortable, arrayMove, rectSortingStrategy, sortableKeyboardCoordinates } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { FileText, Inbox, CalendarClock, Wallet, Banknote, Truck, Warehouse, BookText, ArrowUpRight, GripVertical, Eye, EyeOff, SlidersHorizontal } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { fmtEUR } from "@/lib/fe";
import { useCompany } from "@/context/CompanyContext";
import { mods, vede, pathAllowed, menuOff } from "@/lib/moduli";
import { useAuth, canSend, canAny } from "@/context/AuthContext";

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
  { id: "riba", mod: "fatture_attive", accounting: true, icon: Banknote, titolo: "Effetti Ri.Ba.", to: "/riba",
    ...(r.riba_insoluti_mese ? { n: r.riba_insoluti_mese, testo: "insoluti questo mese", azione: "Gestisci insoluti", tono: "danger" }
      : r.riba_in_scadenza ? { n: r.riba_in_scadenza, testo: "effetti in scadenza nei 10 giorni", azione: "Controlla", tono: "warn" }
        : { n: 0, testo: "nessun effetto in scadenza", azione: "Presenta Ri.Ba.", tono: "ok" }) },
  { id: "ddt", mod: "fatture_attive", icon: Truck, titolo: "DDT", to: "/fatturazione-differita",
    ...(r.ddt_da_fatturare ? { n: r.ddt_da_fatturare, testo: "DDT confermati da fatturare", azione: "Fattura i DDT", tono: "warn" }
      : { n: 0, testo: "nessun DDT da fatturare", azione: "Nuovo DDT", to: "/ddt", tono: "ok" }) },
  { id: "magazzino", diritto: "articoli_magazzino", icon: Warehouse, titolo: "Magazzino", to: "/magazzino",
    ...(r.sottoscorta ? { n: r.sottoscorta, testo: "articoli sotto scorta", azione: "Riordina", tono: "danger" }
      : { n: 0, testo: "scorte sopra il minimo", azione: "Giacenze", to: "/magazzino", tono: "ok" }) },
  { id: "prima-nota", mod: "contabilita", icon: BookText, titolo: "Contabilità", to: "/contabilita/prima-nota",
    n: r.movimenti_mese, testo: r.movimenti_modificati ? `movimenti nel mese, ${r.movimenti_modificati} modificati a mano` : "movimenti nel mese", azione: "Prima nota",
    tono: r.movimenti_modificati ? "warn" : "ok" },
];

export const RiquadriSezioni = () => {
  const co = useCompany().company;
  const m = mods(co);
  const { user } = useAuth();
  const [r, setR] = useState(null);
  const [err, setErr] = useState(false);
  const [pref, setPref] = useState({ ordine: [], nascosti: [] });
  const [edit, setEdit] = useState(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }), useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));
  useEffect(() => { api.get("/dashboard/riquadri").then(({ data }) => setR(data)).catch(() => setErr(true)); }, [co?.id]);
  useEffect(() => { api.get("/me/riquadri").then(({ data }) => setPref(data)).catch(() => {}); }, []);
  if (err) return <p className="mb-6 text-sm text-slate-500" data-testid="riquadri-errore">Riepilogo delle sezioni non disponibile al momento.</p>;
  if (!r) return <div className="mb-6 h-40 animate-pulse rounded-2xl bg-slate-100" data-testid="riquadri-loading" />;
  const off = menuOff(co);
  const ok = (to) => pathAllowed(to, m, off);
  const list = tiles(r).map((x) => (x.id === "ddt" && !ok(x.to) ? { ...x, to: "/ddt" } : x))
    .filter((x) => (!x.mod || m[x.mod]) && vede(co, x.id) && ok(x.to) && (!x.accounting || canSend(user)) && (!x.diritto || canAny(user, x.diritto)));
  const sorted = (o) => [...list].sort((a, b) => ((o.indexOf(a.id) + 1 || 99) - (o.indexOf(b.id) + 1 || 99)));
  const save = async (p) => {
    try { const { data } = await api.put("/me/riquadri", p); setPref(data); setEdit(null); toast.success("Dashboard personalizzata salvata"); } catch (e) { toast.error(errMsg(e)); }
  };
  const onDragEnd = ({ active, over }) => {
    if (!over || active.id === over.id) return;
    setEdit((e) => ({ ...e, ordine: arrayMove(e.ordine, e.ordine.indexOf(active.id), e.ordine.indexOf(over.id)) }));
  };
  const head = (
    <div className="mb-3 flex flex-wrap items-center justify-end gap-2">
      {edit ? <>
        <span className="mr-auto text-xs text-slate-500">Trascina i riquadri per cambiare l'ordine, usa l'occhio per mostrarli o nasconderli.</span>
        <Button size="sm" variant="ghost" onClick={() => save({ ordine: [], nascosti: [] })} data-testid="riquadri-reset-btn">Ripristina</Button>
        <Button size="sm" variant="outline" onClick={() => setEdit(null)} data-testid="riquadri-annulla-btn">Annulla</Button>
        <Button size="sm" onClick={() => save(edit)} data-testid="riquadri-salva-btn">Salva</Button>
      </> : <Button size="sm" variant="ghost" onClick={() => setEdit({ ordine: sorted(pref.ordine).map((x) => x.id), nascosti: [...pref.nascosti] })} data-testid="riquadri-personalizza-btn"><SlidersHorizontal className="mr-1.5 h-4 w-4" />Personalizza</Button>}
    </div>
  );
  if (edit) {
    const byId = Object.fromEntries(list.map((x) => [x.id, x]));
    const toggle = (id) => setEdit((e) => ({ ...e, nascosti: e.nascosti.includes(id) ? e.nascosti.filter((k) => k !== id) : [...e.nascosti, id] }));
    return (
      <div className="mb-6">
        {head}
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
          <SortableContext items={edit.ordine} strategy={rectSortingStrategy}>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4" data-testid="riquadri-edit">
              {edit.ordine.filter((id) => byId[id]).map((id) => <Sortable key={id} x={byId[id]} hidden={edit.nascosti.includes(id)} onToggle={() => toggle(id)} />)}
            </div>
          </SortableContext>
        </DndContext>
      </div>
    );
  }
  const visibili = sorted(pref.ordine).filter((x) => !pref.nascosti.includes(x.id));
  return (
    <div className="mb-6">
      {head}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4" data-testid="riquadri-sezioni">
        {visibili.length === 0 && <p className="text-sm text-slate-500" data-testid="riquadri-tutti-nascosti">Hai nascosto tutti i riquadri: usa Personalizza per mostrarli.</p>}
        {visibili.map((x, i) => <Tile key={x.id} x={x} i={i} />)}
      </div>
    </div>
  );
};

const Sortable = ({ x, hidden, onToggle }) => {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: x.id });
  return (
    <div ref={setNodeRef} style={{ transform: CSS.Transform.toString(transform), transition }} className={`relative ${isDragging ? "z-10 opacity-80" : ""} ${hidden ? "opacity-40 grayscale" : ""}`} data-testid={`riquadro-edit-${x.id}`}>
      <div className="absolute inset-x-3 top-3 z-10 flex justify-between">
        <button {...attributes} {...listeners} className="cursor-grab touch-none rounded-md bg-white/90 p-1.5 shadow-sm ring-1 ring-black/5 active:cursor-grabbing" aria-label={`Sposta ${x.titolo}`} data-testid={`riquadro-drag-${x.id}`}><GripVertical className="h-4 w-4" /></button>
        <button onClick={onToggle} className="rounded-md bg-white/90 p-1.5 shadow-sm ring-1 ring-black/5" aria-label={hidden ? "Mostra" : "Nascondi"} data-testid={`riquadro-toggle-${x.id}`}>{hidden ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}</button>
      </div>
      <Tile x={x} i={0} still />
    </div>
  );
};

const Tile = ({ x, i, still }) => {
  const Icon = x.icon;
  const Box = still ? "div" : Link;
  return (
          <Box to={still ? undefined : x.to} className={`group relative flex aspect-[4/3] flex-col justify-between rounded-2xl border p-5 shadow-sm transition-[transform,border-color,box-shadow] duration-200 sm:aspect-square ${still ? "ring-2 ring-dashed ring-slate-300" : "hover:-translate-y-0.5 hover:shadow-md"} ${TONO[x.tono]}`}
            style={still ? undefined : { animation: `fadeUp .4s ease-out ${i * 50}ms both` }} data-testid={still ? undefined : `riquadro-${x.id}`}>
            <div className={`flex items-start justify-between ${still ? "invisible" : ""}`}>
              <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-white/80 shadow-sm ring-1 ring-black/5"><Icon className="h-5 w-5" /></span>
              <span className={`mt-1 h-2.5 w-2.5 rounded-full ${DOT[x.tono]}`} data-testid={`riquadro-${x.id}-stato`} />
            </div>
            <div>
              <div className="text-xs font-semibold uppercase tracking-wider opacity-70">{x.titolo}</div>
              <div className="mt-1 text-3xl font-extrabold tabular-nums" data-testid={`riquadro-${x.id}-valore`}>{x.fmt ? fmtEUR(x.n) : x.n}</div>
              <div className="text-sm opacity-80">{x.testo}</div>
            </div>
            <div className="flex items-center justify-between text-sm font-semibold">
              <span data-testid={still ? undefined : `riquadro-${x.id}-azione`}>{x.azione}</span>
              <ArrowUpRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
            </div>
          </Box>
  );
};

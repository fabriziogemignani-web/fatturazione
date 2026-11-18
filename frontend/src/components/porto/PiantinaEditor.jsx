import { useRef, useState } from "react";
import { toast } from "sonner";
import { Upload, Trash2, PenLine, X } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { NSelect } from "@/components/ui/nselect";
import { usePiantina, Segnaposto } from "@/components/porto/PiantinaPorto";

const rel = (e, el) => { const r = el.getBoundingClientRect(); return { x: Math.min(Math.max((e.clientX - r.left) / r.width, 0), 1), y: Math.min(Math.max((e.clientY - r.top) / r.height, 0), 1) }; };

export const PiantinaEditor = ({ base, reload }) => {
  const [{ url, info }, loadImg] = usePiantina();
  const box = useRef(null);
  const [f, setF] = useState({ pontile_id: "", da: "", a: "" });
  const [linea, setLinea] = useState(null);
  const [drag, setDrag] = useState(null);
  const posti = base.posti.filter((p) => p.pontile_id === f.pontile_id);
  const upload = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    try { await api.post("/porto/piantina", fd); toast.success("Piantina caricata"); loadImg(); } catch (err) { toast.error(errMsg(err)); }
  };
  const rimuovi = async () => {
    if (!window.confirm("Rimuovere la piantina e tutte le posizioni dei posti?")) return;
    try { await api.delete("/porto/piantina"); loadImg(); reload(); } catch (err) { toast.error(errMsg(err)); }
  };
  const selezione = () => {
    const i = posti.findIndex((p) => p.id === f.da), j = posti.findIndex((p) => p.id === f.a);
    if (i < 0 || j < 0) return [];
    return i <= j ? posti.slice(i, j + 1) : posti.slice(j, i + 1).reverse();
  };
  const clic = async (e) => {
    if (!linea || drag) return;
    const pt = rel(e, box.current);
    if (!linea.p1) { setLinea({ p1: pt }); return; }
    const ids = selezione().map((p) => p.id);
    try {
      const { data } = await api.post("/porto/piantina/disponi", { posto_ids: ids, x1: linea.p1.x, y1: linea.p1.y, x2: pt.x, y2: pt.y });
      toast.success(`${data.posizionati} posti disposti`); reload();
    } catch (err) { toast.error(errMsg(err)); }
    setLinea(null);
  };
  const move = (e) => { if (drag) setDrag({ ...drag, pos: rel(e, box.current) }); };
  const drop = async () => {
    if (!drag) return;
    const d = drag;
    setDrag(null);
    if (!d.pos) return;
    try { await api.put(`/porto/posti/${d.id}/pos`, d.pos); reload(); } catch (err) { toast.error(errMsg(err)); }
  };
  const n = selezione().length;
  return (
    <section className="mb-6 rounded-xl border border-slate-200 bg-white p-5" data-testid="porto-config-piantina">
      <h2 className="mb-1 text-base font-bold text-slate-800">Piantina interattiva</h2>
      <p className="mb-4 text-xs text-slate-500">Carica l'immagine del porto, scegli un gruppo di posti di un pontile e traccia la linea dove stanno (clic su inizio e fine): i posti si dispongono in automatico. Poi puoi trascinare ogni punto per correggerlo.</p>
      <div className="flex flex-wrap items-end gap-2 text-sm">
        <label className="inline-flex cursor-pointer items-center rounded-md border border-slate-300 px-3 py-2 hover:bg-slate-50" data-testid="piantina-upload-label">
          <Upload className="mr-1 h-4 w-4" />{info?.presente ? "Sostituisci immagine" : "Carica immagine"}
          <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={upload} data-testid="piantina-upload" />
        </label>
        {info?.presente && <Button variant="outline" className="text-rose-600" onClick={rimuovi} data-testid="piantina-rimuovi"><Trash2 className="mr-1 h-4 w-4" />Rimuovi</Button>}
      </div>
      {url && (
        <>
          <div className="mt-4 flex flex-wrap items-end gap-2 text-sm">
            <label>Pontile<NSelect value={f.pontile_id} onChange={(e) => setF({ pontile_id: e.target.value, da: "", a: "" })} className="w-40" data-testid="piantina-pontile"><option value="">Seleziona...</option>{base.pontili.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}</NSelect></label>
            <label>Dal posto<NSelect value={f.da} onChange={(e) => setF({ ...f, da: e.target.value })} className="w-28" data-testid="piantina-da"><option value="">...</option>{posti.map((p) => <option key={p.id} value={p.id}>{p.codice}</option>)}</NSelect></label>
            <label>Al posto<NSelect value={f.a} onChange={(e) => setF({ ...f, a: e.target.value })} className="w-28" data-testid="piantina-a"><option value="">...</option>{posti.map((p) => <option key={p.id} value={p.id}>{p.codice}</option>)}</NSelect></label>
            {!linea ? <Button disabled={!n} onClick={() => setLinea({})} data-testid="piantina-traccia"><PenLine className="mr-1 h-4 w-4" />Traccia linea ({n} posti)</Button>
              : <Button variant="outline" onClick={() => setLinea(null)} data-testid="piantina-annulla"><X className="mr-1 h-4 w-4" />Annulla</Button>}
          </div>
          {linea && <p className="mt-2 text-sm font-semibold text-blue-700" data-testid="piantina-istruzione">{linea.p1 ? `Clicca dove sta l'ultimo posto (${posti.find((p) => p.id === f.a)?.codice})` : `Clicca dove sta il primo posto (${posti.find((p) => p.id === f.da)?.codice})`}</p>}
          <div ref={box} onClick={clic} onPointerMove={move} onPointerUp={drop} onPointerLeave={drop}
            className={`relative mt-3 inline-block max-w-full touch-none select-none overflow-hidden rounded-lg border ${linea ? "cursor-crosshair" : ""}`} data-testid="piantina-editor">
            <img src={url} alt="Piantina del porto" className="block max-h-[78vh] max-w-full" draggable={false} />
            {linea?.p1 && <span className="absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-blue-600 ring-4 ring-blue-200" style={{ left: `${linea.p1.x * 100}%`, top: `${linea.p1.y * 100}%` }} />}
            {base.posti.filter((p) => p.pos).map((p) => {
              const pos = drag?.id === p.id && drag.pos ? drag.pos : p.pos;
              return <Segnaposto key={p.id} p={{ ...p, pos }} stato={p.pontile_id === f.pontile_id ? "transito" : "contratto"} sel={drag?.id === p.id}
                onClick={(e) => e.stopPropagation()} onPointerDown={(e) => { if (linea) return; e.stopPropagation(); setDrag({ id: p.id, pos: null }); }} />;
            })}
          </div>
          <p className="mt-1 text-xs text-slate-500">{base.posti.filter((p) => p.pos).length} di {base.posti.length} posti posizionati. In arancione i posti del pontile selezionato.</p>
        </>
      )}
    </section>
  );
};

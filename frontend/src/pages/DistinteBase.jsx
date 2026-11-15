import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, Pencil } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR } from "@/lib/fe";
import { PageHeader } from "@/components/Common";
import { SearchPicker } from "@/components/SearchPicker";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";

const NEW = { article_id: "", lotto: 1, note: "", componenti: [], fasi: [] };
const sel = "h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm";

const Componenti = ({ f, setF, aItems }) => (
  <div data-testid="db-componenti">
    <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-slate-500">Componenti per 1 unità di prodotto</div>
    {f.componenti.map((c, i) => (
      <div key={i} className="mb-1 grid grid-cols-12 items-center gap-2" data-testid={`db-comp-${i}`}>
        <span className="col-span-7 truncate text-sm">{aItems.find((a) => a.key === c.article_id)?.label || c.codice}</span>
        <Input className="col-span-3 text-right" type="number" min={0} step="0.0001" value={c.quantita} onChange={(e) => setF({ ...f, componenti: f.componenti.map((x, j) => (j === i ? { ...x, quantita: e.target.value } : x)) })} data-testid={`db-comp-qta-${i}`} />
        <span className="col-span-1 text-xs text-slate-500">{aItems.find((a) => a.key === c.article_id)?.um}</span>
        <button className="col-span-1 text-rose-600" onClick={() => setF({ ...f, componenti: f.componenti.filter((_, j) => j !== i) })} data-testid={`db-comp-del-${i}`}><Trash2 className="h-4 w-4" /></button>
      </div>
    ))}
    <SearchPicker items={aItems.filter((a) => a.key !== f.article_id)} value="" onPick={(i) => setF({ ...f, componenti: [...f.componenti, { article_id: i.key, quantita: 1 }] })} onClear={() => {}} placeholder="Aggiungi componente o semilavorato…" testId="db-add-comp" className="w-full" />
  </div>
);

const Fasi = ({ f, setF, centri }) => {
  const upd = (i, k, v) => setF({ ...f, fasi: f.fasi.map((x, j) => (j === i ? { ...x, [k]: v } : x)) });
  return (
    <div data-testid="db-fasi">
      <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-slate-500">Ciclo di lavoro (fasi in ordine)</div>
      {f.fasi.map((x, i) => (
        <div key={i} className="mb-1 grid grid-cols-12 items-center gap-2" data-testid={`db-fase-${i}`}>
          <span className="col-span-1 text-xs font-semibold text-slate-500">{(i + 1) * 10}</span>
          <Input className="col-span-4" placeholder="Descrizione fase" value={x.descrizione} onChange={(e) => upd(i, "descrizione", e.target.value)} data-testid={`db-fase-desc-${i}`} />
          <select className={`${sel} col-span-3`} value={x.centro_id} onChange={(e) => upd(i, "centro_id", e.target.value)} data-testid={`db-fase-centro-${i}`}><option value="">Centro…</option>{centri.map((c) => <option key={c.id} value={c.id}>{c.codice} · {c.descrizione}</option>)}</select>
          <Input className="col-span-2" type="number" min={0} title="Attrezzaggio (minuti per lotto)" placeholder="Setup min" value={x.setup_min} onChange={(e) => upd(i, "setup_min", e.target.value)} data-testid={`db-fase-setup-${i}`} />
          <Input className="col-span-1" type="number" min={0} title="Minuti per pezzo" placeholder="min/pz" value={x.minuti_pezzo} onChange={(e) => upd(i, "minuti_pezzo", e.target.value)} data-testid={`db-fase-min-${i}`} />
          <button className="col-span-1 text-rose-600" onClick={() => setF({ ...f, fasi: f.fasi.filter((_, j) => j !== i) })} data-testid={`db-fase-del-${i}`}><Trash2 className="h-4 w-4" /></button>
        </div>
      ))}
      <Button size="sm" variant="outline" onClick={() => setF({ ...f, fasi: [...f.fasi, { descrizione: "", centro_id: centri[0]?.id || "", setup_min: 0, minuti_pezzo: 0 }] })} disabled={!centri.length} data-testid="db-add-fase"><Plus className="mr-1 h-3.5 w-3.5" />Aggiungi fase</Button>
      {!centri.length && <span className="ml-2 text-xs text-amber-700">Crea prima i centri di lavoro</span>}
    </div>
  );
};

export default function DistinteBase() {
  const [rows, setRows] = useState(null);
  const [arts, setArts] = useState([]);
  const [centri, setCentri] = useState([]);
  const [f, setF] = useState(null);
  const load = () => api.get("/produzione/distinte").then(({ data }) => setRows(data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); api.get("/articles").then(({ data }) => setArts(data)); api.get("/produzione/centri").then(({ data }) => setCentri(data)); }, []);
  const aItems = useMemo(() => arts.map((a) => ({ key: a.id, label: `${a.codice} · ${a.descrizione}`, um: a.unita_misura })), [arts]);
  const save = async () => {
    const body = { article_id: f.article_id, lotto: Number(f.lotto) || 1, note: f.note || "", componenti: f.componenti.map((c) => ({ article_id: c.article_id, quantita: Number(c.quantita) })), fasi: f.fasi.map((x) => ({ ...x, setup_min: Number(x.setup_min) || 0, minuti_pezzo: Number(x.minuti_pezzo) || 0 })) };
    try { f.id ? await api.put(`/produzione/distinte/${f.id}`, body) : await api.post("/produzione/distinte", body); toast.success("Distinta salvata"); setF(null); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  const del = async (d) => { if (!window.confirm(`Eliminare la distinta di ${d.codice}?`)) return; try { await api.delete(`/produzione/distinte/${d.id}`); load(); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <div data-testid="distinte-page">
      <PageHeader eyebrow="Produzione" title="Distinte base e cicli" subtitle="Componenti, semilavorati (con la loro distinta: multilivello) e fasi di lavoro; il costo standard somma materiali e lavorazioni">
        <Button onClick={() => setF({ ...NEW })} data-testid="db-new-btn"><Plus className="mr-2 h-4 w-4" />Nuova distinta</Button>
      </PageHeader>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm" data-testid="db-table">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500"><tr><th className="px-4 py-3">Prodotto</th><th className="px-4 py-3">Componenti</th><th className="px-4 py-3">Fasi</th><th className="px-4 py-3 text-right">Materiali</th><th className="px-4 py-3 text-right">Lavorazioni</th><th className="px-4 py-3 text-right">Costo standard</th><th /></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {rows?.length === 0 && <tr><td colSpan={7} className="px-4 py-10 text-center text-slate-500" data-testid="db-empty">Nessuna distinta base</td></tr>}
            {rows?.map((d) => (
              <tr key={d.id} data-testid={`db-row-${d.id}`}>
                <td className="px-4 py-3"><span className="mono text-xs font-semibold">{d.codice}</span> {d.descrizione}<div className="text-xs text-slate-500">lotto {d.lotto} {d.unita_misura}</div></td>
                <td className="px-4 py-3 text-xs">{d.componenti.map((c) => `${c.quantita} × ${c.codice}`).join(", ")}</td>
                <td className="px-4 py-3 text-xs">{d.fasi.map((x) => x.descrizione).join(" → ") || "—"}</td>
                <td className="px-4 py-3 text-right">{fmtEUR(d.costo.materiali)}</td><td className="px-4 py-3 text-right">{fmtEUR(d.costo.lavorazioni)}</td>
                <td className="px-4 py-3 text-right font-semibold" data-testid={`db-costo-${d.id}`}>{fmtEUR(d.costo.materiali + d.costo.lavorazioni)}</td>
                <td className="whitespace-nowrap px-4 py-3 text-right"><Button size="sm" variant="outline" onClick={() => setF(d)} data-testid={`db-edit-${d.id}`}><Pencil className="h-3.5 w-3.5" /></Button> <Button size="sm" variant="outline" className="text-rose-600" onClick={() => del(d)} data-testid={`db-del-${d.id}`}><Trash2 className="h-3.5 w-3.5" /></Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Dialog open={!!f} onOpenChange={(v) => !v && setF(null)}>
        <DialogContent className="max-h-[92vh] overflow-y-auto bg-white sm:max-w-3xl" data-testid="db-dialog">
          <DialogHeader><DialogTitle>{f?.id ? `Distinta ${f.codice}` : "Nuova distinta base"}</DialogTitle></DialogHeader>
          {f && <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-4">
              <label className="text-xs text-slate-600 sm:col-span-3">Prodotto finito o semilavorato<SearchPicker items={aItems} value={aItems.find((a) => a.key === f.article_id)?.label} onPick={(i) => setF({ ...f, article_id: i.key })} onClear={() => setF({ ...f, article_id: "" })} placeholder="Cerca articolo" testId="db-prodotto" className="w-full" /></label>
              <label className="text-xs text-slate-600">Lotto standard<Input type="number" min={1} value={f.lotto} onChange={(e) => setF({ ...f, lotto: e.target.value })} data-testid="db-lotto" /></label>
            </div>
            <Componenti f={f} setF={setF} aItems={aItems} />
            <Fasi f={f} setF={setF} centri={centri} />
            <label className="block text-xs text-slate-600">Note<Input value={f.note || ""} onChange={(e) => setF({ ...f, note: e.target.value })} data-testid="db-note" /></label>
          </div>}
          <DialogFooter><Button variant="outline" onClick={() => setF(null)}>Annulla</Button><Button onClick={save} disabled={!f?.article_id || !f?.componenti.length} data-testid="db-save">Salva distinta</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

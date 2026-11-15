import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, Save } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR } from "@/lib/fe";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function CentriLavoro() {
  const [rows, setRows] = useState([]);
  const [n, setN] = useState({ codice: "", descrizione: "", costo_orario: "" });
  const load = () => api.get("/produzione/centri").then(({ data }) => setRows(data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, []);
  const body = (x) => ({ codice: x.codice, descrizione: x.descrizione, costo_orario: Number(x.costo_orario) || 0 });
  const add = async () => { try { await api.post("/produzione/centri", body(n)); setN({ codice: "", descrizione: "", costo_orario: "" }); load(); } catch (e) { toast.error(errMsg(e)); } };
  const save = async (x) => { try { await api.put(`/produzione/centri/${x.id}`, body(x)); toast.success("Salvato"); load(); } catch (e) { toast.error(errMsg(e)); } };
  const del = async (x) => { if (!window.confirm(`Eliminare ${x.codice}?`)) return; try { await api.delete(`/produzione/centri/${x.id}`); load(); } catch (e) { toast.error(errMsg(e)); } };
  const upd = (id, k, v) => setRows(rows.map((x) => (x.id === id ? { ...x, [k]: v } : x)));
  return (
    <div data-testid="centri-page">
      <PageHeader eyebrow="Produzione" title="Centri di lavoro" subtitle="Reparti, macchine o linee con il costo orario usato per valorizzare le lavorazioni" />
      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="grid grid-cols-12 gap-2 border-b border-slate-100 pb-2 text-xs font-semibold uppercase tracking-wider text-slate-500"><span className="col-span-2">Codice</span><span className="col-span-6">Descrizione</span><span className="col-span-2">Costo orario €</span></div>
        {rows.map((x) => (
          <div key={x.id} className="grid grid-cols-12 items-center gap-2 py-1" data-testid={`centro-row-${x.id}`}>
            <Input className="col-span-2" value={x.codice} onChange={(e) => upd(x.id, "codice", e.target.value)} data-testid={`centro-codice-${x.id}`} />
            <Input className="col-span-6" value={x.descrizione} onChange={(e) => upd(x.id, "descrizione", e.target.value)} />
            <Input className="col-span-2" type="number" min={0} step="0.01" value={x.costo_orario} onChange={(e) => upd(x.id, "costo_orario", e.target.value)} data-testid={`centro-costo-${x.id}`} />
            <span className="col-span-2 flex gap-1"><Button size="sm" variant="outline" onClick={() => save(x)} data-testid={`centro-save-${x.id}`}><Save className="h-3.5 w-3.5" /></Button><Button size="sm" variant="outline" className="text-rose-600" onClick={() => del(x)} data-testid={`centro-del-${x.id}`}><Trash2 className="h-3.5 w-3.5" /></Button><span className="self-center text-xs text-slate-400">{fmtEUR(Number(x.costo_orario) || 0)}/h</span></span>
          </div>
        ))}
        <div className="mt-2 grid grid-cols-12 items-center gap-2 border-t border-slate-100 pt-3">
          <Input className="col-span-2" placeholder="es. TOR01" value={n.codice} onChange={(e) => setN({ ...n, codice: e.target.value })} data-testid="centro-new-codice" />
          <Input className="col-span-6" placeholder="es. Tornio CNC" value={n.descrizione} onChange={(e) => setN({ ...n, descrizione: e.target.value })} data-testid="centro-new-descrizione" />
          <Input className="col-span-2" type="number" min={0} step="0.01" placeholder="€/ora" value={n.costo_orario} onChange={(e) => setN({ ...n, costo_orario: e.target.value })} data-testid="centro-new-costo" />
          <Button className="col-span-2" onClick={add} disabled={!n.codice || !n.descrizione} data-testid="centro-add-btn"><Plus className="mr-1 h-4 w-4" />Aggiungi</Button>
        </div>
      </div>
    </div>
  );
}

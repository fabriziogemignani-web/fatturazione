import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Pencil, Trash2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NSelect } from "@/components/ui/nselect";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";

const VUOTA = { nome: "", party_id: "", matricola: "", tipo: "motore", lunghezza: "", larghezza: "", pescaggio: "", bandiera: "IT", note: "" };

const BarcaDialog = ({ open, barca, clienti, onClose, onSaved }) => {
  const [f, setF] = useState(VUOTA);
  useEffect(() => { if (open) { setF(barca ? { ...VUOTA, ...barca } : VUOTA); } }, [open, barca]);
  const s = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    const body = { ...f, lunghezza: Number(f.lunghezza), larghezza: Number(f.larghezza || 0), pescaggio: Number(f.pescaggio || 0) };
    try {
      if (barca?.id) await api.put(`/porto/barche/${barca.id}`, body); else await api.post("/porto/barche", body);
      toast.success("Barca salvata"); onSaved(); onClose();
    } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="barca-dialog">
        <DialogHeader><DialogTitle>{barca?.id ? "Modifica barca" : "Nuova barca"}</DialogTitle></DialogHeader>
        <div className="grid grid-cols-2 gap-3 text-sm">
          <label className="col-span-2">Nome<Input value={f.nome} onChange={s("nome")} data-testid="barca-nome" /></label>
          <label className="col-span-2">Armatore (cliente)
            <NSelect value={f.party_id} onChange={s("party_id")} data-testid="barca-armatore">
              <option value="">Seleziona...</option>
              {clienti.map((c) => <option key={c.id} value={c.id}>{c.denominazione}</option>)}
            </NSelect>
          </label>
          <label>Matricola / targa<Input value={f.matricola} onChange={s("matricola")} data-testid="barca-matricola" /></label>
          <label>Tipo<NSelect value={f.tipo} onChange={s("tipo")} data-testid="barca-tipo"><option value="motore">Motore</option><option value="vela">Vela</option><option value="gommone">Gommone</option><option value="altro">Altro</option></NSelect></label>
          <label>Lunghezza (m)<Input type="number" step="0.01" value={f.lunghezza} onChange={s("lunghezza")} data-testid="barca-lunghezza" /></label>
          <label>Larghezza (m)<Input type="number" step="0.01" value={f.larghezza} onChange={s("larghezza")} data-testid="barca-larghezza" /></label>
          <label>Pescaggio (m)<Input type="number" step="0.01" value={f.pescaggio} onChange={s("pescaggio")} data-testid="barca-pescaggio" /></label>
          <label>Bandiera<Input value={f.bandiera} onChange={s("bandiera")} data-testid="barca-bandiera" /></label>
          <label className="col-span-2">Note<Input value={f.note} onChange={s("note")} data-testid="barca-note" /></label>
        </div>
        <DialogFooter><Button onClick={save} data-testid="barca-save">Salva</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default function PortoBarche() {
  const [rows, setRows] = useState([]);
  const [clienti, setClienti] = useState([]);
  const [edit, setEdit] = useState(null);
  const [q, setQ] = useState("");
  const load = () => api.get("/porto/barche").then(({ data }) => setRows(data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); api.get("/parties", { params: { tipo: "cliente" } }).then(({ data }) => setClienti(data)).catch(() => {}); }, []);
  const del = async (b) => {
    if (!window.confirm(`Eliminare la barca ${b.nome}?`)) return;
    try { await api.delete(`/porto/barche/${b.id}`); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  const vis = rows.filter((b) => `${b.nome} ${b.armatore} ${b.matricola}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <div data-testid="porto-barche-page">
      <PageHeader eyebrow="Porto turistico" title="Barche e armatori">
        <Input placeholder="Cerca barca o armatore" value={q} onChange={(e) => setQ(e.target.value)} className="w-56" data-testid="barche-cerca" />
        <Button onClick={() => setEdit({})} data-testid="barche-nuova"><Plus className="mr-1 h-4 w-4" />Nuova barca</Button>
      </PageHeader>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-sm" data-testid="barche-table">
          <thead className="border-b bg-slate-50 text-left text-xs uppercase text-slate-500"><tr><th className="px-4 py-3">Nome</th><th className="px-4 py-3">Armatore</th><th className="px-4 py-3">Tipo</th><th className="px-4 py-3 text-right">L × B (m)</th><th className="px-4 py-3">Matricola</th><th /></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {vis.length === 0 && <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-500">Nessuna barca.</td></tr>}
            {vis.map((b) => (
              <tr key={b.id} data-testid={`barca-row-${b.id}`}>
                <td className="px-4 py-3 font-semibold">{b.nome}</td><td className="px-4 py-3">{b.armatore}</td><td className="px-4 py-3 capitalize">{b.tipo}</td>
                <td className="px-4 py-3 text-right">{b.lunghezza} × {b.larghezza || "—"}</td><td className="px-4 py-3">{b.matricola || "—"}</td>
                <td className="whitespace-nowrap px-4 py-3 text-right">
                  <Button size="sm" variant="ghost" onClick={() => setEdit(b)} data-testid={`barca-edit-${b.id}`}><Pencil className="h-3.5 w-3.5" /></Button>
                  <Button size="sm" variant="ghost" onClick={() => del(b)} data-testid={`barca-del-${b.id}`}><Trash2 className="h-3.5 w-3.5 text-rose-600" /></Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <BarcaDialog open={!!edit} barca={edit} clienti={clienti} onClose={() => setEdit(null)} onSaved={load} />
    </div>
  );
}

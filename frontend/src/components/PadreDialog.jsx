import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";

export const PadreDialog = ({ company, onClose, onSaved }) => {
  const [rows, setRows] = useState([]);
  useEffect(() => {
    if (company) { api.get("/ai/padre").then(({ data }) => setRows(data.pacchetti)).catch(() => {}); }
  }, [company]);
  const upd = (i, k, v) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  const save = async () => {
    try {
      await api.put(`/companies/${company.id}/padre`, { pacchetti: rows.map((r) => ({ ...r, crediti: Number(r.crediti), prezzo: Number(r.prezzo) })) });
      toast.success(`${company.denominazione} è ora la società padre`); onSaved(); onClose();
    } catch (e) { toast.error(errMsg(e)); }
  };
  const remove = async () => {
    try { await api.delete(`/companies/${company.id}/padre`); toast.success("Flag società padre tolto"); onSaved(); onClose(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Dialog open={!!company} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl" data-testid="padre-dialog">
        <DialogHeader>
          <DialogTitle>Società padre e listino crediti IA</DialogTitle>
          <DialogDescription>La società padre è il produttore del software: le aziende comprano da lei i crediti IA con carta. Può esserci una sola società padre.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          {rows.map((r, i) => (
            <div key={i} className="grid grid-cols-[1fr_1.4fr_1fr_1fr_auto] items-center gap-2" data-testid={`padre-pacchetto-${i}`}>
              <Input value={r.id} onChange={(e) => upd(i, "id", e.target.value.toLowerCase())} placeholder="codice" data-testid={`padre-pk-id-${i}`} />
              <Input value={r.nome} onChange={(e) => upd(i, "nome", e.target.value)} placeholder="nome" data-testid={`padre-pk-nome-${i}`} />
              <Input type="number" value={r.crediti} onChange={(e) => upd(i, "crediti", e.target.value)} placeholder="crediti" data-testid={`padre-pk-crediti-${i}`} />
              <Input type="number" step="0.01" value={r.prezzo} onChange={(e) => upd(i, "prezzo", e.target.value)} placeholder="€" data-testid={`padre-pk-prezzo-${i}`} />
              <Button size="icon" variant="ghost" onClick={() => setRows(rows.filter((_, j) => j !== i))} data-testid={`padre-pk-del-${i}`}><Trash2 className="h-4 w-4 text-rose-600" /></Button>
            </div>
          ))}
          {rows.length < 6 && <Button size="sm" variant="outline" onClick={() => setRows([...rows, { id: `p${rows.length + 1}`, nome: "", crediti: 1000, prezzo: 20 }])} data-testid="padre-pk-add"><Plus className="mr-1 h-3.5 w-3.5" />Pacchetto</Button>}
          <p className="text-xs text-slate-500">1 credito = 1.000 token consumati dall'IA. Prezzi in euro.</p>
        </div>
        <DialogFooter className="gap-2">
          {company?.societa_padre && <Button variant="outline" className="text-rose-600" onClick={remove} data-testid="padre-remove-btn">Togli flag padre</Button>}
          <Button onClick={save} data-testid="padre-save-btn">Salva come società padre</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

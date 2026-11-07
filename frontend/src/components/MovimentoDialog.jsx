import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { fmtEUR } from "@/lib/fe";

export const TIPI_MOV = [["carico", "Carico"], ["scarico", "Scarico"], ["rettifica", "Rettifica inventario"]];
const today = () => new Date().toISOString().slice(0, 10);

export const MovimentoDialog = ({ open, onClose, onSaved, articoli, causali, preset }) => {
  const [f, setF] = useState({});
  useEffect(() => {
    if (!open) { return; }
    const a = articoli.find((x) => x.id === preset?.article_id);
    setF({ article_id: preset?.article_id || "", tipo: preset?.tipo || "carico", data: today(), quantita: "", costo_unitario: a?.costo_medio ? String(a.costo_medio) : "",
      causale: (causali[preset?.tipo || "carico"] || [])[0] || "", documento: "", note: "" });
  }, [open, preset, articoli, causali]);
  const a = articoli.find((x) => x.id === f.article_id);
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const setTipo = (v) => setF((x) => ({ ...x, tipo: v, causale: (causali[v] || [])[0] || "" }));
  const save = async () => {
    try {
      const body = { ...f, quantita: Number(f.quantita), costo_unitario: f.tipo === "scarico" || f.costo_unitario === "" ? null : Number(f.costo_unitario) };
      const { data } = await api.post("/magazzino/movimenti", body);
      toast.success(`Movimento registrato · giacenza ${data.articolo.giacenza} ${data.unita_misura}`.trim());
      onSaved(); onClose();
    } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-white sm:max-w-lg" data-testid="movimento-dialog">
        <DialogHeader>
          <DialogTitle>Movimento di magazzino</DialogTitle>
          <DialogDescription>{a ? `${a.codice} · giacenza ${a.giacenza ?? 0} ${a.unita_misura || ""} · costo medio ${fmtEUR(a.costo_medio || 0)}` : "Scegli l'articolo"}</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="text-xs text-slate-600 sm:col-span-2">Articolo
            <Select value={f.article_id} onValueChange={(v) => setF((x) => ({ ...x, article_id: v, costo_unitario: String(articoli.find((y) => y.id === v)?.costo_medio || "") }))}>
              <SelectTrigger data-testid="mov-article-select"><SelectValue placeholder="Scegli…" /></SelectTrigger>
              <SelectContent className="max-h-72 bg-white">{articoli.map((x) => <SelectItem key={x.id} value={x.id}>{x.codice} · {x.descrizione}</SelectItem>)}</SelectContent>
            </Select>
          </label>
          <div className="flex gap-2 sm:col-span-2">
            {TIPI_MOV.map(([k, l]) => (
              <button key={k} type="button" onClick={() => setTipo(k)} data-testid={`mov-tipo-${k}`}
                className={`flex-1 rounded-md border px-2 py-2 text-xs font-semibold ${f.tipo === k ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 text-slate-600"}`}>{l}</button>
            ))}
          </div>
          <label className="text-xs text-slate-600">Data<Input type="date" value={f.data || ""} onChange={(e) => set("data", e.target.value)} data-testid="mov-data-input" /></label>
          <label className="text-xs text-slate-600">Quantità{f.tipo === "rettifica" ? " (+ o −)" : ""}<Input type="number" step="any" value={f.quantita ?? ""} onChange={(e) => set("quantita", e.target.value)} data-testid="mov-quantita-input" /></label>
          {f.tipo !== "scarico" && <label className="text-xs text-slate-600">Costo unitario (€){f.tipo === "rettifica" ? " – vuoto = costo medio" : ""}<Input type="number" step="0.0001" min={0} value={f.costo_unitario ?? ""} onChange={(e) => set("costo_unitario", e.target.value)} data-testid="mov-costo-input" /></label>}
          <label className="text-xs text-slate-600">Causale
            <Select value={f.causale} onValueChange={(v) => set("causale", v)}>
              <SelectTrigger data-testid="mov-causale-select"><SelectValue /></SelectTrigger>
              <SelectContent className="bg-white">{(causali[f.tipo] || []).map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
            </Select>
          </label>
          <label className="text-xs text-slate-600">Documento di riferimento<Input value={f.documento || ""} onChange={(e) => set("documento", e.target.value)} placeholder="DDT 45/2026" data-testid="mov-documento-input" /></label>
          <label className="text-xs text-slate-600 sm:col-span-2">Note<Input value={f.note || ""} onChange={(e) => set("note", e.target.value)} data-testid="mov-note-input" /></label>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} data-testid="mov-cancel-btn">Annulla</Button>
          <Button onClick={save} disabled={!f.article_id || !f.quantita} data-testid="mov-save-btn">Registra</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

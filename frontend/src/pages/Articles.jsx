import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Pencil, Trash2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { ALIQUOTE, NATURE, UNITA, fmtEUR } from "@/lib/fe";
import { PageHeader, Field } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const EMPTY = { codice: "", descrizione: "", unita_misura: "", prezzo: "", aliquota: 22, natura: null };

const Sel = ({ value, onChange, options, testId }) => (
  <Select value={value} onValueChange={onChange}>
    <SelectTrigger data-testid={testId}><SelectValue /></SelectTrigger>
    <SelectContent className="bg-white">{options.map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent>
  </Select>
);

const ArticleDialog = ({ open, onOpenChange, item, onSaved }) => {
  const [f, setF] = useState(EMPTY);
  useEffect(() => { if (open) setF(item ? { ...EMPTY, ...item } : EMPTY); }, [open, item]);
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));

  const save = async () => {
    try {
      const body = { ...f, prezzo: Number(f.prezzo || 0) };
      item ? await api.put(`/articles/${item.id}`, body) : await api.post("/articles", body);
      toast.success("Articolo salvato");
      onSaved();
      onOpenChange(false);
    } catch (e) { toast.error(errMsg(e)); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white sm:max-w-xl" data-testid="article-dialog">
        <DialogHeader><DialogTitle>{item ? "Modifica articolo" : "Nuovo articolo o servizio"}</DialogTitle></DialogHeader>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Codice"><Input value={f.codice} onChange={(e) => set("codice", e.target.value)} data-testid="article-codice-input" /></Field>
          <Field label="Unità di misura"><Sel value={f.unita_misura || "-"} onChange={(v) => set("unita_misura", v === "-" ? "" : v)} options={UNITA.map((u) => [u || "-", u || "Nessuna"])} testId="article-um-select" /></Field>
          <Field label="Descrizione" className="sm:col-span-2"><Input value={f.descrizione} onChange={(e) => set("descrizione", e.target.value)} data-testid="article-descrizione-input" /></Field>
          <Field label="Prezzo unitario (€)"><Input type="number" step="0.01" value={f.prezzo} onChange={(e) => set("prezzo", e.target.value)} data-testid="article-prezzo-input" /></Field>
          <Field label="Aliquota IVA"><Sel value={String(f.aliquota)} onChange={(v) => setF((x) => ({ ...x, aliquota: Number(v), natura: Number(v) === 0 ? x.natura || "N2.2" : null }))} options={ALIQUOTE.map((a) => [String(a), `IVA ${a}%`])} testId="article-aliquota-select" /></Field>
          {Number(f.aliquota) === 0 && (
            <Field label="Natura IVA" className="sm:col-span-2"><Sel value={f.natura || "N2.2"} onChange={(v) => set("natura", v)} options={NATURE} testId="article-natura-select" /></Field>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="article-cancel-btn">Annulla</Button>
          <Button onClick={save} data-testid="article-save-btn">Salva</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default function Articles() {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const load = () => api.get("/articles").then(({ data }) => setItems(data));
  useEffect(() => { load(); }, []);

  const remove = async (a) => {
    if (!window.confirm(`Eliminare ${a.codice}?`)) return;
    try { await api.delete(`/articles/${a.id}`); toast.success("Eliminato"); load(); } catch (e) { toast.error(errMsg(e)); }
  };

  return (
    <div>
      <PageHeader eyebrow="Archivio" title="Articoli e servizi">
        <Button onClick={() => { setEditing(null); setOpen(true); }} data-testid="new-article-btn"><Plus className="mr-2 h-4 w-4" />Nuovo articolo</Button>
      </PageHeader>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm" data-testid="articles-table">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr><th className="px-4 py-3 font-medium">Codice</th><th className="px-4 py-3 font-medium">Descrizione</th><th className="px-4 py-3 font-medium">U.M.</th><th className="px-4 py-3 text-right font-medium">Prezzo</th><th className="px-4 py-3 font-medium">IVA</th><th className="px-4 py-3" /></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items.map((a) => (
              <tr key={a.id} className="hover:bg-slate-50" data-testid={`article-row-${a.id}`}>
                <td className="mono px-4 py-3 text-xs font-medium text-slate-900">{a.codice}</td>
                <td className="px-4 py-3 text-slate-800">{a.descrizione}</td>
                <td className="px-4 py-3 text-slate-600">{a.unita_misura || "—"}</td>
                <td className="px-4 py-3 text-right font-semibold text-slate-900">{fmtEUR(a.prezzo)}</td>
                <td className="px-4 py-3"><span className="mono rounded-md border border-slate-200 bg-slate-100 px-2 py-0.5 text-xs">{a.aliquota ? `${a.aliquota}%` : a.natura}</span></td>
                <td className="whitespace-nowrap px-4 py-3 text-right">
                  <button onClick={() => { setEditing(a); setOpen(true); }} className="rounded p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-900" data-testid={`article-edit-${a.id}`}><Pencil className="h-4 w-4" /></button>
                  <button onClick={() => remove(a)} className="rounded p-1.5 text-slate-500 hover:bg-rose-50 hover:text-rose-600" data-testid={`article-delete-${a.id}`}><Trash2 className="h-4 w-4" /></button>
                </td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={6} className="px-4 py-12 text-center text-slate-500" data-testid="articles-empty">Nessun articolo. Inserisci le voci di fatturazione che usi più spesso.</td></tr>}
          </tbody>
        </table>
      </div>
      <ArticleDialog open={open} onOpenChange={setOpen} item={editing} onSaved={load} />
    </div>
  );
}

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Pencil, Trash2, FlaskConical } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { fmtEUR, fmtDate } from "@/lib/fe";

const EMPTY = { nome: "", contiene: "", segno: "uscita", importo_min: "", importo_max: "", categoria: "", note: "", attiva: true };
const SEGNI = [["uscita", "Uscite"], ["entrata", "Entrate"], ["entrambi", "Entrambi"]];
const num = (v) => (v === "" || v == null ? null : Number(v));

const Chip = ({ on, onClick, children, id }) => (
  <button type="button" onClick={onClick} data-testid={id}
    className={`rounded-full border px-3 py-1 text-xs font-semibold ${on ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 text-slate-600 hover:border-slate-400"}`}>{children}</button>
);

const RuleForm = ({ f, setF, cats, onSave, onCancel }) => {
  const [prova, setProva] = useState(null);
  const body = () => ({ ...f, importo_min: num(f.importo_min), importo_max: num(f.importo_max) });
  const test = async () => { try { const { data } = await api.post("/banca/regole/prova", body()); setProva(data); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-4" data-testid="rule-form">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="text-xs text-slate-600">Nome regola<Input value={f.nome} onChange={(e) => setF({ ...f, nome: e.target.value })} data-testid="rule-nome-input" /></label>
        <label className="text-xs text-slate-600">La descrizione contiene<Input value={f.contiene} placeholder="commissioni, canone conto" onChange={(e) => setF({ ...f, contiene: e.target.value })} data-testid="rule-contiene-input" /></label>
      </div>
      <p className="text-[11px] text-slate-500">Parole separate da spazio: devono esserci tutte. Separate da virgola: basta una delle alternative.</p>
      <div className="flex flex-wrap items-center gap-2">{SEGNI.map(([k, l]) => <Chip key={k} id={`rule-segno-${k}`} on={f.segno === k} onClick={() => setF({ ...f, segno: k })}>{l}</Chip>)}
        <Input type="number" min={0} step="0.01" placeholder="importo min" className="w-32" value={f.importo_min ?? ""} onChange={(e) => setF({ ...f, importo_min: e.target.value })} data-testid="rule-min-input" />
        <Input type="number" min={0} step="0.01" placeholder="importo max" className="w-32" value={f.importo_max ?? ""} onChange={(e) => setF({ ...f, importo_max: e.target.value })} data-testid="rule-max-input" />
      </div>
      <div className="flex flex-wrap gap-2">{cats.map((c, i) => <Chip key={c} id={`rule-cat-${i}`} on={f.categoria === c} onClick={() => setF({ ...f, categoria: c })}>{c}</Chip>)}</div>
      <Input placeholder="Nota sul movimento (facoltativa)" value={f.note || ""} onChange={(e) => setF({ ...f, note: e.target.value })} data-testid="rule-note-input" />
      {prova && (
        <div className="rounded-md bg-white p-2 text-xs text-slate-600" data-testid="rule-prova-result">
          <b>{prova.n}</b> {prova.n === 1 ? "movimento da riconciliare corrisponde" : "movimenti da riconciliare corrispondono"}{prova.esempi.map((x) => <div key={x.id}>{fmtDate(x.data)} · {fmtEUR(x.importo)} · {x.descrizione}</div>)}
        </div>
      )}
      <div className="flex gap-2">
        <Button size="sm" onClick={() => onSave(body())} disabled={!f.nome.trim() || f.contiene.trim().length < 2 || !f.categoria} data-testid="rule-save-btn">Salva regola</Button>
        <Button size="sm" variant="outline" onClick={test} disabled={f.contiene.trim().length < 2 || !f.categoria} data-testid="rule-test-btn"><FlaskConical className="mr-1 h-3.5 w-3.5" />Prova</Button>
        <Button size="sm" variant="ghost" onClick={onCancel} data-testid="rule-cancel-btn">Annulla</Button>
      </div>
    </div>
  );
};

export const RegoleDialog = ({ open, onClose, onChanged }) => {
  const [data, setData] = useState({ regole: [], categorie: [] });
  const [edit, setEdit] = useState(null);
  const load = () => api.get("/banca/regole").then(({ data: d }) => setData(d)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { if (open) { load(); setEdit(null); } }, [open]);
  const save = async (body) => {
    try {
      if (edit.id) await api.put(`/banca/regole/${edit.id}`, body); else await api.post("/banca/regole", body);
      const { data: r } = await api.post("/banca/auto");
      toast.success(`Regola salvata · ${r.riconciliati} movimenti riconciliati`);
      setEdit(null); load(); onChanged();
    } catch (e) { toast.error(errMsg(e)); }
  };
  const toggle = async (r) => { try { await api.put(`/banca/regole/${r.id}`, { ...r, attiva: !r.attiva }); load(); } catch (e) { toast.error(errMsg(e)); } };
  const del = async (r) => { if (!window.confirm(`Eliminare la regola ${r.nome}?`)) return; try { await api.delete(`/banca/regole/${r.id}`); load(); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] grid-cols-1 overflow-y-auto bg-white sm:max-w-2xl [&>*]:min-w-0" data-testid="rules-dialog">
        <DialogHeader>
          <DialogTitle>Regole di abbinamento</DialogTitle>
          <DialogDescription>I movimenti che corrispondono a una regola vengono riconciliati da soli nella categoria scelta, se non c'è una fattura sicura da abbinare.</DialogDescription>
        </DialogHeader>
        {edit ? <RuleForm f={edit} setF={setEdit} cats={data.categorie} onSave={save} onCancel={() => setEdit(null)} />
          : <Button size="sm" className="self-start" onClick={() => setEdit({ ...EMPTY })} data-testid="rule-new-btn">Nuova regola</Button>}
        <div className="divide-y divide-slate-100">
          {data.regole.length === 0 && <p className="py-4 text-sm text-slate-500" data-testid="rules-empty">Nessuna regola salvata.</p>}
          {data.regole.map((r) => (
            <div key={r.id} className="flex items-center gap-3 py-3" data-testid={`rule-row-${r.id}`}>
              <Switch checked={r.attiva} onCheckedChange={() => toggle(r)} data-testid={`rule-toggle-${r.id}`} />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-slate-900">{r.nome}</div>
                <div className="truncate text-xs text-slate-500">"{r.contiene}" · {SEGNI.find((s) => s[0] === r.segno)?.[1]} → {r.categoria} · applicata {r.applicata || 0} {r.applicata === 1 ? "volta" : "volte"}</div>
              </div>
              <Button size="sm" variant="ghost" onClick={() => setEdit({ ...r, importo_min: r.importo_min ?? "", importo_max: r.importo_max ?? "" })} data-testid={`rule-edit-${r.id}`}><Pencil className="h-3.5 w-3.5" /></Button>
              <Button size="sm" variant="ghost" onClick={() => del(r)} data-testid={`rule-delete-${r.id}`}><Trash2 className="h-3.5 w-3.5" /></Button>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
};

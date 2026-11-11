import { Trash2, StickyNote } from "lucide-react";
import { useState } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ALIQUOTE, NATURE, fmtEUR, lineTotal } from "@/lib/fe";
import { useInvalid } from "@/components/Common";

export const LineRow = ({ line, idx, onChange, onRemove, disabled, canRemove }) => {
  const [bad, clear] = useInvalid();
  const [noteOpen, setNoteOpen] = useState(false);
  const showNote = noteOpen || !!line.note;
  const set = (k, v) => { clear(`lines.${idx}.${k}`); onChange(idx, { ...line, [k]: v }); };
  const total = lineTotal(line);
  const b = (k) => bad(`lines.${idx}.${k}`);
  return (
    <div className="grid grid-cols-12 gap-2 rounded-lg border border-slate-200 p-3" data-testid={`line-row-${idx}`}>
      <Input disabled={disabled} className={`col-span-12 md:col-span-3 ${b("descrizione")}`} placeholder="Descrizione" value={line.descrizione} onChange={(e) => set("descrizione", e.target.value)} data-testid={`line-descrizione-${idx}`} />
      <Input disabled={disabled} className={`col-span-3 md:col-span-2 ${b("quantita")}`} type="number" min="0" step="any" placeholder="Qtà" value={line.quantita} onChange={(e) => set("quantita", e.target.value)} data-testid={`line-quantita-${idx}`} />
      <Input disabled={disabled} className={`col-span-3 md:col-span-2 ${b("prezzo_unitario")}`} type="number" step="0.01" placeholder="Prezzo" value={line.prezzo_unitario} onChange={(e) => set("prezzo_unitario", e.target.value)} data-testid={`line-prezzo-${idx}`} />
      <Input disabled={disabled} className={`col-span-3 md:col-span-1 px-2 ${b("sconto")}`} placeholder="Sc.%" title="Sconto % (anche in cascata, es. 10+5)" value={line.sconto || ""} onChange={(e) => set("sconto", e.target.value)} data-testid={`line-sconto-${idx}`} />
      <Select disabled={disabled} value={String(line.aliquota)} onValueChange={(v) => { clear(`lines.${idx}.aliquota`); clear(`lines.${idx}.natura`); onChange(idx, { ...line, aliquota: Number(v), natura: Number(v) === 0 ? line.natura || "N2.2" : null }); }}>
        <SelectTrigger className={`col-span-3 md:col-span-2 ${b("aliquota")}`} data-testid={`line-aliquota-${idx}`}><SelectValue /></SelectTrigger>
        <SelectContent className="bg-white">
          {ALIQUOTE.map((a) => <SelectItem key={a} value={String(a)} data-testid={`line-aliquota-option-${a}`}>IVA {a}%</SelectItem>)}
        </SelectContent>
      </Select>
      <div className="col-span-12 flex items-center justify-end gap-1 md:col-span-2">
        <span className="text-sm font-semibold text-slate-900" data-testid={`line-total-${idx}`}>{fmtEUR(total)}</span>
        {!disabled && <button type="button" onClick={() => setNoteOpen(!showNote)} title="Nota di riga" className={`rounded p-1 hover:bg-amber-50 hover:text-amber-700 ${line.note ? "text-amber-600" : "text-slate-400"}`} data-testid={`line-note-toggle-${idx}`}><StickyNote className="h-4 w-4" /></button>}
        {!disabled && canRemove && (
          <button onClick={() => onRemove(idx)} className="rounded p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600" data-testid={`line-remove-${idx}`}><Trash2 className="h-4 w-4" /></button>
        )}
      </div>
      {showNote && (
        <div className="col-span-12">
          <Textarea disabled={disabled} rows={2} maxLength={500} placeholder="Nota della riga (es. periodo di riferimento, matricola, dettagli del servizio)"
            className={`bg-amber-50/40 text-sm ${b("note")}`} value={line.note || ""} onChange={(e) => set("note", e.target.value)} data-testid={`line-note-${idx}`} />
          <div className="mt-0.5 text-right text-[10px] text-slate-400">{(line.note || "").length}/500</div>
        </div>
      )}
      {Number(line.aliquota) === 0 && (
        <Select disabled={disabled} value={line.natura || "N2.2"} onValueChange={(v) => set("natura", v)}>
          <SelectTrigger className={`col-span-12 ${b("natura")}`} data-testid={`line-natura-${idx}`}><SelectValue placeholder="Natura IVA" /></SelectTrigger>
          <SelectContent className="bg-white">
            {NATURE.map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}
          </SelectContent>
        </Select>
      )}
    </div>
  );
};

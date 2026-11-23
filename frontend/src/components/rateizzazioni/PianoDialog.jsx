import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Field, FieldErrors, useFieldErrors } from "@/components/Common";
import { ContoSelect, useConti } from "@/components/ContoSelect";
import { api } from "@/lib/api";
import { fmtEUR } from "@/lib/fe";
import { mods } from "@/lib/moduli";
import { useCompany } from "@/context/CompanyContext";

const num = (v) => (v === "" ? 0 : Number(v));
const tot = (r) => num(r.capitale) + num(r.sanzioni) + num(r.interessi);

const RateTable = ({ rate, setRate }) => {
  const upd = (i, k, v) => setRate(rate.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="w-full text-sm" data-testid="piano-rate-table">
        <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500"><tr><th className="px-2 py-2">#</th><th className="px-2 py-2">Scadenza</th><th className="px-2 py-2">Imposta</th><th className="px-2 py-2">Sanzioni</th><th className="px-2 py-2">Interessi e oneri</th><th className="px-2 py-2 text-right">Totale</th><th /></tr></thead>
        <tbody className="divide-y divide-slate-100">
          {rate.map((r, i) => (
            <tr key={i} data-testid={`piano-rata-${i}`}>
              <td className="px-2 py-1 text-xs text-slate-500">{i + 1}</td>
              <td className="px-2 py-1"><Input type="date" value={r.scadenza} onChange={(e) => upd(i, "scadenza", e.target.value)} className="h-8 w-36" data-testid={`piano-rata-${i}-scadenza`} /></td>
              {["capitale", "sanzioni", "interessi"].map((k) => <td key={k} className="px-2 py-1"><Input type="number" step="0.01" min={0} value={r[k]} onChange={(e) => upd(i, k, e.target.value)} className="h-8 w-28" data-testid={`piano-rata-${i}-${k}`} /></td>)}
              <td className="whitespace-nowrap px-2 py-1 text-right font-semibold">{fmtEUR(tot(r))}</td>
              <td className="px-2 py-1"><button type="button" onClick={() => setRate(rate.filter((_, j) => j !== i))} className="text-slate-400 hover:text-rose-600" data-testid={`piano-rata-${i}-del`}><Trash2 className="h-4 w-4" /></button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="flex items-center justify-between px-3 py-2 text-xs">
        <button type="button" onClick={() => setRate([...rate, { scadenza: rate[rate.length - 1]?.scadenza || "", capitale: 0, sanzioni: 0, interessi: 0 }])} className="inline-flex items-center gap-1 font-semibold text-blue-600" data-testid="piano-add-rata"><Plus className="h-3.5 w-3.5" />Aggiungi rata</button>
        <span>{rate.length} rate · totale <b data-testid="piano-totale">{fmtEUR(rate.reduce((s, r) => s + tot(r), 0))}</b></span>
      </div>
    </div>
  );
};

export const PianoDialog = ({ piano, onClose, onSaved }) => {
  const coge = mods(useCompany().company).contabilita;
  const [conti] = useConti(!!piano && coge);
  const [f, setF] = useState(null);
  const [saving, setSaving] = useState(false);
  const { fail, reset, value } = useFieldErrors();
  useEffect(() => { if (piano) { setF(piano); reset(); } }, [piano, reset]);
  if (!piano || !f) return null;
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    setSaving(true);
    try {
      const body = { ...f, rate: f.rate.map((r) => ({ scadenza: r.scadenza, capitale: num(r.capitale), sanzioni: num(r.sanzioni), interessi: num(r.interessi) })) };
      await (f.id ? api.put(`/rateizzazioni/${f.id}`, body) : api.post("/rateizzazioni", body));
      toast.success(f.id ? "Piano aggiornato" : "Piano di rateizzazione salvato");
      onSaved();
      onClose();
    } catch (e) { fail(e); } finally { setSaving(false); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto bg-white sm:max-w-3xl" data-testid="piano-dialog">
        <FieldErrors value={value}>
          <DialogHeader><DialogTitle>{f.id ? "Modifica piano di rateizzazione" : "Controlla il piano letto dal PDF"}</DialogTitle></DialogHeader>
          {f.pdf_id && !f.id && <p className="rounded-lg bg-blue-50 p-3 text-xs text-blue-900" data-testid="piano-ia-note">Dati letti con l'intelligenza artificiale: verifica date e importi con il piano originale prima di salvare.</p>}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Ente" name="ente"><Input value={f.ente} onChange={set("ente")} data-testid="piano-ente" /></Field>
            <Field label="Numero piano / protocollo" name="numero"><Input value={f.numero || ""} onChange={set("numero")} data-testid="piano-numero" /></Field>
            <Field label="Descrizione" name="descrizione" className="sm:col-span-2"><Input value={f.descrizione || ""} onChange={set("descrizione")} data-testid="piano-descrizione" /></Field>
            <Field label="Data del piano" name="data"><Input type="date" value={f.data} onChange={set("data")} data-testid="piano-data" /></Field>
          </div>
          {coge && (
            <div className="grid grid-cols-1 gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3 sm:grid-cols-3" data-testid="piano-conti">
              {[["conto_debito", "Conto del debito (imposta)"], ["conto_sanzioni", "Conto sanzioni"], ["conto_interessi", "Conto interessi e oneri"]].map(([k, l]) => (
                <Field key={k} label={l} name={k}><ContoSelect conti={conti} value={f[k]} onChange={(v) => setF({ ...f, [k]: v })} testId={`piano-${k.replace("_", "-")}`} /></Field>
              ))}
            </div>
          )}
          <Field name="rate"><RateTable rate={f.rate} setRate={(rate) => setF({ ...f, rate })} /></Field>
          {f.note && <p className="text-xs text-amber-800" data-testid="piano-note">{f.note}</p>}
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={onClose} data-testid="piano-cancel">Annulla</Button>
            <Button onClick={save} disabled={saving || !f.rate.length} data-testid="piano-save">{saving ? "Salvataggio…" : "Salva piano"}</Button>
          </DialogFooter>
        </FieldErrors>
      </DialogContent>
    </Dialog>
  );
};

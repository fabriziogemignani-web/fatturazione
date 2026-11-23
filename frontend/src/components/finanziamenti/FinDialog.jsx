import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { NSelect } from "@/components/ui/nselect";
import { Field, FieldErrors, useFieldErrors } from "@/components/Common";
import { ContoSelect, useConti } from "@/components/ContoSelect";
import { CalcoloPiano } from "@/components/finanziamenti/CalcoloPiano";
import { api } from "@/lib/api";
import { fmtEUR } from "@/lib/fe";
import { mods } from "@/lib/moduli";
import { useCompany } from "@/context/CompanyContext";

const num = (v) => (v === "" || v == null ? 0 : Number(v));
const CONTI = { finanziamento: [["conto_debito", "Conto del debito (quota capitale)"], ["conto_interessi", "Conto interessi passivi"]], leasing: [["conto_canone", "Conto canoni di leasing"], ["conto_iva", "Conto IVA sui canoni"]] };

const RateFin = ({ f, setRate }) => {
  const rate = f.rate;
  const iva = f.tipo === "leasing" ? num(f.aliquota_iva) / 100 : 0;
  const upd = (i, k, v) => setRate(rate.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  const tot = (r) => (num(r.capitale) + num(r.interessi)) * (1 + iva);
  return (
    <div className="max-h-80 overflow-auto rounded-lg border border-slate-200">
      <table className="w-full text-sm" data-testid="fin-rate-table">
        <thead className="sticky top-0 bg-slate-50 text-left text-xs uppercase text-slate-500"><tr><th className="px-2 py-2">#</th><th className="px-2 py-2">Scadenza</th><th className="px-2 py-2">Voce</th><th className="px-2 py-2">Quota capitale</th><th className="px-2 py-2">Interessi</th>{iva > 0 && <th className="px-2 py-2 text-right">IVA</th>}<th className="px-2 py-2 text-right">Totale</th><th /></tr></thead>
        <tbody className="divide-y divide-slate-100">
          {rate.map((r, i) => (
            <tr key={i} data-testid={`fin-rata-${i}`}>
              <td className="px-2 py-1 text-xs text-slate-500">{i + 1}</td>
              <td className="px-2 py-1"><Input type="date" value={r.scadenza} onChange={(e) => upd(i, "scadenza", e.target.value)} className="h-8 w-36" data-testid={`fin-rata-${i}-scadenza`} /></td>
              <td className="px-2 py-1"><Input value={r.descrizione || ""} onChange={(e) => upd(i, "descrizione", e.target.value)} className="h-8 w-28" data-testid={`fin-rata-${i}-desc`} /></td>
              {["capitale", "interessi"].map((k) => <td key={k} className="px-2 py-1"><Input type="number" step="0.01" min={0} value={r[k]} onChange={(e) => upd(i, k, e.target.value)} className="h-8 w-28" data-testid={`fin-rata-${i}-${k}`} /></td>)}
              {iva > 0 && <td className="whitespace-nowrap px-2 py-1 text-right text-xs">{fmtEUR((num(r.capitale) + num(r.interessi)) * iva)}</td>}
              <td className="whitespace-nowrap px-2 py-1 text-right font-semibold">{fmtEUR(tot(r))}</td>
              <td className="px-2 py-1"><button type="button" onClick={() => setRate(rate.filter((_, j) => j !== i))} className="text-slate-400 hover:text-rose-600" data-testid={`fin-rata-${i}-del`}><Trash2 className="h-4 w-4" /></button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="sticky bottom-0 flex items-center justify-between bg-white px-3 py-2 text-xs">
        <button type="button" onClick={() => setRate([...rate, { scadenza: rate[rate.length - 1]?.scadenza || f.data, capitale: 0, interessi: 0, descrizione: f.tipo === "leasing" ? "Canone" : "Rata" }])} className="inline-flex items-center gap-1 font-semibold text-blue-600" data-testid="fin-add-rata"><Plus className="h-3.5 w-3.5" />Aggiungi rata</button>
        <span>{rate.length} rate · capitale {fmtEUR(rate.reduce((s, r) => s + num(r.capitale), 0))} · totale <b data-testid="fin-totale">{fmtEUR(rate.reduce((s, r) => s + tot(r), 0))}</b></span>
      </div>
    </div>
  );
};

export const FinDialog = ({ piano, onClose, onSaved }) => {
  const coge = mods(useCompany().company).contabilita;
  const [conti] = useConti(!!piano && coge);
  const [fornitori, setFornitori] = useState([]);
  const [f, setF] = useState(null);
  const [saving, setSaving] = useState(false);
  const { fail, reset, value } = useFieldErrors();
  useEffect(() => { if (piano) { setF(piano); reset(); api.get("/parties", { params: { tipo: "fornitore" } }).then(({ data }) => setFornitori(data)).catch(() => {}); } }, [piano, reset]);
  if (!piano || !f) return null;
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    setSaving(true);
    try {
      const body = { ...f, importo: num(f.importo), tasso: num(f.tasso), aliquota_iva: num(f.aliquota_iva), party_id: f.party_id || null,
        rate: f.rate.map((r) => ({ scadenza: r.scadenza, capitale: num(r.capitale), interessi: num(r.interessi), descrizione: r.descrizione || "" })) };
      await (f.id ? api.put(`/finanziamenti/${f.id}`, body) : api.post("/finanziamenti", body));
      toast.success(f.id ? "Piano aggiornato" : "Piano salvato");
      onSaved();
      onClose();
    } catch (e) { fail(e); } finally { setSaving(false); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[92vh] overflow-y-auto overflow-x-hidden bg-white sm:max-w-4xl [&>*]:min-w-0" data-testid="fin-dialog">
        <FieldErrors value={value}>
          <DialogHeader><DialogTitle>{f.id ? "Modifica piano" : f.pdf_id ? "Controlla il piano letto dal PDF" : "Nuovo finanziamento o leasing"}</DialogTitle></DialogHeader>
          {f.pdf_id && !f.id && <p className="rounded-lg bg-blue-50 p-3 text-xs text-blue-900" data-testid="fin-ia-note">Dati letti con l'intelligenza artificiale: verifica date e importi con il contratto prima di salvare.</p>}
          <div className="flex gap-2" data-testid="fin-tipo">
            {[["finanziamento", "Finanziamento / mutuo"], ["leasing", "Leasing"]].map(([v, l]) => <button key={v} type="button" onClick={() => setF({ ...f, tipo: v })} data-testid={`fin-tipo-${v}`} className={`rounded-full border px-4 py-1.5 text-sm font-semibold transition-colors ${f.tipo === v ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 text-slate-600"}`}>{l}</button>)}
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Field label={f.tipo === "leasing" ? "Società di leasing" : "Banca / ente"} name="ente"><Input value={f.ente} onChange={set("ente")} data-testid="fin-ente" /></Field>
            <Field label="Numero contratto" name="numero"><Input value={f.numero || ""} onChange={set("numero")} data-testid="fin-numero" /></Field>
            <Field label="Data contratto" name="data"><Input type="date" value={f.data} onChange={set("data")} data-testid="fin-data" /></Field>
            <Field label="Descrizione" name="descrizione" className="sm:col-span-3"><Input value={f.descrizione || ""} onChange={set("descrizione")} data-testid="fin-descrizione" /></Field>
            <Field label={f.tipo === "leasing" ? "Valore del bene" : "Capitale finanziato"} name="importo"><Input type="number" step="0.01" min={0} value={f.importo} onChange={set("importo")} data-testid="fin-importo" /></Field>
            <Field label="Tasso annuo %" name="tasso"><Input type="number" step="0.001" min={0} value={f.tasso} onChange={set("tasso")} data-testid="fin-tasso" /></Field>
            {f.tipo === "leasing" && <Field label="IVA sui canoni %" name="aliquota_iva"><Input type="number" step="1" min={0} value={f.aliquota_iva} onChange={set("aliquota_iva")} data-testid="fin-iva" /></Field>}
            {f.tipo === "leasing" && <Field label="Fornitore (per collegare le fatture)" name="party_id" className="sm:col-span-3">
              <NSelect value={f.party_id || ""} onChange={set("party_id")} className="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm" data-testid="fin-party">
                <option value="">— tutti i fornitori —</option>{fornitori.map((p) => <option key={p.id} value={p.id}>{p.denominazione}</option>)}
              </NSelect></Field>}
          </div>
          {coge && <div className="grid grid-cols-1 gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3 sm:grid-cols-2" data-testid="fin-conti">
            {CONTI[f.tipo].map(([k, l]) => <Field key={k} label={l} name={k}><ContoSelect conti={conti} value={f[k]} onChange={(v) => setF({ ...f, [k]: v })} testId={`fin-${k.replace("_", "-")}`} /></Field>)}
          </div>}
          <CalcoloPiano f={f} onRate={(rate) => setF({ ...f, rate })} />
          <Field name="rate"><RateFin f={f} setRate={(rate) => setF({ ...f, rate })} /></Field>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={onClose} data-testid="fin-cancel">Annulla</Button>
            <Button onClick={save} disabled={saving || !f.rate.length} data-testid="fin-save">{saving ? "Salvataggio…" : "Salva piano"}</Button>
          </DialogFooter>
        </FieldErrors>
      </DialogContent>
    </Dialog>
  );
};

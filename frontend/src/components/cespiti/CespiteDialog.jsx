import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { NSelect } from "@/components/ui/nselect";
import { Field, FieldErrors, useFieldErrors } from "@/components/Common";
import { ContoSelect, useConti } from "@/components/ContoSelect";
import { api } from "@/lib/api";
import { mods } from "@/lib/moduli";
import { useCompany } from "@/context/CompanyContext";

const CONTI = [["conto_cespite", "Conto del cespite"], ["conto_fondo", "Fondo ammortamento"], ["conto_ammortamento", "Conto ammortamento (costo)"]];

export const CespiteDialog = ({ val, categorie, onClose, onSaved }) => {
  const coge = mods(useCompany().company).contabilita;
  const [conti] = useConti(!!val && coge);
  const [f, setF] = useState(null);
  const [saving, setSaving] = useState(false);
  const { fail, reset, value } = useFieldErrors();
  useEffect(() => { if (val) { setF(val); reset(); } }, [val, reset]);
  if (!val || !f) return null;
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const cat = (id) => {
    const c = categorie.find((x) => x.id === id);
    setF({ ...f, categoria: id, aliquota: c.aliquota, conto_cespite: c.conto_cespite, conto_fondo: c.conto_fondo, conto_ammortamento: c.conto_ammortamento });
  };
  const save = async () => {
    setSaving(true);
    try {
      const body = { ...f, costo: Number(f.costo), aliquota: Number(f.aliquota), fondo_iniziale: Number(f.fondo_iniziale || 0), data_entrata_funzione: f.data_entrata_funzione || null };
      await (f.id ? api.put(`/cespiti/${f.id}`, body) : api.post("/cespiti", body));
      toast.success(f.id ? "Cespite aggiornato" : "Cespite creato");
      onSaved();
      onClose();
    } catch (e) { fail(e); } finally { setSaving(false); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[92vh] overflow-y-auto bg-white sm:max-w-2xl [&>*]:min-w-0" data-testid="cespite-dialog">
        <FieldErrors value={value}>
          <DialogHeader><DialogTitle>{f.id ? "Modifica cespite" : f.passive_id ? "Crea il cespite dalla fattura" : "Nuovo cespite"}</DialogTitle></DialogHeader>
          {f.passive_id && !f.id && <p className="rounded-lg bg-blue-50 p-3 text-xs text-blue-900" data-testid="cespite-da-fattura">Dalla fattura {f.numero_display} di {f.fornitore}: controlla categoria e aliquota prima di confermare.</p>}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Descrizione" name="descrizione" className="sm:col-span-2"><Input value={f.descrizione} onChange={set("descrizione")} data-testid="cespite-descrizione" /></Field>
            <Field label="Categoria (coefficienti DM 31/12/1988)" name="categoria" className="sm:col-span-2">
              <NSelect value={f.categoria} onChange={(e) => cat(e.target.value)} className="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm" data-testid="cespite-categoria">
                {categorie.map((c) => <option key={c.id} value={c.id}>{c.nome} — {c.aliquota}%</option>)}
              </NSelect></Field>
            <Field label="Costo storico" name="costo"><Input type="number" step="0.01" min={0} value={f.costo} onChange={set("costo")} data-testid="cespite-costo" /></Field>
            <Field label="Aliquota di ammortamento %" name="aliquota"><Input type="number" step="0.01" min={0} max={100} value={f.aliquota} onChange={set("aliquota")} data-testid="cespite-aliquota" /></Field>
            <Field label="Data di acquisto" name="data_acquisto"><Input type="date" value={f.data_acquisto} onChange={set("data_acquisto")} data-testid="cespite-data" /></Field>
            <Field label="Entrata in funzione (se diversa)" name="data_entrata_funzione"><Input type="date" value={f.data_entrata_funzione || ""} onChange={set("data_entrata_funzione")} data-testid="cespite-funzione" /></Field>
            <Field label="Fondo già ammortizzato al 31/12 dell'anno scorso" name="fondo_iniziale"><Input type="number" step="0.01" min={0} value={f.fondo_iniziale || 0} onChange={set("fondo_iniziale")} data-testid="cespite-fondo-iniziale" /></Field>
            <Field label="Fornitore" name="fornitore"><Input value={f.fornitore || ""} onChange={set("fornitore")} data-testid="cespite-fornitore" /></Field>
          </div>
          {coge && <div className="grid grid-cols-1 gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3 sm:grid-cols-3" data-testid="cespite-conti">
            {CONTI.map(([k, l]) => <Field key={k} label={l} name={k}><ContoSelect conti={conti} value={f[k]} onChange={(v) => setF({ ...f, [k]: v })} testId={`cespite-${k.replaceAll("_", "-")}`} /></Field>)}
          </div>}
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={onClose} data-testid="cespite-cancel">Annulla</Button>
            <Button onClick={save} disabled={saving} data-testid="cespite-save">{saving ? "Salvataggio…" : "Salva cespite"}</Button>
          </DialogFooter>
        </FieldErrors>
      </DialogContent>
    </Dialog>
  );
};

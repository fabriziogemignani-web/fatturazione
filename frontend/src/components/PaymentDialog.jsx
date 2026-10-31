import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { fmtEUR, today, METODI_INCASSO } from "@/lib/fe";
import { Field, FieldErrors, useFieldErrors } from "@/components/Common";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const TONE = { pagata: "bg-emerald-100 text-emerald-800", parziale: "bg-amber-100 text-amber-800", aperta: "bg-slate-100 text-slate-700", scaduta: "bg-rose-100 text-rose-800" };
const LABEL = { pagata: "Pagata", parziale: "Parziale", aperta: "Da incassare", scaduta: "Scaduta" };

export const RataBadge = ({ r, testId }) => {
  const k = r.scaduta ? "scaduta" : r.stato;
  return <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${TONE[k]}`} data-testid={testId}>{LABEL[k]}{r.scaduta && r.stato === "parziale" ? " (parz.)" : ""}{r.giorni_ritardo ? ` · ${r.giorni_ritardo} gg` : ""}</span>;
};

export const PaymentDialog = ({ open, onOpenChange, doc, crediti = [], importo, compensa, onDone, kind = "invoices" }) => {
  const [f, setF] = useState({});
  const [busy, setBusy] = useState(false);
  const { fail, reset, value } = useFieldErrors();
  const credits = crediti.filter((c) => c.party_id === doc?.party_id);

  useEffect(() => {
    if (!open || !doc) return;
    reset();
    const nc = compensa ? credits[0] : null;
    const max = nc ? Math.min(nc.residuo, importo ?? doc.residuo) : (importo ?? doc.residuo);
    setF({ data: today(), importo: max, metodo: nc ? "compensazione" : "bonifico", nc_id: nc?.id || null, note: "" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, doc, compensa, importo, reset]);

  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const save = async () => {
    setBusy(true);
    reset();
    try {
      await api.post(`/${kind}/${doc.id}/pagamenti`, { ...f, importo: Number(f.importo), nc_id: f.metodo === "compensazione" ? f.nc_id : null });
      toast.success(f.metodo === "compensazione" ? "Compensazione registrata" : kind === "passive" ? "Pagamento registrato" : "Incasso registrato");
      onOpenChange(false);
      onDone?.();
    } catch (e) { fail(e); } finally { setBusy(false); }
  };

  if (!doc) return null;
  const metodi = METODI_INCASSO.filter(([k]) => k !== "compensazione" || credits.length);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white sm:max-w-lg" data-testid="payment-dialog">
        <DialogHeader><DialogTitle>{f.metodo === "compensazione" ? "Compensa con nota di credito" : kind === "passive" ? "Registra pagamento al fornitore" : "Registra incasso"}</DialogTitle></DialogHeader>
        <p className="text-sm text-slate-600">Fattura <b>{doc.numero_display}</b> · {doc.cliente} · residuo <b data-testid="payment-residuo">{fmtEUR(doc.residuo)}</b></p>
        <FieldErrors value={value}>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Data" name="data"><Input type="date" value={f.data || ""} onChange={(e) => set("data", e.target.value)} data-testid="payment-date-input" /></Field>
            <Field label="Importo (€)" name="importo"><Input type="number" step="0.01" min="0" value={f.importo ?? ""} onChange={(e) => set("importo", e.target.value)} data-testid="payment-amount-input" /></Field>
            <Field label="Metodo" name="metodo" className="sm:col-span-2">
              <Select value={f.metodo || "bonifico"} onValueChange={(v) => setF((x) => ({ ...x, metodo: v, nc_id: v === "compensazione" ? x.nc_id || credits[0]?.id : null }))}>
                <SelectTrigger data-testid="payment-method-select"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-white">{metodi.map(([k, l]) => <SelectItem key={k} value={k} data-testid={`payment-method-${k}`}>{l}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            {f.metodo === "compensazione" && (
              <Field label="Nota di credito" name="nc_id" className="sm:col-span-2">
                <Select value={f.nc_id || ""} onValueChange={(v) => set("nc_id", v)}>
                  <SelectTrigger data-testid="payment-nc-select"><SelectValue placeholder="Seleziona nota di credito" /></SelectTrigger>
                  <SelectContent className="bg-white">{credits.map((c) => <SelectItem key={c.id} value={c.id} data-testid={`payment-nc-${c.id}`}>{c.numero_display} · credito {fmtEUR(c.residuo)}</SelectItem>)}</SelectContent>
                </Select>
              </Field>
            )}
            <Field label="Note" name="note" className="sm:col-span-2"><Input maxLength={200} value={f.note || ""} onChange={(e) => set("note", e.target.value)} data-testid="payment-note-input" /></Field>
          </div>
        </FieldErrors>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="payment-cancel-btn">Annulla</Button>
          <Button onClick={save} disabled={busy} data-testid="payment-save-btn">Registra</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

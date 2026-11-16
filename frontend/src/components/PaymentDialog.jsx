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

export const RataBadge = ({ r, testId, passive = false }) => {
  const k = r.scadenza && r.scaduta ? "scaduta" : r.stato;
  const label = k === "aperta" && passive ? "Da pagare" : LABEL[k];
  return <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${TONE[k]}`} data-testid={testId}>{label}{r.scaduta && r.stato === "parziale" ? " (parz.)" : ""}{r.giorni_ritardo ? ` · ${r.giorni_ritardo} gg` : ""}</span>;
};

const TIPO = { banca: "Banca", carta: "Carta", cassa: "Cassa" };

const ContoField = ({ conti, value, onChange }) => (
  <Field label="Conto di pagamento (prima nota)" name="conto" className="sm:col-span-2">
    <Select value={value || ""} onValueChange={onChange}>
      <SelectTrigger data-testid="payment-conto-select"><SelectValue placeholder="Seleziona banca, carta o cassa" /></SelectTrigger>
      <SelectContent className="bg-white">{conti.map((c) => <SelectItem key={c.conto} value={c.conto} data-testid={`payment-conto-${c.conto}`}>{TIPO[c.tipo]} · {c.label} ({c.conto})</SelectItem>)}</SelectContent>
    </Select>
    <p className="mt-1 text-xs text-slate-500">Il movimento viene registrato in prima nota su questo conto. Le carte si gestiscono nel piano dei conti (06.03).</p>
  </Field>
);

export const PaymentDialog = ({ open, onOpenChange, doc, crediti = [], importo, compensa, onDone, kind = "invoices" }) => {
  const [f, setF] = useState({});
  const [busy, setBusy] = useState(false);
  const [cp, setCp] = useState({ conti: [], default: {} });
  const { fail, reset, value } = useFieldErrors();
  const credits = crediti.filter((c) => c.party_id === doc?.party_id);

  useEffect(() => {
    if (!open || !doc) return;
    reset();
    const nc = compensa ? credits[0] : null;
    const max = nc ? Math.min(nc.residuo, importo ?? doc.residuo) : (importo ?? doc.residuo);
    setF({ data: today(), importo: max, metodo: nc ? "compensazione" : "bonifico", nc_id: nc?.id || null, note: "", ritenuta_subita: 0, conRit: false, conto: null });
    api.get("/contabilita/conti-pagamento").then(({ data }) => { setCp(data); setF((x) => ({ ...x, conto: x.conto || data.default?.[x.metodo] || null })); }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, doc, compensa, importo, reset]);

  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const save = async () => {
    setBusy(true);
    reset();
    try {
      const { conRit, ...rest } = f;
      await api.post(`/${kind}/${doc.id}/pagamenti`, { ...rest, importo: Number(f.importo), ritenuta_subita: conRit ? Number(f.ritenuta_subita || 0) : 0, nc_id: f.metodo === "compensazione" ? f.nc_id : null, conto: f.metodo === "compensazione" ? null : f.conto });
      toast.success(f.metodo === "compensazione" ? "Compensazione registrata" : kind === "passive" ? "Pagamento registrato" : "Incasso registrato");
      onOpenChange(false);
      onDone?.();
    } catch (e) { fail(e); } finally { setBusy(false); }
  };

  const ritenuta = async (on) => {
    if (!on) return setF((x) => ({ ...x, conRit: false, ritenuta_subita: 0, importo: importo ?? doc.residuo }));
    setF((x) => ({ ...x, conRit: true }));
    try {
      const { data } = await api.get(`/invoices/${doc.id}`);
      const r = Math.round((data.imponibile || 0) * 4) / 100;
      setF((x) => ({ ...x, conRit: true, ritenuta_subita: r, importo: Math.round(((importo ?? doc.residuo) - r) * 100) / 100 }));
    } catch { setF((x) => ({ ...x, conRit: true })); }
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
              <Select value={f.metodo || "bonifico"} onValueChange={(v) => setF((x) => ({ ...x, metodo: v, conto: cp.default?.[v] || x.conto, nc_id: v === "compensazione" ? x.nc_id || credits[0]?.id : null }))}>
                <SelectTrigger data-testid="payment-method-select"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-white">{metodi.map(([k, l]) => <SelectItem key={k} value={k} data-testid={`payment-method-${k}`}>{l}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            {f.metodo !== "compensazione" && cp.conti.length > 0 && <ContoField conti={cp.conti} value={f.conto} onChange={(v) => set("conto", v)} />}
            {f.metodo === "compensazione" && (
              <Field label="Nota di credito" name="nc_id" className="sm:col-span-2">
                <Select value={f.nc_id || ""} onValueChange={(v) => set("nc_id", v)}>
                  <SelectTrigger data-testid="payment-nc-select"><SelectValue placeholder="Seleziona nota di credito" /></SelectTrigger>
                  <SelectContent className="bg-white">{credits.map((c) => <SelectItem key={c.id} value={c.id} data-testid={`payment-nc-${c.id}`}>{c.numero_display} · credito {fmtEUR(c.residuo)}</SelectItem>)}</SelectContent>
                </Select>
              </Field>
            )}
            {kind === "invoices" && f.metodo !== "compensazione" && (
              <div className="rounded-lg border border-amber-200 bg-amber-50/50 p-3 sm:col-span-2" data-testid="payment-ritenuta-box">
                <label className="flex items-center justify-between gap-3 text-sm text-slate-700">Il cliente (condominio) ha trattenuto la ritenuta del 4%
                  <input type="checkbox" checked={!!f.conRit} onChange={(e) => ritenuta(e.target.checked)} data-testid="payment-ritenuta-check" /></label>
                {f.conRit && <div className="mt-2 flex items-center gap-2 text-xs text-slate-600">Ritenuta subita €<Input type="number" step="0.01" min="0" value={f.ritenuta_subita} onChange={(e) => set("ritenuta_subita", e.target.value)} className="w-32 bg-white" data-testid="payment-ritenuta-input" />chiude la fattura insieme all'incasso</div>}
              </div>
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

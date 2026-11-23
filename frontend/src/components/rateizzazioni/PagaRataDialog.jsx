import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { NSelect } from "@/components/ui/nselect";
import { Field, FieldErrors, useFieldErrors } from "@/components/Common";
import { api } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";

const oggi = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };

export const PagaRataDialog = ({ req, conti, onClose, onDone }) => {
  const [data, setData] = useState(oggi());
  const [conto, setConto] = useState("");
  const [saving, setSaving] = useState(false);
  const { fail, reset, value } = useFieldErrors();
  const opts = conti?.conti || [];
  useEffect(() => { if (req) { setData(oggi()); setConto(conti?.default?.bonifico || opts[0]?.conto || ""); reset(); } }, [req]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!req) return null;
  const { piano, rata } = req;
  const save = async () => {
    setSaving(true);
    try {
      await api.post(`/rateizzazioni/${piano.id}/rate/${rata.n}/paga`, { data, conto });
      toast.success(conti ? "Rata pagata e registrata in prima nota" : "Rata segnata come pagata");
      onDone();
      onClose();
    } catch (e) { fail(e); } finally { setSaving(false); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-white sm:max-w-md" data-testid="paga-rata-dialog">
        <FieldErrors value={value}>
          <DialogHeader><DialogTitle>Paga rata {rata.n}/{piano.rate.length}</DialogTitle></DialogHeader>
          <p className="text-sm text-slate-600">{piano.ente} {piano.numero} · scadenza {fmtDate(rata.scadenza)} · <b>{fmtEUR(rata.totale)}</b></p>
          <p className="text-xs text-slate-500">Imposta {fmtEUR(rata.capitale)} · sanzioni {fmtEUR(rata.sanzioni)} · interessi e oneri {fmtEUR(rata.interessi)}</p>
          <Field label="Data del pagamento" name="data"><Input type="date" value={data} onChange={(e) => setData(e.target.value)} data-testid="paga-rata-data" /></Field>
          {conti && (
            <Field label="Pagata da (banca o cassa)" name="conto">
              <NSelect value={conto} onChange={(e) => setConto(e.target.value)} className="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm" data-testid="paga-rata-conto">
                {opts.map((o) => <option key={o.conto} value={o.conto}>{o.label} ({o.conto})</option>)}
              </NSelect>
            </Field>
          )}
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={onClose} data-testid="paga-rata-cancel">Annulla</Button>
            <Button onClick={save} disabled={saving} data-testid="paga-rata-save">{saving ? "Registrazione…" : "Registra pagamento"}</Button>
          </DialogFooter>
        </FieldErrors>
      </DialogContent>
    </Dialog>
  );
};

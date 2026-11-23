import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { NSelect } from "@/components/ui/nselect";
import { Field, FieldErrors, useFieldErrors } from "@/components/Common";
import { api } from "@/lib/api";

const oggi = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };

export const PagaRataDialog = ({ req, conti, onClose, onDone }) => {
  const [data, setData] = useState(oggi());
  const [conto, setConto] = useState("");
  const [saving, setSaving] = useState(false);
  const { fail, reset, value } = useFieldErrors();
  const opts = conti?.conti || [];
  useEffect(() => { if (req) { setData(req.data || oggi()); setConto(conti?.default?.bonifico || opts[0]?.conto || ""); reset(); } }, [req]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!req) return null;
  const save = async () => {
    setSaving(true);
    try {
      await api.post(req.url, { data, conto });
      toast.success(conti ? "Movimento registrato in prima nota" : "Rata segnata come pagata");
      onDone();
      onClose();
    } catch (e) { fail(e); } finally { setSaving(false); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-white sm:max-w-md" data-testid="paga-rata-dialog">
        <FieldErrors value={value}>
          <DialogHeader><DialogTitle>{req.titolo}</DialogTitle></DialogHeader>
          <p className="text-sm text-slate-600">{req.info}</p>
          {req.dettaglio && <p className="text-xs text-slate-500">{req.dettaglio}</p>}
          <Field label="Data del movimento" name="data"><Input type="date" value={data} onChange={(e) => setData(e.target.value)} data-testid="paga-rata-data" /></Field>
          {conti && (
            <Field label={req.labelConto || "Pagata da (banca o cassa)"} name="conto">
              <NSelect value={conto} onChange={(e) => setConto(e.target.value)} className="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm" data-testid="paga-rata-conto">
                {opts.map((o) => <option key={o.conto} value={o.conto}>{o.label} ({o.conto})</option>)}
              </NSelect>
            </Field>
          )}
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={onClose} data-testid="paga-rata-cancel">Annulla</Button>
            <Button onClick={save} disabled={saving} data-testid="paga-rata-save">{saving ? "Registrazione…" : "Registra"}</Button>
          </DialogFooter>
        </FieldErrors>
      </DialogContent>
    </Dialog>
  );
};

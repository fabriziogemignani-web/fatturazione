import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";

export const CollegaFatturaDialog = ({ req, onClose, onDone }) => {
  const [list, setList] = useState(null);
  useEffect(() => { if (req) { setList(null); api.get(`/finanziamenti/${req.piano.id}/fatture`).then(({ data }) => setList(data)).catch((e) => toast.error(errMsg(e))); } }, [req]);
  if (!req) return null;
  const { piano, rata } = req;
  const pick = async (inv) => {
    try {
      await api.post(`/finanziamenti/${piano.id}/rate/${rata.n}/collega`, { invoice_id: inv.id });
      toast.success(`Fattura ${inv.numero_display} collegata alla rata ${rata.n}`);
      onDone();
      onClose();
    } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[85vh] overflow-y-auto bg-white sm:max-w-2xl" data-testid="collega-fattura-dialog">
        <DialogHeader><DialogTitle>Collega la fattura del canone {rata.n}/{piano.rate.length}</DialogTitle></DialogHeader>
        <p className="text-sm text-slate-600">Scadenza {fmtDate(rata.scadenza)} · canone {fmtEUR(rata.totale)}. Costo e IVA arrivano dalla fattura passiva; la rata risulta pagata quando paghi la fattura.</p>
        {!list ? <p className="text-sm text-slate-500">Caricamento…</p> : list.length === 0 ? <p className="text-sm text-slate-500" data-testid="collega-empty">Nessuna fattura passiva disponibile{piano.party_id ? " per questo fornitore" : ""}.</p> : (
          <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
            {list.map((i) => (
              <li key={i.id} className={`flex items-center justify-between gap-3 px-3 py-2 text-sm ${Math.abs(i.netto - rata.totale) < 0.01 ? "bg-emerald-50" : ""}`} data-testid={`collega-inv-${i.id}`}>
                <span className="min-w-0 truncate"><b>{i.numero_display}</b> del {fmtDate(i.data)} · {i.fornitore}</span>
                <span className="flex items-center gap-3 whitespace-nowrap"><span>{fmtEUR(i.netto)}{i.residuo > 0.005 ? <span className="ml-1 text-xs text-rose-600">da pagare {fmtEUR(i.residuo)}</span> : <span className="ml-1 text-xs text-emerald-700">pagata</span>}</span>
                  <Button size="sm" onClick={() => pick(i)} data-testid={`collega-pick-${i.id}`}>Collega</Button></span>
              </li>
            ))}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  );
};

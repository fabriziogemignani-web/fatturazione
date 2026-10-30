import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Send, FileDown } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDateTime } from "@/lib/fe";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

export const downloadEstratto = async (partyId, name) => {
  try {
    const { data } = await api.get(`/clienti/${partyId}/estratto-conto.pdf`, { responseType: "blob" });
    const url = URL.createObjectURL(new Blob([data], { type: "application/pdf" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `Estratto_conto_${(name || "cliente").replace(/[^A-Za-z0-9]+/g, "_")}.pdf`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  } catch (e) { toast.error(errMsg(e)); }
};

export const SollecitoDialog = ({ open, onOpenChange, partyId, cliente }) => {
  const [p, setP] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!open || !partyId) return;
    setP(null);
    api.get(`/clienti/${partyId}/sollecito`).then(({ data }) => setP(data)).catch((e) => toast.error(errMsg(e)));
  }, [open, partyId]);

  const send = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/clienti/${partyId}/sollecito`);
      toast.success(`Sollecito inviato a ${data.to}`);
      onOpenChange(false);
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] overflow-y-auto bg-white sm:max-w-2xl" data-testid="sollecito-dialog">
        <DialogHeader><DialogTitle>Sollecito di pagamento · {cliente}</DialogTitle></DialogHeader>
        {!p ? <p className="text-sm text-slate-500">Caricamento anteprima…</p> : (
          <div className="space-y-3">
            <div className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-3">
              <div><div className="text-xs text-slate-500">Destinatario</div><div className={`font-semibold ${p.to ? "" : "text-rose-600"}`} data-testid="sollecito-to">{p.to || "Nessuna email/PEC in anagrafica"}</div></div>
              <div><div className="text-xs text-slate-500">Rate scadute</div><div className="font-semibold" data-testid="sollecito-rate">{p.rate}</div></div>
              <div><div className="text-xs text-slate-500">Totale scaduto</div><div className="font-bold text-rose-700" data-testid="sollecito-scaduto">{fmtEUR(p.scaduto)}</div></div>
            </div>
            <p className="text-xs text-slate-500">Oggetto: <b>{p.subject}</b> · Allegato: estratto conto PDF</p>
            <iframe title="Anteprima sollecito" srcDoc={p.html} sandbox="" className="h-80 w-full rounded-lg border border-slate-200" data-testid="sollecito-preview" />
            {p.storico.length > 0 && (
              <div className="text-xs text-slate-500" data-testid="sollecito-storico">
                Solleciti precedenti: {p.storico.map((s) => `${fmtDateTime(s.created_at)} (${fmtEUR(s.importo_scaduto)})`).join(" · ")}
              </div>
            )}
          </div>
        )}
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => downloadEstratto(partyId, cliente)} data-testid="sollecito-pdf-btn"><FileDown className="mr-2 h-4 w-4" />Estratto conto PDF</Button>
          <Button onClick={send} disabled={busy || !p || !p.to || !p.rate} data-testid="sollecito-send-btn"><Send className="mr-2 h-4 w-4" />{busy ? "Invio…" : "Invia sollecito"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

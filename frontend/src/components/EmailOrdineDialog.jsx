import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2, Printer, Mail } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtDateTime } from "@/lib/fe";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";

export const apriOrdinePdf = async (tipo, o, conferma) => {
  const w = window.open("", "_blank");
  try {
    const { data } = await api.get(`/ordini/${tipo}/${o.id}/pdf`, { params: { conferma }, responseType: "blob" });
    const url = URL.createObjectURL(new Blob([data], { type: "application/pdf" }));
    if (w) w.location.href = url; else { const a = document.createElement("a"); a.href = url; a.download = `Ordine_${o.numero}.pdf`; a.click(); }
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch (e) { if (w) w.close(); toast.error(errMsg(e)); }
};

export const EmailOrdineDialog = ({ tipo, o, onClose, onSent }) => {
  const [conferma, setConferma] = useState(tipo === "cliente");
  const [f, setF] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.get(`/ordini/${tipo}/${o.id}/email`, { params: { conferma } }).then(({ data }) => setF(data)).catch((e) => toast.error(errMsg(e))); }, [conferma]); // eslint-disable-line react-hooks/exhaustive-deps
  const send = async () => {
    setBusy(true);
    try { await api.post(`/ordini/${tipo}/${o.id}/email`, { to: f.to, oggetto: f.oggetto, messaggio: f.messaggio, conferma }); toast.success(`Email inviata a ${f.to}`); onSent(); onClose(); } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="bg-white sm:max-w-2xl" data-testid="ord-email-dialog">
        <DialogHeader><DialogTitle>Invia {tipo === "cliente" ? (conferma ? "conferma d'ordine" : "ordine") : "ordine al fornitore"} {o.numero_display}</DialogTitle></DialogHeader>
        {tipo === "cliente" && (
          <div className="flex gap-2 text-xs">{[[true, "Conferma d'ordine"], [false, "Ordine"]].map(([k, l]) => <button key={l} onClick={() => setConferma(k)} className={`rounded-full border px-3 py-1.5 font-semibold ${conferma === k ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 text-slate-600"}`} data-testid={`ord-email-tipo-${k ? "conferma" : "ordine"}`}>{l}</button>)}</div>
        )}
        {!f ? <p className="text-sm text-slate-500">Caricamento…</p> : (
          <div className="space-y-3">
            <label className="block text-xs text-slate-600">Destinatario<Input value={f.to} onChange={(e) => setF({ ...f, to: e.target.value })} placeholder="email del cliente o fornitore" data-testid="ord-email-to" /></label>
            <label className="block text-xs text-slate-600">Oggetto<Input value={f.oggetto} onChange={(e) => setF({ ...f, oggetto: e.target.value })} data-testid="ord-email-oggetto" /></label>
            <label className="block text-xs text-slate-600">Messaggio<Textarea rows={8} value={f.messaggio} onChange={(e) => setF({ ...f, messaggio: e.target.value })} data-testid="ord-email-messaggio" /></label>
            <div className="flex items-center gap-2 text-xs text-slate-500">Allegato: PDF dell'{conferma && tipo === "cliente" ? "conferma d'ordine" : "ordine"}
              <button className="inline-flex items-center gap-1 font-semibold text-blue-700 hover:underline" onClick={() => apriOrdinePdf(tipo, o, conferma)} data-testid="ord-email-anteprima"><Printer className="h-3.5 w-3.5" />anteprima</button></div>
            {f.inviate?.length > 0 && <div className="text-xs text-slate-500" data-testid="ord-email-storico">Già inviato: {f.inviate.map((x) => `${x.to} il ${fmtDateTime(x.at)}`).join(" · ")}</div>}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Annulla</Button>
          <Button onClick={send} disabled={busy || !f?.to} data-testid="ord-email-send">{busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Mail className="mr-2 h-4 w-4" />}Invia email</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

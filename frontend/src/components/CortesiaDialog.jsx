import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Mail } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

export const CortesiaDialog = ({ inv, open, onOpenChange, onSent }) => {
  const [to, setTo] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!open || !inv) return;
    setTo(inv.cliente?.email || inv.cliente?.pec || "");
    api.get("/parties").then(({ data }) => { const p = data.find((x) => x.id === inv.party_id); if (p?.email || p?.pec) setTo(p.email || p.pec); }).catch(() => {});
  }, [open, inv]);
  const send = async () => {
    setBusy(true);
    try {
      await api.post(`/comunicazioni/cortesia/${inv.id}`, { to: to.trim() || null });
      toast.success(`Fattura di cortesia inviata a ${to.trim() || "cliente"}`);
      onOpenChange(false); onSent?.();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="cortesia-dialog">
        <DialogHeader>
          <DialogTitle>Invia fattura di cortesia</DialogTitle>
          <DialogDescription>Fattura {inv?.numero_display} · {inv?.cliente?.denominazione}. Il PDF parte allegato con il testo impostato in Comunicazioni, dal server di posta dell'azienda.</DialogDescription>
        </DialogHeader>
        <label className="text-sm font-medium text-slate-700">Destinatario</label>
        <Input type="email" value={to} onChange={(e) => setTo(e.target.value)} placeholder="email del cliente" data-testid="cortesia-to-input" />
        <p className="text-xs text-slate-500">Proposto dall'anagrafica del cliente: puoi cambiarlo solo per questo invio.</p>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="cortesia-cancel-btn">Annulla</Button>
          <Button onClick={send} disabled={busy || !to.trim()} data-testid="cortesia-send-btn"><Mail className="mr-2 h-4 w-4" />{busy ? "Invio…" : "Invia"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export const CortesiaMassivaDialog = ({ ids, open, onOpenChange, onDone }) => {
  const [escludi, setEscludi] = useState(true);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [prog, setProg] = useState(0);
  useEffect(() => { if (open) { setRes(null); setEscludi(true); setProg(0); } }, [open]);
  const run = async () => {
    setBusy(true);
    const tot = { inviate: 0, saltate: [], errori: [] };
    try {
      for (let i = 0; i < ids.length; i += 20) {
        const { data } = await api.post("/comunicazioni/cortesia-massiva", { ids: ids.slice(i, i + 20), escludi_inviate: escludi });
        tot.inviate += data.inviate; tot.saltate.push(...data.saltate); tot.errori.push(...data.errori);
        setProg(Math.min(i + 20, ids.length));
      }
    } catch (e) { toast.error(errMsg(e)); }
    setRes(tot); onDone?.(); setBusy(false);
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !busy && onOpenChange(o)}>
      <DialogContent className="max-w-lg" data-testid="cortesia-massiva-dialog">
        <DialogHeader>
          <DialogTitle>Invio massivo fatture di cortesia</DialogTitle>
          <DialogDescription>{ids.length} fatture selezionate. Ognuna parte all'email o PEC del cliente in anagrafica.</DialogDescription>
        </DialogHeader>
        {!res && (
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" checked={escludi} onChange={(e) => setEscludi(e.target.checked)} className="h-4 w-4" data-testid="cortesia-escludi-checkbox" />
            Salta le fatture a cui la cortesia è già stata inviata
          </label>
        )}
        {res && (
          <div className="space-y-2 text-sm" data-testid="cortesia-massiva-esito">
            <div className="rounded-lg bg-emerald-50 p-3 font-semibold text-emerald-800" data-testid="cortesia-massiva-inviate">Inviate: {res.inviate}</div>
            {res.saltate.length > 0 && <div className="rounded-lg bg-slate-50 p-3 text-slate-700" data-testid="cortesia-massiva-saltate">Saltate {res.saltate.length}: {res.saltate.map((s) => `${s.numero} (${s.motivo})`).join(", ")}</div>}
            {res.errori.length > 0 && (
              <div className="max-h-48 overflow-auto rounded-lg bg-rose-50 p-3 text-rose-800" data-testid="cortesia-massiva-errori">
                <div className="mb-1 font-semibold">Non inviate {res.errori.length}:</div>
                {res.errori.map((e) => <div key={e.numero}>{e.numero} · {e.cliente}: {e.errore}</div>)}
              </div>
            )}
          </div>
        )}
        <DialogFooter>
          {res ? <Button onClick={() => onOpenChange(false)} data-testid="cortesia-massiva-close-btn">Chiudi</Button> : <>
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy} data-testid="cortesia-massiva-cancel-btn">Annulla</Button>
            <Button onClick={run} disabled={busy} data-testid="cortesia-massiva-send-btn"><Mail className="mr-2 h-4 w-4" />{busy ? `Invio in corso… ${prog}/${ids.length}` : `Invia ${ids.length} fatture`}</Button>
          </>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

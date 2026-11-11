import { useState } from "react";
import { toast } from "sonner";
import { PenLine, Link2, Copy, X } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useAuth, canSend } from "@/context/AuthContext";
import { fmtDateTime } from "@/lib/fe";
import { Button } from "@/components/ui/button";
import { FirmaDialog, RUOLI_FIRMA } from "@/components/SignaturePad";

export const FirmeDdt = ({ d, onChanged }) => {
  const { user } = useAuth();
  const [ruolo, setRuolo] = useState(null);
  const [link, setLink] = useState(null);
  const firme = d.firme || {};
  const save = async (body) => {
    try { await api.post(`/ddt/${d.id}/firme`, body); toast.success("Firma salvata nel DDT"); onChanged(); return true; } catch (e) { toast.error(errMsg(e)); return false; }
  };
  const togli = async (r) => {
    if (!window.confirm("Eliminare questa firma?")) return;
    try { await api.delete(`/ddt/${d.id}/firme/${r}`); onChanged(); } catch (e) { toast.error(errMsg(e)); }
  };
  const creaLink = async () => {
    try {
      const { data } = await api.post(`/ddt/${d.id}/link-firma`);
      setLink({ url: `${window.location.origin}/firma-ddt/${data.token}`, scade: data.expires_at });
    } catch (e) { toast.error(errMsg(e)); }
  };
  const copia = async () => { try { await navigator.clipboard.writeText(link.url); toast.success("Link copiato"); } catch { toast.error("Copia non riuscita: seleziona il link a mano"); } };
  const nomeDefault = ruolo === "vettore" ? d.vettore?.denominazione : "";
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5" data-testid="ddt-firme-card">
      <h3 className="mb-3 flex items-center gap-2 font-semibold text-slate-800"><PenLine className="h-4 w-4" />Firme alla consegna</h3>
      <div className="space-y-3">
        {RUOLI_FIRMA.map(([k, label]) => (
          <div key={k} className="rounded-lg border border-slate-200 p-3" data-testid={`ddt-firma-${k}`}>
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-semibold text-slate-700">{label}</span>
              {firme[k] ? (canSend(user) && <button onClick={() => togli(k)} title="Elimina firma" className="rounded p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600" data-testid={`ddt-firma-remove-${k}`}><X className="h-4 w-4" /></button>)
                : <Button size="sm" variant="outline" onClick={() => setRuolo(k)} data-testid={`ddt-firma-btn-${k}`}>Firma</Button>}
            </div>
            {firme[k] && (
              <div className="mt-2">
                <img src={`data:image/png;base64,${firme[k].png_b64}`} alt={`Firma ${label}`} className="h-16 rounded bg-slate-50 object-contain" />
                <div className="text-xs text-slate-500">{firme[k].nome} · {fmtDateTime(firme[k].at)} · {firme[k].by}</div>
              </div>
            )}
          </div>
        ))}
      </div>
      <Button variant="outline" size="sm" className="mt-3 w-full" onClick={creaLink} data-testid="ddt-link-firma-btn"><Link2 className="mr-2 h-4 w-4" />Link di firma per tablet (24 ore)</Button>
      {link && (
        <div className="mt-2 rounded-lg bg-slate-50 p-2 text-xs" data-testid="ddt-link-firma-box">
          <div className="break-all font-mono text-slate-700" data-testid="ddt-link-firma-url">{link.url}</div>
          <div className="mt-1 flex items-center justify-between text-slate-500"><span>Scade il {fmtDateTime(link.scade)} · un nuovo link annulla il precedente</span>
            <button onClick={copia} className="inline-flex items-center gap-1 rounded px-2 py-1 hover:bg-slate-200" data-testid="ddt-link-firma-copy"><Copy className="h-3.5 w-3.5" />Copia</button></div>
        </div>
      )}
      <FirmaDialog ruolo={ruolo} nomeDefault={nomeDefault} onClose={() => setRuolo(null)} onSave={save} />
    </div>
  );
};

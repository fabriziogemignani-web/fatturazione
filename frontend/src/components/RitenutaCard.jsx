import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { fmtEUR } from "@/lib/fe";
import { Button } from "@/components/ui/button";

export const RitenutaCard = ({ d, edit, onSaved }) => {
  const [f, setF] = useState({ aliquota: 20, imponibile: 0 });
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { setF({ aliquota: d.ritenuta_aliquota ?? 20, imponibile: d.ritenuta_imponibile ?? d.imponibile ?? 0 }); }, [d]);
  if (d.tipo_documento === "TD04" && !d.ritenuta_importo) return null;
  const save = async () => {
    setBusy(true);
    try { await api.put(`/passive/${d.id}/ritenuta`, { aliquota: Number(f.aliquota), imponibile: Number(f.imponibile) }); toast.success("Ritenuta aggiornata e registrazione contabile rifatta"); setOpen(false); onSaved(); } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };
  const prev = Math.round(Number(f.imponibile) * Number(f.aliquota)) / 100;
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm" data-testid="passive-ritenuta-card">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-semibold text-slate-900">Ritenuta d'acconto</h3>
        {edit && !open && <button onClick={() => setOpen(true)} className="text-xs font-semibold text-blue-600 hover:underline" data-testid="passive-ritenuta-edit">{d.ritenuta_importo ? "Modifica" : "Applica ritenuta"}</button>}
      </div>
      {d.ritenuta_importo > 0 ? (
        <div className="mt-2 space-y-1 text-sm" data-testid="passive-ritenuta-info">
          <div className="flex justify-between"><span className="text-slate-600">Ritenuta {d.ritenuta_aliquota ? `${d.ritenuta_aliquota}%` : ""}{d.ritenuta_imponibile ? ` su ${fmtEUR(d.ritenuta_imponibile)}` : ""}</span><b>{fmtEUR(d.ritenuta_importo)}</b></div>
          <div className="flex justify-between"><span className="text-slate-600">Netto da pagare al professionista</span><b>{fmtEUR(d.netto)}</b></div>
          <p className="text-xs text-slate-500">{d.ritenuta_auto ? "Calcolata dall'anagrafica del fornitore. " : ""}Va versata con F24 (codice tributo indicato nel fornitore, di norma 1040) entro il 16 del mese dopo ogni pagamento, in proporzione a quanto pagato.</p>
        </div>
      ) : <p className="mt-2 text-sm text-slate-500" data-testid="passive-ritenuta-none">Nessuna ritenuta su questa fattura.</p>}
      {open && (
        <div className="mt-3 grid grid-cols-2 gap-3 text-xs" data-testid="passive-ritenuta-form">
          <label className="space-y-1"><span className="font-medium text-slate-600">Imponibile ritenuta</span>
            <input type="number" step="0.01" min={0} value={f.imponibile} onChange={(e) => setF({ ...f, imponibile: e.target.value })} className="h-9 w-full rounded-md border border-slate-200 px-2 text-sm" data-testid="passive-ritenuta-imponibile" /></label>
          <label className="space-y-1"><span className="font-medium text-slate-600">Aliquota %</span>
            <input type="number" step="0.01" min={0} max={100} value={f.aliquota} onChange={(e) => setF({ ...f, aliquota: e.target.value })} className="h-9 w-full rounded-md border border-slate-200 px-2 text-sm" data-testid="passive-ritenuta-aliquota" /></label>
          <div className="col-span-2 flex items-center justify-between gap-2">
            <span className="text-slate-600">Ritenuta: <b>{fmtEUR(prev)}</b></span>
            <div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => setOpen(false)} data-testid="passive-ritenuta-cancel">Annulla</Button><Button size="sm" onClick={save} disabled={busy} data-testid="passive-ritenuta-save">Salva</Button></div>
          </div>
        </div>
      )}
    </div>
  );
};

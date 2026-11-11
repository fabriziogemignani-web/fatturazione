import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

const CAMPI = [["cliente_codice_fiscale", "Codice fiscale cliente"], ["cliente_codice_destinatario", "Codice destinatario cliente"], ["cliente_pec", "PEC cliente"],
  ["cliente_email", "Email cliente"], ["cliente_telefono", "Telefono cliente"], ["causale", "Causale"], ["note_righe", "Note delle righe"],
  ["riepilogo_iva", "Riepilogo IVA"], ["scadenza", "Scadenza pagamento"], ["coordinate_bancarie", "Coordinate bancarie"]];
const DATI = [["telefono", "Telefono"], ["email", "Email"], ["pec", "PEC"], ["sito", "Sito web"], ["rea", "REA"], ["capitale_sociale", "Capitale sociale"]];

export const LayoutDocumentiCard = () => {
  const [l, setL] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.get("/company/layout").then(({ data }) => setL(data)).catch((e) => toast.error(errMsg(e))); }, []);
  if (!l) return null;
  const set = (k, v) => setL({ ...l, [k]: v });
  const logo = (f) => {
    if (!f) return;
    if (!["image/png", "image/jpeg"].includes(f.type) || f.size > 400 * 1024) { toast.error("Usa un'immagine PNG o JPG fino a 400 KB"); return; }
    const r = new FileReader();
    r.onload = () => set("logo", r.result);
    r.readAsDataURL(f);
  };
  const save = async () => {
    setBusy(true);
    try { await api.put("/company/layout", l); toast.success("Grafica dei documenti salvata"); } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };
  return (
    <div className="mt-6 max-w-3xl rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm" data-testid="layout-card">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div><h3 className="font-semibold text-slate-900">Grafica di fatture, note di credito e DDT</h3><p className="text-xs text-slate-500">Vale per la stampa, il PDF di cortesia inviato via email e il PDF dei DDT.</p></div>
        <Button onClick={save} disabled={busy} data-testid="layout-save-btn">Salva grafica</Button>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <span className="text-xs text-slate-600">Logo (in alto a sinistra)</span>
          <div className="mt-1 flex items-center gap-3">
            {l.logo ? <img src={l.logo} alt="Logo" className="h-14 max-w-[160px] rounded border border-slate-200 object-contain" data-testid="layout-logo-preview" /> : <span className="text-xs text-slate-400">Nessun logo</span>}
            <label className="cursor-pointer rounded-md border border-slate-200 px-3 py-1.5 text-xs hover:bg-slate-50">Scegli<input type="file" accept="image/png,image/jpeg" className="hidden" onChange={(e) => logo(e.target.files[0])} data-testid="layout-logo-input" /></label>
            {l.logo && <button onClick={() => set("logo", null)} className="text-xs text-rose-600" data-testid="layout-logo-remove">Rimuovi</button>}
          </div>
        </div>
        <label className="text-xs text-slate-600">Colore principale<div className="mt-1 flex items-center gap-2"><input type="color" value={l.colore} onChange={(e) => set("colore", e.target.value)} className="h-9 w-14 rounded border border-slate-200" data-testid="layout-colore-input" /><span className="font-mono text-xs">{l.colore}</span></div></label>
        {DATI.map(([k, lab]) => <label key={k} className="text-xs text-slate-600">{lab}<Input value={l[k] || ""} onChange={(e) => set(k, e.target.value)} data-testid={`layout-${k}-input`} /></label>)}
      </div>
      <div className="mt-5">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Campi mostrati sul documento</div>
        <div className="grid gap-2 sm:grid-cols-2">
          {CAMPI.map(([k, lab]) => (
            <label key={k} className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-sm"><span>{lab}</span>
              <Switch checked={l.campi?.[k] !== false} onCheckedChange={(v) => set("campi", { ...l.campi, [k]: v })} data-testid={`layout-campo-${k}`} /></label>
          ))}
        </div>
      </div>
      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <label className="text-xs text-slate-600">Piè di pagina delle fatture<Textarea rows={4} value={l.piede_fattura || ""} onChange={(e) => set("piede_fattura", e.target.value)} placeholder="Condizioni di vendita, informativa privacy…" data-testid="layout-piede-fattura" /></label>
        <label className="text-xs text-slate-600">Piè di pagina delle note di credito<Textarea rows={4} value={l.piede_nc || ""} onChange={(e) => set("piede_nc", e.target.value)} data-testid="layout-piede-nc" /></label>
        <label className="text-xs text-slate-600 sm:col-span-2">Piè di pagina dei DDT<Textarea rows={3} value={l.piede_ddt || ""} onChange={(e) => set("piede_ddt", e.target.value)} placeholder="Es. condizioni di consegna, reclami entro 8 giorni…" data-testid="layout-piede-ddt" /></label>
      </div>
    </div>
  );
};

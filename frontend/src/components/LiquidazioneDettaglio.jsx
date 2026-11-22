import { useEffect, useState } from "react";
import { toast } from "sonner";
import { FileText, ShieldCheck, RotateCcw } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

const apri = async (req) => {
  const w = window.open("", "_blank");
  try {
    const { data } = await req();
    const url = URL.createObjectURL(new Blob([data], { type: "application/pdf" }));
    if (w) w.location.href = url; else window.location.href = url;
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    return true;
  } catch (e) {
    if (w) w.close();
    const msg = e.response?.data instanceof Blob ? JSON.parse(await e.response.data.text()).detail : errMsg(e);
    toast.error(typeof msg === "string" ? msg : "Stampa non riuscita");
    return false;
  }
};

const R = ({ l, v, tone = "", testId }) => (
  <div className="flex justify-between border-b border-slate-100 py-1.5 text-sm"><span className="text-slate-600">{l}</span><span className={`mono font-semibold ${tone}`} data-testid={testId}>{fmtEUR(v || 0)}</span></div>
);

const Aliquote = ({ titolo, blocco }) => (
  <div className="rounded-lg border border-slate-200">
    <div className="border-b border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-bold uppercase tracking-wider text-slate-600">{titolo}</div>
    <table className="w-full text-xs">
      <thead className="text-slate-500"><tr><th className="px-3 py-1 text-left font-medium">Aliquota / natura</th><th className="px-3 py-1 text-right font-medium">Imponibile</th><th className="px-3 py-1 text-right font-medium">Imposta</th></tr></thead>
      <tbody>
        {(blocco?.totali || []).map((x, i) => <tr key={i} className="border-t border-slate-100"><td className="px-3 py-1">{x.aliquota ? `${x.aliquota}%` : x.natura || "—"}{x.descrizione ? ` · ${x.descrizione}` : ""}</td><td className="mono px-3 py-1 text-right">{fmtEUR(x.imponibile)}</td><td className="mono px-3 py-1 text-right">{fmtEUR(x.imposta)}</td></tr>)}
        {!(blocco?.totali || []).length && <tr><td colSpan={3} className="px-3 py-2 text-slate-400">Nessun movimento</td></tr>}
      </tbody>
    </table>
  </div>
);

export const LiquidazioneDettaglio = ({ p, anno, per, onClose }) => {
  const [uff, setUff] = useState(null);
  const load = () => api.get("/liquidazione-iva/ufficiali", { params: { anno, periodicita: per } }).then(({ data }) => setUff(data.stampe)).catch(() => setUff([]));
  useEffect(() => { if (p) load(); }, [p, anno, per]);
  if (!p) return null;
  const st = (uff || []).find((s) => s.periodo === p.periodo);
  const dovuto = p.saldo > 0 ? p.saldo + p.interessi + p.debito_precedente : p.debito_precedente + Math.min(p.saldo, 0);
  const ufficiale = async () => {
    if (!window.confirm(`Stampa UFFICIALE della liquidazione ${p.label} ${anno}: viene numerata e archiviata e non si potrà ripetere (resta la ristampa). Continuare?`)) return;
    if (await apri(() => api.post("/liquidazione-iva/ufficiale", { anno, periodicita: per, periodo: p.periodo }, { responseType: "blob" }))) load();
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto bg-white" data-testid="liq-dettaglio">
        <DialogHeader><DialogTitle>Liquidazione IVA · {p.label} {anno}</DialogTitle></DialogHeader>
        <div className={`rounded-xl p-4 text-white ${dovuto > 0 ? "bg-rose-600" : "bg-emerald-600"}`} data-testid="liq-det-esito">
          <div className="text-xs font-semibold uppercase tracking-wider text-white/80">{dovuto > 0 ? "IVA da versare" : "IVA a credito"}</div>
          <div className="text-2xl font-extrabold">{fmtEUR(Math.abs(dovuto))}</div>
          <div className="text-xs text-white/85">{p.documenti_vendite} vendite · {p.documenti_acquisti} acquisti{p.documenti_corrispettivi ? ` · ${p.documenti_corrispettivi} gg corrispettivi` : ""}{p.sotto_soglia ? " · sotto 25,82 €: rinviato al periodo successivo" : ""}</div>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <R l="IVA vendite" v={p.iva_debito + p.iva_split - p.iva_rc - p.iva_corrispettivi} />
            <R l="di cui split payment (esclusa)" v={p.iva_split} tone="text-slate-500" />
            <R l="IVA corrispettivi" v={p.iva_corrispettivi} />
            <R l="Reverse charge a debito" v={p.iva_rc} />
            <R l="Totale IVA a debito" v={p.iva_debito} tone="text-rose-700" testId="liq-det-debito" />
          </div>
          <div>
            <R l="IVA acquisti detraibile" v={p.iva_credito} tone="text-emerald-700" testId="liq-det-credito" />
            <R l="IVA indetraibile (a costo)" v={p.iva_indetraibile} tone="text-amber-700" />
            <R l="Credito periodo precedente" v={p.credito_precedente} tone="text-emerald-700" />
            <R l="Debito rinviato dal periodo precedente" v={p.debito_precedente} />
            {per === "trimestrale" && <R l="Interessi 1%" v={p.interessi} />}
            <R l={p.da_versare > 0 ? "Da versare" : "Credito a riporto"} v={p.da_versare || p.credito_riporto} tone={p.da_versare > 0 ? "text-rose-700" : "text-emerald-700"} testId="liq-det-saldo" />
          </div>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <Aliquote titolo="Vendite per aliquota" blocco={p.vendite} />
          <Aliquote titolo="Acquisti per aliquota" blocco={p.acquisti} />
          {p.documenti_corrispettivi > 0 && <Aliquote titolo="Corrispettivi per aliquota" blocco={p.corrispettivi} />}
        </div>
        <div className="flex flex-wrap items-center gap-2 border-t border-slate-200 pt-3">
          <Button variant="outline" onClick={() => apri(() => api.get("/liquidazione-iva/pdf", { params: { anno, periodicita: per, periodo: p.periodo }, responseType: "blob" }))} data-testid="liq-det-prova"><FileText className="mr-2 h-4 w-4" />Stampa di prova</Button>
          {st ? (
            <>
              <Button onClick={() => apri(() => api.get(`/stampe-fiscali/stampe/${st.id}/pdf`, { responseType: "blob" }))} data-testid="liq-det-ristampa"><RotateCcw className="mr-2 h-4 w-4" />Ristampa ufficiale</Button>
              <span className="text-xs text-slate-500" data-testid="liq-det-ufficiale-info">Stampata in ufficiale il {fmtDate(st.created_at)} da {st.created_by} · pagine {anno}/{st.pagina_da}–{st.pagina_a}</span>
            </>
          ) : (
            <Button onClick={ufficiale} disabled={uff === null} data-testid="liq-det-ufficiale"><ShieldCheck className="mr-2 h-4 w-4" />Stampa ufficiale</Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};

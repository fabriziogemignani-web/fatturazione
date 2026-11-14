import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Printer } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR } from "@/lib/fe";
import { Button } from "@/components/ui/button";

const apri = async (params) => {
  const w = window.open("", "_blank");
  try {
    const { data } = await api.get("/ritenute/certificazione/pdf", { params, responseType: "blob" });
    const url = URL.createObjectURL(new Blob([data], { type: "application/pdf" }));
    if (w) w.location.href = url;
    else { const a = document.createElement("a"); a.href = url; a.download = `Certificazione_compensi_${params.anno}.pdf`; a.click(); }
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch (e) {
    if (w) w.close();
    let msg = errMsg(e);
    try { if (e.response?.data instanceof Blob) msg = JSON.parse(await e.response.data.text()).detail; } catch { msg = "Impossibile generare la stampa"; }
    toast.error(typeof msg === "string" ? msg : "Impossibile generare la stampa");
  }
};

const Riga = ({ f, anno }) => (
  <tr className="hover:bg-slate-50" data-testid={`cert-row-${f.key}`}>
    <td className="px-4 py-3"><div className="font-medium">{f.fornitore}</div><div className="text-xs text-slate-500">{f.codice_fiscale || f.partita_iva} · causale {f.causale} · cod. {f.codice}</div></td>
    <td className="px-4 py-3 text-right">{fmtEUR(f.compenso)}</td>
    <td className="px-4 py-3 text-right">{fmtEUR(f.imponibile_ritenuta)}</td>
    <td className="px-4 py-3 text-right font-semibold">{fmtEUR(f.ritenuta)}</td>
    <td className="px-4 py-3 text-right text-emerald-700">{fmtEUR(f.versata)}</td>
    <td className="px-4 py-3 text-right">{f.da_versare ? <span className="font-semibold text-amber-700" data-testid={`cert-da-versare-${f.key}`}>{fmtEUR(f.da_versare)}</span> : <span className="text-xs text-emerald-700">tutto versato</span>}</td>
    <td className="px-4 py-3 text-right"><Button size="sm" variant="outline" onClick={() => apri({ anno, party: f.key })} data-testid={`cert-pdf-${f.key}`}><Printer className="mr-1 h-3.5 w-3.5" />Stampa</Button></td>
  </tr>
);

export const RitenuteCertificazione = () => {
  const [anno, setAnno] = useState(new Date().getFullYear() - (new Date().getMonth() < 3 ? 1 : 0));
  const [d, setD] = useState(null);
  useEffect(() => { setD(null); api.get("/ritenute/certificazione", { params: { anno } }).then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e))); }, [anno]);
  const anni = Array.from({ length: 6 }, (_, i) => new Date().getFullYear() - i);
  return (
    <div className="space-y-4" data-testid="cert-page">
      <div className="flex flex-wrap items-center gap-3">
        <select value={anno} onChange={(e) => setAnno(Number(e.target.value))} className="h-9 rounded-md border border-slate-200 bg-white px-2 text-sm" data-testid="cert-anno">{anni.map((a) => <option key={a} value={a}>{a}</option>)}</select>
        <p className="text-xs text-slate-500">Compensi pagati nell'anno ai professionisti con ritenuta, divisi per fornitore, con le ritenute versate tramite F24.</p>
        <Button className="ml-auto" onClick={() => apri({ anno })} disabled={!d?.fornitori.length} data-testid="cert-pdf-tutti"><Printer className="mr-2 h-4 w-4" />Stampa tutte le certificazioni</Button>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm" data-testid="cert-table">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr><th className="px-4 py-3">Professionista</th><th className="px-4 py-3 text-right">Compenso lordo</th><th className="px-4 py-3 text-right">Imponibile ritenuta</th><th className="px-4 py-3 text-right">Ritenute operate</th><th className="px-4 py-3 text-right">Versate</th><th className="px-4 py-3 text-right">Da versare</th><th /></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {!d && <tr><td colSpan={7} className="px-4 py-10 text-center text-slate-500">Caricamento…</td></tr>}
            {d?.fornitori.length === 0 && <tr><td colSpan={7} className="px-4 py-10 text-center text-slate-500" data-testid="cert-empty">Nessun compenso con ritenuta pagato nel {anno}</td></tr>}
            {d?.fornitori.map((f) => <Riga key={f.key} f={f} anno={anno} />)}
          </tbody>
          {d?.fornitori.length > 0 && (
            <tfoot className="bg-slate-50 font-semibold"><tr>
              <td className="px-4 py-3">Totale {anno}</td><td className="px-4 py-3 text-right" data-testid="cert-tot-compenso">{fmtEUR(d.totali.compenso)}</td><td className="px-4 py-3 text-right">{fmtEUR(d.totali.imponibile_ritenuta)}</td>
              <td className="px-4 py-3 text-right" data-testid="cert-tot-ritenuta">{fmtEUR(d.totali.ritenuta)}</td><td className="px-4 py-3 text-right" data-testid="cert-tot-versata">{fmtEUR(d.totali.versata)}</td><td className="px-4 py-3 text-right">{fmtEUR(d.totali.da_versare)}</td><td />
            </tr></tfoot>
          )}
        </table>
      </div>
      {d?.totali.da_versare > 0 && <p className="text-xs text-amber-700" data-testid="cert-avviso">Alcune ritenute non risultano ancora versate: segnalale come versate nel mese di riferimento prima di consegnare le certificazioni.</p>}
    </div>
  );
};

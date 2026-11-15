import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Factory, ShoppingCart, RefreshCw } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { OrdineDialog } from "@/components/OrdineDialog";

const today = () => new Date().toISOString().slice(0, 10);

const Tabella = ({ rows, testId, extra }) => (
  <table className="w-full text-sm" data-testid={testId}>
    <thead className="bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500"><tr><th className="px-4 py-2">Articolo</th><th className="px-4 py-2 text-right">Disponibile</th><th className="px-4 py-2 text-right">Quantità proposta</th><th className="px-4 py-2">{extra[0]}</th></tr></thead>
    <tbody className="divide-y divide-slate-100">
      {rows.length === 0 && <tr><td colSpan={4} className="px-4 py-6 text-center text-slate-500">Nulla da proporre</td></tr>}
      {rows.map((r) => <tr key={r.article_id} data-testid={`${testId}-row-${r.article_id}`}><td className="px-4 py-2"><span className="mono text-xs">{r.codice}</span> {r.descrizione}</td><td className={`px-4 py-2 text-right ${r.disponibilita < 0 ? "text-rose-700" : ""}`}>{r.disponibilita}</td><td className="px-4 py-2 text-right font-semibold">{r.quantita}</td><td className="px-4 py-2 text-xs">{extra[1](r)}</td></tr>)}
    </tbody>
  </table>
);

export default function Mrp() {
  const [d, setD] = useState(null);
  const [bozza, setBozza] = useState(null);
  const load = () => { setD(null); api.get("/produzione/mrp").then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e))); };
  useEffect(() => { load(); }, []);
  const genera = async () => {
    try { const { data } = await api.post("/produzione/ordini/genera", { righe: d.produrre.map((r) => ({ article_id: r.article_id, quantita: r.quantita, data: today(), note: "Proposta MRP" })) }); toast.success(`${data.length} ordini di produzione creati`); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  const acquista = async () => {
    try {
      const { data: parts } = await api.get("/parties", { params: { tipo: "fornitore" } });
      const norm = (s) => (s || "").trim().toLowerCase();
      const forn = parts.find((p) => d.acquistare.length && norm(p.denominazione) === norm(d.acquistare[0].fornitore_abituale));
      const righe = d.acquistare.filter((r) => norm(r.fornitore_abituale) === norm(d.acquistare[0].fornitore_abituale));
      setBozza({ party_id: forn?.id || "", lines: righe.map(({ article_id, codice, descrizione, quantita, unita_misura, aliquota, natura, prezzo_unitario }) => ({ article_id, codice, descrizione, quantita, unita_misura, aliquota, natura, prezzo_unitario, sconto: "" })) });
    } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div data-testid="mrp-page">
      <PageHeader eyebrow="Produzione" title="Fabbisogno materiali (MRP)" subtitle="Disponibilità (giacenza − impegnato + ordinato e in produzione) confrontata con le scorte minime, esplodendo le distinte livello per livello">
        <Button variant="outline" onClick={load} data-testid="mrp-ricalcola"><RefreshCw className="mr-2 h-4 w-4" />Ricalcola</Button>
      </PageHeader>
      {!d ? <p className="text-sm text-slate-500">Calcolo in corso…</p> : (
        <div className="space-y-6">
          <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3"><h3 className="flex items-center gap-2 font-semibold"><Factory className="h-4 w-4 text-blue-600" />Da produrre</h3>
              <Button size="sm" onClick={genera} disabled={!d.produrre.length} data-testid="mrp-genera-op">Crea ordini di produzione</Button></div>
            <Tabella rows={d.produrre} testId="mrp-produrre" extra={["Livello distinta", (r) => `livello ${r.livello} · scorta min. ${r.scorta_minima}`]} />
          </div>
          <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3"><h3 className="flex items-center gap-2 font-semibold"><ShoppingCart className="h-4 w-4 text-blue-600" />Da acquistare</h3>
              <Button size="sm" variant="outline" onClick={acquista} disabled={!d.acquistare.length} data-testid="mrp-ordina-acquisti">Crea ordine fornitore{d.acquistare.length ? ` (${d.acquistare[0].fornitore_abituale || "senza fornitore"})` : ""}</Button></div>
            <Tabella rows={d.acquistare} testId="mrp-acquistare" extra={["Fornitore abituale", (r) => r.fornitore_abituale || "—"]} />
          </div>
        </div>
      )}
      <OrdineDialog tipo="fornitore" bozza={bozza} open={!!bozza} onOpenChange={(v) => !v && setBozza(null)} onSaved={() => { setBozza(null); load(); }} />
    </div>
  );
}

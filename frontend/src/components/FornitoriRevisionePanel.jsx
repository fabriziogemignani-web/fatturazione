import { useEffect, useState } from "react";
import { toast } from "sonner";
import { UserCheck } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, RITENUTE, CAUSALI, CASSE, GESTIONI_IVA, MODALITA, NATURE } from "@/lib/fe";
import { ContoSelect, useConti } from "@/components/ContoSelect";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";

const sel = "block h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm";
const KEYS = ["persona", "nome", "cognome", "soggetto_ritenuta", "ritenuta_tipo", "ritenuta_aliquota", "ritenuta_base", "ritenuta_causale", "ritenuta_codice_tributo",
  "cassa_tipo", "cassa_aliquota", "cassa_ritenuta", "conto_costo", "gestione_iva", "natura_default", "pagamento_modalita", "pagamento_rate", "pagamento_giorni", "pagamento_fine_mese"];
const DEF = { persona: "giuridica", nome: "", cognome: "", soggetto_ritenuta: false, ritenuta_tipo: "RT01", ritenuta_aliquota: 20, ritenuta_base: 100, ritenuta_causale: "A", ritenuta_codice_tributo: "1040",
  cassa_tipo: "", cassa_aliquota: 4, cassa_ritenuta: false, conto_costo: "", gestione_iva: "", natura_default: "", pagamento_modalita: "", pagamento_rate: 1, pagamento_giorni: 30, pagamento_fine_mese: false };
const L = ({ t, children }) => <label className="text-xs text-slate-600">{t}{children}</label>;
const Pick = ({ v, set, opts, testId }) => <select className={sel} value={v ?? ""} onChange={(e) => set(e.target.value)} data-testid={testId}>{opts.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>;

const Ritenuta = ({ f, s }) => (
  <div className="rounded-lg border border-amber-200 bg-amber-50/50 p-3">
    <label className="flex items-center justify-between text-sm font-semibold text-slate-800">Soggetto a ritenuta d'acconto<Switch checked={f.soggetto_ritenuta} onCheckedChange={(v) => s({ soggetto_ritenuta: v })} data-testid="rev-ritenuta-switch" /></label>
    {f.soggetto_ritenuta && <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
      <L t="Tipo"><Pick v={f.ritenuta_tipo} set={(v) => s({ ritenuta_tipo: v })} opts={RITENUTE} testId="rev-rit-tipo" /></L>
      <L t="Aliquota %"><Input type="number" value={f.ritenuta_aliquota} onChange={(e) => s({ ritenuta_aliquota: Number(e.target.value) })} data-testid="rev-rit-aliquota" /></L>
      <L t="Base imponibile %"><Input type="number" value={f.ritenuta_base} onChange={(e) => s({ ritenuta_base: Number(e.target.value) })} data-testid="rev-rit-base" /></L>
      <L t="Causale"><Pick v={f.ritenuta_causale} set={(v) => s({ ritenuta_causale: v })} opts={CAUSALI} testId="rev-rit-causale" /></L>
      <L t="Codice tributo"><Input value={f.ritenuta_codice_tributo || ""} maxLength={4} onChange={(e) => s({ ritenuta_codice_tributo: e.target.value.toUpperCase() })} data-testid="rev-rit-tributo" /></L>
      <L t="Cassa previdenziale"><Pick v={f.cassa_tipo} set={(v) => s({ cassa_tipo: v })} opts={[["", "Nessuna"], ...CASSE]} testId="rev-cassa-tipo" /></L>
      {f.cassa_tipo && <L t="Aliquota cassa %"><Input type="number" value={f.cassa_aliquota} onChange={(e) => s({ cassa_aliquota: Number(e.target.value) })} data-testid="rev-cassa-aliquota" /></L>}
    </div>}
  </div>
);

const Revisione = ({ x, onClose, onDone }) => {
  const [conti] = useConti(true);
  const [f, setF] = useState(() => Object.fromEntries(KEYS.map((k) => [k, x[k] ?? DEF[k]])));
  const s = (p) => setF({ ...f, ...p });
  const save = async () => {
    try {
      const { data } = await api.post(`/parties/${x.id}/revisione`, f);
      toast.success(`Fornitore confermato${data.fatture_aggiornate ? ` · ${data.fatture_aggiornate} fatture da registrare aggiornate` : ""}`);
      onDone(); onClose();
    } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="bg-white sm:max-w-2xl" data-testid="rev-dialog">
        <DialogHeader><DialogTitle>Completa {x.denominazione}</DialogTitle></DialogHeader>
        <p className="text-xs text-slate-500">P.IVA {x.partita_iva || "—"} · C.F. {x.codice_fiscale || "—"} · {x.fatture} fatture ricevute · IVA rilevata: {x.iva_rilevata.join(", ") || "—"}. I valori sono già proposti dal file XML: controllali e conferma.</p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <L t="Soggetto"><Pick v={f.persona} set={(v) => s({ persona: v })} opts={[["giuridica", "Persona giuridica"], ["fisica", "Persona fisica"]]} testId="rev-persona" /></L>
          {f.persona === "fisica" && <><L t="Nome"><Input value={f.nome} onChange={(e) => s({ nome: e.target.value })} data-testid="rev-nome" /></L>
            <L t="Cognome"><Input value={f.cognome} onChange={(e) => s({ cognome: e.target.value })} data-testid="rev-cognome" /></L></>}
          <L t="Gestione IVA"><Pick v={f.gestione_iva} set={(v) => s({ gestione_iva: v })} opts={GESTIONI_IVA} testId="rev-gestione-iva" /></L>
          <L t="Natura IVA abituale"><Pick v={f.natura_default} set={(v) => s({ natura_default: v })} opts={[["", "IVA ordinaria"], ...NATURE.map((n) => [n[0], n[1]])]} testId="rev-natura" /></L>
          <L t="Pagamento"><Pick v={f.pagamento_modalita} set={(v) => s({ pagamento_modalita: v })} opts={[["", "Non indicato"], ...MODALITA.filter(([k]) => /^(MP0[1258]|MP12)$/.test(k))]} testId="rev-pag-modalita" /></L>
          <L t="Rate"><Input type="number" min={1} max={12} value={f.pagamento_rate} onChange={(e) => s({ pagamento_rate: Number(e.target.value) })} data-testid="rev-pag-rate" /></L>
          <L t="Giorni"><Input type="number" min={0} max={365} value={f.pagamento_giorni} onChange={(e) => s({ pagamento_giorni: Number(e.target.value) })} data-testid="rev-pag-giorni" /></L>
          <label className="flex items-end gap-2 pb-2 text-xs text-slate-600"><Switch checked={f.pagamento_fine_mese} onCheckedChange={(v) => s({ pagamento_fine_mese: v })} data-testid="rev-pag-fm" />Fine mese</label>
        </div>
        <L t="Conto di costo"><ContoSelect conti={conti} tipi={["costo", "attivita"]} value={f.conto_costo} onChange={(v) => s({ conto_costo: v })} allowEmpty="Quello unico dei parametri" testId="rev-conto-costo" /></L>
        <Ritenuta f={f} s={s} />
        <DialogFooter><Button variant="outline" onClick={onClose}>Annulla</Button><Button onClick={save} data-testid="rev-save">Conferma fornitore</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const GEST = Object.fromEntries(GESTIONI_IVA);

export const FornitoriRevisionePanel = () => {
  const [rows, setRows] = useState(null);
  const [cur, setCur] = useState(null);
  const load = () => api.get("/parties/da-verificare/elenco").then(({ data }) => setRows(data)).catch(() => setRows([]));
  useEffect(() => { load(); }, []);
  const conferma = async () => {
    try { const { data } = await api.post("/parties/da-verificare/conferma"); toast.success(`${data.confermati} fornitori confermati${data.restanti ? ` · ${data.restanti} da completare` : ""}`); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  if (!rows?.length) return null;
  const completi = rows.filter((x) => !x.mancano.length).length;
  return (
    <div className="mt-6 rounded-xl border border-amber-200 bg-white shadow-sm" data-testid="fornitori-rev-panel">
      <div className="flex items-center gap-2 border-b border-slate-100 px-5 py-4"><UserCheck className="h-4 w-4 text-amber-600" /><h3 className="font-semibold text-slate-900">Nuovi fornitori da revisionare</h3>
        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800" data-testid="fornitori-rev-count">{rows.length}</span>
        {completi > 0 && <Button size="sm" className="ml-auto" onClick={conferma} data-testid="fornitori-rev-conferma-tutti">Conferma i completi ({completi})</Button>}</div>
      <ul className="divide-y divide-slate-100">
        {rows.map((x) => (
          <li key={x.id} className="flex flex-wrap items-center justify-between gap-2 px-5 py-3 text-sm" data-testid={`fornitori-rev-${x.id}`}>
            <span><b>{x.denominazione}</b> <span className="text-slate-500">· {x.persona === "fisica" ? "persona fisica" : "persona giuridica"}{x.soggetto_ritenuta ? ` · ritenuta ${x.ritenuta_aliquota}%` : ""}{x.gestione_iva ? ` · ${GEST[x.gestione_iva]}` : ""} · {x.fatture} fatture {fmtEUR(x.totale)}</span>
              {x.mancano.length > 0 ? <span className="ml-2 text-xs font-semibold text-amber-700" data-testid={`fornitori-rev-mancano-${x.id}`}>Manca: {x.mancano.join(", ")}</span>
                : <span className="ml-2 text-xs font-semibold text-emerald-700" data-testid={`fornitori-rev-completo-${x.id}`}>Dati completi</span>}</span>
            <Button size="sm" variant="outline" onClick={() => setCur(x)} data-testid={`fornitori-rev-btn-${x.id}`}>Completa e conferma</Button>
          </li>
        ))}
      </ul>
      {cur && <Revisione x={cur} onClose={() => setCur(null)} onDone={load} />}
    </div>
  );
};

import { NSelect } from "@/components/ui/nselect";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { RefreshCw, Loader2, Sparkles } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, ALIQUOTE, NATURE } from "@/lib/fe";
import { useConti, ContoSelect } from "@/components/ContoSelect";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { RateoBox, rateoBody, rateoInvalido } from "@/components/RateoBox";

const AF = [["", "Nessuna autofattura"], ["TD16", "TD16 - Reverse charge interno"], ["TD17", "TD17 - Servizi dall'estero"], ["TD18", "TD18 - Beni intracomunitari"], ["TD19", "TD19 - Beni ex art. 17 c.2"]];
const today = () => new Date().toISOString().slice(0, 10);
const r2 = (v) => Math.round((Number(v) || 0) * 100) / 100;
const sel = "h-9 rounded-md border border-slate-200 bg-white px-2 text-sm";

const init = (d) => ({
  numero: d.numero, data: d.data, data_registrazione: today(), aliquota_rc: 22, detraibilita_iva: d.detraibilita_iva ?? 100, autofattura: "",
  had_rit: !!d.ritenuta_importo, ritenuta_aliquota: d.ritenuta_importo ? d.ritenuta_aliquota ?? "" : "", ritenuta_imponibile: d.ritenuta_importo ? d.ritenuta_imponibile ?? "" : "",
  riepilogo: d.riepilogo.map((r) => ({ aliquota: r.aliquota, natura: r.natura || "", imponibile: r.imponibile, imposta: r.imposta, conto: "" })),
});
const ritBody = (f) => ({ ritenuta_aliquota: f.ritenuta_aliquota === "" ? (f.had_rit ? 0 : null) : Number(f.ritenuta_aliquota), ritenuta_imponibile: f.ritenuta_aliquota === "" || f.ritenuta_imponibile === "" ? null : Number(f.ritenuta_imponibile) });

const Ritenuta = ({ f, setF, prev }) => (
  <div className="flex flex-wrap items-end gap-3 rounded-lg border border-amber-200 bg-amber-50/50 p-3 text-xs text-slate-600" data-testid="regpas-ritenuta">
    <label>Ritenuta d'acconto %<Input type="number" min={0} max={100} step="0.01" value={f.ritenuta_aliquota} placeholder="nessuna" onChange={(e) => setF({ ...f, ritenuta_aliquota: e.target.value })} className="w-28 bg-white" data-testid="regpas-rit-aliquota" /></label>
    <label>Imponibile ritenuta €<Input type="number" min={0} step="0.01" value={f.ritenuta_imponibile} placeholder="= imponibile" onChange={(e) => setF({ ...f, ritenuta_imponibile: e.target.value })} className="w-32 bg-white" data-testid="regpas-rit-imponibile" disabled={f.ritenuta_aliquota === ""} /></label>
    {prev?.ritenuta_importo > 0 && <span className="pb-2" data-testid="regpas-rit-info">Ritenuta {fmtEUR(prev.ritenuta_importo || 0)} → conto ritenute da versare · netto a pagare {fmtEUR(prev.netto)}</span>}
  </div>
);

const Righe = ({ f, setF, conti }) => {
  const set = (i, k, v) => setF({ ...f, riepilogo: f.riepilogo.map((x, j) => {
    if (j !== i) return x;
    const n = { ...x, [k]: v };
    if (k === "imponibile" || k === "aliquota") n.imposta = r2((Number(n.imponibile) || 0) * Number(n.aliquota) / 100);
    return n;
  }) });
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-sm" data-testid="regpas-righe">
        <thead className="text-left text-xs uppercase tracking-wider text-slate-500"><tr><th className="py-1">Aliquota / natura</th><th>Imponibile</th><th>IVA</th><th>Conto di costo</th></tr></thead>
        <tbody>
          {f.riepilogo.map((x, i) => (
            <tr key={i} className="border-t border-slate-100">
              <td className="py-2 pr-2">
                <NSelect className={sel} value={x.aliquota} onChange={(e) => set(i, "aliquota", Number(e.target.value))} data-testid={`regpas-aliquota-${i}`}>{ALIQUOTE.map((a) => <option key={a} value={a}>{a}%</option>)}</NSelect>
                {Number(x.aliquota) === 0 && <NSelect className={`${sel} ml-1 w-32`} value={x.natura} onChange={(e) => set(i, "natura", e.target.value)} data-testid={`regpas-natura-${i}`}><option value="">Natura…</option>{NATURE.map(([k]) => <option key={k} value={k}>{k}</option>)}</NSelect>}
              </td>
              <td className="pr-2"><Input type="number" step="0.01" value={x.imponibile} onChange={(e) => set(i, "imponibile", e.target.value)} className="w-28 text-right" data-testid={`regpas-imponibile-${i}`} /></td>
              <td className="pr-2"><Input type="number" step="0.01" value={x.imposta} onChange={(e) => set(i, "imposta", e.target.value)} className="w-24 text-right" data-testid={`regpas-imposta-${i}`} /></td>
              <td><ContoSelect conti={conti} value={x.conto} onChange={(v) => set(i, "conto", v)} allowEmpty placeholder="Predefinito" testId={`regpas-conto-${i}`} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

const IaConti = ({ iaP, onRipristina }) => {
  if (!iaP) return null;
  if (iaP.loading) return <div className="flex items-center gap-2 rounded-lg border border-violet-200 bg-violet-50 p-3 text-xs text-violet-800" data-testid="regpas-ia-loading"><Loader2 className="h-3.5 w-3.5 animate-spin" />L'IA sta classificando le righe nei conti di costo secondo il codice civile…</div>;
  if (iaP.errore) return <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600" data-testid="regpas-ia-errore">Proposta conti IA non disponibile: {iaP.errore}. Scegli i conti a mano.</div>;
  return (
    <div className="rounded-lg border border-violet-200 bg-violet-50 p-3 text-xs text-violet-900" data-testid="regpas-ia-proposta">
      <div className="mb-1 flex flex-wrap items-center gap-2"><Sparkles className="h-3.5 w-3.5" /><b>Conti proposti dall'IA per voce di bilancio (artt. 2424-2425 c.c.)</b>: controllali prima di confermare.
        <button className="ml-auto font-semibold underline" onClick={onRipristina} data-testid="regpas-ia-ripristina">Ripristina righe della fattura</button></div>
      <ul className="max-h-40 space-y-0.5 overflow-y-auto">{iaP.righe.map((x) => (
        <li key={x.n} data-testid={`regpas-ia-riga-${x.n}`}><span className="text-violet-500">{x.n}.</span> {x.descrizione} · {fmtEUR(x.importo)} → {x.conto ? <><b className="mono">{x.conto}</b> {x.conto_nome} <span className="text-violet-600">({x.voce_cee})</span>{x.motivo ? ` — ${x.motivo}` : ""}</> : <i>nessun conto, usa il predefinito</i>}</li>
      ))}</ul>
    </div>
  );
};

export const RegistraPassivaDialog = ({ d, open, onOpenChange, onDone }) => {
  const [conti] = useConti(open);
  const [f, setF] = useState(null);
  const [prev, setPrev] = useState(null);
  const [err, setErr] = useState("");
  const [bemP, setBemP] = useState(null);
  const [iaP, setIaP] = useState(null);
  const [busy, setBusy] = useState(false);
  const [rr, setRr] = useState({});
  const [regIva, setRegIva] = useState(null);
  const body = () => ({ ...f, ...ritBody(f), registro_iva_id: regIva?.registro_id || null, rateo: prev?.ratei_risconti ? rateoBody(rr) : null, autofattura: f.autofattura || null, riepilogo: f.riepilogo.map((x) => ({ ...x, imponibile: r2(x.imponibile), imposta: r2(x.imposta), natura: x.natura || null })) });
  const anteprima = async (ff = f, silent = false) => {
    try {
      const { data } = await api.post(`/passive/${d.id}/registrazione/anteprima`, { ...ff, ...ritBody(ff), autofattura: null, riepilogo: ff.riepilogo.map((x) => ({ ...x, imponibile: r2(x.imponibile), imposta: r2(x.imposta), natura: x.natura || null })) });
      setPrev(data);
      setErr("");
      return data;
    } catch (e) { setErr(errMsg(e)); setPrev(null); if (!silent) toast.error(errMsg(e)); return null; }
  };
  useEffect(() => {
    if (!open) return;
    const ff = init(d);
    setF(ff);
    setBemP(null);
    setIaP(null);
    setRr({});
    api.get("/stampe-fiscali/proposta", { params: { id: d.id } }).then(({ data }) => setRegIva(data)).catch(() => setRegIva(null));
    anteprima(ff).then((p) => {
      if (p?.autofattura_proposta) setF((x) => ({ ...x, autofattura: p.autofattura_proposta }));
      const rp = p?.ritenuta_proposta;
      if (rp) setF((x) => ({ ...x, ritenuta_aliquota: rp.aliquota ? String(rp.aliquota) : "", ritenuta_imponibile: rp.aliquota ? String(rp.imponibile) : "" }));
      if (p?.rateo_esistente) setRr({ attivo: true, dal: p.rateo_esistente.competenza_dal, al: p.rateo_esistente.competenza_al, tipo: p.rateo_esistente.tipo, note: p.rateo_esistente.note, tipoManuale: true });
    });
    api.get(`/passive/${d.id}/proposta-bem`).then(({ data }) => {
      if (data.riepilogo.length && data.riepilogo.some((x) => x.conto)) { setBemP({ ...data, orig: ff.riepilogo }); setF((x) => ({ ...x, riepilogo: data.riepilogo })); return true; }
      return false;
    }).catch(() => false).then((bem) => {
      if (bem) return;
      setIaP({ loading: true });
      api.post(`/ai/passive/${d.id}/conti`, {}, { timeout: 120000 }).then(({ data }) => {
        if (data.riepilogo.some((x) => x.conto)) { setIaP({ ...data, orig: ff.riepilogo }); setF((x) => ({ ...x, riepilogo: data.riepilogo })); } else setIaP(null);
      }).catch((e) => setIaP({ errore: errMsg(e) }));
    });
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!open || !f) return undefined;
    const h = setTimeout(() => { anteprima(f, true); }, 600);
    return () => clearTimeout(h);
  }, [f?.numero, f?.data, f?.data_registrazione, f?.aliquota_rc, f?.detraibilita_iva, f?.ritenuta_aliquota, f?.ritenuta_imponibile, JSON.stringify(f?.riepilogo)]); // eslint-disable-line react-hooks/exhaustive-deps
  const save = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/passive/${d.id}/registrazione`, body());
      toast.success(`Registrata con protocollo ${data.protocollo}${data.autofattura_id ? ": autofattura creata in bozza, controllala e inviala allo SDI" : ""}`);
      onDone(data);
      onOpenChange(false);
    } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };
  if (!f) return null;
  const rc = prev?.reverse_charge?.length > 0;
  const nome = (c) => conti.find((x) => x.codice === c)?.descrizione || "";
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] overflow-y-auto bg-white sm:max-w-3xl" data-testid="regpas-dialog">
        <DialogHeader><DialogTitle>Registra fattura ricevuta · {d.fornitore.denominazione}</DialogTitle></DialogHeader>
        <div className="grid gap-3 sm:grid-cols-5">
          <label className="text-xs text-slate-600">Numero<Input value={f.numero} onChange={(e) => setF({ ...f, numero: e.target.value })} data-testid="regpas-numero" /></label>
          <label className="text-xs text-slate-600">Data documento<Input type="date" value={f.data} onChange={(e) => setF({ ...f, data: e.target.value })} data-testid="regpas-data" /></label>
          <label className="text-xs text-slate-600">Data registrazione<Input type="date" value={f.data_registrazione} onChange={(e) => setF({ ...f, data_registrazione: e.target.value })} data-testid="regpas-data-reg" /></label>
          <label className="text-xs text-slate-600">IVA detraibile %<Input type="number" min={0} max={100} value={f.detraibilita_iva} onChange={(e) => setF({ ...f, detraibilita_iva: Number(e.target.value) })} data-testid="regpas-detraibilita" /></label>
          <label className="text-xs text-slate-600">Aliquota reverse charge<NSelect className={`${sel} block w-full`} value={f.aliquota_rc} onChange={(e) => setF({ ...f, aliquota_rc: Number(e.target.value) })} data-testid="regpas-aliquota-rc">{[22, 10, 5, 4].map((a) => <option key={a} value={a}>{a}%</option>)}</NSelect></label>
          {regIva && <label className="text-xs text-slate-600 sm:col-span-5">Registro IVA (proposto dal programma, puoi cambiarlo)<NSelect className={`${sel} block w-full`} value={regIva.registro_id} onChange={(e) => setRegIva({ ...regIva, registro_id: e.target.value })} data-testid="regpas-registro-iva">{regIva.registri.map((r) => <option key={r.id} value={r.id}>{r.codice} · {r.descrizione}</option>)}</NSelect></label>}
        </div>
        {bemP && (
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800" data-testid="regpas-bem-proposta">
            <span>Righe di costo precompilate dalle entrate merce collegate ({bemP.bem.map((n) => `BEM ${n}`).join(", ")}) con i conti costo degli articoli{bemP.senza_conto ? ` · ${bemP.senza_conto} articoli senza conto costo usano la contropartita predefinita` : ""}.</span>
            <button className="ml-auto font-semibold underline" onClick={() => { setF({ ...f, riepilogo: bemP.orig }); setBemP(null); }} data-testid="regpas-bem-ripristina">Ripristina righe della fattura</button>
          </div>
        )}
        <IaConti iaP={iaP} onRipristina={() => { setF({ ...f, riepilogo: iaP.orig }); setIaP(null); }} />
        <Righe f={f} setF={setF} conti={conti} />
        <Ritenuta f={f} setF={setF} prev={prev} />
        {prev?.ratei_risconti && <RateoBox rr={rr} setRr={setRr} dataReg={f.data_registrazione} origine="acquisto" />}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <label className="text-xs text-slate-600">Autofattura / integrazione da inviare allo SDI
            <NSelect className={`${sel} ml-2`} value={f.autofattura} disabled={!rc} onChange={(e) => setF({ ...f, autofattura: e.target.value })} data-testid="regpas-autofattura">{AF.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</NSelect>
          </label>
          <Button size="sm" variant="outline" onClick={() => anteprima()} data-testid="regpas-anteprima-btn"><RefreshCw className="mr-1 h-3.5 w-3.5" />Aggiorna anteprima</Button>
        </div>
        {err && <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700" data-testid="regpas-anteprima-error">{err}</div>}
        {prev?.ritenuta_proposta && <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-xs text-blue-900" data-testid="regpas-calcolo-anagrafica">Calcolato dall'anagrafica del professionista ({prev.ritenuta_proposta.regime}){prev.ritenuta_proposta.cassa ? ` · cassa ${fmtEUR(prev.ritenuta_proposta.cassa)} ${prev.ritenuta_proposta.cassa_in_base ? "(rivalsa INPS, dentro la base ritenuta)" : "(cassa privata, fuori dalla base ritenuta)"}` : ""} · {prev.ritenuta_proposta.aliquota ? `ritenuta ${prev.ritenuta_proposta.aliquota}% su ${fmtEUR(prev.ritenuta_proposta.imponibile)} = ${fmtEUR(prev.ritenuta_proposta.importo)}` : "nessuna ritenuta"}</div>}
        {prev?.avvisi_percipiente?.length > 0 && <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800" data-testid="regpas-avvisi-percipiente">Anagrafica del professionista incompleta per CU e 770: {prev.avvisi_percipiente.join(", ")}. Completala in Clienti e fornitori.</div>}
        {prev && (
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs" data-testid="regpas-anteprima">
            <div className="mb-1 font-semibold">{prev.causale} · {prev.descrizione} · totale documento {fmtEUR(prev.totale)}</div>
            {prev.reverse_charge?.map((x, i) => <div key={i} className="text-indigo-700">Reverse charge {x.natura}: IVA {x.aliquota}% su {fmtEUR(x.imponibile)} = {fmtEUR(x.imposta)}</div>)}
            <table className="mt-1 w-full"><tbody>
              {prev.righe.map((x, i) => <tr key={i} data-testid={`regpas-prev-${i}`}><td className="mono py-0.5">{x.conto}</td><td>{nome(x.conto)}{x.party_nome ? ` · ${x.party_nome}` : ""}</td><td className="text-right">{x.dare ? fmtEUR(x.dare) : ""}</td><td className="text-right">{x.avere ? fmtEUR(x.avere) : ""}</td></tr>)}
            </tbody></table>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Annulla</Button>
          <Button onClick={save} disabled={busy || rateoInvalido(rr)} data-testid="regpas-save">{busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Conferma registrazione</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

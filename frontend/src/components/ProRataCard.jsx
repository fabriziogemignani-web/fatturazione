import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Percent } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR } from "@/lib/fe";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

const Kv = ({ l, v, tone = "", id }) => <div><div className="text-[11px] uppercase tracking-wide text-slate-500">{l}</div><div className={`text-sm font-semibold ${tone}`} data-testid={id}>{v}</div></div>;

const Conguaglio = ({ d, reg, annulla }) => (
  <div className="mt-3 flex flex-wrap items-center gap-3 border-t border-slate-100 pt-3 text-sm">
    <span data-testid="prorata-conguaglio">Conguaglio: <b className={d.conguaglio < 0 ? "text-rose-700" : "text-emerald-700"}>{fmtEUR(d.conguaglio)}</b> {d.conguaglio < 0 ? "(IVA detratta in più: da restituire in dichiarazione annuale)" : d.conguaglio > 0 ? "(ulteriore IVA detraibile)" : ""}</span>
    {d.registrazione ? <><span className="text-xs text-emerald-700" data-testid="prorata-registrato">Registrato in prima nota n. {d.registrazione.numero} del {d.registrazione.data}</span><Button size="sm" variant="outline" onClick={annulla} data-testid="prorata-annulla-btn">Annulla</Button></>
      : <Button size="sm" disabled={!d.conguaglio} onClick={reg} data-testid="prorata-registra-btn">Registra conguaglio al 31/12</Button>}
  </div>
);

export const ProRataCard = ({ anno, onChange }) => {
  const [d, setD] = useState(null);
  const [v, setV] = useState("");
  const load = () => api.get("/pro-rata", { params: { anno } }).then(({ data }) => { setD(data); setV(data.provvisorio ?? ""); }).catch(() => setD(null));
  useEffect(() => { load(); }, [anno]);
  if (!d) return null;
  const save = async (attivo, pct = v, a = anno) => {
    try { await api.put("/pro-rata", { attivo, anno: a, percentuale: Number(pct || 0) }); toast.success("Pro rata salvato"); load(); onChange?.(); } catch (e) { toast.error(errMsg(e)); }
  };
  const act = async (fn) => { try { await fn(); toast.success("Fatto"); load(); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <div className="mb-5 rounded-xl border border-slate-200 bg-white p-4 print:hidden" data-testid="prorata-card">
      <div className="flex flex-wrap items-center gap-4">
        <span className="flex items-center gap-2 font-semibold text-slate-800"><Percent className="h-4 w-4 text-violet-600" />Pro rata di detraibilità (art. 19 c. 5 e 19-bis)</span>
        <label className="flex items-center gap-2 text-sm">Attivo<Switch checked={d.attivo} onCheckedChange={(x) => save(x)} data-testid="prorata-switch" /></label>
        {d.attivo && <label className="flex items-center gap-2 text-sm">Provvisorio {anno}<Input type="number" min={0} max={100} value={v} onChange={(e) => setV(e.target.value)} className="h-8 w-20" data-testid="prorata-provvisorio" />%<Button size="sm" variant="outline" onClick={() => save(true)} disabled={v === ""} data-testid="prorata-salva-btn">Salva</Button></label>}
      </div>
      {d.attivo && <>
        <p className="mt-2 text-xs text-slate-500">Nelle liquidazioni periodiche l'IVA sugli acquisti è detratta con il pro rata provvisorio (di norma il definitivo dell'anno prima); la parte non detraibile va a costo. A fine anno il definitivo si calcola sulle vendite: operazioni con diritto alla detrazione (imponibili, N3, N6) / (le stesse + esenti N4), arrotondato all'unità.</p>
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
          <Kv l="Operazioni con detrazione" v={fmtEUR(d.operazioni_detraibili)} id="prorata-detr" />
          <Kv l="Operazioni esenti" v={fmtEUR(d.operazioni_esenti)} id="prorata-esenti" />
          <Kv l="Pro rata definitivo" v={`${d.definitivo}%`} tone="text-violet-700" id="prorata-definitivo" />
          <Kv l="IVA acquisti (prima del pro rata)" v={fmtEUR(d.iva_base)} id="prorata-base" />
          <Kv l="IVA detratta (provvisorio)" v={fmtEUR(d.iva_detratta)} id="prorata-detratta" />
          <Kv l="IVA spettante (definitivo)" v={fmtEUR(d.iva_spettante)} id="prorata-spettante" />
          <div className="col-span-2 flex items-end sm:col-span-4 lg:col-span-1"><Button size="sm" variant="outline" className="whitespace-normal text-left" onClick={() => save(true, d.definitivo, anno + 1)} data-testid="prorata-usa-btn">Usa {d.definitivo}% come provvisorio {anno + 1}</Button></div>
        </div>
        {d.provvisorio != null && <Conguaglio d={d} reg={() => act(() => api.post("/pro-rata/conguaglio", { anno }))} annulla={() => act(() => api.delete(`/pro-rata/conguaglio/${anno}`))} />}
      </>}
    </div>
  );
};

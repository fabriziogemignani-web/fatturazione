import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { fmtDate } from "@/lib/fe";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ContoSelect } from "@/components/ContoSelect";

const Gruppo = ({ g, conti, onChange, canEdit }) => (
  <div className="rounded-lg border border-slate-100 bg-slate-50 p-2">
    <div className="mb-1 text-xs font-semibold text-slate-600">IVA {g.aliquota}%{g.natura ? ` ${g.natura}` : ""}{g.codice_iva ? ` · codice ${g.codice_iva} (detr. ${g.detraibilita}%)` : ""}{g.peso != null && g.peso < 100 ? ` · ${g.peso}% dell'aliquota` : ""}</div>
    {g.conti.map((c, i) => (
      <div key={i} className="mb-1 flex items-center gap-2">
        <div className="min-w-0 flex-1">{canEdit ? <ContoSelect conti={conti} value={c.conto} onChange={(v) => onChange({ ...g, conti: g.conti.map((x, j) => (j === i ? { ...x, conto: v } : x)) })} testId={`modello-conto-${g.aliquota}-${i}`} /> : <span className="mono text-sm">{c.conto}</span>}</div>
        <Input type="number" min={0} max={100} value={c.quota} disabled={!canEdit} onChange={(e) => onChange({ ...g, conti: g.conti.map((x, j) => (j === i ? { ...x, quota: e.target.value } : x)) })} className="h-8 w-24 text-right" data-testid={`modello-quota-${g.aliquota}-${i}`} /><span className="text-xs text-slate-500">%</span>
        {canEdit && g.conti.length > 1 && <button onClick={() => onChange({ ...g, conti: g.conti.filter((_, j) => j !== i) })} className="text-xs text-rose-600" data-testid={`modello-rimuovi-${g.aliquota}-${i}`}>Togli</button>}
      </div>
    ))}
    {canEdit && <button onClick={() => onChange({ ...g, conti: [...g.conti, { conto: "", quota: 0 }] })} className="text-xs font-semibold text-blue-700" data-testid={`modello-aggiungi-${g.aliquota}`}>+ Aggiungi conto</button>}
  </div>
);

const Modello = ({ m, conti, canEdit, reload }) => {
  const [righe, setRighe] = useState(m.righe);
  const dirty = JSON.stringify(righe) !== JSON.stringify(m.righe);
  const save = async (attivo = m.attivo) => {
    try { await api.put(`/ai/modelli/${m.id}`, { attivo, righe: righe.map((g) => ({ ...g, conti: g.conti.map((c) => ({ ...c, quota: Number(c.quota) })) })) }); toast.success("Modello salvato"); reload(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div className={`rounded-xl border bg-white p-4 ${m.attivo ? "border-slate-200" : "border-dashed border-slate-300 bg-slate-50"}`} data-testid={`modello-${m.id}`}>
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <span className="font-semibold text-slate-800">{m.fornitore}</span>
        <span className="text-xs text-slate-500">usato {m.utilizzi || 0} volte · ultima fattura {m.ultima_fattura} · aggiornato {fmtDate(m.updated_at)}</span>
        <label className="ml-auto flex items-center gap-2 text-xs">Attivo<Switch checked={m.attivo} disabled={!canEdit} onCheckedChange={(v) => save(v)} data-testid={`modello-attivo-${m.id}`} /></label>
      </div>
      <div className="grid gap-2 md:grid-cols-2">{righe.map((g, i) => <Gruppo key={i} g={g} conti={conti} canEdit={canEdit} onChange={(n) => setRighe(righe.map((x, j) => (j === i ? n : x)))} />)}</div>
      {dirty && <div className="mt-2 flex gap-2"><Button size="sm" onClick={() => save()} data-testid={`modello-salva-${m.id}`}>Salva modifiche</Button><Button size="sm" variant="ghost" onClick={() => setRighe(m.righe)}>Annulla</Button></div>}
    </div>
  );
};

export const ModelliTab = ({ conti, canEdit }) => {
  const [list, setList] = useState(null);
  const load = () => api.get("/ai/modelli").then(({ data }) => setList(data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, []);
  if (!list) return <div className="text-sm text-slate-500">Caricamento…</div>;
  return (
    <div className="space-y-3" data-testid="modelli-tab">
      <p className="text-sm text-slate-600">Alla prima fattura di un fornitore i conti di costo vengono proposti dall'IA; quando registri la fattura i conti scelti (con le quote per aliquota) diventano il modello del fornitore. Dalle fatture successive la registrazione si compila con il modello, senza IA. Il modello si aggiorna a ogni registrazione; disattivalo per tornare alla proposta IA.</p>
      {list.length === 0 && <div className="rounded-xl border border-dashed border-slate-200 p-8 text-center text-sm text-slate-500" data-testid="modelli-empty">Nessun modello: si crea da solo alla prima registrazione di una fattura ricevuta.</div>}
      {list.map((m) => <Modello key={m.id + m.updated_at} m={m} conti={conti} canEdit={canEdit} reload={load} />)}
    </div>
  );
};

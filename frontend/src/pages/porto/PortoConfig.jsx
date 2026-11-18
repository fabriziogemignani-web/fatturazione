import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, Save } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { NSelect } from "@/components/ui/nselect";
import { ALIQUOTE, NATURE } from "@/lib/fe";
import { usePortoBase } from "@/lib/porto";

const Card = ({ title, children, id }) => <section className="mb-6 rounded-xl border border-slate-200 bg-white p-5" data-testid={id}><h2 className="mb-4 text-base font-bold text-slate-800">{title}</h2>{children}</section>;

const Stagione = () => {
  const [c, setC] = useState(null);
  useEffect(() => { api.get("/porto/config").then(({ data }) => setC(data)).catch(() => {}); }, []);
  if (!c) return null;
  const s = (k) => (e) => setC({ ...c, [k]: e.target.value });
  const save = async () => {
    try { await api.put("/porto/config", { alta_da: c.alta_da, alta_a: c.alta_a, aliquota: Number(c.aliquota), natura: Number(c.aliquota) ? null : c.natura }); toast.success("Impostazioni salvate"); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Card title="Stagione e IVA" id="porto-config-stagione">
      <div className="flex flex-wrap items-end gap-3 text-sm">
        <label>Alta stagione dal (MM-GG)<Input value={c.alta_da} onChange={s("alta_da")} className="w-28" data-testid="config-alta-da" /></label>
        <label>al (MM-GG)<Input value={c.alta_a} onChange={s("alta_a")} className="w-28" data-testid="config-alta-a" /></label>
        <label>Aliquota IVA ormeggi<NSelect value={String(c.aliquota)} onChange={s("aliquota")} className="w-28" data-testid="config-aliquota">{ALIQUOTE.map((a) => <option key={a} value={String(a)}>{a}%</option>)}</NSelect></label>
        {Number(c.aliquota) === 0 && <label>Natura<NSelect value={c.natura || ""} onChange={s("natura")} className="w-64" data-testid="config-natura"><option value="">Seleziona...</option>{NATURE.map((n) => <option key={n.code || n[0]} value={n.code || n[0]}>{n.label || n[1] || n.code}</option>)}</NSelect></label>}
        <Button onClick={save} data-testid="config-save"><Save className="mr-1 h-4 w-4" />Salva</Button>
      </div>
      <p className="mt-2 text-xs text-slate-500">Fuori da questo periodo si applicano i prezzi di bassa stagione. I prezzi del listino sono IVA esclusa.</p>
    </Card>
  );
};

const Listino = () => {
  const [f, setF] = useState([]);
  useEffect(() => { api.get("/porto/config").then(({ data }) => setF(data.listino || [])).catch(() => {}); }, []);
  const cols = [["da_m", "Da m"], ["a_m", "A m"], ["giorno_alta", "€/giorno alta"], ["giorno_bassa", "€/giorno bassa"], ["mese_alta", "€/mese alta"], ["mese_bassa", "€/mese bassa"], ["annuale", "€/anno"]];
  const upd = (i, k, v) => setF(f.map((x, j) => (j === i ? { ...x, [k]: v } : x)));
  const save = async () => {
    try { const { data } = await api.put("/porto/listino", { fasce: f.map((x) => Object.fromEntries(cols.map(([k]) => [k, Number(x[k] || 0)]))) }); setF(data); toast.success("Listino salvato"); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Card title="Listino per lunghezza barca" id="porto-config-listino">
      <div className="overflow-x-auto">
        <table className="text-sm"><thead><tr>{cols.map(([k, l]) => <th key={k} className="px-1 pb-1 text-left text-xs font-semibold text-slate-500">{l}</th>)}<th /></tr></thead>
          <tbody>{f.map((x, i) => (
            <tr key={i} data-testid={`listino-fascia-${i}`}>
              {cols.map(([k]) => <td key={k} className="px-1 py-0.5"><Input type="number" step="0.01" value={x[k] ?? ""} onChange={(e) => upd(i, k, e.target.value)} className="w-24" data-testid={`listino-${k}-${i}`} /></td>)}
              <td><Button size="icon" variant="ghost" onClick={() => setF(f.filter((_, j) => j !== i))} data-testid={`listino-del-${i}`}><Trash2 className="h-4 w-4 text-rose-600" /></Button></td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <div className="mt-3 flex gap-2">
        <Button variant="outline" size="sm" onClick={() => { const last = f[f.length - 1]; setF([...f, { da_m: last ? Math.round((Number(last.a_m) + 0.01) * 100) / 100 : 0, a_m: last ? Number(last.a_m) + 2 : 8 }]); }} data-testid="listino-add"><Plus className="mr-1 h-3.5 w-3.5" />Fascia</Button>
        <Button size="sm" onClick={save} data-testid="listino-save"><Save className="mr-1 h-3.5 w-3.5" />Salva listino</Button>
      </div>
    </Card>
  );
};

const Pontili = ({ base, reload }) => {
  const [nome, setNome] = useState("");
  const [serie, setSerie] = useState({ pontile_id: "", prefisso: "", da: 1, a: 10, lunghezza_max: 10, larghezza_max: 0 });
  const add = async () => { try { await api.post("/porto/pontili", { nome, ordine: base.pontili.length + 1 }); setNome(""); reload(); } catch (e) { toast.error(errMsg(e)); } };
  const delP = async (p) => { if (!window.confirm(`Eliminare ${p.nome}?`)) return; try { await api.delete(`/porto/pontili/${p.id}`); reload(); } catch (e) { toast.error(errMsg(e)); } };
  const crea = async () => {
    try { const { data } = await api.post("/porto/posti/serie", { ...serie, da: Number(serie.da), a: Number(serie.a), lunghezza_max: Number(serie.lunghezza_max), larghezza_max: Number(serie.larghezza_max || 0) }); toast.success(`Creati ${data.creati} posti${data.saltati ? `, ${data.saltati} già esistenti` : ""}`); reload(); } catch (e) { toast.error(errMsg(e)); }
  };
  const s = (k) => (e) => setSerie({ ...serie, [k]: e.target.value });
  return (
    <Card title="Pontili e creazione posti" id="porto-config-pontili">
      <div className="flex flex-wrap gap-2">
        {base.pontili.map((p) => (
          <span key={p.id} className="flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-sm" data-testid={`pontile-${p.id}`}>{p.nome} <span className="text-xs text-slate-500">({base.posti.filter((x) => x.pontile_id === p.id).length})</span>
            <button onClick={() => delP(p)} aria-label="Elimina" data-testid={`pontile-del-${p.id}`}><Trash2 className="h-3.5 w-3.5 text-rose-600" /></button></span>
        ))}
        <Input placeholder="Nuovo pontile (es. Pontile A)" value={nome} onChange={(e) => setNome(e.target.value)} className="w-56" data-testid="pontile-nome" />
        <Button size="sm" onClick={add} disabled={!nome.trim()} data-testid="pontile-add"><Plus className="mr-1 h-3.5 w-3.5" />Aggiungi</Button>
      </div>
      <div className="mt-5 flex flex-wrap items-end gap-2 border-t pt-4 text-sm">
        <label>Pontile<NSelect value={serie.pontile_id} onChange={s("pontile_id")} className="w-44" data-testid="serie-pontile"><option value="">Seleziona...</option>{base.pontili.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}</NSelect></label>
        <label>Prefisso<Input value={serie.prefisso} onChange={s("prefisso")} className="w-20" data-testid="serie-prefisso" /></label>
        <label>Da n.<Input type="number" value={serie.da} onChange={s("da")} className="w-20" data-testid="serie-da" /></label>
        <label>A n.<Input type="number" value={serie.a} onChange={s("a")} className="w-20" data-testid="serie-a" /></label>
        <label>Lungh. max (m)<Input type="number" step="0.1" value={serie.lunghezza_max} onChange={s("lunghezza_max")} className="w-24" data-testid="serie-lunghezza" /></label>
        <label>Largh. max (m)<Input type="number" step="0.1" value={serie.larghezza_max} onChange={s("larghezza_max")} className="w-24" data-testid="serie-larghezza" /></label>
        <Button onClick={crea} disabled={!serie.pontile_id} data-testid="serie-crea">Crea posti</Button>
      </div>
    </Card>
  );
};

const Posti = ({ base, reload }) => {
  const toggle = async (p) => {
    try { await api.put(`/porto/posti/${p.id}`, { ...p, fuori_servizio: !p.fuori_servizio }); reload(); } catch (e) { toast.error(errMsg(e)); }
  };
  const setLun = async (p, v) => { if (Number(v) > 0 && Number(v) !== p.lunghezza_max) { try { await api.put(`/porto/posti/${p.id}`, { ...p, lunghezza_max: Number(v) }); reload(); } catch (e) { toast.error(errMsg(e)); } } };
  const del = async (p) => { try { await api.delete(`/porto/posti/${p.id}`); reload(); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <Card title={`Posti barca (${base.posti.length})`} id="porto-config-posti">
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {base.posti.map((p) => (
          <div key={p.id} className="flex items-center gap-2 rounded-lg border border-slate-200 px-2 py-1 text-sm" data-testid={`posto-${p.codice}`}>
            <b className="w-12">{p.codice}</b>
            <Input type="number" step="0.1" defaultValue={p.lunghezza_max} onBlur={(e) => setLun(p, e.target.value)} className="h-7 w-16" title="Lunghezza massima (m)" data-testid={`posto-lunghezza-${p.codice}`} />
            <Switch checked={!p.fuori_servizio} onCheckedChange={() => toggle(p)} title="In servizio" data-testid={`posto-servizio-${p.codice}`} />
            <button className="ml-auto" onClick={() => del(p)} aria-label="Elimina posto" data-testid={`posto-del-${p.codice}`}><Trash2 className="h-3.5 w-3.5 text-rose-600" /></button>
          </div>
        ))}
      </div>
    </Card>
  );
};

export default function PortoConfig() {
  const [base, reload] = usePortoBase();
  return (
    <div data-testid="porto-config-page">
      <PageHeader eyebrow="Porto turistico" title="Configurazione porto" />
      <Stagione />
      <Listino />
      <Pontili base={base} reload={reload} />
      <Posti base={base} reload={reload} />
    </div>
  );
}

import { useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NSelect } from "@/components/ui/nselect";

const EMPTY = { codice: "", descrizione: "", tipo: "acquisti", causali: [] };

const Editor = ({ init, causali, onSave, onCancel }) => {
  const [f, setF] = useState(init);
  const opts = causali.filter((c) => c.registro === f.tipo);
  const toggle = (c) => setF({ ...f, causali: f.causali.includes(c) ? f.causali.filter((x) => x !== c) : [...f.causali, c] });
  return (
    <div className="space-y-3 rounded-lg border border-blue-200 bg-blue-50/40 p-4" data-testid="reg-editor">
      <div className="grid gap-3 sm:grid-cols-4">
        <label className="text-xs text-slate-600">Codice<Input value={f.codice} maxLength={6} onChange={(e) => setF({ ...f, codice: e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "") })} className="bg-white" data-testid="reg-codice" /></label>
        <label className="text-xs text-slate-600 sm:col-span-2">Descrizione<Input value={f.descrizione} onChange={(e) => setF({ ...f, descrizione: e.target.value })} className="bg-white" data-testid="reg-descrizione" /></label>
        <label className="text-xs text-slate-600">Tipo<NSelect className="block w-full" disabled={!!init.predefinito} value={f.tipo} onChange={(e) => setF({ ...f, tipo: e.target.value, causali: [] })} data-testid="reg-tipo"><option value="acquisti">Acquisti</option><option value="vendite">Vendite</option></NSelect></label>
      </div>
      <div>
        <div className="mb-1 text-xs font-semibold text-slate-600">Causali contabili collegate</div>
        <div className="flex flex-wrap gap-2">
          {opts.length === 0 && <span className="text-xs text-slate-500">Nessuna causale IVA {f.tipo} (attiva la contabilità generale o crea le causali in Tabelle contabili)</span>}
          {opts.map((c) => (
            <label key={c.codice} className={`flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-xs ${f.causali.includes(c.codice) ? "border-blue-600 bg-blue-600 text-white" : "border-slate-300 bg-white text-slate-700"}`} data-testid={`reg-causale-${c.codice}`}>
              <input type="checkbox" className="hidden" checked={f.causali.includes(c.codice)} onChange={() => toggle(c.codice)} />{c.codice} · {c.descrizione}
            </label>
          ))}
        </div>
      </div>
      <div className="flex gap-2"><Button onClick={() => onSave(f)} disabled={!f.codice || !f.descrizione} data-testid="reg-save">Salva registro</Button><Button variant="outline" onClick={onCancel}>Annulla</Button></div>
    </div>
  );
};

export const RegistriIvaGestione = ({ data, reload }) => {
  const [edit, setEdit] = useState(null);
  const save = async (f) => {
    try {
      if (f.id) await api.put(`/stampe-fiscali/registri/${f.id}`, f); else await api.post("/stampe-fiscali/registri", f);
      toast.success("Registro salvato"); setEdit(null); reload();
    } catch (e) { toast.error(errMsg(e)); }
  };
  const del = async (r) => {
    if (!window.confirm(`Eliminare il registro ${r.codice}? I documenti torneranno nel registro proposto dal programma.`)) return;
    try { await api.delete(`/stampe-fiscali/registri/${r.id}`); toast.success("Registro eliminato"); reload(); } catch (e) { toast.error(errMsg(e)); }
  };
  const linked = (r) => data.causali.filter((c) => c.registro_id === r.id).map((c) => c.codice);
  return (
    <div className="space-y-4">
      <p className="text-xs text-slate-500">Ogni documento finisce nel registro collegato alla sua causale: il programma propone il registro (intra UE → registro CEE, split payment PA → registro SPL, altrimenti il predefinito) e puoi spostarlo dalla scheda Registri IVA finché il periodo non è stampato in definitiva.</p>
      {edit && !edit.id && <Editor init={EMPTY} causali={data.causali} onSave={save} onCancel={() => setEdit(null)} />}
      {!edit && <Button onClick={() => setEdit({})} data-testid="reg-new"><Plus className="mr-2 h-4 w-4" />Nuovo registro IVA</Button>}
      <div className="grid gap-3 lg:grid-cols-2">
        {data.registri.map((r) => (edit?.id === r.id ? <Editor key={r.id} init={{ ...r, causali: linked(r) }} causali={data.causali} onSave={save} onCancel={() => setEdit(null)} /> : (
          <div key={r.id} className={`rounded-xl border-l-4 bg-white p-4 shadow-sm ${r.tipo === "vendite" ? "border-blue-600" : "border-emerald-600"}`} data-testid={`reg-card-${r.codice}`}>
            <div className="flex items-start justify-between gap-2">
              <div><div className="font-semibold">{r.codice} · {r.descrizione}</div><div className="text-xs text-slate-500">{r.tipo === "vendite" ? "Vendite" : "Acquisti"}{r.predefinito ? " · predefinito" : ""}</div></div>
              <div className="flex gap-1">
                <Button size="sm" variant="outline" onClick={() => setEdit(r)} data-testid={`reg-edit-${r.codice}`}>Modifica</Button>
                {!r.predefinito && <Button size="sm" variant="outline" onClick={() => del(r)} data-testid={`reg-del-${r.codice}`}><Trash2 className="h-4 w-4" /></Button>}
              </div>
            </div>
            <div className="mt-2 text-xs text-slate-600">Causali: {linked(r).join(", ") || "nessuna"}</div>
          </div>
        )))}
      </div>
    </div>
  );
};

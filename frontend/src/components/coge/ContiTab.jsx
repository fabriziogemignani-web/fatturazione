import { useState } from "react";
import { toast } from "sonner";
import { Plus, Pencil, Trash2, Check, X } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const TIPO_CLS = { attivita: "bg-sky-50 text-sky-700", passivita: "bg-violet-50 text-violet-700", costo: "bg-amber-50 text-amber-700", ricavo: "bg-emerald-50 text-emerald-700", chiusura: "bg-slate-100 text-slate-600" };
const TIPI = { attivita: "Attività", passivita: "Passività", costo: "Costo", ricavo: "Ricavo", chiusura: "Chiusura" };

const NewConto = ({ onSaved }) => {
  const [f, setF] = useState({ codice: "", descrizione: "", tipo: "attivita" });
  const save = async () => {
    try { await api.post("/contabilita/conti", f); toast.success("Conto creato"); setF({ codice: "", descrizione: "", tipo: f.tipo }); onSaved(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div className="mb-4 flex flex-wrap items-end gap-2 rounded-xl border border-slate-200 bg-white p-4" data-testid="new-conto-form">
      <label className="text-xs text-slate-600">Codice<Input value={f.codice} onChange={(e) => setF({ ...f, codice: e.target.value })} placeholder="es. 30.07.017" className="mono w-36" data-testid="new-conto-codice" /></label>
      <label className="flex-1 text-xs text-slate-600">Descrizione<Input value={f.descrizione} onChange={(e) => setF({ ...f, descrizione: e.target.value })} data-testid="new-conto-descrizione" /></label>
      {!f.codice.includes(".") && (
        <label className="text-xs text-slate-600">Tipo (solo per nuovi mastri)
          <select value={f.tipo} onChange={(e) => setF({ ...f, tipo: e.target.value })} className="block h-9 rounded-md border border-slate-200 px-2 text-sm" data-testid="new-conto-tipo">
            {Object.entries(TIPI).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </label>
      )}
      <Button onClick={save} data-testid="new-conto-save"><Plus className="mr-1 h-4 w-4" />Aggiungi</Button>
      <p className="w-full text-xs text-slate-500">Formato: 00 mastro · 00.00 conto · 00.00.000 sottoconto. Solo i sottoconti si usano nelle registrazioni; il tipo è ereditato dal mastro.</p>
    </div>
  );
};

const Row = ({ c, canEdit, onSaved }) => {
  const [ed, setEd] = useState(null);
  const save = async () => {
    try { await api.put(`/contabilita/conti/${c.id}`, { descrizione: ed }); setEd(null); onSaved(); } catch (e) { toast.error(errMsg(e)); }
  };
  const del = async () => {
    if (!window.confirm(`Eliminare il conto ${c.codice}?`)) return;
    try { await api.delete(`/contabilita/conti/${c.id}`); toast.success("Conto eliminato"); onSaved(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <tr className={c.livello === 1 ? "bg-slate-50 font-bold" : c.livello === 2 ? "font-semibold" : ""} data-testid={`conto-row-${c.codice}`}>
      <td className={`mono px-3 py-2 text-xs ${c.livello === 3 ? "pl-8" : c.livello === 2 ? "pl-5" : ""}`}>{c.codice}</td>
      <td className="px-3 py-2 text-sm">{ed !== null ? <Input value={ed} onChange={(e) => setEd(e.target.value)} className="h-8" data-testid={`conto-edit-input-${c.codice}`} /> : c.descrizione}</td>
      <td className="px-3 py-2"><span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${TIPO_CLS[c.tipo]}`}>{TIPI[c.tipo]}</span></td>
      <td className="px-3 py-2 text-xs text-slate-500">{c.livello === 3 ? (c.movimentato ? "movimentato" : "") : c.livello === 2 ? "conto" : "mastro"}</td>
      <td className="whitespace-nowrap px-3 py-2 text-right">
        {canEdit && (ed !== null ? <>
          <button onClick={save} className="rounded p-1.5 text-emerald-600 hover:bg-emerald-50" aria-label="Salva" data-testid={`conto-edit-save-${c.codice}`}><Check className="h-4 w-4" /></button>
          <button onClick={() => setEd(null)} className="rounded p-1.5 text-slate-500 hover:bg-slate-100" aria-label="Annulla"><X className="h-4 w-4" /></button>
        </> : <>
          <button onClick={() => setEd(c.descrizione)} className="rounded p-1.5 text-slate-500 hover:bg-slate-100" aria-label="Modifica" data-testid={`conto-edit-${c.codice}`}><Pencil className="h-4 w-4" /></button>
          {!c.movimentato && <button onClick={del} className="rounded p-1.5 text-slate-500 hover:bg-rose-50 hover:text-rose-600" aria-label="Elimina" data-testid={`conto-delete-${c.codice}`}><Trash2 className="h-4 w-4" /></button>}
        </>)}
      </td>
    </tr>
  );
};

export const ContiTab = ({ conti, reload, canEdit }) => {
  const [q, setQ] = useState("");
  const rows = q ? conti.filter((c) => `${c.codice} ${c.descrizione}`.toLowerCase().includes(q.toLowerCase())) : conti;
  return (
    <div>
      {canEdit && <NewConto onSaved={reload} />}
      <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cerca per codice o descrizione…" className="mb-3 max-w-sm bg-white" data-testid="conti-search" />
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm" data-testid="conti-table">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500"><tr><th className="px-3 py-3">Codice</th><th className="px-3 py-3">Descrizione</th><th className="px-3 py-3">Tipo</th><th className="px-3 py-3">Livello</th><th /></tr></thead>
          <tbody className="divide-y divide-slate-100">{rows.map((c) => <Row key={c.id} c={c} canEdit={canEdit} onSaved={reload} />)}</tbody>
        </table>
      </div>
    </div>
  );
};

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Pencil, Trash2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { ContoSelect, contoLabel } from "@/components/ContoSelect";

const CFG = {
  causali: {
    url: "/contabilita/causali", label: "causale", empty: { codice: "", descrizione: "", registro: "nessuno", conto_dare: "", conto_avere: "" },
    cols: ["Codice", "Descrizione", "Registro IVA", "Conti proposti"],
    cells: (x, conti) => [x.registro === "nessuno" ? "—" : x.registro, [x.conto_dare && `D ${contoLabel(conti, x.conto_dare)}`, x.conto_avere && `A ${contoLabel(conti, x.conto_avere)}`].filter(Boolean).join(" · ") || "—"],
  },
  iva: {
    url: "/contabilita/codici-iva", label: "codice IVA", empty: { codice: "", descrizione: "", aliquota: 22, natura: "", reverse_charge: false, detraibilita: 100 },
    cols: ["Codice", "Descrizione", "Aliquota / natura", "Detraibilità"],
    cells: (x) => [`${x.aliquota}%${x.natura ? ` · ${x.natura}` : ""}${x.reverse_charge ? " · reverse charge" : ""}`, `${x.detraibilita}%`],
  },
};

const Form = ({ kind, f, setF, conti }) => (
  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
    <label className="text-xs text-slate-600">Codice<Input value={f.codice} disabled={f.sistema} onChange={(e) => setF({ ...f, codice: e.target.value.toUpperCase() })} className="mono" data-testid="tab-form-codice" /></label>
    <label className="text-xs text-slate-600">Descrizione<Input value={f.descrizione} onChange={(e) => setF({ ...f, descrizione: e.target.value })} data-testid="tab-form-descrizione" /></label>
    {kind === "causali" ? <>
      <label className="text-xs text-slate-600 sm:col-span-2">Registro IVA
        <select value={f.registro} onChange={(e) => setF({ ...f, registro: e.target.value })} className="block h-9 w-full rounded-md border border-slate-200 px-2 text-sm" data-testid="tab-form-registro">
          <option value="nessuno">Nessuno</option><option value="vendite">Vendite</option><option value="acquisti">Acquisti</option>
        </select>
      </label>
      <label className="text-xs text-slate-600">Conto proposto in Dare<ContoSelect conti={conti} value={f.conto_dare} onChange={(v) => setF({ ...f, conto_dare: v })} allowEmpty="Nessuno" testId="tab-form-conto-dare" /></label>
      <label className="text-xs text-slate-600">Conto proposto in Avere<ContoSelect conti={conti} value={f.conto_avere} onChange={(v) => setF({ ...f, conto_avere: v })} allowEmpty="Nessuno" testId="tab-form-conto-avere" /></label>
    </> : <>
      <label className="text-xs text-slate-600">Aliquota %<Input type="number" step="0.01" value={f.aliquota} onChange={(e) => setF({ ...f, aliquota: e.target.value })} data-testid="tab-form-aliquota" /></label>
      <label className="text-xs text-slate-600">Natura (per aliquota 0)<Input value={f.natura || ""} onChange={(e) => setF({ ...f, natura: e.target.value.toUpperCase() })} placeholder="es. N2.2" data-testid="tab-form-natura" /></label>
      <label className="text-xs text-slate-600">Detraibilità %<Input type="number" step="1" value={f.detraibilita} onChange={(e) => setF({ ...f, detraibilita: e.target.value })} data-testid="tab-form-detraibilita" /></label>
      <label className="flex items-center justify-between gap-3 self-end pb-2 text-sm text-slate-700">Reverse charge<Switch checked={!!f.reverse_charge} onCheckedChange={(v) => setF({ ...f, reverse_charge: v })} data-testid="tab-form-rc" /></label>
    </>}
  </div>
);

export const TabellaTab = ({ kind, conti, canEdit }) => {
  const c = CFG[kind];
  const [rows, setRows] = useState([]);
  const [f, setF] = useState(null);
  const load = () => api.get(c.url).then(({ data }) => setRows(data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, [kind]); // eslint-disable-line react-hooks/exhaustive-deps
  const save = async () => {
    const body = kind === "iva" ? { ...f, aliquota: Number(f.aliquota || 0), detraibilita: Number(f.detraibilita || 0), natura: f.natura || null } : f;
    try { f.id ? await api.put(`${c.url}/${f.id}`, body) : await api.post(c.url, body); toast.success("Salvato"); setF(null); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  const del = async (x) => {
    if (!window.confirm(`Eliminare ${x.codice}?`)) return;
    try { await api.delete(`${c.url}/${x.id}`); toast.success("Eliminato"); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div>
      {canEdit && <div className="mb-3 flex justify-end"><Button onClick={() => setF({ ...c.empty })} data-testid={`new-${kind}-btn`}><Plus className="mr-1 h-4 w-4" />Nuovo {c.label}</Button></div>}
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm" data-testid={`${kind}-table`}>
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500"><tr>{c.cols.map((h) => <th key={h} className="px-3 py-3">{h}</th>)}<th /></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((x) => (
              <tr key={x.id} data-testid={`${kind}-row-${x.codice}`}>
                <td className="mono px-3 py-2 text-xs font-semibold">{x.codice}</td><td className="px-3 py-2">{x.descrizione}{x.sistema && <span className="ml-2 rounded bg-slate-100 px-1.5 text-[10px] text-slate-500">sistema</span>}</td>
                {c.cells(x, conti).map((v, i) => <td key={i} className="px-3 py-2 text-xs text-slate-600">{v}</td>)}
                <td className="whitespace-nowrap px-3 py-2 text-right">{canEdit && <>
                  <button onClick={() => setF({ ...x })} className="rounded p-1.5 text-slate-500 hover:bg-slate-100" aria-label="Modifica" data-testid={`${kind}-edit-${x.codice}`}><Pencil className="h-4 w-4" /></button>
                  {!x.sistema && <button onClick={() => del(x)} className="rounded p-1.5 text-slate-500 hover:bg-rose-50 hover:text-rose-600" aria-label="Elimina" data-testid={`${kind}-delete-${x.codice}`}><Trash2 className="h-4 w-4" /></button>}
                </>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Dialog open={!!f} onOpenChange={(v) => !v && setF(null)}>
        <DialogContent className="bg-white sm:max-w-xl" data-testid={`${kind}-dialog`}>
          <DialogHeader><DialogTitle>{f?.id ? `Modifica ${c.label}` : `Nuovo ${c.label}`}</DialogTitle></DialogHeader>
          {f && <Form kind={kind} f={f} setF={setF} conti={conti} />}
          <DialogFooter><Button variant="outline" onClick={() => setF(null)}>Annulla</Button><Button onClick={save} data-testid="tab-form-save">Salva</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

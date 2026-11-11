import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Trash2, Pencil } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

const VUOTA = () => ({ protocollo: "", data: "", anno: new Date().getFullYear(), importo: "", verificata: false, revocata: false, note: "" });

const Barra = ({ x }) => {
  const pct = Math.max(0, Math.min(100, x.percentuale_residua));
  return (
    <div className="mt-1 h-1.5 w-full rounded-full bg-slate-100">
      <div className={`h-1.5 rounded-full ${pct <= 10 ? "bg-rose-500" : pct <= 30 ? "bg-amber-500" : "bg-emerald-500"}`} style={{ width: `${pct}%` }} />
    </div>
  );
};

export const IntentiCard = ({ partyId }) => {
  const [rows, setRows] = useState(null);
  const [f, setF] = useState(null);
  const load = useCallback(() => { api.get("/intenti", { params: { party_id: partyId } }).then(({ data }) => setRows(data)).catch((e) => toast.error(errMsg(e))); }, [partyId]);
  useEffect(() => { load(); }, [load]);
  const save = async () => {
    try {
      const body = { ...f, party_id: partyId, importo: Number(f.importo), anno: Number(f.anno) };
      if (f.id) await api.put(`/intenti/${f.id}`, body); else await api.post("/intenti", body);
      toast.success("Dichiarazione d'intento salvata");
      setF(null);
      load();
    } catch (e) { toast.error(errMsg(e)); }
  };
  const del = async (x) => {
    if (!window.confirm(`Eliminare la dichiarazione ${x.protocollo}?`)) return;
    try { await api.delete(`/intenti/${x.id}`); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  if (!rows) return null;
  return (
    <div className="rounded-lg border border-slate-200 p-3" data-testid="intenti-card">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-600">Dichiarazioni d'intento (plafond)</span>
        {!f && <Button size="sm" variant="outline" onClick={() => setF(VUOTA())} data-testid="intenti-add-btn">Aggiungi</Button>}
      </div>
      {rows.length === 0 && !f && <p className="text-xs text-slate-500">Nessuna dichiarazione: le fatture con natura N3.5 verranno bloccate.</p>}
      <ul className="space-y-2">
        {rows.map((x) => (
          <li key={x.id} className={`rounded-md border px-3 py-2 text-xs ${x.revocata ? "border-slate-200 opacity-60" : "border-slate-200"}`} data-testid={`intento-${x.id}`}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span><b className="mono">{x.protocollo}</b> del {fmtDate(x.data)} · anno {x.anno}{x.revocata && " · revocata"}{x.verificata && " · verificata"}</span>
              <span className="flex items-center gap-1">
                <button onClick={() => setF({ ...x })} className="text-slate-500 hover:text-slate-900" data-testid={`intento-edit-${x.id}`}><Pencil className="h-3.5 w-3.5" /></button>
                {!x.utilizzato && <button onClick={() => del(x)} className="text-rose-600" data-testid={`intento-del-${x.id}`}><Trash2 className="h-3.5 w-3.5" /></button>}
              </span>
            </div>
            <div className="mt-1 flex justify-between text-slate-600"><span>Plafond {fmtEUR(x.importo)} · usato {fmtEUR(x.utilizzato)}</span><b data-testid={`intento-residuo-${x.id}`}>Residuo {fmtEUR(x.residuo)}</b></div>
            <Barra x={x} />
          </li>
        ))}
      </ul>
      {f && (
        <div className="mt-2 grid grid-cols-2 gap-2 rounded-md bg-slate-50 p-2 sm:grid-cols-4" data-testid="intento-form">
          <label className="col-span-2 text-xs text-slate-600">Protocollo ricevuta<Input value={f.protocollo} onChange={(e) => setF({ ...f, protocollo: e.target.value })} placeholder="12345678901234567-000001" className="mono" data-testid="intento-protocollo-input" /></label>
          <label className="text-xs text-slate-600">Data ricevuta<Input type="date" value={f.data} onChange={(e) => setF({ ...f, data: e.target.value })} data-testid="intento-data-input" /></label>
          <label className="text-xs text-slate-600">Anno<Input type="number" value={f.anno} onChange={(e) => setF({ ...f, anno: e.target.value })} data-testid="intento-anno-input" /></label>
          <label className="col-span-2 text-xs text-slate-600">Importo plafond €<Input type="number" step="0.01" value={f.importo} onChange={(e) => setF({ ...f, importo: e.target.value })} data-testid="intento-importo-input" /></label>
          <label className="flex items-center gap-2 text-xs"><Switch checked={f.verificata} onCheckedChange={(v) => setF({ ...f, verificata: v })} data-testid="intento-verificata" />Verificata sul sito AdE</label>
          <label className="flex items-center gap-2 text-xs"><Switch checked={f.revocata} onCheckedChange={(v) => setF({ ...f, revocata: v })} data-testid="intento-revocata" />Revocata</label>
          <div className="col-span-2 flex justify-end gap-2 sm:col-span-4">
            <Button size="sm" variant="outline" onClick={() => setF(null)}>Annulla</Button>
            <Button size="sm" onClick={save} data-testid="intento-save-btn">Salva dichiarazione</Button>
          </div>
        </div>
      )}
    </div>
  );
};

export const IntentiPanel = () => {
  const [rows, setRows] = useState(null);
  useEffect(() => { api.get("/intenti/avvisi").then(({ data }) => setRows(data)).catch(() => {}); }, []);
  if (!rows || rows.length === 0) return null;
  return (
    <div className="mt-6 rounded-xl border border-amber-200 bg-white shadow-sm" data-testid="intenti-panel">
      <div className="border-b border-amber-100 px-5 py-4"><h3 className="font-semibold text-slate-900">Plafond dichiarazioni d'intento in esaurimento</h3><p className="text-xs text-slate-500">Residuo sotto il 10%: chiedi al cliente una nuova dichiarazione.</p></div>
      <ul className="divide-y divide-slate-100">
        {rows.map((x) => (
          <li key={x.id} className="flex flex-wrap items-center justify-between gap-2 px-5 py-3 text-sm" data-testid={`intenti-panel-${x.id}`}>
            <span><b>{x.cliente}</b> · <span className="mono text-xs">{x.protocollo}</span> · anno {x.anno}</span>
            <span className={x.residuo <= 0 ? "font-semibold text-rose-700" : "font-semibold text-amber-700"}>{x.residuo <= 0 ? "Esaurito" : `Residuo ${fmtEUR(x.residuo)}`} su {fmtEUR(x.importo)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
};

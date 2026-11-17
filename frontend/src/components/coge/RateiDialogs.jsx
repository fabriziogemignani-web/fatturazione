import { NSelect } from "@/components/ui/nselect";

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { SearchPicker } from "@/components/SearchPicker";
import { useConti, ContoSelect } from "@/components/ContoSelect";
import { NOMI_RR, proponiRR } from "@/components/RateoBox";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";

const sel = "block h-9 rounded-md border border-slate-200 bg-white px-2 text-sm";
const today = () => { const d = new Date(); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10); };

export const ModificaRR = ({ x, anno, onClose, onDone }) => {
  const [f, setF] = useState({ competenza_dal: x.competenza_dal, competenza_al: x.competenza_al, tipo: x.tipo, note: x.note || "" });
  const save = async () => { try { await api.put(`/contabilita/ratei/${x.id}`, f, { params: { anno } }); toast.success("Rateo/risconto aggiornato"); onDone(); onClose(); } catch (e) { toast.error(errMsg(e)); } };
  const prop = proponiRR(x.data_registrazione, f.competenza_dal, f.competenza_al);
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="bg-white sm:max-w-lg" data-testid="rr-edit-dialog">
        <DialogHeader><DialogTitle>Modifica · {x.documento} {x.party_nome}</DialogTitle></DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <label className="text-xs text-slate-600">Competenza dal<Input type="date" value={f.competenza_dal} onChange={(e) => setF({ ...f, competenza_dal: e.target.value })} data-testid="rr-edit-dal" /></label>
          <label className="text-xs text-slate-600">Competenza al<Input type="date" value={f.competenza_al} onChange={(e) => setF({ ...f, competenza_al: e.target.value })} data-testid="rr-edit-al" /></label>
          <label className="text-xs text-slate-600">Tipo<NSelect className={`${sel} w-full`} value={f.tipo} onChange={(e) => setF({ ...f, tipo: e.target.value })} data-testid="rr-edit-tipo">{["risconto", "rateo"].map((k) => <option key={k} value={k}>{NOMI_RR[x.origine][k]}</option>)}</NSelect></label>
          <label className="text-xs text-slate-600">Note<Input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} data-testid="rr-edit-note" /></label>
        </div>
        <p className="text-xs text-slate-500">{prop ? `Proposto: ${NOMI_RR[x.origine][prop]}` : "Competenza tutta nell'esercizio di registrazione"} · le contabilizzazioni in simulazione vengono annullate e vanno rifatte.</p>
        <DialogFooter><Button variant="outline" onClick={onClose}>Annulla</Button><Button onClick={save} data-testid="rr-edit-save">Salva</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const Righe = ({ righe, set, conti, tipo }) => (
  <div className="space-y-2">
    {righe.map((r, i) => (
      <div key={i} className="flex gap-2">
        <ContoSelect conti={conti} tipi={[tipo]} value={r.conto} onChange={(v) => set(righe.map((x, j) => (j === i ? { ...x, conto: v } : x)))} testId={`rr-new-conto-${i}`} />
        <Input type="number" step="0.01" placeholder="Importo €" value={r.importo} onChange={(e) => set(righe.map((x, j) => (j === i ? { ...x, importo: e.target.value } : x)))} className="w-36 text-right" data-testid={`rr-new-importo-${i}`} />
        {righe.length > 1 && <button className="text-rose-600" onClick={() => set(righe.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" /></button>}
      </div>
    ))}
    <Button size="sm" variant="outline" onClick={() => set([...righe, { conto: "", importo: "" }])} data-testid="rr-new-add-riga"><Plus className="mr-1 h-3.5 w-3.5" />Conto</Button>
  </div>
);

export const NuovoRR = ({ onClose, onDone }) => {
  const [conti] = useConti();
  const [parties, setParties] = useState([]);
  const [f, setF] = useState({ origine: "acquisto", party_id: "", documento: "", data_documento: today(), data_registrazione: today(), competenza_dal: "", competenza_al: "", tipo: "", note: "", righe: [{ conto: "", importo: "" }] });
  useEffect(() => { api.get("/parties").then(({ data }) => setParties(data)).catch(() => {}); }, []);
  const ruolo = f.origine === "acquisto" ? "fornitore" : "cliente";
  const items = useMemo(() => parties.filter((p) => p.tipo === ruolo).map((p) => ({ key: p.id, label: p.denominazione, sub: p.partita_iva })), [parties, ruolo]);
  const setDate = (patch) => { const n = { ...f, ...patch }; n.tipo = proponiRR(n.data_registrazione, n.competenza_dal, n.competenza_al) || n.tipo; setF(n); };
  const save = async () => {
    try { await api.post("/contabilita/ratei", { ...f, righe: f.righe.map((r) => ({ conto: r.conto, importo: Number(r.importo) })) }); toast.success("Rateo/risconto inserito in archivio"); onDone(); onClose(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto bg-white sm:max-w-2xl" data-testid="rr-new-dialog">
        <DialogHeader><DialogTitle>Nuovo rateo / risconto</DialogTitle></DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-xs text-slate-600">Documento di<NSelect className={`${sel} w-full`} value={f.origine} onChange={(e) => setF({ ...f, origine: e.target.value, party_id: "", righe: [{ conto: "", importo: "" }] })} data-testid="rr-new-origine"><option value="acquisto">Acquisto (fornitore)</option><option value="vendita">Vendita (cliente)</option></NSelect></label>
          <label className="text-xs text-slate-600">{ruolo === "cliente" ? "Cliente" : "Fornitore"}<SearchPicker items={items} value={items.find((i) => i.key === f.party_id)?.label} onPick={(i) => setF({ ...f, party_id: i.key })} onClear={() => setF({ ...f, party_id: "" })} placeholder={`Cerca ${ruolo}`} testId="rr-new-party" className="w-full" /></label>
          <label className="text-xs text-slate-600">Numero documento<Input value={f.documento} onChange={(e) => setF({ ...f, documento: e.target.value })} data-testid="rr-new-documento" /></label>
          <label className="text-xs text-slate-600">Data documento<Input type="date" value={f.data_documento} onChange={(e) => setF({ ...f, data_documento: e.target.value })} data-testid="rr-new-data-doc" /></label>
          <label className="text-xs text-slate-600">Data registrazione<Input type="date" value={f.data_registrazione} onChange={(e) => setDate({ data_registrazione: e.target.value })} data-testid="rr-new-data-reg" /></label>
          <label className="text-xs text-slate-600">Tipo<NSelect className={`${sel} w-full`} value={f.tipo} onChange={(e) => setF({ ...f, tipo: e.target.value })} data-testid="rr-new-tipo"><option value="">Scegli…</option>{["risconto", "rateo"].map((k) => <option key={k} value={k}>{NOMI_RR[f.origine][k]}</option>)}</NSelect></label>
          <label className="text-xs text-slate-600">Competenza dal<Input type="date" value={f.competenza_dal} onChange={(e) => setDate({ competenza_dal: e.target.value })} data-testid="rr-new-dal" /></label>
          <label className="text-xs text-slate-600">Competenza al<Input type="date" value={f.competenza_al} onChange={(e) => setDate({ competenza_al: e.target.value })} data-testid="rr-new-al" /></label>
        </div>
        <div className="text-xs font-semibold text-slate-600">Conti di {f.origine === "acquisto" ? "costo" : "ricavo"} e imponibile</div>
        <Righe righe={f.righe} set={(righe) => setF({ ...f, righe })} conti={conti} tipo={f.origine === "acquisto" ? "costo" : "ricavo"} />
        <DialogFooter><Button variant="outline" onClick={onClose}>Annulla</Button>
          <Button onClick={save} disabled={!f.party_id || !f.documento || !f.tipo || !f.competenza_dal || !f.competenza_al || f.righe.some((r) => !r.conto || !Number(r.importo))} data-testid="rr-new-save">Inserisci</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

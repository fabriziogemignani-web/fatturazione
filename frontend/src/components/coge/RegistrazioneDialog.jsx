import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, today } from "@/lib/fe";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { ContoSelect } from "@/components/ContoSelect";
import { SaldacontoPanel } from "@/components/coge/SaldacontoPanel";

const blank = () => ({ conto: "", dare: "", avere: "", party_id: "", note: "" });
const n = (v) => Math.round(Number(v || 0) * 100) / 100;

const Riga = ({ r, i, conti, parties, set, del }) => {
  const party = ["05.01", "13.02"].some((p) => r.conto.startsWith(p));
  return (
    <div className="grid grid-cols-12 items-center gap-2 border-b border-slate-100 py-2" data-testid={`reg-riga-${i}`}>
      <div className="col-span-12 sm:col-span-5">
        <ContoSelect conti={conti} value={r.conto} onChange={(v) => set({ conto: v })} testId={`reg-riga-conto-${i}`} />
        {party && (
          <select value={r.party_id || ""} onChange={(e) => set({ party_id: e.target.value })} className="mt-1 h-8 w-full rounded-md border border-slate-200 px-2 text-xs" data-testid={`reg-riga-party-${i}`}>
            <option value="">Nessun cliente/fornitore</option>
            {parties.filter((p) => (r.conto.startsWith("05.01") ? p.tipo === "cliente" : p.tipo === "fornitore")).map((p) => <option key={p.id} value={p.id}>{p.denominazione}</option>)}
          </select>
        )}
      </div>
      <Input className="col-span-4 sm:col-span-2 text-right" type="number" step="0.01" min={0} placeholder="Dare" value={r.dare} onChange={(e) => set({ dare: e.target.value, avere: e.target.value ? "" : r.avere })} data-testid={`reg-riga-dare-${i}`} />
      <Input className="col-span-4 sm:col-span-2 text-right" type="number" step="0.01" min={0} placeholder="Avere" value={r.avere} onChange={(e) => set({ avere: e.target.value, dare: e.target.value ? "" : r.dare })} data-testid={`reg-riga-avere-${i}`} />
      <Input className="col-span-3 sm:col-span-2" placeholder="Nota" value={r.note} onChange={(e) => set({ note: e.target.value })} data-testid={`reg-riga-note-${i}`} />
      <button onClick={del} className="col-span-1 rounded p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600" aria-label="Elimina riga" data-testid={`reg-riga-del-${i}`}><Trash2 className="h-4 w-4" /></button>
    </div>
  );
};

export const RegistrazioneDialog = ({ open, item, conti, causali, onClose, onSaved }) => {
  const [f, setF] = useState({ data: today(), causale: "GE", descrizione: "", righe: [blank(), blank()] });
  const [parties, setParties] = useState([]);
  const [busy, setBusy] = useState(false);
  const [sc, setSc] = useState([]);
  const [auto, setAuto] = useState(true);
  useEffect(() => {
    if (!open) return;
    setSc([]);
    setAuto(!item);
    if (item) api.get(`/contabilita/saldaconto/registrazione/${item.id}`).then(({ data }) => setSc(data.map((x) => ({ invoice_id: x.invoice_id, importo: x.importo, passivo: x.passivo })))).catch(() => {});
  }, [open, item]);
  useEffect(() => {
    if (!open) return;
    api.get("/parties").then(({ data }) => setParties(data)).catch(() => {});
    setF(item ? { data: item.data, causale: item.causale, descrizione: item.descrizione, righe: item.righe.map((r) => ({ conto: r.conto, dare: r.dare || "", avere: r.avere || "", party_id: r.party_id || "", note: r.note || "" })) }
      : { data: today(), causale: "GE", descrizione: "", righe: [blank(), blank()] });
  }, [open, item]);
  const setRiga = (i, p) => setF((x) => ({ ...x, righe: x.righe.map((r, k) => (k === i ? { ...r, ...p } : r)) }));
  const pickCausale = (codice) => {
    const c = causali.find((x) => x.codice === codice);
    setF((x) => {
      const empty = x.righe.every((r) => !r.conto && !r.dare && !r.avere);
      const righe = empty && c && (c.conto_dare || c.conto_avere) ? [{ ...blank(), conto: c.conto_dare || "" }, { ...blank(), conto: c.conto_avere || "" }] : x.righe;
      return { ...x, causale: codice, descrizione: x.descrizione || c?.descrizione || "", righe };
    });
  };
  const td = n(f.righe.reduce((s, r) => s + n(r.dare), 0));
  const ta = n(f.righe.reduce((s, r) => s + n(r.avere), 0));
  const quadra = td > 0 && td === ta;
  const save = async () => {
    setBusy(true);
    const body = { ...f, righe: f.righe.filter((r) => r.conto || n(r.dare) || n(r.avere)).map((r) => ({ ...r, dare: n(r.dare), avere: n(r.avere), party_id: r.party_id || null })), saldaconto: sc.filter((i) => n(i.importo) > 0).map((i) => ({ ...i, importo: n(i.importo) })) };
    try {
      item ? await api.put(`/contabilita/registrazioni/${item.id}`, body) : await api.post("/contabilita/registrazioni", body);
      toast.success("Registrazione salvata");
      onSaved();
      onClose();
    } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-h-[92vh] overflow-y-auto bg-white sm:max-w-4xl" data-testid="registrazione-dialog">
        <DialogHeader>
          <DialogTitle>{item ? `Modifica registrazione n. ${item.numero}/${item.anno}` : "Nuova registrazione in partita doppia"}</DialogTitle>
          <DialogDescription>Ogni riga va in Dare oppure in Avere. Il totale Dare deve essere uguale al totale Avere.</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
          <label className="text-xs font-medium text-slate-600">Data<Input type="date" value={f.data} onChange={(e) => setF({ ...f, data: e.target.value })} data-testid="reg-data-input" /></label>
          <label className="text-xs font-medium text-slate-600">Causale
            <select value={f.causale} onChange={(e) => pickCausale(e.target.value)} className="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm" data-testid="reg-causale-select">
              {causali.map((c) => <option key={c.codice} value={c.codice}>{c.codice} · {c.descrizione}</option>)}
            </select>
          </label>
          <label className="text-xs font-medium text-slate-600 sm:col-span-2">Descrizione<Input value={f.descrizione} onChange={(e) => setF({ ...f, descrizione: e.target.value })} data-testid="reg-descrizione-input" /></label>
        </div>
        <div className="mt-2">
          <div className="hidden grid-cols-12 gap-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500 sm:grid"><span className="col-span-5">Conto</span><span className="col-span-2 text-right">Dare</span><span className="col-span-2 text-right">Avere</span><span className="col-span-2">Nota</span></div>
          {f.righe.map((r, i) => <Riga key={i} r={r} i={i} conti={conti} parties={parties} set={(p) => setRiga(i, p)} del={() => setF((x) => ({ ...x, righe: x.righe.filter((_, k) => k !== i) }))} />)}
          <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
            <Button variant="outline" size="sm" onClick={() => setF((x) => ({ ...x, righe: [...x.righe, blank()] }))} data-testid="reg-add-riga-btn"><Plus className="mr-1 h-4 w-4" />Aggiungi riga</Button>
            <div className={`rounded-lg px-3 py-1.5 text-sm font-semibold ${quadra ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"}`} data-testid="reg-quadratura">
              Dare {fmtEUR(td)} · Avere {fmtEUR(ta)} {quadra ? "· quadrata" : `· differenza ${fmtEUR(Math.abs(td - ta))}`}
            </div>
          </div>
        </div>
        <SaldacontoPanel righe={f.righe} parties={parties} items={sc} setItems={setSc} auto={auto} setAuto={setAuto} editId={item?.id} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose} data-testid="reg-cancel-btn">Annulla</Button>
          <Button onClick={save} disabled={busy || !quadra} data-testid="reg-save-btn">{busy ? "Salvataggio…" : "Registra"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, Loader2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, ALIQUOTE, NATURE } from "@/lib/fe";
import { SearchPicker } from "@/components/SearchPicker";
import { DestinazioneSelect } from "@/components/DestinazioneSelect";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";

const today = () => new Date().toISOString().slice(0, 10);
const NEW = { data: today(), party_id: "", data_consegna: "", riferimento: "", destinazione: null, note: "", lines: [] };
const sel = "h-9 rounded-md border border-slate-200 bg-white px-2 text-sm";
const lt = (l) => (Number(l.quantita) || 0) * (Number(l.prezzo_unitario) || 0);

const Riga = ({ l, i, set, del, art }) => (
  <tr className="border-t border-slate-100" data-testid={`ord-riga-${i}`}>
    <td className="py-2 pr-2"><Input value={l.descrizione} onChange={(e) => set(i, "descrizione", e.target.value)} data-testid={`ord-desc-${i}`} />
      {art?.gestione_magazzino && <div className="mt-0.5 text-[11px] text-slate-500" data-testid={`ord-disp-${i}`}>Giacenza {art.giacenza ?? 0} · impegnato {art.impegnato || 0} · ordinato {art.ordinato || 0} · <b className={(art.disponibilita ?? 0) < 0 ? "text-rose-700" : "text-emerald-700"}>disponibile {art.disponibilita ?? art.giacenza ?? 0}</b></div>}
      {l.evasa > 0 && <div className="text-[11px] text-blue-700">Già evasa: {l.evasa}</div>}
    </td>
    <td className="pr-2"><Input type="number" step="0.01" min={0} value={l.quantita} onChange={(e) => set(i, "quantita", e.target.value)} className="w-20 text-right" data-testid={`ord-qta-${i}`} /></td>
    <td className="pr-2"><Input type="number" step="0.01" min={0} value={l.prezzo_unitario} onChange={(e) => set(i, "prezzo_unitario", e.target.value)} className="w-24 text-right" data-testid={`ord-prezzo-${i}`} /></td>
    <td className="pr-2"><Input value={l.sconto || ""} onChange={(e) => set(i, "sconto", e.target.value)} placeholder="es. 10+5" className="w-20" data-testid={`ord-sconto-${i}`} /></td>
    <td className="pr-2">
      <select className={sel} value={l.aliquota} onChange={(e) => set(i, "aliquota", Number(e.target.value))} data-testid={`ord-aliquota-${i}`}>{ALIQUOTE.map((a) => <option key={a} value={a}>{a}%</option>)}</select>
      {Number(l.aliquota) === 0 && <select className={`${sel} mt-1 w-24`} value={l.natura || ""} onChange={(e) => set(i, "natura", e.target.value)} data-testid={`ord-natura-${i}`}><option value="">Natura</option>{NATURE.map(([k]) => <option key={k} value={k}>{k}</option>)}</select>}
    </td>
    <td className="text-right">{fmtEUR(lt(l))}</td>
    <td className="pl-2">{!(l.evasa > 0) && <button onClick={() => del(i)} className="text-rose-600" data-testid={`ord-del-${i}`}><Trash2 className="h-4 w-4" /></button>}</td>
  </tr>
);

export const OrdineDialog = ({ tipo, ordine, bozza, open, onOpenChange, onSaved }) => {
  const [f, setF] = useState(NEW);
  const [parties, setParties] = useState([]);
  const [arts, setArts] = useState([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!open) return;
    setF(ordine ? { ...NEW, ...ordine, destinazione: ordine.destinazione || null } : bozza ? { ...NEW, data: today(), party_id: bozza.party_id || "", note: "Riordino articoli sottoscorta", lines: bozza.lines } : { ...NEW, data: today() });
    api.get("/parties", { params: { tipo } }).then(({ data }) => setParties(data)).catch(() => {});
    api.get("/articles").then(({ data }) => setArts(data)).catch(() => {});
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  const party = parties.find((p) => p.id === f.party_id);
  const pItems = useMemo(() => parties.map((p) => ({ key: p.id, label: p.denominazione, sub: p.partita_iva || p.codice_fiscale })), [parties]);
  const aItems = useMemo(() => arts.map((a) => ({ key: a.id, label: `${a.codice} · ${a.descrizione}`, sub: a.gestione_magazzino ? `disp. ${a.disponibilita ?? a.giacenza ?? 0} ${a.unita_misura || ""}` : "" })), [arts]);
  const set = (i, k, v) => setF({ ...f, lines: f.lines.map((l, j) => (j === i ? { ...l, [k]: v } : l)) });
  const addArt = async (it) => {
    const a = arts.find((x) => x.id === it.key);
    let ln = { article_id: a.id, descrizione: a.descrizione, quantita: 1, unita_misura: a.unita_misura || "", prezzo_unitario: a.prezzo ?? 0, sconto: "", aliquota: a.aliquota ?? 22, natura: a.natura || "" };
    if (tipo === "cliente" && f.party_id) {
      try { const { data } = await api.get(`/parties/${f.party_id}/prezzo`, { params: { article_id: a.id } }); ln = { ...ln, prezzo_unitario: data.prezzo, sconto: data.sconto || "" }; } catch { /* prezzo articolo */ }
    }
    setF((x) => ({ ...x, lines: [...x.lines, ln] }));
  };
  const save = async () => {
    setBusy(true);
    const body = { ...f, destinazione: f.destinazione?.indirizzo ? f.destinazione : null, lines: f.lines.map((l) => ({ id: l.id, article_id: l.article_id || null, descrizione: l.descrizione, quantita: Number(l.quantita), unita_misura: l.unita_misura || "", prezzo_unitario: Number(l.prezzo_unitario) || 0, sconto: l.sconto || "", aliquota: Number(l.aliquota), natura: Number(l.aliquota) === 0 ? l.natura || null : null, note: l.note || "" })) };
    try {
      const { data } = ordine ? await api.put(`/ordini/${tipo}/${ordine.id}`, body) : await api.post(`/ordini/${tipo}`, body);
      toast.success(`Ordine ${data.numero_display} salvato`);
      onSaved(data);
      onOpenChange(false);
    } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };
  const dest = f.destinazione || {};
  const setDest = (k, v) => setF({ ...f, destinazione: { denominazione: "", indirizzo: "", cap: "", comune: "", provincia: "", ...dest, [k]: v } });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] overflow-y-auto bg-white sm:max-w-5xl" data-testid="ord-dialog">
        <DialogHeader><DialogTitle>{ordine ? `Modifica ordine ${ordine.numero_display}` : `Nuovo ordine ${tipo === "cliente" ? "cliente" : "fornitore"}`}</DialogTitle></DialogHeader>
        <div className="grid gap-3 sm:grid-cols-4">
          <label className="text-xs text-slate-600 sm:col-span-2">{tipo === "cliente" ? "Cliente" : "Fornitore"}
            {ordine?.evasioni?.length ? <div className="mt-1 text-sm font-medium">{ordine.party.denominazione}</div>
              : <SearchPicker items={pItems} value={party?.denominazione || ordine?.party?.denominazione} onPick={(i) => setF({ ...f, party_id: i.key, destinazione: null })} onClear={() => setF({ ...f, party_id: "" })} placeholder={`Cerca ${tipo}`} testId="ord-party" className="w-full" />}
          </label>
          <label className="text-xs text-slate-600">Data ordine<Input type="date" value={f.data} onChange={(e) => setF({ ...f, data: e.target.value })} data-testid="ord-data" /></label>
          <label className="text-xs text-slate-600">Consegna prevista<Input type="date" value={f.data_consegna || ""} onChange={(e) => setF({ ...f, data_consegna: e.target.value })} data-testid="ord-consegna" /></label>
          <label className="text-xs text-slate-600 sm:col-span-2">{tipo === "cliente" ? "Riferimento ordine del cliente" : "Riferimento / offerta fornitore"}<Input value={f.riferimento || ""} onChange={(e) => setF({ ...f, riferimento: e.target.value })} data-testid="ord-riferimento" /></label>
          <label className="text-xs text-slate-600 sm:col-span-2">Note<Input value={f.note || ""} onChange={(e) => setF({ ...f, note: e.target.value })} data-testid="ord-note" /></label>
        </div>
        {tipo === "cliente" && (
          <div className="rounded-lg border border-slate-200 p-3" data-testid="ord-destinazione">
            <div className="text-xs font-semibold text-slate-700">Destinazione merce {f.destinazione?.indirizzo ? "" : "(sede del cliente se vuota)"}</div>
            <DestinazioneSelect destinazioni={party?.destinazioni || []} onPick={(d) => setF({ ...f, destinazione: d })} testId="ord-dest-select" />
            <div className="mt-2 grid gap-2 sm:grid-cols-6">
              {[["denominazione", "Presso", "sm:col-span-2"], ["indirizzo", "Indirizzo", "sm:col-span-4"], ["cap", "CAP", ""], ["comune", "Comune", "sm:col-span-4"], ["provincia", "Prov.", ""]].map(([k, ph, c]) => (
                <Input key={k} className={c} placeholder={ph} value={dest[k] || ""} onChange={(e) => setDest(k, k === "provincia" ? e.target.value.toUpperCase().slice(0, 2) : e.target.value)} data-testid={`ord-dest-${k}`} />
              ))}
            </div>
          </div>
        )}
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm" data-testid="ord-righe">
            <thead className="text-left text-xs uppercase tracking-wider text-slate-500"><tr><th className="py-1">Descrizione</th><th>Q.tà</th><th>Prezzo</th><th>Sconto</th><th>IVA</th><th className="text-right">Importo</th><th /></tr></thead>
            <tbody>{f.lines.map((l, i) => <Riga key={i} l={l} i={i} set={set} del={(j) => setF({ ...f, lines: f.lines.filter((_, k) => k !== j) })} art={arts.find((a) => a.id === l.article_id)} />)}</tbody>
          </table>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <SearchPicker items={aItems} value="" onPick={addArt} onClear={() => {}} placeholder="Aggiungi articolo dal catalogo…" testId="ord-add-articolo" className="w-80" />
          <Button size="sm" variant="outline" onClick={() => setF({ ...f, lines: [...f.lines, { descrizione: "", quantita: 1, prezzo_unitario: 0, sconto: "", aliquota: 22, natura: "" }] })} data-testid="ord-add-riga"><Plus className="mr-1 h-3.5 w-3.5" />Riga libera</Button>
          <span className="ml-auto text-sm font-semibold" data-testid="ord-totale">Imponibile {fmtEUR(f.lines.reduce((s, l) => s + lt(l), 0))}</span>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Annulla</Button>
          <Button onClick={save} disabled={busy || !f.party_id || !f.lines.length} data-testid="ord-save">{busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Salva ordine</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

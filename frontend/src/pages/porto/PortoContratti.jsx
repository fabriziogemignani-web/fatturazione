import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Pencil, Trash2, FileText, Lock } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NSelect } from "@/components/ui/nselect";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { usePortoBase, oggi } from "@/lib/porto";

const anno = new Date().getFullYear();
const VUOTO = { barca_id: "", posto_id: "", tipo: "annuale", data_inizio: `${anno}-01-01`, data_fine: `${anno}-12-31`, n_rate: "4", importo: "", note: "" };

const ContrattoDialog = ({ open, k, base, onClose, onSaved }) => {
  const [f, setF] = useState(VUOTO);
  const [calc, setCalc] = useState(null);
  useEffect(() => { if (open) { setF(k?.id ? { ...VUOTO, ...k, barca_id: k.barca.id, n_rate: String(k.n_rate), importo: String(k.importo) } : VUOTO); setCalc(null); } }, [open, k]);
  useEffect(() => {
    if (!open || !f.barca_id || !f.data_inizio || !f.data_fine) { return; }
    api.get("/porto/prezzo", { params: { barca_id: f.barca_id, da: f.data_inizio, a: f.data_fine, tipo: f.tipo } }).then(({ data }) => setCalc(data)).catch((e) => setCalc({ errore: errMsg(e) }));
  }, [open, f.barca_id, f.data_inizio, f.data_fine, f.tipo]);
  const s = (key) => (e) => setF({ ...f, [key]: e.target.value });
  const barca = base.barche.find((b) => b.id === f.barca_id);
  const posti = base.posti.filter((p) => !p.fuori_servizio && (!barca || p.lunghezza_max >= barca.lunghezza));
  const save = async () => {
    const body = { ...f, n_rate: Number(f.n_rate), importo: f.importo === "" ? null : Number(f.importo) };
    try {
      if (k?.id) await api.put(`/porto/contratti/${k.id}`, body); else await api.post("/porto/contratti", body);
      toast.success("Contratto salvato"); onSaved(); onClose();
    } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-xl" data-testid="contratto-dialog">
        <DialogHeader><DialogTitle>{k?.id ? "Modifica contratto" : "Nuovo contratto di ormeggio"}</DialogTitle></DialogHeader>
        <div className="grid grid-cols-2 gap-3 text-sm">
          <label className="col-span-2">Barca<NSelect value={f.barca_id} onChange={s("barca_id")} data-testid="contratto-barca"><option value="">Seleziona...</option>{base.barche.map((b) => <option key={b.id} value={b.id}>{b.nome} ({b.lunghezza} m) - {b.armatore}</option>)}</NSelect></label>
          <label className="col-span-2">Posto barca (adatti alla lunghezza)<NSelect value={f.posto_id} onChange={s("posto_id")} data-testid="contratto-posto"><option value="">Seleziona...</option>{posti.map((p) => <option key={p.id} value={p.id}>{p.codice} (max {p.lunghezza_max} m)</option>)}</NSelect></label>
          <label>Tipo<NSelect value={f.tipo} onChange={s("tipo")} data-testid="contratto-tipo"><option value="annuale">Annuale</option><option value="stagionale">Stagionale</option><option value="mensile">Mensile</option></NSelect></label>
          <label>Rate<NSelect value={f.n_rate} onChange={s("n_rate")} data-testid="contratto-rate">{[1, 2, 3, 4, 6, 12].map((n) => <option key={n} value={String(n)}>{n === 1 ? "Unica" : `${n} rate`}</option>)}</NSelect></label>
          <label>Dal<Input type="date" value={f.data_inizio} onChange={s("data_inizio")} data-testid="contratto-inizio" /></label>
          <label>Al<Input type="date" value={f.data_fine} onChange={s("data_fine")} data-testid="contratto-fine" /></label>
          <label className="col-span-2">Importo IVA esclusa (vuoto = da listino)<Input type="number" step="0.01" value={f.importo} onChange={s("importo")} placeholder={calc?.imponibile != null ? String(calc.imponibile) : ""} data-testid="contratto-importo" /></label>
          <p className="col-span-2 text-xs text-slate-600" data-testid="contratto-prezzo-listino">{calc?.errore ? <span className="text-rose-600">{calc.errore}</span> : calc ? `Da listino: ${fmtEUR(calc.imponibile)} + IVA ${calc.aliquota}% = ${fmtEUR(calc.totale)}` : "Scegli barca e periodo per il prezzo da listino"}</p>
          <label className="col-span-2">Note<Input value={f.note} onChange={s("note")} data-testid="contratto-note" /></label>
        </div>
        <DialogFooter><Button onClick={save} data-testid="contratto-save">Salva</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const FatturaRate = ({ open, onClose, onDone }) => {
  const [fino, setFino] = useState(oggi());
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { api.get("/porto/rate", { params: { fino_al: fino } }).then(({ data }) => setRows(data)).catch(() => setRows([])); } }, [open, fino]);
  const go = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/porto/rate/fattura", { fino_al: fino });
      toast.success(`${data.create.length} fatture create in bozza`);
      data.errori.forEach((e) => toast.error(e));
      onDone(); onClose();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl" data-testid="fattura-rate-dialog">
        <DialogHeader><DialogTitle>Fattura rate in scadenza</DialogTitle><DialogDescription>Crea una fattura in bozza, con data di oggi, per ogni rata con scadenza fino alla data scelta.</DialogDescription></DialogHeader>
        <label className="text-sm">Rate con scadenza fino al<Input type="date" value={fino} onChange={(e) => e.target.value && setFino(e.target.value)} className="w-44" data-testid="fattura-rate-fino" /></label>
        <div className="max-h-72 overflow-y-auto rounded border">
          <table className="w-full text-sm"><tbody className="divide-y">
            {rows.length === 0 && <tr><td className="p-4 text-center text-slate-500" data-testid="fattura-rate-vuoto">Nessuna rata da fatturare.</td></tr>}
            {rows.map((r) => <tr key={`${r.contratto_id}-${r.n}`} data-testid={`rata-${r.contratto_id}-${r.n}`}><td className="px-3 py-2">{fmtDate(r.scadenza)}</td><td className="px-3 py-2">{r.cliente}</td><td className="px-3 py-2">{r.barca} · {r.posto}</td><td className="px-3 py-2">rata {r.rata}</td><td className="px-3 py-2 text-right font-semibold">{fmtEUR(r.importo)}</td></tr>)}
          </tbody></table>
        </div>
        <DialogFooter><Button onClick={go} disabled={busy || rows.length === 0} data-testid="fattura-rate-conferma">{busy ? "Creazione..." : `Crea ${rows.length} fatture`}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default function PortoContratti() {
  const [base] = usePortoBase();
  const [rows, setRows] = useState([]);
  const [edit, setEdit] = useState(null);
  const [fr, setFr] = useState(false);
  const [stato, setStato] = useState("attivo");
  const load = () => api.get("/porto/contratti", { params: stato ? { stato } : {} }).then(({ data }) => setRows(data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, [stato]); // eslint-disable-line react-hooks/exhaustive-deps
  const act = async (fn, msg) => { try { await fn(); toast.success(msg); load(); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <div data-testid="porto-contratti-page">
      <PageHeader eyebrow="Porto turistico" title="Contratti di ormeggio">
        <NSelect value={stato} onChange={(e) => setStato(e.target.value)} className="w-36" data-testid="contratti-filtro"><option value="attivo">Attivi</option><option value="chiuso">Chiusi</option><option value="">Tutti</option></NSelect>
        <Button variant="outline" onClick={() => setFr(true)} data-testid="contratti-fattura-rate"><FileText className="mr-1 h-4 w-4" />Fattura rate</Button>
        <Button onClick={() => setEdit({})} data-testid="contratti-nuovo"><Plus className="mr-1 h-4 w-4" />Nuovo contratto</Button>
      </PageHeader>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-sm" data-testid="contratti-table">
          <thead className="border-b bg-slate-50 text-left text-xs uppercase text-slate-500"><tr><th className="px-4 py-3">N.</th><th className="px-4 py-3">Cliente / barca</th><th className="px-4 py-3">Posto</th><th className="px-4 py-3">Periodo</th><th className="px-4 py-3 text-right">Importo</th><th className="px-4 py-3">Rate fatturate</th><th /></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {rows.length === 0 && <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-500">Nessun contratto.</td></tr>}
            {rows.map((k) => {
              const fatt = k.rate.filter((x) => x.fattura_id).length;
              return (
                <tr key={k.id} data-testid={`contratto-row-${k.id}`}>
                  <td className="px-4 py-3 font-semibold">{k.numero}/{k.anno}<div className="text-xs font-normal capitalize text-slate-500">{k.tipo}</div></td>
                  <td className="px-4 py-3">{k.cliente}<div className="text-xs text-slate-500">{k.barca.nome} · {k.barca.lunghezza} m</div></td>
                  <td className="px-4 py-3 font-semibold">{k.posto.codice}</td>
                  <td className="px-4 py-3">{fmtDate(k.data_inizio)} → {fmtDate(k.data_fine)}</td>
                  <td className="px-4 py-3 text-right font-semibold">{fmtEUR(k.importo)}</td>
                  <td className="px-4 py-3" data-testid={`contratto-rate-${k.id}`} title={k.rate.map((x) => `${x.n}: ${x.scadenza} ${x.fattura_numero || "da fatturare"}`).join("\n")}>{fatt}/{k.rate.length}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-right">
                    {fatt === 0 && <Button size="sm" variant="ghost" onClick={() => setEdit(k)} data-testid={`contratto-edit-${k.id}`}><Pencil className="h-3.5 w-3.5" /></Button>}
                    {k.stato === "attivo" && <Button size="sm" variant="ghost" title="Chiudi contratto" onClick={() => window.confirm("Chiudere il contratto? Le rate non fatturate non verranno più proposte.") && act(() => api.post(`/porto/contratti/${k.id}/chiudi`), "Contratto chiuso")} data-testid={`contratto-chiudi-${k.id}`}><Lock className="h-3.5 w-3.5" /></Button>}
                    {fatt === 0 && <Button size="sm" variant="ghost" onClick={() => window.confirm("Eliminare il contratto?") && act(() => api.delete(`/porto/contratti/${k.id}`), "Contratto eliminato")} data-testid={`contratto-del-${k.id}`}><Trash2 className="h-3.5 w-3.5 text-rose-600" /></Button>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <ContrattoDialog open={!!edit} k={edit} base={base} onClose={() => setEdit(null)} onSaved={load} />
      <FatturaRate open={fr} onClose={() => setFr(false)} onDone={load} />
    </div>
  );
}

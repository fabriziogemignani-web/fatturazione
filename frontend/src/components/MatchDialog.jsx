import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { fmtEUR, fmtDate } from "@/lib/fe";

const TABS_IN = [["incasso", "Incasso fattura"], ["corrispettivi", "Corrispettivi"], ["altro", "Altro"]];
const TABS_OUT = [["pagamento", "Pagamento fornitore"], ["iva", "Versamento IVA"], ["altro", "Altro"]];

const Tab = ({ on, onClick, children, id }) => (
  <button type="button" onClick={onClick} data-testid={`match-tab-${id}`}
    className={`rounded-full border px-3 py-1 text-xs font-semibold ${on ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 text-slate-600 hover:border-slate-400"}`}>{children}</button>
);

const Fatture = ({ list, sel, setSel, q, setQ }) => {
  const rows = list.filter((d) => !q || `${d.numero_display} ${d.cliente}`.toLowerCase().includes(q.toLowerCase()));
  const toggle = (id) => setSel(sel.includes(id) ? sel.filter((x) => x !== id) : [...sel, id]);
  return (
    <div>
      <Input placeholder="Cerca numero o nome…" value={q} onChange={(e) => setQ(e.target.value)} className="mb-2" data-testid="match-search-input" />
      <div className="max-h-64 divide-y divide-slate-100 overflow-y-auto rounded-md border border-slate-200">
        {rows.length === 0 && <p className="p-3 text-sm text-slate-500">Nessuna fattura aperta</p>}
        {rows.map((d) => (
          <label key={d.id} className="flex cursor-pointer items-center gap-3 px-3 py-2 text-sm hover:bg-slate-50" data-testid={`match-fattura-${d.id}`}>
            <input type="checkbox" checked={sel.includes(d.id)} onChange={() => toggle(d.id)} />
            <span className="flex-1"><b>{d.numero_display}</b> · {d.cliente} <span className="text-xs text-slate-400">{fmtDate(d.data)}</span></span>
            <span className="font-semibold">{fmtEUR(d.residuo)}</span>
          </label>
        ))}
      </div>
      <p className="mt-1 text-xs text-slate-500">Puoi selezionare più fatture: l'importo viene ripartito nell'ordine scelto.</p>
    </div>
  );
};

const Proposte = ({ list, tipo, sel, setSel }) => {
  const rows = list.filter((p) => p.tipo === tipo);
  if (!rows.length) return <p className="text-sm text-slate-500" data-testid="match-no-proposte">Nessun riferimento con lo stesso importo.</p>;
  return rows.map((p) => (
    <label key={p.ref_id} className="flex items-center gap-3 rounded-md border border-slate-200 px-3 py-2 text-sm" data-testid={`match-ref-${p.ref_id}`}>
      <input type="radio" checked={sel[0] === p.ref_id} onChange={() => setSel([p.ref_id])} />
      <span className="flex-1">{p.label}</span><span className="font-semibold">{fmtEUR(p.residuo)}</span>
    </label>
  ));
};

export const MatchDialog = ({ tx, onClose, onDone }) => {
  const [data, setData] = useState(null);
  const [tipo, setTipo] = useState(null);
  const [sel, setSel] = useState([]);
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const [note, setNote] = useState("");
  useEffect(() => {
    if (!tx) { return; }
    setData(null); setSel([]); setQ(""); setCat(""); setNote("");
    setTipo(tx.importo > 0 ? "incasso" : "pagamento");
    api.get(`/banca/movimenti/${tx.id}/candidati`).then(({ data: d }) => {
      setData(d);
      const best = d.proposte[0];
      if (best) { setTipo(best.tipo); setSel([best.ref_id]); }
    }).catch((e) => toast.error(errMsg(e)));
  }, [tx]);
  const save = async () => {
    try {
      const { data: r } = await api.post(`/banca/movimenti/${tx.id}/riconcilia`, { tipo, ref_ids: sel, categoria: cat || null, note });
      toast.success(r.match.non_abbinato > 0 ? `Riconciliato; restano ${fmtEUR(r.match.non_abbinato)} non abbinati` : "Movimento riconciliato");
      onDone();
    } catch (e) { toast.error(errMsg(e)); }
  };
  const tabs = tx?.importo > 0 ? TABS_IN : TABS_OUT;
  return (
    <Dialog open={!!tx} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-white sm:max-w-xl" data-testid="match-dialog">
        <DialogHeader>
          <DialogTitle>Abbina movimento · <span className={tx?.importo > 0 ? "text-emerald-700" : "text-rose-700"}>{tx && fmtEUR(tx.importo)}</span></DialogTitle>
          <DialogDescription>{tx && `${fmtDate(tx.data)} · ${tx.descrizione}`}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-wrap gap-2">{tabs.map(([k, l]) => <Tab key={k} id={k} on={tipo === k} onClick={() => { setTipo(k); setSel([]); }}>{l}</Tab>)}</div>
        {!data ? <p className="text-sm text-slate-500">Caricamento…</p> : (
          <div className="space-y-2">
            {(tipo === "incasso" || tipo === "pagamento") && <Fatture list={data.fatture} sel={sel} setSel={setSel} q={q} setQ={setQ} />}
            {(tipo === "corrispettivi" || tipo === "iva") && <Proposte list={data.proposte} tipo={tipo} sel={sel} setSel={setSel} />}
            {tipo === "altro" && (
              <div className="space-y-2">
                <div className="flex flex-wrap gap-2">{data.categorie.map((c) => <Tab key={c} id={`cat-${c.slice(0, 8)}`} on={cat === c} onClick={() => setCat(c)}>{c}</Tab>)}</div>
                <Input placeholder="Nota (facoltativa)" value={note} onChange={(e) => setNote(e.target.value)} data-testid="match-note-input" />
              </div>
            )}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Annulla</Button>
          <Button onClick={save} disabled={tipo === "altro" ? !cat : !sel.length} data-testid="match-save-btn">Conferma abbinamento</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

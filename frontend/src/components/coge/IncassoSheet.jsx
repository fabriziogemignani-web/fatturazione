import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { CheckSquare, Landmark, Square } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { SearchPicker } from "@/components/SearchPicker";

const n = (v) => Math.round(Number(v || 0) * 100) / 100;
const today = () => new Date().toISOString().slice(0, 10);

const Righe = ({ rows, sel, toggle, setImp }) => (
  <div className="max-h-[42vh] overflow-auto rounded-lg border border-slate-200">
    <table className="w-full text-sm">
      <thead className="sticky top-0 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
        <tr><th className="w-8 px-2 py-2 sm:w-10 sm:px-3" /><th className="py-2">Fattura</th><th>Scadenza</th><th className="hidden text-right sm:table-cell">Totale</th><th className="pl-2 text-right">Residuo</th><th className="w-24 px-2 text-right sm:w-32 sm:px-3">Da pagare</th></tr>
      </thead>
      <tbody className="divide-y divide-slate-100">{rows.map((x) => {
        const on = x.invoice_id in sel;
        const late = x.scadenza < today();
        return (
          <tr key={x.invoice_id} onClick={() => toggle(x)} className={`cursor-pointer transition-colors ${on ? "bg-blue-50" : "hover:bg-slate-50"}`} data-testid={`inc-row-${x.invoice_id}`}>
            <td className="px-2 py-2 sm:px-3">{on ? <CheckSquare className="h-4 w-4 text-blue-600" /> : <Square className="h-4 w-4 text-slate-400" />}</td>
            <td className="py-2 font-medium">{x.numero_display}<div className="text-[11px] font-normal text-slate-500">del {fmtDate(x.data)}{x.stato === "parziale" ? " · parziale" : ""}</div></td>
            <td className={late ? "font-semibold text-rose-700" : ""}>{fmtDate(x.scadenza)}</td>
            <td className="hidden text-right sm:table-cell">{fmtEUR(x.netto)}</td>
            <td className="pl-2 text-right font-semibold">{fmtEUR(x.residuo)}</td>
            <td className="px-2 text-right sm:px-3" onClick={(e) => e.stopPropagation()}>
              {on && <input type="number" step="0.01" min={0} max={x.residuo} value={sel[x.invoice_id]} onChange={(e) => setImp(x.invoice_id, e.target.value === "" ? "" : Math.min(Math.max(Number(e.target.value), 0), x.residuo))}
                className="h-8 w-20 sm:w-28 rounded border border-slate-200 px-2 text-right" data-testid={`inc-importo-${x.invoice_id}`} />}
            </td>
          </tr>
        );
      })}</tbody>
    </table>
  </div>
);

export const IncassoSheet = ({ tipo, conti, onClose, onSaved }) => {
  const pas = tipo === "PG";
  const [par, setPar] = useState(null);
  const [parties, setParties] = useState([]);
  const [party, setParty] = useState(null);
  const [rows, setRows] = useState(null);
  const [sel, setSel] = useState({});
  const [f, setF] = useState({ data: today(), banca: "", descrizione: "" });
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.get("/contabilita/parametri").then(({ data }) => { setPar(data.parametri); setF((x) => ({ ...x, banca: data.parametri.banca })); }).catch(() => {});
    api.get("/parties").then(({ data }) => setParties(data.filter((p) => p.tipo === (pas ? "fornitore" : "cliente")))).catch(() => {});
  }, [pas]);
  useEffect(() => {
    if (!party) return;
    setRows(null); setSel({});
    api.get("/contabilita/saldaconto/partite", { params: { party_id: party.id, tipo: pas ? "fornitore" : "cliente" } }).then(({ data }) => setRows(data.aperte)).catch((e) => toast.error(errMsg(e)));
  }, [party, pas]);
  const banche = useMemo(() => (par ? conti.filter((c) => c.livello === 3 && c.codice.startsWith(par.banca.slice(0, 5))) : []), [conti, par]);
  const toggle = (x) => setSel((s) => { const c = { ...s }; if (x.invoice_id in c) delete c[x.invoice_id]; else c[x.invoice_id] = x.residuo; return c; });
  const tutte = () => setSel(Object.keys(sel).length === rows.length ? {} : Object.fromEntries(rows.map((x) => [x.invoice_id, x.residuo])));
  const tot = n(Object.values(sel).reduce((s, v) => s + n(v), 0));
  const scelte = (rows || []).filter((x) => x.invoice_id in sel);
  const descr = f.descrizione || `${pas ? "Pagamento" : "Incasso"} fatt. ${scelte.map((x) => x.numero_display).join(", ")} ${party?.denominazione || ""}`.slice(0, 200);
  const save = async () => {
    if (tot <= 0) return toast.error("Seleziona almeno una fattura");
    if (!f.banca) return toast.error("Scegli il conto banca");
    setBusy(true);
    const cp = { conto: pas ? par.fornitori : par.clienti, dare: pas ? tot : 0, avere: pas ? 0 : tot, party_id: party.id, nota: "" };
    const bk = { conto: f.banca, dare: pas ? 0 : tot, avere: pas ? tot : 0, party_id: null, nota: "" };
    try {
      await api.post("/contabilita/registrazioni", { data: f.data, causale: tipo, descrizione: descr, righe: pas ? [cp, bk] : [bk, cp],
        saldaconto: scelte.filter((x) => n(sel[x.invoice_id]) > 0).map((x) => ({ invoice_id: x.invoice_id, importo: n(sel[x.invoice_id]), passivo: pas })) });
      toast.success(`${pas ? "Pagamento" : "Incasso"} registrato: ${scelte.length} fatture chiuse o ridotte`);
      onSaved(); onClose();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-4xl" data-testid="incasso-sheet">
        <DialogHeader>
          <DialogTitle>{pas ? "Pagamento a fornitore" : "Incasso da cliente"}</DialogTitle>
          <DialogDescription>Scegli {pas ? "il fornitore" : "il cliente"}, poi clicca le fatture da {pas ? "pagare" : "incassare"}. La contropartita è sempre la banca.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-[1fr_160px_1fr]">
          <SearchPicker items={parties.map((p) => ({ key: p.id, label: p.denominazione, sub: p.partita_iva || p.codice_fiscale || "", search: p.codice_fiscale }))} value={party?.denominazione || ""}
            onPick={(i) => setParty(parties.find((p) => p.id === i.key))} onClear={() => { setParty(null); setRows(null); setSel({}); }}
            placeholder={pas ? "Cerca fornitore…" : "Cerca cliente…"} testId="inc-party-search" />
          <input type="date" value={f.data} onChange={(e) => setF({ ...f, data: e.target.value })} className="h-9 rounded-md border border-slate-200 px-2 text-sm" data-testid="inc-data-input" />
          <label className="flex items-center gap-2"><Landmark className="h-4 w-4 shrink-0 text-slate-500" />
            <select value={f.banca} onChange={(e) => setF({ ...f, banca: e.target.value })} className="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm" data-testid="inc-banca-select">
              {banche.map((c) => <option key={c.codice} value={c.codice}>{c.codice} {c.descrizione}</option>)}
            </select>
          </label>
        </div>
        {!party && <div className="rounded-lg border border-dashed border-slate-300 py-10 text-center text-sm text-slate-500" data-testid="inc-empty">Cerca {pas ? "un fornitore" : "un cliente"} per vedere le sue fatture aperte</div>}
        {party && !rows && <div className="py-8 text-center text-sm text-slate-500">Caricamento fatture aperte…</div>}
        {rows && rows.length === 0 && <div className="rounded-lg bg-emerald-50 py-8 text-center text-sm text-emerald-800" data-testid="inc-no-aperte">Nessuna fattura aperta per {party.denominazione}</div>}
        {rows && rows.length > 0 && (
          <>
            <div className="flex items-center justify-between text-xs text-slate-600">
              <button onClick={tutte} className="font-semibold text-blue-600 hover:underline" data-testid="inc-select-all">{Object.keys(sel).length === rows.length ? "Deseleziona tutte" : `Seleziona tutte (${rows.length})`}</button>
              <span>Residuo totale aperto: <b>{fmtEUR(rows.reduce((s, x) => s + x.residuo, 0))}</b></span>
            </div>
            <Righe rows={rows} sel={sel} toggle={toggle} setImp={(id, v) => setSel((s) => ({ ...s, [id]: v }))} />
            <input value={f.descrizione} onChange={(e) => setF({ ...f, descrizione: e.target.value })} placeholder={descr} maxLength={200} className="h-9 w-full rounded-md border border-slate-200 px-2 text-sm" data-testid="inc-descrizione-input" />
          </>
        )}
        <DialogFooter className="items-center gap-3 sm:justify-between">
          <div className="text-sm" data-testid="inc-totale">{scelte.length} fatture · <b className="text-base">{fmtEUR(tot)}</b>{tot > 0 && <span className="ml-2 text-xs text-slate-500">{pas ? "Dare Fornitori / Avere Banca" : "Dare Banca / Avere Clienti"}</span>}</div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose} data-testid="inc-cancel-btn">Annulla</Button>
            <Button onClick={save} disabled={busy || tot <= 0} data-testid="inc-save-btn">{busy ? "Registrazione…" : `Registra ${pas ? "pagamento" : "incasso"}`}</Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

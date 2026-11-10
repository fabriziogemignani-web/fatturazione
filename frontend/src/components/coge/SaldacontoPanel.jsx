import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Wand2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { Switch } from "@/components/ui/switch";

const n = (v) => Math.round(Number(v || 0) * 100) / 100;
const STATO = { aperta: "bg-amber-50 text-amber-700", parziale: "bg-sky-50 text-sky-700", chiusa: "bg-emerald-50 text-emerald-700" };

const Partite = ({ pid, nome, passivo, importo, items, setItems, auto, setAuto, editId }) => {
  const [d, setD] = useState(null);
  const [chiuse, setChiuse] = useState(false);
  const tag = passivo ? "forn" : "cli";
  useEffect(() => {
    api.get("/contabilita/saldaconto/partite", { params: { party_id: pid, tipo: passivo ? "fornitore" : "cliente", escludi_reg: editId || undefined } })
      .then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e)));
  }, [pid, passivo, editId]);
  const ids = useMemo(() => new Set((d?.aperte || []).map((x) => x.invoice_id)), [d]);
  const replace = (rows) => setItems((prev) => [...prev.filter((i) => !ids.has(i.invoice_id)), ...rows]);
  const runAuto = () => api.post("/contabilita/saldaconto/auto", { party_id: pid, tipo: passivo ? "fornitore" : "cliente", importo, escludi_reg: editId || undefined })
    .then(({ data }) => replace(data.righe.map((r) => ({ invoice_id: r.invoice_id, importo: r.importo, passivo })))).catch((e) => toast.error(errMsg(e)));
  useEffect(() => {
    if (!d || !auto || importo <= 0) return;
    const h = setTimeout(runAuto, 300);
    return () => clearTimeout(h);
  }, [d, auto, importo]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => setItems((prev) => prev.filter((i) => !ids.has(i.invoice_id))), [ids, setItems]);
  if (!d) return <div className="text-xs text-slate-500">Caricamento partite…</div>;
  const val = (iid) => items.find((i) => i.invoice_id === iid)?.importo ?? "";
  const setVal = (iid, v) => { setAuto(false); setItems((prev) => [...prev.filter((i) => i.invoice_id !== iid), ...(v === "" ? [] : [{ invoice_id: iid, importo: v, passivo }])]); };
  const abbinato = n(items.filter((i) => ids.has(i.invoice_id)).reduce((s, i) => s + n(i.importo), 0));
  const resto = n(importo - abbinato);
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-3" data-testid={`sc-panel-${tag}-${pid}`}>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-sm">
        <div><b>{passivo ? "Pagamento a" : "Incasso da"} {nome}</b> · {fmtEUR(importo)}</div>
        <button onClick={() => { setAuto(true); runAuto(); }} className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600 hover:underline" data-testid={`sc-auto-btn-${tag}-${pid}`}><Wand2 className="h-3.5 w-3.5" />Saldaconto automatico</button>
      </div>
      {d.aperte.length === 0 && <div className="py-2 text-xs text-slate-500" data-testid={`sc-no-aperte-${tag}-${pid}`}>Nessuna partita aperta: l'importo resta come acconto sul conto.</div>}
      {d.aperte.length > 0 && (
        <table className="w-full text-xs">
          <thead className="text-left uppercase tracking-wider text-slate-500"><tr><th className="py-1">Fattura</th><th>Scadenza</th><th className="text-right">Totale</th><th className="text-right">Residuo</th><th>Stato</th><th className="w-28 text-right">Abbina</th></tr></thead>
          <tbody className="divide-y divide-slate-100">{d.aperte.map((x) => (
            <tr key={x.invoice_id} data-testid={`sc-row-${x.invoice_id}`}>
              <td className="py-1.5 font-medium">{x.numero_display}<div className="text-[10px] text-slate-500">del {fmtDate(x.data)}</div></td>
              <td>{fmtDate(x.scadenza)}</td><td className="text-right">{fmtEUR(x.netto)}</td><td className="text-right font-semibold">{fmtEUR(x.residuo)}</td>
              <td><span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${STATO[x.stato]}`}>{x.stato}</span></td>
              <td className="text-right"><input type="number" step="0.01" min={0} max={x.residuo} value={val(x.invoice_id)} onChange={(e) => setVal(x.invoice_id, e.target.value)}
                className="h-7 w-24 rounded border border-slate-200 bg-white px-1.5 text-right" data-testid={`sc-importo-${x.invoice_id}`} /></td>
            </tr>
          ))}</tbody>
        </table>
      )}
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs">
        <label className="inline-flex items-center gap-2 text-slate-600"><Switch checked={chiuse} onCheckedChange={setChiuse} data-testid={`sc-chiuse-switch-${tag}-${pid}`} />Mostra partite chiuse ({d.chiuse.length})</label>
        <span className={resto < -0.005 ? "font-semibold text-rose-700" : "text-slate-600"} data-testid={`sc-riepilogo-${tag}-${pid}`}>Abbinato {fmtEUR(abbinato)} · {resto < -0.005 ? `eccede di ${fmtEUR(-resto)}` : `non abbinato ${fmtEUR(resto)}`}</span>
      </div>
      {chiuse && (
        <div className="mt-2 space-y-1 border-t border-slate-200 pt-2 text-xs" data-testid={`sc-chiuse-${tag}-${pid}`}>
          {d.chiuse.length === 0 && <div className="text-slate-500">Nessuna partita chiusa</div>}
          {d.chiuse.map((x) => (
            <div key={x.invoice_id} className="flex flex-wrap justify-between gap-2" data-testid={`sc-chiusa-${x.invoice_id}`}>
              <span><b>{x.numero_display}</b> del {fmtDate(x.data)} · {fmtEUR(x.netto)}</span>
              <span className="text-slate-500">{x.pagamenti.map((p) => `${fmtDate(p.data)} ${fmtEUR(p.importo)}${p.coge_rif ? ` (${p.coge_rif})` : ""}`).join(" · ") || "compensata"}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export const SaldacontoPanel = ({ righe, parties, items, setItems, auto, setAuto, editId }) => {
  const [p, setP] = useState(null);
  useEffect(() => { api.get("/contabilita/parametri").then(({ data }) => setP(data.parametri)).catch(() => {}); }, []);
  if (!p) return null;
  const tot = {};
  righe.forEach((r) => {
    if (!r.party_id || (r.conto !== p.clienti && r.conto !== p.fornitori)) return;
    const pas = r.conto === p.fornitori;
    const k = `${pas ? 1 : 0}|${r.party_id}`;
    tot[k] = n((tot[k] || 0) + (pas ? n(r.dare) - n(r.avere) : n(r.avere) - n(r.dare)));
  });
  const keys = Object.keys(tot).filter((k) => tot[k] > 0);
  if (!keys.length) return null;
  const name = (pid) => parties.find((x) => x.id === pid)?.denominazione || "";
  return (
    <div className="mt-4 space-y-3" data-testid="saldaconto-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-sm font-semibold text-slate-800">Saldaconto · partite aperte e chiuse</h4>
        <label className="inline-flex items-center gap-2 text-xs text-slate-600"><Switch checked={auto} onCheckedChange={setAuto} data-testid="sc-auto-switch" />Abbina in automatico dalla scadenza più vecchia</label>
      </div>
      {keys.map((k) => {
        const [pas, pid] = k.split("|");
        return <Partite key={k} pid={pid} nome={name(pid)} passivo={pas === "1"} importo={tot[k]} items={items} setItems={setItems} auto={auto} setAuto={setAuto} editId={editId} />;
      })}
      <p className="text-[11px] text-slate-500">Gli importi abbinati chiudono le fatture anche nello scadenzario clienti/fornitori. La parte non abbinata resta come acconto sul conto.</p>
    </div>
  );
};

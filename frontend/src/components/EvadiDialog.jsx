import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtDate } from "@/lib/fe";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";

const today = () => new Date().toISOString().slice(0, 10);
const res = (l) => Math.round((l.quantita - (l.evasa || 0)) * 10000) / 10000;

export const EvadiDialog = ({ tipo, o, open, onOpenChange, onDone }) => {
  const [q, setQ] = useState({});
  const [data, setData] = useState(today());
  const [chiudi, setChiudi] = useState(false);
  const [docF, setDocF] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setQ(Object.fromEntries(o.lines.map((l) => [l.id, String(res(l))]))); setData(today()); setChiudi(false); setDocF(""); } }, [open, o]);
  const send = async (forza = false) => {
    setBusy(true);
    try {
      const righe = o.lines.filter((l) => Number(q[l.id]) > 0).map((l) => ({ line_id: l.id, quantita: Number(q[l.id]) }));
      const { data: d } = await api.post(`/ordini/${tipo}/${o.id}/evadi`, { data, righe, chiudi, forza, documento_fornitore: docF });
      toast.success(d.documento ? `${tipo === "cliente" ? "DDT" : "Entrata merce"} ${d.documento.numero} creato e confermato` : "Ordine chiuso");
      onDone(d);
      onOpenChange(false);
    } catch (e) {
      const det = e.response?.data?.detail;
      if (e.response?.status === 409 && det?.carenze) {
        const msg = det.carenze.map((c) => `${c.codice}: richiesti ${c.richiesta}, disponibili ${c.disponibile}`).join("\n");
        if (window.confirm(`Giacenza insufficiente:\n${msg}\n\nConfermare comunque il DDT?`)) { setBusy(false); send(true); return; }
      } else toast.error(errMsg(e));
    }
    setBusy(false);
  };
  const tot = o.lines.reduce((s, l) => s + (Number(q[l.id]) || 0), 0);
  const parziale = o.lines.some((l) => (Number(q[l.id]) || 0) < res(l));
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] overflow-y-auto bg-white sm:max-w-3xl" data-testid="evadi-dialog">
        <DialogHeader><DialogTitle>Evadi ordine {o.numero_display} · {tipo === "cliente" ? "genera DDT di vendita" : "genera entrata merce (BEM)"}</DialogTitle></DialogHeader>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs text-slate-600">Data documento<Input type="date" value={data} onChange={(e) => setData(e.target.value)} data-testid="evadi-data" /></label>
          {tipo === "fornitore" && <label className="text-xs text-slate-600">N. DDT del fornitore<Input value={docF} onChange={(e) => setDocF(e.target.value)} data-testid="evadi-doc-fornitore" /></label>}
          <Button variant="outline" size="sm" onClick={() => setQ(Object.fromEntries(o.lines.map((l) => [l.id, String(res(l))])))} data-testid="evadi-tutto">Evadi tutto il residuo</Button>
          <Button variant="outline" size="sm" onClick={() => setQ({})} data-testid="evadi-azzera">Azzera quantità</Button>
        </div>
        <table className="w-full text-sm" data-testid="evadi-table">
          <thead className="text-left text-xs uppercase tracking-wider text-slate-500"><tr><th className="py-1">Articolo</th><th className="text-right">Ordinata</th><th className="text-right">Evasa</th><th className="text-right">Residuo</th><th className="text-right">Da evadere</th></tr></thead>
          <tbody>
            {o.lines.map((l) => (
              <tr key={l.id} className="border-t border-slate-100" data-testid={`evadi-row-${l.id}`}>
                <td className="py-2">{l.codice && <span className="mono text-xs">{l.codice} · </span>}{l.descrizione}</td>
                <td className="text-right">{l.quantita}</td><td className="text-right text-slate-500">{l.evasa || 0}</td><td className="text-right font-semibold">{res(l)}</td>
                <td className="py-1 pl-2 text-right"><Input type="number" min={0} max={res(l)} step="0.01" disabled={res(l) <= 0} value={q[l.id] ?? ""} onChange={(e) => setQ({ ...q, [l.id]: e.target.value })} className="ml-auto w-24 text-right" data-testid={`evadi-qta-${l.id}`} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        <label className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50/60 p-3 text-sm text-slate-700">
          <input type="checkbox" className="mt-1" checked={chiudi} onChange={(e) => setChiudi(e.target.checked)} data-testid="evadi-chiudi" />
          <span><b>Chiudi l'ordine</b> anche se resta un residuo (evasione forzata). {parziale ? "Senza spunta il residuo resta aperto e impegnato." : ""}{tot === 0 ? " Con tutte le quantità a zero l'ordine viene solo chiuso." : ""}</span>
        </label>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Annulla</Button>
          <Button onClick={() => send()} disabled={busy || (tot === 0 && !chiudi)} data-testid="evadi-conferma">{busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}{tot === 0 ? "Chiudi ordine" : tipo === "cliente" ? "Crea DDT" : "Registra entrata merce"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export const Evasioni = ({ o }) => {
  const evs = (o.evasioni || []);
  if (!evs.length) return null;
  return (
    <div className="mt-2 space-y-1 text-xs" data-testid={`ord-evasioni-${o.id}`}>
      {evs.map((e) => (
        <div key={e.id} className={e.annullata ? "text-slate-400 line-through" : "text-slate-600"}>
          {fmtDate(e.data)} · {e.tipo === "ddt" ? <Link to={`/ddt/${e.doc_id}`} className="font-semibold text-blue-700 hover:underline">DDT {e.numero}</Link> : <Link to="/bem" className="font-semibold text-blue-700 hover:underline">BEM {e.numero}</Link>} · {e.righe.length} righe{e.annullata ? " (annullato)" : ""}
        </div>
      ))}
    </div>
  );
};

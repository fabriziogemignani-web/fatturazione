import { useEffect, useState } from "react";
import { toast } from "sonner";
import { CreditCard, Printer, Landmark } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate, today } from "@/lib/fe";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth, canSend } from "@/context/AuthContext";

const meseCorrente = () => today().slice(0, 7);

const Movimenti = ({ c }) => (
  <table className="w-full text-sm" data-testid={`carta-mov-${c.conto}`}>
    <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
      <tr><th className="px-3 py-2">Data</th><th className="px-3 py-2">Reg.</th><th className="px-3 py-2">Descrizione</th><th className="px-3 py-2 text-right">Spesa</th><th className="px-3 py-2 text-right">Accredito</th></tr>
    </thead>
    <tbody>
      {c.movimenti.length === 0 && <tr><td colSpan={5} className="px-3 py-6 text-center text-xs text-slate-500">Nessun movimento nel mese</td></tr>}
      {c.movimenti.map((m) => (
        <tr key={m.id} className="border-b border-slate-100" data-testid={`carta-mov-row-${m.id}`}>
          <td className="px-3 py-2 text-xs">{fmtDate(m.data)}</td>
          <td className="mono px-3 py-2 text-xs">{m.numero}/{m.anno}</td>
          <td className="px-3 py-2 text-xs"><b>{m.causale}</b> · {m.descrizione}{m.party_nome && !m.descrizione.includes(m.party_nome) && <span className="text-slate-500"> · {m.party_nome}</span>}</td>
          <td className="px-3 py-2 text-right text-xs">{m.addebito ? fmtEUR(m.addebito) : ""}</td>
          <td className="px-3 py-2 text-right text-xs">{m.accredito ? fmtEUR(m.accredito) : ""}</td>
        </tr>
      ))}
    </tbody>
    <tfoot className="border-t-2 border-slate-800 text-xs font-bold">
      <tr><td colSpan={3} className="px-3 py-2">Totale del mese</td><td className="px-3 py-2 text-right" data-testid={`carta-spese-${c.conto}`}>{fmtEUR(c.totale_spese)}</td><td className="px-3 py-2 text-right">{fmtEUR(c.totale_accrediti)}</td></tr>
    </tfoot>
  </table>
);

const Addebito = ({ c, mese, banche, onDone }) => {
  const fineMese = `${mese}-${String(new Date(Number(mese.slice(0, 4)), Number(mese.slice(5, 7)), 0).getDate()).padStart(2, "0")}`;
  const [f, setF] = useState({ data: fineMese < today() ? today() : `${mese}-${fineMese.slice(8)}`, banca: "" });
  const banca = f.banca || banche[0]?.conto || "";
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/contabilita/carte/addebito", { conto: c.conto, mese, data: f.data, banca });
      toast.success(`Addebito registrato in prima nota n. ${data.numero}/${data.anno}`);
      onDone();
    } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };
  return (
    <div className="flex flex-wrap items-end gap-3 print:hidden" data-testid={`carta-addebito-form-${c.conto}`}>
      <label className="text-xs text-slate-600">Data addebito<Input type="date" value={f.data} onChange={(e) => setF({ ...f, data: e.target.value })} className="w-40 bg-white" data-testid={`carta-addebito-data-${c.conto}`} /></label>
      <label className="text-xs text-slate-600">Banca
        <select value={banca} onChange={(e) => setF({ ...f, banca: e.target.value })} className="block h-9 rounded-md border border-slate-200 bg-white px-2 text-sm" data-testid={`carta-addebito-banca-${c.conto}`}>
          {banche.map((b) => <option key={b.conto} value={b.conto}>{b.label} ({b.conto})</option>)}
        </select>
      </label>
      <Button onClick={save} disabled={busy || !banca} data-testid={`carta-addebito-btn-${c.conto}`}><Landmark className="mr-2 h-4 w-4" />Registra addebito {fmtEUR(c.da_addebitare)}</Button>
    </div>
  );
};

const Carta = ({ c, mese, banche, canEdit, onDone }) => {
  const nomeBanca = (code) => banche.find((b) => b.conto === code)?.label || code;
  return (
  <section className="mb-6 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm print:break-inside-avoid" data-testid={`carta-${c.conto}`}>
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
      <div className="flex items-center gap-2"><CreditCard className="h-5 w-5 text-slate-500" /><b>{c.label}</b><span className="mono text-xs text-slate-500">{c.conto}</span></div>
      <div className="flex gap-6 text-sm">
        <span>Addebitato <b data-testid={`carta-addebitato-${c.conto}`}>{fmtEUR(c.addebitato)}</b></span>
        <span>Da addebitare in banca <b className={c.da_addebitare > 0.005 ? "text-rose-700" : "text-emerald-700"} data-testid={`carta-da-addebitare-${c.conto}`}>{fmtEUR(c.da_addebitare)}</b></span>
      </div>
    </div>
    <div className="overflow-x-auto"><Movimenti c={c} /></div>
    <div className="space-y-2 border-t border-slate-200 bg-slate-50/60 px-4 py-3">
      {c.addebiti.map((a) => <div key={a.id} className="text-xs text-slate-600" data-testid={`carta-addebito-${a.id}`}>Addebito del {fmtDate(a.data)} su {nomeBanca(a.banca)}: {fmtEUR(a.importo)} · prima nota n. {a.numero}/{a.anno}</div>)}
      {canEdit && c.da_addebitare > 0.005 && <Addebito key={mese} c={c} mese={mese} banche={banche} onDone={onDone} />}
    </div>
  </section>
  );
};

export default function EstrattoCarte() {
  const { user } = useAuth();
  const [mese, setMese] = useState(meseCorrente());
  const [d, setD] = useState(null);
  const [banche, setBanche] = useState([]);
  const load = () => api.get("/contabilita/carte/estratto", { params: { mese } }).then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, [mese]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { api.get("/contabilita/conti-pagamento").then(({ data }) => setBanche(data.conti.filter((c) => c.tipo === "banca"))).catch(() => {}); }, []);
  return (
    <div>
      <PageHeader eyebrow="Contabilità generale" title="Estratto conto carte">
        <Button variant="outline" onClick={() => window.print()} data-testid="carte-print-btn"><Printer className="mr-2 h-4 w-4" />Stampa</Button>
      </PageHeader>
      <div className="mb-4 flex flex-wrap items-end gap-3 print:hidden">
        <label className="text-xs text-slate-600">Mese<Input type="month" value={mese} onChange={(e) => e.target.value && setMese(e.target.value)} className="w-44 bg-white" data-testid="carte-mese" /></label>
        <p className="text-xs text-slate-500">Movimenti registrati in prima nota sui conti carta (06.03). L'addebito in banca crea il giroconto Dare carta / Avere banca.</p>
      </div>
      {d && d.carte.length === 0 && <p className="text-sm text-slate-500" data-testid="carte-empty">Nessun conto carta: aggiungi un sottoconto 06.03 nel piano dei conti.</p>}
      {d?.carte.map((c) => <Carta key={c.conto} c={c} mese={mese} banche={banche} canEdit={canSend(user)} onDone={load} />)}
    </div>
  );
}

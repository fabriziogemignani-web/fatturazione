import { useEffect, useState } from "react";
import { toast } from "sonner";
import { PackagePlus, PackageMinus, Trash2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { MovimentoDialog, TIPI_MOV } from "@/components/MovimentoDialog";
import { ScortaBadge, SottoscortaSection } from "@/components/Sottoscorta";
import { useAuth, canSend } from "@/context/AuthContext";
import { fmtEUR, fmtDate } from "@/lib/fe";

const Tab = ({ on, onClick, children, id }) => (
  <button onClick={onClick} data-testid={id} className={`rounded-full px-4 py-1.5 text-sm font-semibold ${on ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}>{children}</button>
);

const Giacenze = ({ rows, onMove }) => (
  <table className="w-full text-sm" data-testid="giacenze-table">
    <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500"><tr>
      <th className="px-4 py-3">Articolo</th><th className="px-4 py-3 text-right">Giacenza</th><th className="px-4 py-3 text-right">Impegnato</th><th className="px-4 py-3 text-right">Ordinato</th><th className="px-4 py-3 text-right">Disponibile</th><th className="px-4 py-3 text-right">Scorta min.</th>
      <th className="px-4 py-3 text-right">Costo medio</th><th className="px-4 py-3 text-right">Valore</th><th className="px-4 py-3">Stato</th><th className="px-4 py-3" />
    </tr></thead>
    <tbody className="divide-y divide-slate-100">
      {rows.length === 0 && <tr><td colSpan={10} className="px-4 py-10 text-center text-slate-500" data-testid="giacenze-empty">Nessun articolo gestito a magazzino: attiva "Gestione magazzino" nell'anagrafica articoli.</td></tr>}
      {rows.map((a) => (
        <tr key={a.id} data-testid={`giacenza-row-${a.id}`}>
          <td className="px-4 py-3"><span className="mono text-xs font-medium">{a.codice}</span> · {a.descrizione}</td>
          <td className={`px-4 py-3 text-right font-bold ${(a.giacenza || 0) <= 0 ? "text-rose-700" : "text-slate-900"}`} data-testid={`giacenza-qty-${a.id}`}>{a.giacenza ?? 0} {a.unita_misura}</td>
          <td className="px-4 py-3 text-right text-amber-700" data-testid={`giacenza-impegnato-${a.id}`}>{a.impegnato || "—"}</td>
          <td className="px-4 py-3 text-right text-blue-700" data-testid={`giacenza-ordinato-${a.id}`}>{a.ordinato || "—"}</td>
          <td className={`px-4 py-3 text-right font-semibold ${(a.disponibilita ?? 0) < 0 ? "text-rose-700" : "text-emerald-700"}`} data-testid={`giacenza-disponibile-${a.id}`}>{a.disponibilita ?? a.giacenza ?? 0}</td>
          <td className="px-4 py-3 text-right text-slate-600">{a.scorta_minima || "—"}</td>
          <td className="px-4 py-3 text-right">{fmtEUR(a.costo_medio || 0)}</td>
          <td className="px-4 py-3 text-right font-semibold" data-testid={`giacenza-valore-${a.id}`}>{fmtEUR(a.valore_magazzino || 0)}</td>
          <td className="px-4 py-3"><ScortaBadge s={a.stato_scorta} testId={`giacenza-stato-${a.id}`} /></td>
          <td className="whitespace-nowrap px-4 py-3 text-right">
            <Button size="sm" variant="outline" onClick={() => onMove(a, "carico")} title="Carico" aria-label="Carico" data-testid={`giacenza-carico-${a.id}`}><PackagePlus className="h-3.5 w-3.5" /></Button>{" "}
            <Button size="sm" variant="outline" onClick={() => onMove(a, "scarico")} title="Scarico" aria-label="Scarico" data-testid={`giacenza-scarico-${a.id}`}><PackageMinus className="h-3.5 w-3.5" /></Button>
          </td>
        </tr>
      ))}
    </tbody>
  </table>
);

const Movimenti = ({ rows, canDel, onDel }) => (
  <table className="w-full text-sm" data-testid="movimenti-table">
    <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500"><tr>
      <th className="px-4 py-3">Data</th><th className="px-4 py-3">Tipo</th><th className="px-4 py-3">Articolo</th><th className="px-4 py-3 text-right">Quantità</th>
      <th className="px-4 py-3 text-right">Costo</th><th className="px-4 py-3 text-right">Giacenza dopo</th><th className="px-4 py-3">Causale / documento</th><th className="px-4 py-3" />
    </tr></thead>
    <tbody className="divide-y divide-slate-100">
      {rows.length === 0 && <tr><td colSpan={8} className="px-4 py-10 text-center text-slate-500" data-testid="movimenti-empty">Nessun movimento</td></tr>}
      {rows.map((m) => {
        const neg = m.tipo === "scarico" || m.quantita < 0;
        return (
          <tr key={m.id} data-testid={`movimento-row-${m.id}`}>
            <td className="whitespace-nowrap px-4 py-3">{fmtDate(m.data)}</td>
            <td className="px-4 py-3">{TIPI_MOV.find((x) => x[0] === m.tipo)?.[1]}</td>
            <td className="px-4 py-3"><span className="mono text-xs">{m.codice}</span> · {m.descrizione}</td>
            <td className={`whitespace-nowrap px-4 py-3 text-right font-bold ${neg ? "text-rose-700" : "text-emerald-700"}`}>{neg ? "−" : "+"}{Math.abs(m.quantita)} {m.unita_misura}</td>
            <td className="px-4 py-3 text-right">{m.costo_unitario != null ? fmtEUR(m.costo_unitario) : "—"}</td>
            <td className="px-4 py-3 text-right text-slate-600">{m.giacenza_dopo != null ? m.giacenza_dopo : "—"}</td>
            <td className="px-4 py-3 text-slate-600">{m.causale}{m.documento ? ` · ${m.documento}` : ""}{m.note ? ` · ${m.note}` : ""}<div className="text-xs text-slate-400">{m.created_by}</div></td>
            <td className="px-4 py-3 text-right">{canDel && <button onClick={() => onDel(m)} className="rounded p-1.5 text-slate-500 hover:bg-rose-50 hover:text-rose-600" data-testid={`movimento-delete-${m.id}`}><Trash2 className="h-4 w-4" /></button>}</td>
          </tr>
        );
      })}
    </tbody>
  </table>
);

export default function Magazzino() {
  const { user } = useAuth();
  const [tab, setTab] = useState("giacenze");
  const [g, setG] = useState({ articoli: [], valore_totale: 0, sottoscorta: 0, causali: {} });
  const [movs, setMovs] = useState([]);
  const [art, setArt] = useState("");
  const [dlg, setDlg] = useState(null);
  const load = () => {
    api.get("/magazzino/articoli").then(({ data }) => setG(data)).catch((e) => toast.error(errMsg(e)));
    api.get("/magazzino/movimenti", { params: { article_id: art || undefined } }).then(({ data }) => setMovs(data)).catch(() => {});
  };
  useEffect(() => { load(); }, [art]); // eslint-disable-line react-hooks/exhaustive-deps
  const del = async (m) => {
    if (!window.confirm("Eliminare il movimento?")) return;
    try { await api.delete(`/magazzino/movimenti/${m.id}`); toast.success("Movimento eliminato"); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  const sotto = g.articoli.filter((a) => ["sottoscorta", "esaurito"].includes(a.stato_scorta));

  return (
    <div>
      <PageHeader eyebrow="Archivio" title="Magazzino">
        <Button variant="outline" onClick={() => setDlg({ tipo: "scarico" })} data-testid="new-scarico-btn"><PackageMinus className="mr-2 h-4 w-4" />Scarico</Button>
        <Button onClick={() => setDlg({ tipo: "carico" })} data-testid="new-carico-btn"><PackagePlus className="mr-2 h-4 w-4" />Carico</Button>
      </PageHeader>
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded-xl bg-slate-900 p-5 text-white"><div className="text-xs text-slate-300">Valore magazzino (costo medio)</div><div className="mt-1 text-2xl font-extrabold" data-testid="magazzino-valore">{fmtEUR(g.valore_totale)}</div></div>
        <div className="rounded-xl border border-slate-200 bg-white p-5"><div className="text-xs text-slate-500">Articoli gestiti</div><div className="mt-1 text-2xl font-extrabold" data-testid="magazzino-articoli">{g.articoli.length}</div></div>
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-5"><div className="text-xs text-amber-700">Sottoscorta</div><div className="mt-1 text-2xl font-extrabold text-amber-800" data-testid="magazzino-sottoscorta">{g.sottoscorta}</div></div>
      </div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Tab id="tab-giacenze" on={tab === "giacenze"} onClick={() => setTab("giacenze")}>Giacenze</Tab>
        <Tab id="tab-movimenti" on={tab === "movimenti"} onClick={() => setTab("movimenti")}>Movimenti</Tab>
        <Tab id="tab-sottoscorta" on={tab === "sottoscorta"} onClick={() => setTab("sottoscorta")}>Sottoscorta ({sotto.length})</Tab>
        {tab === "movimenti" && (
          <select value={art} onChange={(e) => setArt(e.target.value)} className="ml-auto rounded-md border border-slate-200 px-3 py-1.5 text-sm" data-testid="movimenti-article-filter">
            <option value="">Tutti gli articoli</option>{g.articoli.map((a) => <option key={a.id} value={a.id}>{a.codice} · {a.descrizione}</option>)}
          </select>
        )}
      </div>
      {tab === "sottoscorta" ? <SottoscortaSection rows={sotto} onCarico={(a) => setDlg({ tipo: "carico", article_id: a.id })} /> : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
          {tab === "giacenze" ? <Giacenze rows={g.articoli} onMove={(a, tipo) => setDlg({ tipo, article_id: a.id })} /> : <Movimenti rows={movs} canDel={canSend(user)} onDel={del} />}
        </div>
      )}
      <MovimentoDialog open={!!dlg} preset={dlg} onClose={() => setDlg(null)} onSaved={load} articoli={g.articoli} causali={g.causali} />
    </div>
  );
}

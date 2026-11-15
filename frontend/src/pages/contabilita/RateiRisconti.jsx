import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Pencil, Trash2, FlaskConical, CheckCircle2, Undo2, Printer } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { ModificaRR, NuovoRR } from "@/components/coge/RateiDialogs";

const STATO = { da_contabilizzare: ["Da contabilizzare", "bg-slate-100 text-slate-700"], simulata: ["Simulazione", "bg-amber-100 text-amber-800"], definitiva: ["Definitiva", "bg-emerald-100 text-emerald-800"], non_dovuto: ["Non riguarda l'anno", "bg-slate-50 text-slate-400"] };
const annoDef = () => { const d = new Date(); return d.getMonth() < 5 ? d.getFullYear() - 1 : d.getFullYear(); };

const Riga = ({ x, checked, onCheck, onEdit, onDel }) => (
  <tr data-testid={`rr-row-${x.id}`} className={x.stato === "non_dovuto" ? "text-slate-400" : ""}>
    <td className="pl-3"><input type="checkbox" checked={checked} disabled={x.stato === "non_dovuto" || x.stato === "definitiva"} onChange={onCheck} data-testid={`rr-check-${x.id}`} /></td>
    <td className="px-3 py-2"><div className="mono text-xs font-semibold">{x.documento}</div><div className="text-xs text-slate-500">{fmtDate(x.data_documento)} · reg. {fmtDate(x.data_registrazione)}</div></td>
    <td className="px-3 py-2 text-xs">{x.party_nome}<div className="text-slate-500">{x.origine === "acquisto" ? "Fornitore" : "Cliente"}</div></td>
    <td className="px-3 py-2 text-xs font-semibold" data-testid={`rr-tipo-${x.id}`}>{x.nome_tipo}</td>
    <td className="px-3 py-2 text-xs">{fmtDate(x.competenza_dal)} → {fmtDate(x.competenza_al)}<div className="text-slate-500">{x.quota.giorni_totali} gg{x.note ? ` · ${x.note}` : ""}</div></td>
    <td className="px-3 py-2 text-right text-xs">{fmtEUR(x.importo)}</td>
    <td className="px-3 py-2 text-right text-xs font-semibold" data-testid={`rr-quota-${x.id}`}>{x.quota.giorni ? <>{fmtEUR(x.quota.importo)}<div className="font-normal text-slate-500">{x.quota.giorni} gg</div></> : "—"}</td>
    <td className="px-3 py-2"><span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${STATO[x.stato][1]}`} data-testid={`rr-stato-${x.id}`}>{STATO[x.stato][0]}</span></td>
    <td className="whitespace-nowrap px-3 py-2 text-right">
      {!x.definitive.length && <>
        <Button size="sm" variant="outline" onClick={onEdit} title="Modifica veloce" data-testid={`rr-edit-${x.id}`}><Pencil className="h-3.5 w-3.5" /></Button>
        <Button size="sm" variant="outline" className="ml-1 text-rose-600" onClick={onDel} title="Elimina" data-testid={`rr-del-${x.id}`}><Trash2 className="h-3.5 w-3.5" /></Button>
      </>}
    </td>
  </tr>
);

export default function RateiRisconti() {
  const [anno, setAnno] = useState(annoDef());
  const [rows, setRows] = useState(null);
  const [selez, setSelez] = useState({});
  const [edit, setEdit] = useState(null);
  const [nuovo, setNuovo] = useState(false);
  const load = () => api.get("/contabilita/ratei", { params: { anno } }).then(({ data }) => { setRows(data); setSelez({}); }).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, [anno]); // eslint-disable-line react-hooks/exhaustive-deps
  const ids = Object.keys(selez).filter((k) => selez[k]);
  const run = async (path, body, msg) => {
    if (msg && !window.confirm(msg)) return;
    try {
      const { data } = await api.post(`/contabilita/ratei/${path}`, { anno, ids: ids.length ? ids : null, ...body });
      if (data.errori?.length) toast.error(data.errori.join("\n")); else toast.success(path === "annulla" ? `${data.annullati} contabilizzazioni annullate` : `${data.contabilizzati} ratei/risconti contabilizzati`);
      load();
    } catch (e) { toast.error(errMsg(e)); }
  };
  const del = async (x) => { if (!window.confirm(`Eliminare il ${x.nome_tipo.toLowerCase()} di ${x.documento}?`)) return; try { await api.delete(`/contabilita/ratei/${x.id}`); load(); } catch (e) { toast.error(errMsg(e)); } };
  const stampa = async () => {
    const w = window.open("", "_blank");
    try {
      const { data } = await api.get("/contabilita/ratei/pdf", { params: { anno }, responseType: "blob" });
      const url = URL.createObjectURL(new Blob([data], { type: "application/pdf" }));
      if (w) w.location.href = url; else { const a = document.createElement("a"); a.href = url; a.download = `Ratei_risconti_${anno}.pdf`; a.click(); }
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (e) { if (w) w.close(); toast.error(errMsg(e)); }
  };
  const tot = (rows || []).filter((x) => x.quota.giorni).reduce((a, x) => ({ ...a, [x.nome_tipo]: (a[x.nome_tipo] || 0) + x.quota.importo }), {});
  const quanti = ids.length ? `i ${ids.length} selezionati` : "tutti quelli dell'anno";
  return (
    <div data-testid="ratei-page">
      <PageHeader eyebrow="Contabilità generale" title="Ratei e risconti" subtitle="Quote di competenza calcolate a giorni effettivi: scrittura al 31/12 e storno automatico all'1/1 dell'anno dopo">
        <Button variant="outline" onClick={stampa} data-testid="rr-pdf-btn"><Printer className="mr-2 h-4 w-4" />Stampa prospetto</Button>
        <Button variant="outline" onClick={() => setNuovo(true)} data-testid="rr-new-btn"><Plus className="mr-2 h-4 w-4" />Nuovo</Button>
      </PageHeader>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <label className="text-xs text-slate-600">Esercizio<select value={anno} onChange={(e) => setAnno(Number(e.target.value))} className="block h-9 rounded-md border border-slate-200 bg-white px-2 text-sm" data-testid="rr-anno">{[0, 1, 2, 3, 4].map((i) => new Date().getFullYear() + 1 - i).map((y) => <option key={y} value={y}>{y}</option>)}</select></label>
        <Button variant="outline" onClick={() => run("contabilizza", { definitiva: false })} data-testid="rr-simula-btn"><FlaskConical className="mr-2 h-4 w-4" />Contabilizza in simulazione</Button>
        <Button onClick={() => run("contabilizza", { definitiva: true }, `Contabilizzare in definitiva ${quanti} al 31/12/${anno} con storno all'1/1/${anno + 1}?`)} data-testid="rr-definitiva-btn"><CheckCircle2 className="mr-2 h-4 w-4" />Contabilizza definitiva</Button>
        <Button variant="outline" className="text-rose-600" onClick={() => run("annulla", {}, `Annullare le contabilizzazioni ${anno} di ${quanti}?`)} data-testid="rr-annulla-btn"><Undo2 className="mr-2 h-4 w-4" />Annulla contabilizzazione</Button>
        <div className="ml-auto flex flex-wrap gap-2 text-xs" data-testid="rr-totali">{Object.entries(tot).map(([k, v]) => <span key={k} className="rounded-full bg-slate-100 px-3 py-1 font-semibold">{k}: {fmtEUR(v)}</span>)}</div>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm" data-testid="rr-table">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500"><tr><th className="w-8" /><th className="px-3 py-3">Documento</th><th className="px-3 py-3">Anagrafica</th><th className="px-3 py-3">Tipo</th><th className="px-3 py-3">Competenza</th><th className="px-3 py-3 text-right">Imponibile</th><th className="px-3 py-3 text-right">Quota {anno}</th><th className="px-3 py-3">Stato {anno}</th><th /></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {rows?.length === 0 && <tr><td colSpan={9} className="px-4 py-10 text-center text-slate-500" data-testid="rr-empty">Nessun rateo o risconto. Attiva il flag sull'anagrafica e indica le date di competenza quando registri la fattura.</td></tr>}
            {rows?.map((x) => <Riga key={x.id} x={x} checked={!!selez[x.id]} onCheck={() => setSelez({ ...selez, [x.id]: !selez[x.id] })} onEdit={() => setEdit(x)} onDel={() => del(x)} />)}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-slate-500">In simulazione le scritture sono provvisorie: il bilancio le mostra solo se scegli «Anche provvisorie» e l'esercizio non si può chiudere finché restano in simulazione.</p>
      {edit && <ModificaRR x={edit} anno={anno} onClose={() => setEdit(null)} onDone={load} />}
      {nuovo && <NuovoRR onClose={() => setNuovo(false)} onDone={load} />}
    </div>
  );
}

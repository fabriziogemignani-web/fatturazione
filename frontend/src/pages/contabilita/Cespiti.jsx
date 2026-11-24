import { Fragment, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { ChevronDown, ChevronRight, PenLine, Trash2, Sparkles, Archive, Undo2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { useAuth, canSend } from "@/context/AuthContext";
import { CespiteDialog } from "@/components/cespiti/CespiteDialog";
import { AmmortamentiPanel } from "@/components/cespiti/AmmortamentiPanel";

const REGOLE = [["meta", "Metà aliquota nel primo anno"], ["giorni", "Pro rata giorni di possesso"], ["piena", "Aliquota piena"]];
const oggi = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };

const Config = ({ cfg, edit, onSave }) => (
  <div className="mb-5 flex flex-wrap items-center gap-2 text-sm" data-testid="cespiti-config">
    <span className="text-slate-600">Primo anno di ammortamento:</span>
    {REGOLE.map(([v, l]) => <button key={v} disabled={!edit} onClick={() => onSave(v)} data-testid={`cespiti-regola-${v}`} className={`rounded-full border px-3 py-1 text-xs font-semibold transition-colors ${cfg === v ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 text-slate-600 hover:border-slate-400"}`}>{l}</button>)}
  </div>
);

const Proposte = ({ list, edit, onCrea, onIgnora }) => !list.length ? null : (
  <section className="mb-6 rounded-xl border border-violet-200 bg-violet-50/60 p-4" data-testid="cespiti-proposte">
    <h3 className="mb-2 flex items-center gap-2 font-semibold text-violet-900"><Sparkles className="h-4 w-4" />Righe di fatture registrate nelle immobilizzazioni, senza scheda cespite</h3>
    <ul className="divide-y divide-violet-100 text-sm">
      {list.map((p) => (
        <li key={`${p.passive_id}-${p.riga_n}`} className="flex flex-wrap items-center justify-between gap-2 py-2" data-testid={`proposta-${p.passive_id}-${p.riga_n}`}>
          <span className="min-w-0"><b>{p.descrizione}</b><span className="ml-2 text-xs text-slate-500">fatt. {p.numero_display} · {p.fornitore} · conto {p.conto}</span></span>
          <span className="flex items-center gap-2"><b>{fmtEUR(p.costo)}</b>{edit && <>
            <Button size="sm" onClick={() => onCrea(p)} data-testid={`proposta-crea-${p.passive_id}-${p.riga_n}`}>Crea cespite</Button>
            <Button size="sm" variant="ghost" onClick={() => onIgnora(p)} title="Non creare cespiti per questa fattura" data-testid={`proposta-ignora-${p.passive_id}-${p.riga_n}`}>Ignora</Button></>}</span>
        </li>
      ))}
    </ul>
  </section>
);

const Riga = ({ c, edit, a }) => {
  const [open, setOpen] = useState(false);
  return (
    <Fragment>
      <tr className={`hover:bg-slate-50 ${c.data_dismissione ? "text-slate-400" : ""}`} data-testid={`cespite-row-${c.id}`}>
        <td className="px-3 py-2"><button onClick={() => setOpen(!open)} data-testid={`cespite-toggle-${c.id}`}>{open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}</button></td>
        <td className="px-3 py-2"><b>{c.descrizione}</b><div className="text-xs text-slate-500">{c.categoria_nome}{c.data_dismissione ? ` · dismesso il ${fmtDate(c.data_dismissione)}` : ""}</div></td>
        <td className="px-3 py-2">{fmtDate(c.data_acquisto)}</td>
        <td className="px-3 py-2 text-right">{fmtEUR(c.costo)}</td>
        <td className="px-3 py-2 text-right">{c.aliquota}%</td>
        <td className="px-3 py-2 text-right">{fmtEUR(c.fondo_inizio_anno)}</td>
        <td className="px-3 py-2 text-right font-semibold" data-testid={`cespite-quota-${c.id}`}>{fmtEUR(c.quota_anno)}</td>
        <td className="px-3 py-2 text-right">{fmtEUR(c.residuo_inizio_anno)}</td>
        <td className="whitespace-nowrap px-3 py-2 text-right">{edit && <>
          {!c.ammortamenti?.length && <Button size="sm" variant="ghost" onClick={() => a.modifica(c)} title="Modifica" data-testid={`cespite-edit-${c.id}`}><PenLine className="h-4 w-4" /></Button>}
          {c.data_dismissione ? <Button size="sm" variant="ghost" onClick={() => a.riattiva(c)} title="Riattiva" data-testid={`cespite-riattiva-${c.id}`}><Undo2 className="h-4 w-4" /></Button>
            : <Button size="sm" variant="ghost" onClick={() => a.dismetti(c)} title="Dismetti" data-testid={`cespite-dismetti-${c.id}`}><Archive className="h-4 w-4" /></Button>}
          {!c.ammortamenti?.length && <Button size="sm" variant="ghost" onClick={() => a.elimina(c)} title="Elimina" data-testid={`cespite-del-${c.id}`}><Trash2 className="h-4 w-4 text-rose-600" /></Button>}
        </>}</td>
      </tr>
      {open && <tr><td colSpan={9} className="bg-slate-50 px-10 py-3" data-testid={`cespite-piano-${c.id}`}>
        <div className="flex flex-wrap gap-2 text-xs">{c.piano.map((p) => <span key={p.anno} className={`rounded-md border px-2 py-1 ${p.registrato ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-slate-200 bg-white"}`}><b>{p.anno}</b> {fmtEUR(p.quota)} · fondo {fmtEUR(p.fondo)}</span>)}
          {!c.piano.length && <span className="text-slate-500">Nessun ammortamento (bene non ammortizzabile o già ammortizzato)</span>}</div>
      </td></tr>}
    </Fragment>
  );
};

export default function Cespiti() {
  const { user } = useAuth();
  const edit = canSend(user);
  const [sp] = useSearchParams();
  const [rows, setRows] = useState(null);
  const [cat, setCat] = useState([]);
  const [cfg, setCfg] = useState("meta");
  const [prop, setProp] = useState([]);
  const [dlg, setDlg] = useState(null);
  const [rk, setRk] = useState(0);
  const load = useCallback(() => {
    setRk((k) => k + 1);
    api.get("/cespiti").then(({ data }) => setRows(data)).catch((e) => toast.error(errMsg(e)));
    api.get("/cespiti/proposte").then(({ data }) => setProp(data)).catch(() => {});
  }, []);
  useEffect(() => {
    load();
    api.get("/cespiti/categorie").then(({ data }) => setCat(data));
    api.get("/cespiti/config").then(({ data }) => setCfg(data.primo_anno));
  }, [load]);
  const fromProp = useCallback((p) => {
    const c = cat.find((x) => x.id === p.categoria) || {};
    setDlg({ ...p, aliquota: p.aliquota, conto_cespite: p.conto, conto_fondo: c.conto_fondo, conto_ammortamento: c.conto_ammortamento, fondo_iniziale: 0, data_entrata_funzione: "" });
  }, [cat]);
  useEffect(() => {
    const fid = sp.get("fattura");
    const p = fid && cat.length && prop.find((x) => x.passive_id === fid);
    if (p) fromProp(p);
  }, [sp, prop, cat, fromProp]);
  const act = async (fn, msg) => { try { await fn(); toast.success(msg); load(); } catch (e) { toast.error(errMsg(e)); } };
  const a = {
    modifica: setDlg,
    elimina: (c) => window.confirm("Eliminare il cespite?") && act(() => api.delete(`/cespiti/${c.id}`), "Cespite eliminato"),
    dismetti: (c) => { const d = window.prompt("Data di dismissione (AAAA-MM-GG)", oggi()); if (d) act(() => api.post(`/cespiti/${c.id}/dismetti`, { data: d }), "Cespite dismesso"); },
    riattiva: (c) => act(() => api.delete(`/cespiti/${c.id}/dismetti`), "Cespite riattivato"),
  };
  const saveCfg = (v) => api.put("/cespiti/config", { primo_anno: v }).then(() => { setCfg(v); toast.success("Regola del primo anno aggiornata"); load(); }).catch((e) => toast.error(errMsg(e)));
  const nuovo = () => { const c = cat.find((x) => x.id === "attrezzature") || cat[0]; setDlg({ descrizione: "", categoria: c.id, aliquota: c.aliquota, conto_cespite: c.conto_cespite, conto_fondo: c.conto_fondo, conto_ammortamento: c.conto_ammortamento, costo: "", data_acquisto: oggi(), data_entrata_funzione: "", fondo_iniziale: 0, fornitore: "" }); };
  return (
    <div>
      <PageHeader eyebrow="Contabilità" title="Cespiti e ammortamenti">{edit && cat.length > 0 && <Button onClick={nuovo} data-testid="cespite-new-btn">Nuovo cespite</Button>}</PageHeader>
      <Config cfg={cfg} edit={edit} onSave={saveCfg} />
      <Proposte list={prop} edit={edit} onCrea={fromProp} onIgnora={(p) => act(() => api.post(`/cespiti/proposte/${p.passive_id}/ignora`), "Fattura esclusa dalle proposte")} />
      <AmmortamentiPanel edit={edit} onChange={load} reload={rk} />
      <section className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm" data-testid="cespiti-table">
          <thead className="border-b border-slate-200 text-left text-xs uppercase tracking-wider text-slate-500"><tr><th /><th className="px-3 py-2">Cespite</th><th className="px-3 py-2">Acquisto</th><th className="px-3 py-2 text-right">Costo</th><th className="px-3 py-2 text-right">Aliquota</th><th className="px-3 py-2 text-right">Fondo inizio anno</th><th className="px-3 py-2 text-right">Quota {new Date().getFullYear()}</th><th className="px-3 py-2 text-right">Residuo</th><th /></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {!rows ? <tr><td colSpan={9} className="px-5 py-8 text-center text-slate-500">Caricamento…</td></tr>
              : rows.length === 0 ? <tr><td colSpan={9} className="px-5 py-8 text-center text-slate-500" data-testid="cespiti-empty">Nessun cespite registrato.</td></tr>
              : rows.map((c) => <Riga key={c.id} c={c} edit={edit} a={a} />)}
          </tbody>
        </table>
      </section>
      <CespiteDialog val={dlg} categorie={cat} onClose={() => setDlg(null)} onSaved={load} />
    </div>
  );
}

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { FileUp, PenLine, Trash2, Undo2, Wallet, FileText, Loader2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { useAuth, canSend } from "@/context/AuthContext";
import { PianoDialog } from "@/components/rateizzazioni/PianoDialog";
import { PagaRataDialog } from "@/components/rateizzazioni/PagaRataDialog";

const STATO = { pagata: ["Pagata", "bg-emerald-100 text-emerald-800"], scaduta: ["Scaduta", "bg-rose-100 text-rose-800"], in_scadenza: ["In scadenza", "bg-amber-100 text-amber-800"], da_pagare: ["Da pagare", "bg-slate-100 text-slate-700"] };
const oggi = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const VUOTO = () => ({ ente: "Agenzia delle Entrate", numero: "", descrizione: "", data: oggi(), conto_debito: "13.05.003", conto_sanzioni: "30.14.003", conto_interessi: "40.02.001", rate: [{ scadenza: oggi(), capitale: 0, sanzioni: 0, interessi: 0 }] });

const apriPdf = (id) => api.get(`/rateizzazioni/${id}/pdf`, { responseType: "blob" }).then(({ data }) => window.open(URL.createObjectURL(data), "_blank")).catch((e) => toast.error(errMsg(e)));

const RataRow = ({ p, r, edit, onPaga, onAnnulla }) => (
  <tr className={r.stato === "scaduta" ? "bg-rose-50/50" : ""} data-testid={`rata-row-${p.id}-${r.n}`}>
    <td className="px-4 py-2 text-xs text-slate-500">{r.n}/{p.rate.length}</td>
    <td className="px-4 py-2 font-medium">{fmtDate(r.scadenza)}</td>
    <td className="px-4 py-2 text-right">{fmtEUR(r.capitale)}</td>
    <td className="px-4 py-2 text-right">{fmtEUR(r.sanzioni)}</td>
    <td className="px-4 py-2 text-right">{fmtEUR(r.interessi)}</td>
    <td className="px-4 py-2 text-right font-semibold">{fmtEUR(r.totale)}</td>
    <td className="px-4 py-2"><span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${STATO[r.stato][1]}`} data-testid={`rata-stato-${p.id}-${r.n}`}>{STATO[r.stato][0]}</span>
      {r.pagamento && <span className="ml-2 text-xs text-slate-500">il {fmtDate(r.pagamento.data)}{r.pagamento.coge_rif ? ` · ${r.pagamento.coge_rif}` : ""}</span>}</td>
    <td className="whitespace-nowrap px-4 py-2 text-right">
      {edit && !r.pagamento && <Button size="sm" variant="outline" onClick={() => onPaga(p, r)} data-testid={`rata-paga-${p.id}-${r.n}`}><Wallet className="mr-1 h-3.5 w-3.5" />Paga</Button>}
      {edit && r.pagamento && <Button size="sm" variant="ghost" onClick={() => onAnnulla(p, r)} title="Annulla pagamento" data-testid={`rata-annulla-${p.id}-${r.n}`}><Undo2 className="h-3.5 w-3.5" /></Button>}
    </td>
  </tr>
);

const Piano = ({ p, edit, onEdit, onDelete, onPaga, onAnnulla }) => (
  <section className="mb-5 rounded-xl border border-slate-200 bg-white shadow-sm" data-testid={`piano-${p.id}`}>
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
      <div className="min-w-0">
        <h3 className="font-semibold text-slate-900">{p.ente} {p.numero && <span className="mono text-sm text-slate-500">· {p.numero}</span>}</h3>
        <p className="text-xs text-slate-500">{p.descrizione || "Senza descrizione"} · del {fmtDate(p.data)}</p>
      </div>
      <div className="flex flex-wrap items-center gap-4 text-sm">
        <span>Totale <b>{fmtEUR(p.totale)}</b></span>
        <span className="text-emerald-700">Pagato <b>{fmtEUR(p.pagato)}</b></span>
        <span className="text-rose-700" data-testid={`piano-residuo-${p.id}`}>Residuo <b>{fmtEUR(p.residuo)}</b></span>
        <span className="text-xs text-slate-500">{p.rate_pagate}/{p.rate.length} rate</span>
        {p.pdf_id && <Button size="sm" variant="ghost" onClick={() => apriPdf(p.id)} title="Apri PDF" data-testid={`piano-pdf-${p.id}`}><FileText className="h-4 w-4" /></Button>}
        {edit && p.rate_pagate === 0 && <>
          <Button size="sm" variant="ghost" onClick={() => onEdit(p)} title="Modifica" data-testid={`piano-edit-${p.id}`}><PenLine className="h-4 w-4" /></Button>
          <Button size="sm" variant="ghost" onClick={() => onDelete(p)} title="Elimina" data-testid={`piano-del-${p.id}`}><Trash2 className="h-4 w-4 text-rose-600" /></Button>
        </>}
      </div>
    </div>
    {p.rate_scadute > 0 && <p className="bg-rose-50 px-5 py-2 text-xs font-semibold text-rose-700" data-testid={`piano-alert-${p.id}`}>{p.rate_scadute} {p.rate_scadute === 1 ? "rata scaduta" : "rate scadute"} non pagate: verifica il rischio di decadenza del piano.</p>}
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-xs uppercase tracking-wider text-slate-500"><tr><th className="px-4 py-2">Rata</th><th className="px-4 py-2">Scadenza</th><th className="px-4 py-2 text-right">Imposta</th><th className="px-4 py-2 text-right">Sanzioni</th><th className="px-4 py-2 text-right">Interessi e oneri</th><th className="px-4 py-2 text-right">Totale</th><th className="px-4 py-2">Stato</th><th /></tr></thead>
        <tbody className="divide-y divide-slate-100">{p.rate.map((r) => <RataRow key={r.n} p={p} r={r} edit={edit} onPaga={onPaga} onAnnulla={onAnnulla} />)}</tbody>
      </table>
    </div>
  </section>
);

export default function Rateizzazioni() {
  const { user } = useAuth();
  const edit = canSend(user);
  const [d, setD] = useState(null);
  const [dlg, setDlg] = useState(null);
  const [paga, setPaga] = useState(null);
  const [reading, setReading] = useState(false);
  const fileRef = useRef(null);
  const load = useCallback(() => { api.get("/rateizzazioni").then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e))); }, []);
  useEffect(() => { load(); }, [load]);
  const upload = async (file) => {
    if (!file) return;
    setReading(true);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const { data } = await api.post("/rateizzazioni/leggi-pdf", fd, { timeout: 180000 });
      if (!data.rate.length) toast.warning("Nessuna rata trovata nel PDF: inseriscile a mano");
      setDlg({ ...data, rate: data.rate.length ? data.rate : VUOTO().rate });
    } catch (e) { toast.error(errMsg(e)); } finally { setReading(false); if (fileRef.current) fileRef.current.value = ""; }
  };
  const del = async (p) => { if (!window.confirm("Eliminare il piano di rateizzazione?")) return; try { await api.delete(`/rateizzazioni/${p.id}`); toast.success("Piano eliminato"); load(); } catch (e) { toast.error(errMsg(e)); } };
  const annulla = async (p, r) => { if (!window.confirm(`Annullare il pagamento della rata ${r.n}? Viene tolta anche la registrazione in prima nota.`)) return; try { await api.delete(`/rateizzazioni/${p.id}/rate/${r.n}/paga`); toast.success("Pagamento annullato"); load(); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <div>
      <PageHeader eyebrow="Tesoreria" title="Rateizzazioni fiscali">
        {edit && <>
          <input ref={fileRef} type="file" accept="application/pdf" className="hidden" onChange={(e) => upload(e.target.files?.[0])} data-testid="rat-pdf-input" />
          <Button variant="outline" onClick={() => setDlg(VUOTO())} data-testid="rat-new-btn">Inserisci a mano</Button>
          <Button onClick={() => fileRef.current?.click()} disabled={reading} data-testid="rat-upload-btn">{reading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FileUp className="mr-2 h-4 w-4" />}{reading ? "Lettura del PDF…" : "Carica PDF del piano"}</Button>
        </>}
      </PageHeader>
      <p className="mb-5 max-w-3xl text-sm text-slate-600">Carica il piano di rateizzazione dell'Agenzia delle Entrate o dell'Agenzia delle Entrate-Riscossione: l'IA legge rate, scadenze e importi e te li propone da controllare. Le rate entrano nella situazione finanziaria e, quando le paghi, in prima nota.</p>
      {!d ? <div className="text-sm text-slate-500">Caricamento…</div> : d.piani.length === 0
        ? <div className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-500" data-testid="rat-empty">Nessun piano di rateizzazione caricato.</div>
        : d.piani.map((p) => <Piano key={p.id} p={p} edit={edit} onEdit={setDlg} onDelete={del} onPaga={(pp, r) => setPaga({ url: `/rateizzazioni/${pp.id}/rate/${r.n}/paga`, titolo: `Paga rata ${r.n}/${pp.rate.length}`, info: `${pp.ente} ${pp.numero || ""} · scadenza ${fmtDate(r.scadenza)} · ${fmtEUR(r.totale)}`, dettaglio: `Imposta ${fmtEUR(r.capitale)} · sanzioni ${fmtEUR(r.sanzioni)} · interessi e oneri ${fmtEUR(r.interessi)}` })} onAnnulla={annulla} />)}
      <PianoDialog piano={dlg} onClose={() => setDlg(null)} onSaved={load} />
      <PagaRataDialog req={paga} conti={d?.conti_pagamento} onClose={() => setPaga(null)} onDone={load} />
    </div>
  );
}

import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { FileUp, PenLine, Trash2, Undo2, Wallet, FileText, Loader2, Link2, Unlink, Banknote } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { useAuth, canSend } from "@/context/AuthContext";
import { FinDialog } from "@/components/finanziamenti/FinDialog";
import { CollegaFatturaDialog } from "@/components/finanziamenti/CollegaFatturaDialog";
import { PagaRataDialog } from "@/components/rateizzazioni/PagaRataDialog";

const STATO = { pagata: ["Pagata", "bg-emerald-100 text-emerald-800"], scaduta: ["Scaduta", "bg-rose-100 text-rose-800"], in_scadenza: ["In scadenza", "bg-amber-100 text-amber-800"], da_pagare: ["Da pagare", "bg-slate-100 text-slate-700"], fattura: ["Fattura da pagare", "bg-blue-100 text-blue-800"] };
const oggi = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const VUOTO = () => ({ tipo: "finanziamento", ente: "", numero: "", descrizione: "", data: oggi(), importo: "", tasso: "", aliquota_iva: 22, party_id: "", conto_debito: "13.01.003", conto_interessi: "40.02.002", conto_canone: "30.08.002", conto_iva: "05.02.002", rate: [] });

const Azioni = ({ p, r, a }) => {
  if (r.fattura_id) return <><Link to={`/passive/${r.fattura_id}`} className="mr-2 text-xs font-semibold text-blue-600 hover:underline" data-testid={`fin-fattura-${p.id}-${r.n}`}>Fattura</Link>
    {a.edit && <Button size="sm" variant="ghost" onClick={() => a.scollega(p, r)} title="Scollega fattura" data-testid={`fin-scollega-${p.id}-${r.n}`}><Unlink className="h-3.5 w-3.5" /></Button>}</>;
  if (!a.edit) return null;
  if (r.pagamento) return <Button size="sm" variant="ghost" onClick={() => a.annulla(p, r)} title="Annulla pagamento" data-testid={`fin-annulla-${p.id}-${r.n}`}><Undo2 className="h-3.5 w-3.5" /></Button>;
  return <>
    {p.tipo === "leasing" && <Button size="sm" variant="outline" className="mr-1" onClick={() => a.collega(p, r)} data-testid={`fin-collega-${p.id}-${r.n}`}><Link2 className="mr-1 h-3.5 w-3.5" />Fattura</Button>}
    <Button size="sm" variant="outline" onClick={() => a.paga(p, r)} data-testid={`fin-paga-${p.id}-${r.n}`}><Wallet className="mr-1 h-3.5 w-3.5" />Paga</Button>
  </>;
};

const RataRow = ({ p, r, a }) => (
  <tr className={r.stato === "scaduta" ? "bg-rose-50/50" : ""} data-testid={`fin-row-${p.id}-${r.n}`}>
    <td className="px-4 py-2 text-xs text-slate-500">{r.n}/{p.rate.length} {r.descrizione && <span className="text-slate-400">· {r.descrizione}</span>}</td>
    <td className="px-4 py-2 font-medium">{fmtDate(r.scadenza)}</td>
    <td className="px-4 py-2 text-right">{fmtEUR(r.capitale)}</td>
    <td className="px-4 py-2 text-right">{fmtEUR(r.interessi)}</td>
    {p.tipo === "leasing" && <td className="px-4 py-2 text-right">{fmtEUR(r.iva)}</td>}
    <td className="px-4 py-2 text-right font-semibold">{fmtEUR(r.totale)}</td>
    <td className="px-4 py-2"><span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${STATO[r.stato][1]}`} data-testid={`fin-stato-${p.id}-${r.n}`}>{STATO[r.stato][0]}</span>
      {r.pagamento && <span className="ml-2 text-xs text-slate-500">il {fmtDate(r.pagamento.data)}{r.pagamento.coge_rif ? ` · ${r.pagamento.coge_rif}` : ""}</span>}</td>
    <td className="whitespace-nowrap px-4 py-2 text-right"><Azioni p={p} r={r} a={a} /></td>
  </tr>
);

const Erogazione = ({ p, a }) => {
  if (p.tipo !== "finanziamento" || !p.importo) return null;
  if (p.erogazione) return <span className="text-xs text-emerald-700" data-testid={`fin-erogato-${p.id}`}>Erogato il {fmtDate(p.erogazione.data)}{p.erogazione.coge_rif ? ` · ${p.erogazione.coge_rif}` : ""}{a.edit && <button onClick={() => a.annullaErog(p)} className="ml-2 text-slate-400 hover:text-rose-600" title="Annulla erogazione" data-testid={`fin-erog-annulla-${p.id}`}><Undo2 className="inline h-3.5 w-3.5" /></button>}</span>;
  return a.edit ? <Button size="sm" variant="outline" onClick={() => a.eroga(p)} data-testid={`fin-eroga-${p.id}`}><Banknote className="mr-1 h-3.5 w-3.5" />Registra erogazione</Button> : null;
};

const Piano = ({ p, a }) => (
  <section className="mb-5 rounded-xl border border-slate-200 bg-white shadow-sm" data-testid={`fin-${p.id}`}>
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
      <div className="min-w-0">
        <span className={`mr-2 rounded px-2 py-0.5 text-[10px] font-bold uppercase ${p.tipo === "leasing" ? "bg-cyan-100 text-cyan-800" : "bg-indigo-100 text-indigo-800"}`}>{p.tipo}</span>
        <b className="text-slate-900">{p.ente}</b> {p.numero && <span className="mono text-sm text-slate-500">· {p.numero}</span>}
        <p className="mt-1 text-xs text-slate-500">{p.descrizione || "Senza descrizione"} · del {fmtDate(p.data)}{p.importo ? ` · ${p.tipo === "leasing" ? "valore bene" : "capitale"} ${fmtEUR(p.importo)}` : ""}{p.tasso ? ` · tasso ${p.tasso}%` : ""}</p>
        <div className="mt-2"><Erogazione p={p} a={a} /></div>
      </div>
      <div className="flex flex-wrap items-center gap-4 text-sm">
        <span>Totale <b>{fmtEUR(p.totale)}</b></span>
        <span className="text-emerald-700">Pagato <b>{fmtEUR(p.pagato)}</b></span>
        <span className="text-rose-700" data-testid={`fin-residuo-${p.id}`}>Residuo <b>{fmtEUR(p.residuo)}</b></span>
        <span className="text-xs text-slate-500" data-testid={`fin-debito-${p.id}`}>debito residuo {fmtEUR(p.debito_residuo)} · {p.rate_pagate}/{p.rate.length} rate</span>
        {p.pdf_id && <Button size="sm" variant="ghost" onClick={() => a.pdf(p)} title="Apri PDF" data-testid={`fin-pdf-${p.id}`}><FileText className="h-4 w-4" /></Button>}
        {a.edit && !p.erogazione && p.rate_pagate === 0 && !p.rate.some((r) => r.fattura_id) && <>
          <Button size="sm" variant="ghost" onClick={() => a.modifica(p)} title="Modifica" data-testid={`fin-edit-${p.id}`}><PenLine className="h-4 w-4" /></Button>
          <Button size="sm" variant="ghost" onClick={() => a.elimina(p)} title="Elimina" data-testid={`fin-del-${p.id}`}><Trash2 className="h-4 w-4 text-rose-600" /></Button>
        </>}
      </div>
    </div>
    {p.rate_scadute > 0 && <p className="bg-rose-50 px-5 py-2 text-xs font-semibold text-rose-700" data-testid={`fin-alert-${p.id}`}>{p.rate_scadute} {p.rate_scadute === 1 ? "rata scaduta" : "rate scadute"} non pagate.</p>}
    <div className="max-h-[420px] overflow-auto">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-white text-left text-xs uppercase tracking-wider text-slate-500"><tr><th className="px-4 py-2">Rata</th><th className="px-4 py-2">Scadenza</th><th className="px-4 py-2 text-right">Quota capitale</th><th className="px-4 py-2 text-right">Interessi</th>{p.tipo === "leasing" && <th className="px-4 py-2 text-right">IVA</th>}<th className="px-4 py-2 text-right">Totale</th><th className="px-4 py-2">Stato</th><th /></tr></thead>
        <tbody className="divide-y divide-slate-100">{p.rate.map((r) => <RataRow key={r.n} p={p} r={r} a={a} />)}</tbody>
      </table>
    </div>
  </section>
);

export default function Finanziamenti() {
  const { user } = useAuth();
  const [d, setD] = useState(null);
  const [dlg, setDlg] = useState(null);
  const [paga, setPaga] = useState(null);
  const [coll, setColl] = useState(null);
  const [reading, setReading] = useState(false);
  const fileRef = useRef(null);
  const load = useCallback(() => { api.get("/finanziamenti").then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e))); }, []);
  useEffect(() => { load(); }, [load]);
  const act = async (fn, msg) => { try { await fn(); toast.success(msg); load(); } catch (e) { toast.error(errMsg(e)); } };
  const a = {
    edit: canSend(user),
    modifica: setDlg,
    elimina: (p) => window.confirm("Eliminare il piano?") && act(() => api.delete(`/finanziamenti/${p.id}`), "Piano eliminato"),
    paga: (p, r) => setPaga({ url: `/finanziamenti/${p.id}/rate/${r.n}/paga`, titolo: `Paga rata ${r.n}/${p.rate.length}`, info: `${p.ente} ${p.numero || ""} · scadenza ${fmtDate(r.scadenza)} · ${fmtEUR(r.totale)}`,
      dettaglio: p.tipo === "leasing" ? `Canone ${fmtEUR(r.capitale + r.interessi)} + IVA ${fmtEUR(r.iva)}. Registrando dal modulo l'IVA non entra nel registro IVA: per detrarla collega la fattura.` : `Quota capitale ${fmtEUR(r.capitale)} · interessi ${fmtEUR(r.interessi)}` }),
    annulla: (p, r) => window.confirm(`Annullare il pagamento della rata ${r.n}?`) && act(() => api.delete(`/finanziamenti/${p.id}/rate/${r.n}/paga`), "Pagamento annullato"),
    eroga: (p) => setPaga({ url: `/finanziamenti/${p.id}/erogazione`, data: p.data, titolo: "Registra erogazione", info: `${p.ente} ${p.numero || ""} · importo erogato ${fmtEUR(p.importo)}`, dettaglio: "Banca in Dare, debito per finanziamento in Avere.", labelConto: "Accreditato su (banca)" }),
    annullaErog: (p) => window.confirm("Annullare l'erogazione registrata?") && act(() => api.delete(`/finanziamenti/${p.id}/erogazione`), "Erogazione annullata"),
    collega: (p, r) => setColl({ piano: p, rata: r }),
    scollega: (p, r) => act(() => api.delete(`/finanziamenti/${p.id}/rate/${r.n}/collega`), "Fattura scollegata"),
    pdf: (p) => api.get(`/finanziamenti/${p.id}/pdf`, { responseType: "blob" }).then(({ data }) => window.open(URL.createObjectURL(data), "_blank")).catch((e) => toast.error(errMsg(e))),
  };
  const upload = async (file) => {
    if (!file) return;
    setReading(true);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const { data } = await api.post("/finanziamenti/leggi-pdf", fd, { timeout: 180000 });
      if (!data.rate.length) toast.warning("Nessuna rata trovata nel PDF: calcolale o inseriscile a mano");
      setDlg({ ...VUOTO(), ...data, party_id: "" });
    } catch (e) { toast.error(errMsg(e)); } finally { setReading(false); if (fileRef.current) fileRef.current.value = ""; }
  };
  return (
    <div>
      <PageHeader eyebrow="Tesoreria" title="Finanziamenti e leasing">
        {a.edit && <>
          <input ref={fileRef} type="file" accept="application/pdf" className="hidden" onChange={(e) => upload(e.target.files?.[0])} data-testid="fin-pdf-input" />
          <Button variant="outline" onClick={() => setDlg(VUOTO())} data-testid="fin-new-btn">Nuovo piano</Button>
          <Button onClick={() => fileRef.current?.click()} disabled={reading} data-testid="fin-upload-btn">{reading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FileUp className="mr-2 h-4 w-4" />}{reading ? "Lettura del PDF…" : "Carica PDF del piano"}</Button>
        </>}
      </PageHeader>
      <p className="mb-5 max-w-3xl text-sm text-slate-600">Mutui, finanziamenti e leasing con il piano completo delle rate: calcolo automatico, lettura del PDF con l'IA o inserimento a mano. Le rate entrano nella <Link to="/situazione-finanziaria" className="text-blue-600 hover:underline">situazione finanziaria</Link> e, quando le paghi, in prima nota.</p>
      {!d ? <div className="text-sm text-slate-500">Caricamento…</div> : d.piani.length === 0
        ? <div className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-500" data-testid="fin-empty">Nessun finanziamento o leasing caricato.</div>
        : d.piani.map((p) => <Piano key={p.id} p={p} a={a} />)}
      <FinDialog piano={dlg} onClose={() => setDlg(null)} onSaved={load} />
      <PagaRataDialog req={paga} conti={d?.conti_pagamento} onClose={() => setPaga(null)} onDone={load} />
      <CollegaFatturaDialog req={coll} onClose={() => setColl(null)} onDone={load} />
    </div>
  );
}

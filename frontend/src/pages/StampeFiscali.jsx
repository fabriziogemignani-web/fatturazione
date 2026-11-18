import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Printer, FileCheck2, Lock } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NSelect } from "@/components/ui/nselect";
import { PERIODI, range, Totali } from "@/pages/RegistroIvaAcquisti";
import { RegistriIvaGestione } from "@/components/RegistriIvaGestione";

const blobErr = async (e) => {
  const b = e?.response?.data;
  if (b instanceof Blob) {
    try { const j = JSON.parse(await b.text()); return typeof j.detail === "string" ? j.detail : errMsg(e); } catch { return errMsg(e); }
  }
  return errMsg(e);
};

export const apriPdf = async (promise) => {
  try {
    const { data } = await promise;
    window.open(URL.createObjectURL(new Blob([data], { type: "application/pdf" })), "_blank");
    return true;
  } catch (e) { toast.error(await blobErr(e)); return false; }
};

const nextDay = (s) => { const d = new Date(`${s}T12:00:00Z`); d.setUTCDate(d.getUTCDate() + 1); return d.toISOString().slice(0, 10); };

const Definitiva = ({ tipo, registroId, anno, stampe, onDone }) => {
  const key = tipo === "giornale" ? "giornale" : `iva:${registroId}`;
  const last = stampe.filter((s) => s.key === key && s.anno === anno).sort((a, b) => (a.al < b.al ? 1 : -1))[0];
  const dal = last ? nextDay(last.al) : `${anno}-01-01`;
  const [al, setAl] = useState("");
  const go = async () => {
    if (!window.confirm(`Stampa definitiva dal ${fmtDate(dal)} al ${fmtDate(al)}: le pagine vengono numerate da ${anno}/${last ? last.pagina_a + 1 : 1} e i movimenti del periodo vengono bloccati. Continuare?`)) return;
    if (await apriPdf(api.post("/stampe-fiscali/stampa", { tipo, registro_id: registroId || null, anno, dal, al, definitiva: true }, { responseType: "blob" }))) { toast.success("Stampa definitiva salvata"); setAl(""); onDone(); }
  };
  if (dal.slice(0, 4) !== String(anno)) return <span className="text-xs text-emerald-700" data-testid="sf-def-completa">Anno {anno} stampato in definitiva fino al {fmtDate(last.al)}</span>;
  return (
    <div className="flex flex-wrap items-end gap-2" data-testid="sf-def-form">
      <span className="pb-2 text-xs text-slate-600">Definitiva dal <b>{fmtDate(dal)}</b> al</span>
      <Input type="date" min={dal} max={[`${anno}-12-31`, new Date().toISOString().slice(0, 10)].sort()[0]} value={al} onChange={(e) => setAl(e.target.value)} className="w-40 bg-white" data-testid="sf-def-al" />
      <Button onClick={go} disabled={!al || al < dal} data-testid="sf-def-btn"><FileCheck2 className="mr-2 h-4 w-4" />Stampa definitiva</Button>
    </div>
  );
};

const RegRows = ({ d, kind, onMove }) => (
  <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
    <table className="w-full text-sm" data-testid="sf-table">
      <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
        <tr><th className="px-3 py-2">{kind === "vendite" ? "Numero" : "Prot."}</th><th className="px-3 py-2">Data</th><th className="px-3 py-2">{kind === "vendite" ? "Cliente" : "Fornitore"}</th><th className="px-3 py-2 text-right">Imponibile</th><th className="px-3 py-2 text-right">Imposta</th><th className="px-3 py-2 text-right">Totale</th><th className="px-3 py-2">Registro</th></tr>
      </thead>
      <tbody className="divide-y divide-slate-100">
        {d.rows.length === 0 && <tr><td colSpan={7} className="px-3 py-8 text-center text-slate-500" data-testid="sf-empty">Nessun documento nel periodo</td></tr>}
        {d.rows.map((r) => {
          const dd = kind === "vendite" ? r.data : r.data_registrazione;
          const locked = d.bloccato_al && dd <= d.bloccato_al;
          return (
            <tr key={r.id} data-testid={`sf-row-${r.id}`}>
              <td className="mono px-3 py-2 text-xs font-semibold">{kind === "vendite" ? r.numero : r.protocollo}</td>
              <td className="px-3 py-2 text-xs">{fmtDate(dd)}</td>
              <td className="px-3 py-2 text-xs">{kind === "vendite" ? r.cliente : <>{r.fornitore} <span className="text-slate-500">· {r.tipo_documento === "TD04" ? "NC" : "FT"} {r.numero}</span></>}</td>
              <td className="px-3 py-2 text-right text-xs">{fmtEUR(r.riepilogo.reduce((s, x) => s + x.imponibile, 0))}</td>
              <td className="px-3 py-2 text-right text-xs">{fmtEUR(r.riepilogo.reduce((s, x) => s + x.imposta, 0))}</td>
              <td className="px-3 py-2 text-right text-xs font-semibold">{fmtEUR(r.totale)}</td>
              <td className="px-3 py-2 text-xs">{locked ? <span className="inline-flex items-center gap-1 text-slate-500"><Lock className="h-3 w-3" />stampato</span>
                : <NSelect className="h-7 w-44 text-xs" value={r.registro_iva_id} onChange={(e) => onMove(r, e.target.value)} data-testid={`sf-move-${r.id}`}>{d.registri.map((x) => <option key={x.id} value={x.id}>{x.codice} · {x.descrizione}</option>)}</NSelect>}
                {r.registro_proposto && !locked && <div className="text-[10px] text-amber-700">proposto</div>}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  </div>
);

const RegistroTab = ({ registri, stampe, reload }) => {
  const [rid, setRid] = useState(registri[0]?.id);
  const [anno, setAnno] = useState(new Date().getFullYear());
  const [per, setPer] = useState("anno");
  const [d, setD] = useState(null);
  const [dal, al] = range(anno, per);
  const load = () => rid && api.get("/stampe-fiscali/registro", { params: { registro_id: rid, anno, dal, al } }).then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, [rid, anno, per]); // eslint-disable-line react-hooks/exhaustive-deps
  const move = async (r, to) => {
    try { await api.put("/stampe-fiscali/documento", { kind: d.registro.tipo, id: r.id, registro_id: to }); toast.success("Documento spostato di registro"); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <label className="text-xs text-slate-600">Registro<NSelect className="block w-72" value={rid} onChange={(e) => setRid(e.target.value)} data-testid="sf-registro-select">
          <optgroup label="Vendite">{registri.filter((r) => r.tipo === "vendite").map((r) => <option key={r.id} value={r.id}>{r.codice} · {r.descrizione}</option>)}</optgroup>
          <optgroup label="Acquisti">{registri.filter((r) => r.tipo === "acquisti").map((r) => <option key={r.id} value={r.id}>{r.codice} · {r.descrizione}</option>)}</optgroup>
        </NSelect></label>
        <AnnoPeriodo anno={anno} setAnno={setAnno} per={per} setPer={setPer} />
        <Button variant="outline" onClick={() => apriPdf(api.post("/stampe-fiscali/stampa", { tipo: "iva", registro_id: rid, anno, dal, al }, { responseType: "blob" }))} data-testid="sf-prova-btn"><Printer className="mr-2 h-4 w-4" />Stampa di prova</Button>
      </div>
      <div className="mb-4 rounded-lg border border-slate-200 bg-slate-50 p-3"><Definitiva tipo="iva" registroId={rid} anno={anno} stampe={stampe} onDone={() => { reload(); load(); }} /></div>
      {d && <>{d.bloccato_al && <p className="mb-2 text-xs text-slate-600" data-testid="sf-bloccato">Movimenti bloccati fino al {fmtDate(d.bloccato_al)}</p>}<RegRows d={d} kind={d.registro.tipo} onMove={move} /><Totali d={d} /></>}
    </div>
  );
};

const AnnoPeriodo = ({ anno, setAnno, per, setPer }) => (
  <>
    <label className="text-xs text-slate-600">Anno<Input type="number" min={2000} max={2100} value={anno} onChange={(e) => setAnno(Number(e.target.value))} className="w-24 bg-white" data-testid="sf-anno" /></label>
    <label className="text-xs text-slate-600">Periodo<NSelect className="block w-44" value={per} onChange={(e) => setPer(e.target.value)} data-testid="sf-periodo">{PERIODI.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</NSelect></label>
  </>
);

const GiornaleTab = ({ stampe, reload }) => {
  const [anno, setAnno] = useState(new Date().getFullYear());
  const [per, setPer] = useState("anno");
  const [dal, al] = range(anno, per);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <AnnoPeriodo anno={anno} setAnno={setAnno} per={per} setPer={setPer} />
        <Button variant="outline" onClick={() => apriPdf(api.post("/stampe-fiscali/stampa", { tipo: "giornale", anno, dal, al }, { responseType: "blob" }))} data-testid="sf-giornale-prova-btn"><Printer className="mr-2 h-4 w-4" />Stampa di prova</Button>
      </div>
      <div className="rounded-lg border border-slate-200 bg-slate-50 p-3"><Definitiva tipo="giornale" anno={anno} stampe={stampe} onDone={reload} /></div>
      <p className="text-xs text-slate-500">Il libro giornale riporta tutte le registrazioni definitive in ordine di data e numero, con numerazione progressiva delle righe e riporto dei totali da una stampa definitiva alla successiva. Le registrazioni provvisorie (ratei in simulazione) non vengono stampate.</p>
    </div>
  );
};

export const StampeDefinitive = ({ stampe, admin, reload }) => {
  const act = async (fn, msg) => { try { await fn(); toast.success(msg); reload(); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table className="w-full text-sm" data-testid="sf-stampe">
        <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
          <tr><th className="px-3 py-2">Stampa</th><th className="px-3 py-2">Periodo</th><th className="px-3 py-2">Pagine</th><th className="px-3 py-2">Eseguita</th><th className="px-3 py-2">Movimenti</th><th className="px-3 py-2" /></tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {stampe.length === 0 && <tr><td colSpan={6} className="px-3 py-8 text-center text-slate-500">Nessuna stampa definitiva</td></tr>}
          {stampe.map((s) => (
            <tr key={s.id} data-testid={`sf-stampa-${s.id}`}>
              <td className="px-3 py-2 font-medium">{s.titolo}</td>
              <td className="px-3 py-2 text-xs">{fmtDate(s.dal)} – {fmtDate(s.al)}</td>
              <td className="mono px-3 py-2 text-xs">{s.anno}/{s.pagina_da} – {s.anno}/{s.pagina_a}</td>
              <td className="px-3 py-2 text-xs">{fmtDate(s.created_at.slice(0, 10))} · {s.created_by}</td>
              <td className="px-3 py-2 text-xs">{s.blocca ? <span className="text-slate-700"><Lock className="mr-1 inline h-3 w-3" />bloccati</span> : <span className="text-amber-700">riaperti</span>}</td>
              <td className="space-x-1 whitespace-nowrap px-3 py-2 text-right">
                <Button size="sm" variant="outline" onClick={() => apriPdf(api.get(`/stampe-fiscali/stampe/${s.id}/pdf`, { responseType: "blob" }))} data-testid={`sf-ristampa-${s.id}`}>Ristampa</Button>
                {admin && <Button size="sm" variant="outline" onClick={() => act(() => api.put(`/stampe-fiscali/stampe/${s.id}/blocco`, { blocca: !s.blocca }), s.blocca ? "Movimenti riaperti" : "Movimenti bloccati")} data-testid={`sf-blocco-${s.id}`}>{s.blocca ? "Riapri movimenti" : "Blocca di nuovo"}</Button>}
                {admin && <Button size="sm" variant="outline" className="text-rose-700" onClick={() => window.confirm(`Cancellare la stampa definitiva "${s.titolo}" dal ${fmtDate(s.dal)} al ${fmtDate(s.al)}? La numerazione delle pagine successive ripartirà da questa.`) && act(() => api.delete(`/stampe-fiscali/stampe/${s.id}`), "Stampa cancellata")} data-testid={`sf-cancella-${s.id}`}>Cancella</Button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

const TABS = [["iva", "Registri IVA"], ["giornale", "Libro giornale"], ["definitive", "Stampe definitive"], ["registri", "Gestione registri"]];

export default function StampeFiscali() {
  const [tab, setTab] = useState("iva");
  const [reg, setReg] = useState(null);
  const [stampe, setStampe] = useState([]);
  const loadReg = () => api.get("/stampe-fiscali/registri").then(({ data }) => setReg(data)).catch((e) => toast.error(errMsg(e)));
  const loadSt = () => api.get("/stampe-fiscali/stampe").then(({ data }) => setStampe(data)).catch(() => {});
  useEffect(() => { loadReg(); loadSt(); }, []);
  if (!reg) return <div className="text-sm text-slate-500">Caricamento…</div>;
  return (
    <div>
      <PageHeader eyebrow="Fisco e IVA" title="Stampe fiscali" />
      <div className="mb-5 flex flex-wrap gap-2">
        {TABS.map(([k, l]) => <button key={k} onClick={() => setTab(k)} className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${tab === k ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"}`} data-testid={`sf-tab-${k}`}>{l}</button>)}
      </div>
      {tab === "iva" && <RegistroTab key={reg.registri.length} registri={reg.registri} stampe={stampe} reload={loadSt} />}
      {tab === "giornale" && <GiornaleTab stampe={stampe} reload={loadSt} />}
      {tab === "definitive" && <StampeDefinitive stampe={stampe} reload={loadSt} />}
      {tab === "registri" && <RegistriIvaGestione data={reg} reload={loadReg} />}
    </div>
  );
}

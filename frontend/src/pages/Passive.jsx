import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Download, Upload, Loader2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { useAuth, canSend } from "@/context/AuthContext";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { PartyDialog } from "@/components/PartyDialog";

export const STATI_REG = { da_registrare: ["Da registrare", "bg-amber-100 text-amber-800"], registrata: ["Registrata", "bg-emerald-100 text-emerald-800"], contestata: ["Contestata", "bg-rose-100 text-rose-800"] };
const TABS = [["", "Tutte"], ["da_registrare", "Da registrare"], ["registrata", "Registrate"], ["contestata", "Contestate"]];

export const StatoReg = ({ s, testId }) => <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${STATI_REG[s][1]}`} data-testid={testId}>{STATI_REG[s][0]}</span>;

const UploadResults = ({ res, onClose }) => (
  <div className="mb-4 rounded-xl border border-slate-200 bg-white p-4 text-sm shadow-sm" data-testid="passive-upload-results">
    <div className="mb-2 flex justify-between"><b>Esito caricamento</b><button className="text-xs text-slate-500 hover:text-slate-800" onClick={onClose} data-testid="passive-upload-results-close">Chiudi</button></div>
    {res.map((r, i) => (
      <div key={i} className={`py-1 ${r.ok ? "text-emerald-700" : "text-rose-700"}`} data-testid={`passive-upload-result-${i}`}>
        {r.file}: {r.ok ? r.documenti.map((d) => `${d.fornitore} n. ${d.numero} (${fmtEUR(d.totale)})`).join(", ") : r.error}
      </div>
    ))}
  </div>
);

export default function Passive() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [stato, setStato] = useState("");
  const [busy, setBusy] = useState("");
  const [res, setRes] = useState(null);
  const file = useRef(null);
  const [sdi, setSdi] = useState(null);
  const [verifica, setVerifica] = useState([]);
  const [openV, setOpenV] = useState(false);
  const loadVerifica = (apri) => api.get("/parties", { params: { tipo: "fornitore" } }).then(({ data }) => {
    const v = data.filter((p) => p.da_verificare);
    setVerifica(v);
    if (apri && v.length) setOpenV(true);
  }).catch(() => {});
  useEffect(() => { loadVerifica(false); }, []);
  const verificato = () => {
    const rest = verifica.slice(1);
    setVerifica(rest);
    if (rest.length) setTimeout(() => setOpenV(true), 200);
  };
  useEffect(() => { api.get("/company/sdi").then(({ data }) => setSdi(data)).catch(() => {}); }, []);
  const load = () => api.get("/passive", { params: stato ? { stato } : {} }).then(({ data }) => setItems(data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, [stato]); // eslint-disable-line react-hooks/exhaustive-deps

  const sync = async () => {
    setBusy("sync");
    try {
      const { data } = await api.post("/passive/sdi-sync");
      toast.success(data.ricevute.length ? `${data.ricevute.length} nuove fatture ricevute dallo SDI` : "Nessuna nuova fattura");
      load();
      if (data.ricevute.some((d) => d.nuovo_fornitore_id)) loadVerifica(true);
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(""); }
  };
  const upload = async (e) => {
    const fs = [...e.target.files];
    e.target.value = "";
    if (!fs.length) return;
    setBusy("up");
    const fd = new FormData();
    fs.forEach((f) => fd.append("files", f));
    try {
      const { data } = await api.post("/passive/upload", fd);
      setRes(data);
      const ok = data.filter((r) => r.ok).length;
      if (ok) toast.success(`${ok} file importati`);
      if (ok < data.length) toast.error(`${data.length - ok} file non importati`);
      load();
      if (data.some((r) => r.ok && r.documenti.some((d) => d.nuovo_fornitore_id))) loadVerifica(true);
    } catch (err) { toast.error(errMsg(err)); } finally { setBusy(""); }
  };

  return (
    <div>
      <PageHeader eyebrow="Ciclo passivo" title="Fatture ricevute">
        {canSend(user) && <>
          <input ref={file} type="file" multiple accept=".xml,.p7m,application/xml,text/xml" className="hidden" onChange={upload} data-testid="passive-file-input" />
          <Button variant="outline" onClick={() => file.current?.click()} disabled={!!busy} data-testid="passive-upload-btn">{busy === "up" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Upload className="mr-2 h-4 w-4" />}Carica XML / P7M</Button>
          <Button onClick={sync} disabled={!!busy} data-testid="passive-sync-btn">{busy === "sync" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Download className="mr-2 h-4 w-4" />}Scarica da SDI</Button>
        </>}
      </PageHeader>
      {sdi && (sdi.provider === "simulato"
        ? <p className="-mt-4 mb-4 text-xs text-amber-700" data-testid="passive-sim-note">La ricezione dallo SDI è simulata (fatture DEMO) finché non colleghi l'intermediario in Dati azienda. I file reali si importano con "Carica XML / P7M".</p>
        : <p className="-mt-4 mb-4 text-xs text-slate-500" data-testid="passive-sdi-note">Fatture ricevute tramite {sdi.label} ({sdi.ambiente === "sandbox" ? "ambiente di prova" : "ambiente reale"}), scaricate secondo la pianificazione impostata in Dati azienda.</p>)}
      {res && <UploadResults res={res} onClose={() => setRes(null)} />}
      {verifica.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900" data-testid="passive-verifica-banner">
          <span><b>{verifica.length}</b> {verifica.length === 1 ? "fornitore creato" : "fornitori creati"} in automatico dalle fatture: controlla i dati presi dall'XML.</span>
          <Button size="sm" variant="outline" onClick={() => setOpenV(true)} data-testid="passive-verifica-btn">Verifica ora</Button>
        </div>
      )}
      <PartyDialog open={openV && verifica.length > 0} onOpenChange={setOpenV} tipo="fornitore" party={verifica[0]} onSaved={verificato} />
      <div className="mb-4 inline-flex rounded-lg border border-slate-200 bg-white p-1 text-xs font-semibold">
        {TABS.map(([k, l]) => <button key={k || "all"} onClick={() => setStato(k)} className={`rounded-md px-3 py-1.5 transition-colors ${stato === k ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-50"}`} data-testid={`passive-tab-${k || "tutte"}`}>{l}</button>)}
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm" data-testid="passive-table">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr><th className="px-4 py-3 font-medium">Data</th><th className="px-4 py-3 font-medium">Numero</th><th className="px-4 py-3 font-medium">Fornitore</th><th className="px-4 py-3 font-medium">Tipo</th><th className="px-4 py-3 text-right font-medium">Totale</th><th className="px-4 py-3 font-medium">Scadenza</th><th className="px-4 py-3 font-medium">Stato</th><th className="px-4 py-3 font-medium">Origine</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items.length === 0 && <tr><td colSpan={8} className="px-4 py-10 text-center text-slate-500" data-testid="passive-empty">Nessuna fattura ricevuta</td></tr>}
            {items.map((p) => (
              <tr key={p.id} className="cursor-pointer hover:bg-slate-50" onClick={() => navigate(`/passive/${p.id}`)} data-testid={`passive-row-${p.id}`}>
                <td className="px-4 py-3 text-slate-600">{fmtDate(p.data)}</td>
                <td className="mono px-4 py-3 font-medium text-slate-900">{p.numero}</td>
                <td className="px-4 py-3 text-slate-800">{p.fornitore.denominazione}</td>
                <td className="px-4 py-3 text-xs">{p.tipo_documento === "TD04" ? <span className="rounded bg-violet-100 px-1.5 py-0.5 font-semibold text-violet-800">NC</span> : p.tipo_documento}</td>
                <td className="px-4 py-3 text-right font-semibold">{p.tipo_documento === "TD04" ? "- " : ""}{fmtEUR(p.totale)}</td>
                <td className="px-4 py-3 text-slate-600">{p.tipo_documento === "TD04" ? "—" : fmtDate(p.scadenza)}</td>
                <td className="px-4 py-3"><StatoReg s={p.stato_reg} testId={`passive-stato-${p.id}`} /></td>
                <td className="px-4 py-3 text-xs text-slate-500">{p.origine === "upload" ? "File" : p.origine === "sdi" ? "SDI" : "SDI (demo)"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

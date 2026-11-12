import { useEffect, useState } from "react";
import { toast } from "sonner";
import { FileDown, CheckCircle2, Undo2, AlertTriangle } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { Button } from "@/components/ui/button";
import { useAuth, canSend } from "@/context/AuthContext";
import { F24Dialog } from "@/components/F24Dialog";

const STATO = {
  scaduta: ["Scaduta", "bg-rose-600 text-white"], in_scadenza: ["In scadenza", "bg-amber-500 text-white"],
  prossima: ["Prossima", "bg-slate-100 text-slate-600"], versato: ["Versato", "bg-emerald-50 text-emerald-700"],
};

const quando = (g) => (g < 0 ? `scaduta da ${-g} ${-g === 1 ? "giorno" : "giorni"}` : g === 0 ? "scade oggi" : `tra ${g} ${g === 1 ? "giorno" : "giorni"}`);

export const downloadF24Ritenute = async (key) => {
  try {
    const { data } = await api.get(`/scadenze-fiscali/${key}/f24`, { responseType: "blob" });
    const url = URL.createObjectURL(new Blob([data], { type: "application/pdf" }));
    const a = document.createElement("a");
    a.href = url; a.download = `F24_ritenute_${key}.pdf`; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  } catch (e) {
    const msg = e.response?.data instanceof Blob ? JSON.parse(await e.response.data.text()).detail : errMsg(e);
    toast.error(typeof msg === "string" ? msg : "Impossibile preparare l'F24");
  }
};

export const downloadF24Bolli = async (anno, q) => {
  try {
    const { data } = await api.get("/bolli/f24", { params: { anno, trimestre: q }, responseType: "blob" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(data); a.download = `F24_bolli_${anno}_T${q}.pdf`; a.click(); URL.revokeObjectURL(a.href);
  } catch (e) {
    const msg = e.response?.data instanceof Blob ? JSON.parse(await e.response.data.text()).detail : errMsg(e);
    toast.error(typeof msg === "string" ? msg : "Impossibile preparare l'F24");
  }
};

const TIPO = { iva: "IVA", ritenute: "Ritenute d'acconto", bolli: "Imposta di bollo" };
const f24Of = (x, onF24) => (x.tipo === "iva" ? onF24(x.f24) : x.tipo === "bolli" ? downloadF24Bolli(x.anno_riferimento, x.trimestre) : downloadF24Ritenute(x.key));

const Row = ({ x, canEdit, onF24, reload }) => {
  const [l, cls] = STATO[x.stato];
  const versa = async () => {
    try { await api.post("/scadenze-fiscali/versato", { key: x.key }); toast.success("Segnato come versato"); reload(); } catch (e) { toast.error(errMsg(e)); }
  };
  const annulla = async () => {
    try { await api.delete(`/scadenze-fiscali/versato/${x.key}`); toast.success("Versamento annullato"); reload(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <tr className={x.stato === "scaduta" ? "bg-rose-50/50" : x.stato === "in_scadenza" ? "bg-amber-50/50" : ""} data-testid={`fisc-row-${x.key}`}>
      <td className="whitespace-nowrap px-4 py-3"><div className="font-semibold">{fmtDate(x.scadenza)}</div><div className="text-xs text-slate-500">{x.versato ? `versato il ${fmtDate(x.versato.data)}` : quando(x.giorni)}</div>
        <div className="mt-1 font-bold sm:hidden">{fmtEUR(x.importo)}</div></td>
      <td className="px-4 py-3"><span className="mono mr-2 rounded bg-blue-50 px-1.5 py-0.5 text-xs font-bold text-blue-800">{x.codice}</span><span className="text-sm">{TIPO[x.tipo]}</span>
        <div className="text-xs text-slate-500">{x.periodo_label}{x.provvisorio && " · importo provvisorio, periodo in corso"}</div></td>
      <td className="hidden whitespace-nowrap px-4 py-3 text-right font-bold sm:table-cell" data-testid={`fisc-importo-${x.key}`}>{fmtEUR(x.importo)}</td>
      <td className="hidden px-4 py-3 sm:table-cell"><span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${cls}`} data-testid={`fisc-stato-${x.key}`}>{l}</span></td>
      <td className="whitespace-nowrap px-4 py-3 text-right">
        <Button size="sm" variant="outline" onClick={() => f24Of(x, onF24)} data-testid={`fisc-f24-${x.key}`}><FileDown className="mr-1 h-3.5 w-3.5" />{x.tipo === "bolli" ? "Prepara F24" : "F24"}</Button>
        {canEdit && (x.versato
          ? <Button size="sm" variant="ghost" className="ml-1" onClick={annulla} data-testid={`fisc-annulla-${x.key}`}><Undo2 className="h-3.5 w-3.5" /></Button>
          : !x.provvisorio && <Button size="sm" variant="ghost" className="ml-1 text-emerald-700" onClick={versa} data-testid={`fisc-versato-${x.key}`}><CheckCircle2 className="mr-1 h-3.5 w-3.5" />Versato</Button>)}
      </td>
    </tr>
  );
};

export const ScadenzeFiscaliPanel = () => {
  const { user } = useAuth();
  const [d, setD] = useState(null);
  const [f24, setF24] = useState(null);
  const load = () => api.get("/scadenze-fiscali").then(({ data }) => { setD(data); window.dispatchEvent(new Event("fisc-refresh")); }).catch(() => {});
  useEffect(() => { api.get("/scadenze-fiscali").then(({ data }) => setD(data)).catch(() => {}); }, []);
  if (!d) return null;
  return (
    <div className="mt-6 rounded-xl border border-slate-200 bg-white shadow-sm" data-testid="scadenze-fiscali-panel">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-5 py-4">
        <div><h3 className="font-semibold text-slate-900">Scadenzario fiscale F24</h3>
          <p className="text-xs text-slate-500">IVA {d.periodicita_iva}, ritenute d'acconto e bolli virtuali · avviso {d.giorni_avviso} giorni prima</p></div>
        {d.avvisi.length > 0 && <span className="flex items-center gap-1 rounded-full bg-rose-50 px-3 py-1 text-xs font-semibold text-rose-700" data-testid="fisc-avvisi-count"><AlertTriangle className="h-3.5 w-3.5" />{d.avvisi.length} da versare a breve</span>}
      </div>
      {d.scadenze.length === 0 ? <p className="px-5 py-8 text-center text-sm text-slate-500" data-testid="fisc-empty">Nessun F24 da versare nei prossimi mesi</p> : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm"><tbody className="divide-y divide-slate-100">
            {d.scadenze.map((x) => <Row key={x.key} x={x} canEdit={canSend(user)} onF24={setF24} reload={load} />)}
          </tbody></table>
        </div>
      )}
      <F24Dialog req={f24} onClose={() => setF24(null)} />
    </div>
  );
};

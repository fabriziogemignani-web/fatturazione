import { useEffect, useState } from "react";
import { toast } from "sonner";
import { RefreshCw, Settings2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useAuth, isAdmin, canSend } from "@/context/AuthContext";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ConsConfigDialog } from "@/components/ConsConfigDialog";
import { ConsCandidati, ConsArchivio } from "@/components/ConsArchivio";

export default function Conservazione() {
  const { user } = useAuth();
  const canEdit = canSend(user);
  const [anno, setAnno] = useState(new Date().getFullYear() - 1);
  const [tipo, setTipo] = useState("fattura_emessa");
  const [d, setD] = useState(null);
  const [cfg, setCfg] = useState(false);
  const [busy, setBusy] = useState(false);
  const load = (alive = () => true) => api.get("/conservazione", { params: { anno } }).then(({ data }) => { if (alive()) setD(data); }).catch((e) => toast.error(errMsg(e)));
  useEffect(() => {
    let on = true;
    load(() => on);
    return () => { on = false; };
  }, [anno]); // eslint-disable-line react-hooks/exhaustive-deps
  const aggiorna = async () => {
    setBusy(true);
    try { const { data } = await api.post("/conservazione/aggiorna", { ids: [] }); toast.success(`Stato aggiornato per ${data.aggiornati} documenti · ${data.conservati} conservati`); data.errori.forEach((x) => toast.error(`${x.titolo}: ${x.errore}`)); load(); }
    catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };
  if (!d) return <div className="text-sm text-slate-500">Caricamento…</div>;
  const docs = d.documenti.filter((x) => x.tipo === tipo);
  const info = d.tipi.find((x) => x.id === tipo);
  return (
    <div>
      <PageHeader eyebrow="Fisco e IVA" title="Conservazione documenti">
        <Select value={String(anno)} onValueChange={(v) => setAnno(Number(v))}>
          <SelectTrigger className="w-28 bg-white" data-testid="cons-anno-select"><SelectValue /></SelectTrigger>
          <SelectContent className="bg-white">{d.anni.map((a) => <SelectItem key={a} value={String(a)}>{a}</SelectItem>)}</SelectContent>
        </Select>
        {canEdit && d.collegato && <Button variant="outline" onClick={aggiorna} disabled={busy} data-testid="cons-aggiorna-btn"><RefreshCw className="mr-2 h-4 w-4" />Aggiorna stato</Button>}
        {isAdmin(user) && <Button variant="outline" onClick={() => setCfg(true)} data-testid="cons-config-btn"><Settings2 className="mr-2 h-4 w-4" />Collegamento</Button>}
      </PageHeader>
      <p className={`mb-4 rounded-lg border px-4 py-3 text-sm ${d.collegato ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-200 bg-amber-50 text-amber-800"}`} data-testid="cons-stato-collegamento">
        {d.collegato ? `Conservatore A-Cube collegato (${d.ambiente === "production" ? "ambiente reale" : "ambiente di prova"}). L'invio dei documenti avviene solo a mano.`
          : "Conservatore non collegato: i documenti archiviati restano nell'archivio interno, protetti e non cancellabili, ma senza valore di conservazione a norma."}
      </p>
      <div className="mb-4 flex flex-wrap gap-2">
        {d.tipi.map((x) => (
          <button key={x.id} onClick={() => setTipo(x.id)} data-testid={`cons-tab-${x.id}`}
            className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${tipo === x.id ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}>
            {x.label} ({d.documenti.filter((y) => y.tipo === x.id).length})
          </button>
        ))}
      </div>
      {!info.conservatore && <p className="mb-4 text-xs text-slate-500">Il conservatore A-Cube non gestisce questo tipo di documento: resta nell'archivio interno.</p>}
      <ConsCandidati tipo={tipo} anno={anno} canEdit={canEdit} onDone={load} />
      <ConsArchivio docs={docs} canEdit={canEdit} collegato={d.collegato} onChanged={load} />
      <ConsConfigDialog open={cfg} onClose={() => setCfg(false)} onSaved={load} />
    </div>
  );
}

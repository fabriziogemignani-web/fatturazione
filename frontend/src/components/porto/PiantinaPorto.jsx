import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Ship, FileSignature, LogOut } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtDate } from "@/lib/fe";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { STATO_POSTO, usePortoBase } from "@/lib/porto";
import { ArrivoDialog, PartenzaDialog } from "@/pages/porto/PortoTransiti";
import { ContrattoDialog } from "@/pages/porto/PortoContratti";

export const usePiantina = () => {
  const [st, setSt] = useState({ info: null, url: null });
  const load = async () => {
    try {
      const { data: info } = await api.get("/porto/piantina/info");
      if (!info.presente) { setSt({ info, url: null }); return; }
      const { data } = await api.get("/porto/piantina/immagine", { responseType: "blob" });
      setSt((o) => { if (o.url) URL.revokeObjectURL(o.url); return { info, url: URL.createObjectURL(data) }; });
    } catch { setSt({ info: { presente: false }, url: null }); }
  };
  useEffect(() => { load(); }, []);
  return [st, load];
};

export const Segnaposto = ({ p, stato, onClick, onPointerDown, sel }) => (
  <button type="button" onClick={onClick} onPointerDown={onPointerDown}
    className={`absolute h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow transition-transform hover:z-20 hover:scale-150 ${STATO_POSTO[stato]?.dot || "bg-slate-400"} ${sel ? "z-20 scale-150 ring-2 ring-amber-400" : ""}`}
    style={{ left: `${p.pos.x * 100}%`, top: `${p.pos.y * 100}%` }} title={p.codice} aria-label={`Posto ${p.codice}`} data-testid={`piantina-posto-${p.codice}`} />
);

const Scheda = ({ posto, onClose, onAzione }) => {
  const o = posto?.occupazione;
  return (
    <Dialog open={!!posto} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-sm" data-testid="piantina-scheda">
        <DialogHeader>
          <DialogTitle>Posto {posto?.codice}</DialogTitle>
          <DialogDescription>Lunghezza max {posto?.lunghezza_max} m · <span data-testid="piantina-scheda-stato">{STATO_POSTO[posto?.stato]?.label}</span></DialogDescription>
        </DialogHeader>
        {o && (
          <div className="rounded-lg bg-slate-50 p-3 text-sm" data-testid="piantina-scheda-occupazione">
            <div className="font-semibold">{o.barca} <span className="font-normal text-slate-500">({o.lunghezza} m)</span></div>
            <div>Armatore: {o.cliente}</div>
            <div>{o.tipo === "contratto" ? "Contratto" : "Transito"}: {fmtDate(o.da)} → {fmtDate(o.a)}</div>
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          {posto?.stato === "libero" && <Button size="sm" onClick={() => onAzione("arrivo")} data-testid="piantina-azione-arrivo"><Ship className="mr-1 h-3.5 w-3.5" />Registra arrivo</Button>}
          {posto?.stato === "libero" && <Button size="sm" variant="outline" onClick={() => onAzione("contratto")} data-testid="piantina-azione-contratto"><FileSignature className="mr-1 h-3.5 w-3.5" />Nuovo contratto</Button>}
          {o?.tipo === "transito" && o.stato === "presente" && <Button size="sm" onClick={() => onAzione("partenza")} data-testid="piantina-azione-partenza"><LogOut className="mr-1 h-3.5 w-3.5" />Registra partenza</Button>}
        </div>
      </DialogContent>
    </Dialog>
  );
};

export const PiantinaPorto = ({ mappa, onChanged }) => {
  const [{ url }] = usePiantina();
  const [base] = usePortoBase();
  const [sel, setSel] = useState(null);
  const [az, setAz] = useState(null);
  const [tr, setTr] = useState(null);
  const posti = mappa.pontili.flatMap((pt) => pt.posti);
  const piazzati = posti.filter((p) => p.pos);
  const azione = async (a) => {
    if (a === "partenza") {
      try { const { data } = await api.get("/porto/transiti", { params: { stato: "presente" } }); setTr(data.find((x) => x.id === sel.occupazione.id) || null); } catch (e) { toast.error(errMsg(e)); }
    } else setAz({ tipo: a, posto: sel });
    setSel(null);
  };
  if (!url) return <p className="mt-6 text-sm text-slate-500" data-testid="piantina-assente">Nessuna piantina caricata: aggiungila in Configurazione porto, sezione Piantina interattiva.</p>;
  return (
    <div className="mt-4" data-testid="piantina-view">
      {piazzati.length < posti.length && <p className="mb-2 text-xs text-amber-700" data-testid="piantina-non-piazzati">{posti.length - piazzati.length} posti non sono ancora posizionati sulla piantina.</p>}
      <div className="relative inline-block max-w-full select-none overflow-hidden rounded-xl border border-slate-200 bg-white">
        <img src={url} alt="Piantina del porto" className="block max-h-[78vh] max-w-full" draggable={false} data-testid="piantina-img" />
        {piazzati.map((p) => <Segnaposto key={p.id} p={p} stato={p.stato} onClick={() => setSel(p)} />)}
      </div>
      <Scheda posto={sel} onClose={() => setSel(null)} onAzione={azione} />
      <ArrivoDialog open={az?.tipo === "arrivo"} base={base} postoId={az?.posto.id} onClose={() => setAz(null)} onSaved={onChanged} />
      <ContrattoDialog open={az?.tipo === "contratto"} k={az?.tipo === "contratto" ? { posto_id: az.posto.id } : null} base={base} onClose={() => setAz(null)} onSaved={onChanged} />
      <PartenzaDialog tr={tr} onClose={() => setTr(null)} onSaved={onChanged} />
    </div>
  );
};

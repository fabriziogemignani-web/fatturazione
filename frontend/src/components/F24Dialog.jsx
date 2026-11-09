import { useEffect, useState } from "react";
import { toast } from "sonner";
import { FileDown, Plus, Trash2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";

const n = (v) => Math.round(Number(v || 0) * 100) / 100;

const CreditoRow = ({ c, i, sugg, set, del }) => (
  <div className="grid grid-cols-12 gap-2" data-testid={`f24-credito-${i}`}>
    <select value={c.codice} onChange={(e) => set({ codice: e.target.value, descrizione: sugg.find((s) => s[0] === e.target.value)?.[1] || "" })}
      className="col-span-12 h-9 rounded-md border border-slate-200 bg-white px-2 text-sm sm:col-span-6" data-testid={`f24-credito-codice-${i}`}>
      {sugg.map(([k, l]) => <option key={k} value={k}>{k} · {l}</option>)}
    </select>
    <Input className="col-span-4 sm:col-span-2" type="number" value={c.anno} onChange={(e) => set({ anno: e.target.value })} placeholder="Anno" data-testid={`f24-credito-anno-${i}`} />
    <Input className="col-span-6 text-right sm:col-span-3" type="number" step="0.01" min={0} value={c.importo} onChange={(e) => set({ importo: e.target.value })} placeholder="Importo" data-testid={`f24-credito-importo-${i}`} />
    <button onClick={del} className="col-span-2 rounded text-slate-400 hover:bg-rose-50 hover:text-rose-600 sm:col-span-1" aria-label="Elimina credito" data-testid={`f24-credito-del-${i}`}><Trash2 className="mx-auto h-4 w-4" /></button>
  </div>
);

export const F24Dialog = ({ req, onClose }) => {
  const [info, setInfo] = useState(null);
  const [crediti, setCrediti] = useState([]);
  const [data, setData] = useState("");
  const [banca, setBanca] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!req) return;
    setInfo(null); setCrediti([]); setBanca("");
    api.get("/liquidazione-iva/f24", { params: req }).then(({ data: d }) => { setInfo(d); setData(d.debito.scadenza); setBanca((d.banche.find((b) => b.predefinita) || d.banche[0])?.id || ""); })
      .catch((e) => { toast.error(errMsg(e)); onClose(); });
  }, [req]); // eslint-disable-line react-hooks/exhaustive-deps
  const deb = info?.debito;
  const totC = n(crediti.reduce((s, c) => s + n(c.importo), 0));
  const saldo = deb ? n(deb.importo - totC) : 0;
  const scarica = async () => {
    setBusy(true);
    try {
      const body = { ...req, data_versamento: data, banca_id: banca || null, crediti: crediti.map((c) => ({ ...c, anno: Number(c.anno), importo: n(c.importo) })) };
      const { data: blob } = await api.post("/liquidazione-iva/f24", body, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([blob], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url; a.download = `F24_IVA_${deb.codice}_${req.anno}.pdf`; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
      toast.success("Modello F24 scaricato");
    } catch (e) {
      const msg = e?.response?.data instanceof Blob ? JSON.parse(await e.response.data.text()).detail : errMsg(e);
      toast.error(typeof msg === "string" ? msg : "Controlla i dati inseriti");
    }
    setBusy(false);
  };

  return (
    <Dialog open={!!req} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-h-[92vh] overflow-y-auto bg-white sm:max-w-2xl" data-testid="f24-dialog">
        <DialogHeader>
          <DialogTitle>Modello F24 · versamento IVA {deb?.label}</DialogTitle>
          <DialogDescription>Codice tributo e importo sono presi dalla liquidazione. Puoi aggiungere crediti da compensare.</DialogDescription>
        </DialogHeader>
        {!deb ? <div className="text-sm text-slate-500">Caricamento…</div> : (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 rounded-lg border border-blue-200 bg-blue-50 p-4 sm:grid-cols-4">
              <div><div className="text-[10px] uppercase tracking-wider text-blue-700">Codice tributo</div><div className="mono text-lg font-bold" data-testid="f24-codice">{deb.codice}</div></div>
              <div><div className="text-[10px] uppercase tracking-wider text-blue-700">Anno rif.</div><div className="text-lg font-bold" data-testid="f24-anno-rif">{deb.anno_riferimento}</div></div>
              <div><div className="text-[10px] uppercase tracking-wider text-blue-700">A debito</div><div className="text-lg font-bold" data-testid="f24-importo">{fmtEUR(deb.importo)}</div></div>
              <div><div className="text-[10px] uppercase tracking-wider text-blue-700">Scadenza</div><div className="text-lg font-bold" data-testid="f24-scadenza">{fmtDate(deb.scadenza)}</div></div>
              <p className="col-span-2 text-xs text-blue-800 sm:col-span-4">{deb.descrizione}{deb.interessi > 0 ? ` · comprende ${fmtEUR(deb.interessi)} di interessi 1%` : ""}</p>
            </div>
            <div>
              <div className="mb-2 flex items-center justify-between"><span className="text-sm font-semibold text-slate-800">Crediti da compensare</span>
                <Button size="sm" variant="outline" disabled={crediti.length >= 5} onClick={() => setCrediti([...crediti, { codice: info.crediti_suggeriti[0][0], descrizione: info.crediti_suggeriti[0][1], anno: req.anno - 1, importo: "" }])} data-testid="f24-add-credito-btn"><Plus className="mr-1 h-4 w-4" />Aggiungi credito</Button>
              </div>
              <div className="space-y-2">
                {crediti.length === 0 && <p className="text-xs text-slate-500" data-testid="f24-no-crediti">Nessun credito: verrà versato l'intero importo.</p>}
                {crediti.map((c, i) => <CreditoRow key={i} c={c} i={i} sugg={info.crediti_suggeriti} set={(p) => setCrediti(crediti.map((x, k) => (k === i ? { ...x, ...p } : x)))} del={() => setCrediti(crediti.filter((_, k) => k !== i))} />)}
              </div>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <label className="text-xs text-slate-600">Data di versamento<Input type="date" value={data} onChange={(e) => setData(e.target.value)} data-testid="f24-data-input" /></label>
              <label className="text-xs text-slate-600">Conto di addebito
                <select value={banca} onChange={(e) => setBanca(e.target.value)} className="block h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm" data-testid="f24-banca-select">
                  <option value="">Nessuno</option>{info.banche.map((b) => <option key={b.id} value={b.id}>{b.nome} · {b.iban}</option>)}
                </select>
              </label>
            </div>
            <div className={`flex items-center justify-between rounded-lg px-4 py-3 ${saldo < 0 ? "bg-rose-50 text-rose-700" : "bg-slate-900 text-white"}`} data-testid="f24-saldo">
              <span className="text-sm">Saldo finale (A − B)</span><span className="text-xl font-extrabold">{fmtEUR(saldo)}</span>
            </div>
            {saldo < 0 && <p className="text-xs text-rose-700">I crediti non possono superare l'IVA da versare.</p>}
            {crediti.length > 0 && <p className="text-xs text-amber-700" data-testid="f24-telematico-note">Con crediti compensati l'F24 va presentato solo in via telematica (servizi dell'Agenzia delle Entrate, home banking o intermediario).</p>}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose} data-testid="f24-cancel-btn">Chiudi</Button>
          <Button onClick={scarica} disabled={busy || !deb || saldo < 0 || crediti.some((c) => !n(c.importo))} data-testid="f24-download-btn"><FileDown className="mr-2 h-4 w-4" />{busy ? "Preparazione…" : "Scarica PDF"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

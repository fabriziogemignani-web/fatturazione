import { useRef, useState } from "react";
import { toast } from "sonner";
import { Download, Upload, CheckCircle2, AlertTriangle } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";

const LABEL = { Clienti: "Clienti", Fornitori: "Fornitori", Articoli: "Articoli", Listini: "Listini clienti", Giacenze: "Giacenze iniziali", SaldiContabili: "Saldi contabili di apertura", PartiteAperte: "Partite aperte" };

export default function Importazione() {
  const fileRef = useRef(null);
  const [prev, setPrev] = useState(null);
  const [esito, setEsito] = useState(null);
  const [busy, setBusy] = useState(false);
  const modello = async () => {
    try {
      const { data } = await api.get("/importazione/modello", { responseType: "blob" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(data);
      a.download = "modello_importazione.xlsx";
      a.click();
    } catch (e) { toast.error(errMsg(e)); }
  };
  const carica = async (f) => {
    if (!f) return;
    setBusy(true); setEsito(null);
    const fd = new FormData();
    fd.append("file", f);
    try { const { data } = await api.post("/importazione/anteprima", fd); setPrev(data); } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
    fileRef.current.value = "";
  };
  const conferma = async () => {
    if (!window.confirm("Scrivere nel database le righe valide dell'anteprima?")) return;
    setBusy(true);
    try { const { data } = await api.post(`/importazione/${prev.id}/conferma`); setEsito(data.esito); setPrev(null); toast.success("Importazione completata"); } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };
  const righe = prev ? Object.values(prev.riepilogo).reduce((s, x) => s + x.righe, 0) : 0;
  return (
    <div>
      <PageHeader eyebrow="Impostazioni" title="Importazione di massa">
        <Button variant="outline" onClick={modello} data-testid="imp-modello-btn"><Download className="mr-2 h-4 w-4" />Scarica modello Excel</Button>
        <Button onClick={() => fileRef.current.click()} disabled={busy} data-testid="imp-carica-btn"><Upload className="mr-2 h-4 w-4" />{busy ? "Elaborazione…" : "Carica file compilato"}</Button>
        <input ref={fileRef} type="file" accept=".xlsx" className="hidden" onChange={(e) => carica(e.target.files[0])} data-testid="imp-file-input" />
      </PageHeader>
      <p className="mb-6 max-w-3xl text-sm text-slate-600">Il modello contiene già i clienti, i fornitori, gli articoli e i listini presenti per questa azienda. Compila o correggi i fogli (clienti, fornitori, articoli, listini, giacenze, saldi contabili di apertura, partite aperte) e ricaricalo: vedrai un'anteprima con gli errori prima di salvare. I record già presenti vengono aggiornati.</p>
      {esito && (
        <div className="mb-6 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900" data-testid="imp-esito">
          <div className="mb-1 flex items-center gap-2 font-semibold"><CheckCircle2 className="h-4 w-4" />Importazione completata</div>
          {Object.entries(esito).map(([k, v]) => <div key={k}>{LABEL[k]}: {v} righe</div>)}
        </div>
      )}
      {prev && (
        <div className="rounded-xl border border-slate-200 bg-white" data-testid="imp-anteprima">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-3">
            <span className="font-semibold text-slate-800">Anteprima · {righe} righe valide</span>
            <Button onClick={conferma} disabled={busy || !righe || prev.bloccanti.length > 0} data-testid="imp-conferma-btn">Conferma importazione</Button>
          </div>
          {Object.keys(prev.riepilogo).length === 0 && <p className="px-5 py-8 text-center text-sm text-slate-500">Il file non contiene righe da importare</p>}
          <div className="divide-y divide-slate-100">
            {Object.entries(prev.riepilogo).map(([k, x]) => (
              <div key={k} className="px-5 py-3" data-testid={`imp-foglio-${k}`}>
                <div className="flex flex-wrap justify-between gap-2 text-sm">
                  <span className="font-semibold text-slate-900">{LABEL[k]}</span>
                  <span className="text-slate-600">{x.righe} valide{["Clienti", "Fornitori", "Articoli"].includes(k) && ` (${x.nuovi} nuovi, ${x.aggiornati} da aggiornare)`} · <span className={x.errori.length ? "font-semibold text-rose-600" : ""}>{x.errori.length} errori</span></span>
                </div>
                {x.errori.length > 0 && (
                  <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto text-xs text-rose-700">
                    {x.errori.map((e, i) => <li key={i} className="flex gap-2"><AlertTriangle className="h-3.5 w-3.5 shrink-0" />{e.riga === "-" ? "" : `Riga ${e.riga}: `}{e.errore}</li>)}
                  </ul>
                )}
              </div>
            ))}
          </div>
          {prev.bloccanti.length > 0 && <p className="border-t border-slate-200 px-5 py-3 text-sm text-rose-700" data-testid="imp-bloccanti">Correggi i saldi contabili e ricarica il file: la registrazione di apertura deve quadrare.</p>}
        </div>
      )}
    </div>
  );
}

import { useState } from "react";
import { toast } from "sonner";
import { AlertTriangle } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useCompany } from "@/context/CompanyContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

const scaricaBackup = async () => {
  const res = await api.get("/azienda/backup", { responseType: "blob" });
  const name = (res.headers["content-disposition"] || "").match(/filename="([^"]+)"/)?.[1] || "backup_azienda.json.gz";
  const url = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
};

export const CancellazioneAziendaCard = () => {
  const { company, reload } = useCompany();
  const [modo, setModo] = useState("parziale");
  const [anag, setAnag] = useState(false);
  const [nome, setNome] = useState("");
  const [busy, setBusy] = useState(false);
  const ok = nome.trim().toLowerCase() === (company?.denominazione || "").trim().toLowerCase();
  const run = async () => {
    setBusy(true);
    try {
      await scaricaBackup();
      toast.success("Backup scaricato");
      const { data } = await api.post("/azienda/cancella", { modo, anagrafiche: anag, conferma: nome });
      const n = Object.values(data.cancellati).reduce((a, b) => a + b, 0);
      toast.success(modo === "totale" ? `Azienda eliminata (${n} record)` : `Movimenti cancellati (${n} record)`);
      setNome("");
      if (modo === "totale") window.location.href = "/"; else reload?.();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <div className="mt-6 max-w-3xl rounded-xl border border-rose-200 bg-white p-6 shadow-sm" data-testid="cancella-azienda-card">
      <h3 className="flex items-center gap-2 text-lg font-semibold text-rose-700"><AlertTriangle className="h-5 w-5" />Cancellazione dati azienda</h3>
      <p className="mb-4 text-xs text-slate-500">Operazione irreversibile, riservata agli amministratori. Prima di cancellare il programma scarica in automatico un backup completo dei dati dell'azienda.</p>
      <div className="grid gap-3 sm:grid-cols-2">
        {[["parziale", "Parziale", "Cancella i movimenti: contabilità, magazzino, produzione, acquisti e vendite (fatture, DDT, ordini, entrate merce, incassi, pagamenti, Ri.Ba., F24, banca). Restano articoli, distinte base, piano dei conti, parametri, banche e utenti; giacenze azzerate e numerazione da 1."],
          ["totale", "Totale", "Elimina l'azienda e tutti i suoi dati, comprese anagrafiche, articoli, piano dei conti e documenti in conservazione."]].map(([k, t, d]) => (
          <button key={k} type="button" onClick={() => setModo(k)} className={`rounded-lg border p-3 text-left text-xs transition-colors ${modo === k ? "border-rose-400 bg-rose-50" : "border-slate-200 hover:bg-slate-50"}`} data-testid={`cancella-modo-${k}`}>
            <div className="mb-1 text-sm font-semibold text-slate-800">{t}</div><span className="text-slate-600">{d}</span>
          </button>
        ))}
      </div>
      {modo === "parziale" && <label className="mt-3 flex items-center justify-between gap-3 text-sm text-slate-700">Cancella anche clienti e fornitori (con dichiarazioni d'intento)<Switch checked={anag} onCheckedChange={setAnag} data-testid="cancella-anagrafiche-switch" /></label>}
      <label className="mt-4 block text-xs text-slate-600">Per confermare scrivi la ragione sociale: <b>{company?.denominazione}</b>
        <Input value={nome} onChange={(e) => setNome(e.target.value)} className="mt-1" data-testid="cancella-conferma-input" /></label>
      <Button className="mt-4 bg-rose-600 hover:bg-rose-700" disabled={!ok || busy} onClick={run} data-testid="cancella-esegui-btn">
        {busy ? "Attendi…" : modo === "totale" ? "Scarica backup ed elimina l'azienda" : "Scarica backup e cancella i movimenti"}
      </Button>
    </div>
  );
};

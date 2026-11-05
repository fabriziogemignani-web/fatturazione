import { useEffect, useState } from "react";
import { toast } from "sonner";
import { RefreshCw, AlertTriangle } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";

const STEPS = "Verrà fatto prima un backup del database, poi il programma scaricherà la nuova versione e si riavvierà.";

const Running = ({ state }) => (
  <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/80 backdrop-blur-sm" data-testid="update-running-overlay">
    <div className="mx-4 max-w-md rounded-xl bg-white p-6 text-center shadow-2xl">
      <RefreshCw className="mx-auto mb-3 h-8 w-8 animate-spin text-red-600" />
      <h2 className="text-lg font-semibold text-slate-900">Aggiornamento in corso</h2>
      <p className="mt-2 text-sm text-slate-600">Il servizio è momentaneamente sospeso. La pagina si ricaricherà da sola al termine (di solito 3–10 minuti).</p>
      {state && <p className="mt-3 text-xs text-slate-500" data-testid="update-running-state">{state}</p>}
    </div>
  </div>
);

export const UpdateBanner = () => {
  const [st, setSt] = useState(null);
  const [ask, setAsk] = useState(false);
  const [run, setRun] = useState(null);
  const load = () => api.get("/system/update-status").then(({ data }) => setSt(data)).catch(() => {});
  useEffect(() => { load(); const t = setInterval(load, 6 * 3600 * 1000); return () => clearInterval(t); }, []);

  useEffect(() => {
    if (!run) { return undefined; }
    const t = setInterval(async () => {
      try {
        const { data } = await api.get("/system/update-status");
        setRun((r) => ({ ...r, state: data.state }));
        if (data.state.startsWith("errore")) { clearInterval(t); setRun(null); setSt(data); toast.error(`Aggiornamento non riuscito: ${data.state.replace(/^errore:\s*/, "")}`); }
        else if (data.local && data.local !== run.from && !data.state.startsWith("in corso")) { clearInterval(t); window.location.reload(); }
      } catch { /* server in riavvio */ }
    }, 5000);
    return () => clearInterval(t);
  }, [run?.from]); // eslint-disable-line react-hooks/exhaustive-deps

  const start = async () => {
    try { const { data } = await api.post("/system/update"); setAsk(false); setRun({ from: data.from, state: "in corso: backup del database" }); }
    catch (e) { toast.error(errMsg(e)); }
  };

  if (run) return <Running state={run.state} />;
  if (!st?.available) return null;
  return (
    <>
      <button onClick={() => setAsk(true)} data-testid="update-available-btn"
        className="fixed bottom-5 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-full bg-red-600 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-red-600/30 transition-transform hover:scale-105 hover:bg-red-700 print:hidden lg:left-[calc(50%+8rem)]">
        <RefreshCw className="h-4 w-4" />Aggiornamento disponibile
      </button>
      <Dialog open={ask} onOpenChange={setAsk}>
        <DialogContent className="bg-white sm:max-w-md" data-testid="update-confirm-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><AlertTriangle className="h-5 w-5 text-red-600" />Aggiornare il programma?</DialogTitle>
            <DialogDescription>Durante l'aggiornamento il servizio sarà interrotto per tutti gli utenti per alcuni minuti: salvate il lavoro in corso. {STEPS}</DialogDescription>
          </DialogHeader>
          {st.remote?.message && <p className="rounded-md bg-slate-50 p-3 text-xs text-slate-600" data-testid="update-version-info">Nuova versione: {st.remote.message}</p>}
          <DialogFooter>
            <Button variant="outline" onClick={() => setAsk(false)} data-testid="update-cancel-btn">Annulla</Button>
            <Button className="bg-red-600 hover:bg-red-700" onClick={start} data-testid="update-confirm-btn">Backup e aggiorna</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

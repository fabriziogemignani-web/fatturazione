import { useState } from "react";
import { Search, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export const PaSearch = ({ onPick }) => {
  const [q, setQ] = useState("");
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);

  const search = async (e) => {
    e?.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.get("/ipa/search", { params: { q } });
      setRes(data);
    } catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); }
  };

  return (
    <div className="space-y-2" data-testid="ipa-search">
      <div className="flex gap-2">
        <Input className="bg-white" placeholder="Cerca nell'Indice PA: ente, codice fiscale o codice ufficio" value={q}
          onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && search(e)} data-testid="ipa-search-input" />
        <Button type="button" variant="outline" onClick={search} disabled={busy || q.trim().length < 3} data-testid="ipa-search-btn">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
        </Button>
      </div>
      {res && (
        <div className="max-h-56 overflow-y-auto rounded-lg border border-sky-200 bg-white" data-testid="ipa-results">
          {res.length === 0 && <p className="p-3 text-xs text-slate-500" data-testid="ipa-no-results">Nessun ufficio trovato</p>}
          {res.map((r) => (
            <button type="button" key={r.codice_uo} onClick={() => { onPick(r); setRes(null); }} data-testid={`ipa-result-${r.codice_uo}`}
              className="block w-full border-b border-slate-100 px-3 py-2 text-left transition-colors last:border-0 hover:bg-sky-50">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-semibold text-slate-800">{r.ente}</span>
                <span className="mono rounded bg-sky-100 px-1.5 py-0.5 text-xs font-bold text-sky-800">{r.codice_uo}</span>
              </div>
              <div className="text-xs text-slate-500">{r.descrizione_uo} · CF {r.codice_fiscale} · {r.indirizzo} {r.cap}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

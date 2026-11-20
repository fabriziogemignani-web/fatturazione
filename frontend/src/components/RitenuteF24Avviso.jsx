import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { AlertTriangle, FileDown } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { Button } from "@/components/ui/button";

const scarica = async (mese) => {
  try {
    const { data } = await api.get(`/ritenute/${mese}/f24`, { responseType: "blob" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(data); a.download = `F24_ritenute_${mese}.pdf`; a.click(); URL.revokeObjectURL(a.href);
  } catch (e) { toast.error(errMsg(e)); }
};

export const RitenuteF24Avviso = () => {
  const [mesi, setMesi] = useState([]);
  useEffect(() => { api.get("/ritenute/da-versare").then(({ data }) => setMesi(data.mesi.filter((m) => !m.provvisorio && m.giorni <= 6))).catch(() => {}); }, []);
  if (!mesi.length) return null;
  return (
    <div className="mb-6 space-y-2" data-testid="rit-f24-avviso">
      {mesi.map((m) => {
        const scaduta = m.giorni < 0;
        return (
          <div key={m.key} className={`flex flex-wrap items-center gap-3 rounded-xl border px-4 py-3 text-sm ${scaduta ? "border-rose-200 bg-rose-50 text-rose-900" : "border-amber-200 bg-amber-50 text-amber-900"}`} data-testid={`rit-f24-avviso-${m.mese}`}>
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span className="flex-1">
              <b>Ritenute d'acconto di {m.label}: {fmtEUR(m.importo)}</b> da versare con F24 (codice tributo 1040) {scaduta ? `· scaduto il ${fmtDate(m.scadenza)}, valuta il ravvedimento` : `entro il ${fmtDate(m.scadenza)}${m.giorni === 0 ? " (oggi)" : ` · mancano ${m.giorni} giorni`}`}
            </span>
            <Button size="sm" variant="outline" className="bg-white" onClick={() => scarica(m.mese)} data-testid={`rit-f24-scarica-${m.mese}`}><FileDown className="mr-1.5 h-4 w-4" />F24 pronto</Button>
            <Link to={`/ritenute?mese=${m.mese}`} className="text-xs font-semibold underline" data-testid={`rit-f24-apri-${m.mese}`}>Dettaglio e segna versato</Link>
          </div>
        );
      })}
    </div>
  );
};

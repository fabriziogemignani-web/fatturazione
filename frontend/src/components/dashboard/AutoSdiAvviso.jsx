import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Zap } from "lucide-react";
import { api } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";

export const AutoSdiAvviso = () => {
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/contabilita/registrazioni-da-verificare").then(({ data }) => setD(data)).catch(() => setD(null)); }, []);
  if (!d?.n) return null;
  return (
    <section className="rounded-2xl border border-yellow-300 bg-yellow-50 p-4 fade-up" data-testid="auto-sdi-avviso">
      <div className="flex flex-wrap items-center gap-3">
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-yellow-400 text-yellow-950"><Zap className="h-4 w-4" /></span>
        <div className="min-w-[200px] flex-1">
          <p className="font-semibold text-yellow-950" data-testid="auto-sdi-count">{d.n === 1 ? "1 fattura registrata in automatico dallo SDI da verificare" : `${d.n} fatture registrate in automatico dallo SDI da verificare`}</p>
          <p className="text-xs text-yellow-900">Totale {fmtEUR(d.totale)} · registrate con il modello del fornitore: controlla i conti in prima nota.</p>
        </div>
        <Link to="/contabilita/prima-nota?verifica=1" className="rounded-md bg-yellow-400 px-3 py-1.5 text-xs font-semibold text-yellow-950 transition-colors hover:bg-yellow-500" data-testid="auto-sdi-vai">Verifica in prima nota</Link>
      </div>
      <ul className="mt-2 space-y-0.5 pl-0 text-xs text-yellow-900 sm:pl-11">
        {d.ultime.map((e) => <li key={e.id} className="truncate" data-testid={`auto-sdi-riga-${e.id}`}>{fmtDate(e.data)} · n. {e.numero} · {e.descrizione} · {fmtEUR(e.totale)}</li>)}
        {d.n > d.ultime.length && <li className="italic">…e altre {d.n - d.ultime.length}</li>}
      </ul>
    </section>
  );
};

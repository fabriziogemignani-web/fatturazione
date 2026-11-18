import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";

export default function PagamentoEsito({ annullato }) {
  const [sp] = useSearchParams();
  const sid = sp.get("session_id");
  const [st, setSt] = useState(annullato ? "annullato" : "attesa");
  useEffect(() => {
    if (annullato || !sid) { return; }
    let n = 0, stop = false;
    const poll = async () => {
      try {
        const { data } = await api.get(`/payments/status/${sid}`);
        if (data.payment_status === "paid") { setSt("pagato"); return; }
        if (["expired", "failed"].includes(data.payment_status)) { setSt("errore"); return; }
      } catch { setSt("errore"); return; }
      n += 1;
      if (n >= 15) { setSt("timeout"); return; }
      if (!stop) setTimeout(poll, 2000);
    };
    poll();
    return () => { stop = true; };
  }, [sid, annullato]);
  const txt = {
    attesa: "Sto verificando il pagamento...", pagato: "Pagamento riuscito: i crediti IA sono stati caricati.",
    annullato: "Pagamento annullato: nessun addebito.", errore: "Il pagamento non è andato a buon fine.", timeout: "La conferma sta tardando: ricontrolla tra qualche minuto dalla dashboard.",
  }[st];
  const Icon = st === "attesa" ? Loader2 : st === "pagato" ? CheckCircle2 : XCircle;
  return (
    <div className="mx-auto mt-16 max-w-md rounded-xl border bg-white p-8 text-center shadow-sm" data-testid="pagamento-esito">
      <Icon className={`mx-auto h-10 w-10 ${st === "pagato" ? "text-emerald-600" : st === "attesa" ? "animate-spin text-violet-600" : "text-rose-600"}`} />
      <p className="mt-4 text-base text-slate-800" data-testid={`pagamento-stato-${st}`}>{txt}</p>
      <Button asChild className="mt-6" data-testid="pagamento-torna-dashboard"><Link to="/">Torna alla dashboard</Link></Button>
    </div>
  );
}

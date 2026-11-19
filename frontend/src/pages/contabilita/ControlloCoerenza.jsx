import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ShieldCheck, AlertOctagon, AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";

const Problema = ({ p, i }) => {
  const err = p.gravita === "errore";
  const Icon = err ? AlertOctagon : AlertTriangle;
  return (
    <li className={`flex items-start gap-3 px-4 py-3 ${err ? "bg-rose-50/50" : ""}`} data-testid={`coerenza-problema-${i}`}>
      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${err ? "text-rose-600" : "text-amber-600"}`} />
      <span className="flex-1 text-sm text-slate-800">{p.messaggio}</span>
      {p.link && <Link to={p.link} className="shrink-0 text-xs font-semibold text-blue-600 hover:text-blue-800">Apri</Link>}
    </li>
  );
};

export default function ControlloCoerenza() {
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try { setRes((await api.get("/controlli/coerenza")).data); } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };
  const aree = res ? [...new Set(res.problemi.map((p) => p.area))] : [];

  return (
    <div>
      <PageHeader eyebrow="Contabilità generale" title="Controllo di coerenza">
        <Button onClick={run} disabled={busy} data-testid="coerenza-run-btn">{busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ShieldCheck className="mr-2 h-4 w-4" />}Esegui controllo</Button>
      </PageHeader>
      <p className="mb-6 max-w-3xl text-sm text-slate-600">Ricalcola i conti partendo dalle singole registrazioni, incassi e pagamenti e segnala dove i dati non tornano. Non modifica nulla: ti mostra solo cosa controllare.</p>
      {res && (
        <>
          <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="rounded-xl border border-slate-200 bg-white p-4"><div className="text-xs uppercase tracking-wider text-slate-500">Errori</div><div className={`mono mt-1 text-2xl font-bold ${res.errori ? "text-rose-700" : "text-emerald-700"}`} data-testid="coerenza-errori">{res.errori}</div></div>
            <div className="rounded-xl border border-slate-200 bg-white p-4"><div className="text-xs uppercase tracking-wider text-slate-500">Avvisi</div><div className={`mono mt-1 text-2xl font-bold ${res.avvisi ? "text-amber-700" : "text-emerald-700"}`} data-testid="coerenza-avvisi">{res.avvisi}</div></div>
            <div className="rounded-xl border border-slate-200 bg-white p-4 text-xs text-slate-600"><div className="mb-1 uppercase tracking-wider text-slate-500">Controlli eseguiti</div>{res.controlli.length} verifiche{!res.contabilita && " (contabilità generale non attiva: solo fatture e scadenze)"}</div>
          </div>
          {!res.problemi.length && <div className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm font-semibold text-emerald-800" data-testid="coerenza-ok"><CheckCircle2 className="h-5 w-5" />Tutto coerente: nessuna differenza trovata.</div>}
          {aree.map((a) => (
            <div key={a} className="mb-4 overflow-hidden rounded-xl border border-slate-200 bg-white" data-testid={`coerenza-area-${a}`}>
              <div className="border-b border-slate-200 bg-slate-50 px-4 py-2 text-sm font-bold text-slate-800">{a}</div>
              <ul className="divide-y divide-slate-100">{res.problemi.map((p, i) => p.area === a && <Problema key={i} p={p} i={i} />)}</ul>
            </div>
          ))}
          <details className="mt-4 text-xs text-slate-500"><summary className="cursor-pointer">Cosa viene controllato</summary><ul className="mt-2 list-disc pl-5">{res.controlli.map((c) => <li key={c}>{c}</li>)}</ul></details>
        </>
      )}
    </div>
  );
}

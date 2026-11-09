import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Lock, LockOpen, Eye } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { useAuth, canSend } from "@/context/AuthContext";

const Scrittura = ({ s, i }) => (
  <div className="overflow-hidden rounded-xl border border-slate-200 bg-white" data-testid={`chiusura-scrittura-${i}`}>
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 bg-slate-50 px-4 py-2.5">
      <div className="text-sm font-semibold text-slate-800">{s.numero ? `N. ${s.numero}/${s.anno} · ` : ""}{s.causale} · {s.descrizione}</div>
      <div className="text-xs text-slate-500">{fmtDate(s.data)} · {fmtEUR(s.totale)}</div>
    </div>
    <table className="w-full text-xs">
      <tbody className="divide-y divide-slate-50">
        {s.righe.map((r, k) => (
          <tr key={k}><td className="px-4 py-1.5"><span className="mono">{r.conto}</span> {r.conto_descrizione}{r.party_nome && <span className="text-slate-500"> · {r.party_nome}</span>}</td>
            <td className="w-32 px-4 py-1.5 text-right">{r.dare ? fmtEUR(r.dare) : ""}</td><td className="w-32 px-4 py-1.5 text-right">{r.avere ? fmtEUR(r.avere) : ""}</td></tr>
        ))}
      </tbody>
    </table>
  </div>
);

export default function Chiusura() {
  const { user } = useAuth();
  const canEdit = canSend(user);
  const [anno, setAnno] = useState(new Date().getFullYear() - 1);
  const [d, setD] = useState(null);
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const load = () => api.get(`/contabilita/chiusura/${anno}`).then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { setShow(false); load(); }, [anno]); // eslint-disable-line react-hooks/exhaustive-deps
  const act = async (fn, ok) => {
    setBusy(true);
    try { await fn(); toast.success(ok); setShow(false); await load(); } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };
  const chiudi = () => window.confirm(`Confermi la chiusura dell'esercizio ${anno}? Le registrazioni del ${anno} verranno bloccate.`)
    && act(() => api.post(`/contabilita/chiusura/${anno}`), `Esercizio ${anno} chiuso e conti riaperti al 01/01/${anno + 1}`);
  const riapri = () => window.confirm(`Annullare la chiusura dell'esercizio ${anno}? Verranno eliminate le scritture di chiusura e di riapertura.`)
    && act(() => api.delete(`/contabilita/chiusura/${anno}`), `Chiusura ${anno} annullata`);
  if (!d) return <div className="text-sm text-slate-500">Caricamento…</div>;
  const utile = d.risultato >= 0;

  return (
    <div>
      <PageHeader eyebrow="Contabilità generale" title="Chiusura e apertura esercizio">
        <select value={anno} onChange={(e) => setAnno(Number(e.target.value))} className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm" data-testid="chiusura-anno-select">
          {d.anni.map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
      </PageHeader>
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className={`rounded-xl p-5 ${d.chiuso ? "bg-slate-900 text-white" : "border border-slate-200 bg-white"}`} data-testid="chiusura-stato">
          <div className={`text-xs ${d.chiuso ? "text-slate-300" : "text-slate-500"}`}>Stato esercizio {anno}</div>
          <div className="mt-1 flex items-center gap-2 text-xl font-extrabold">{d.chiuso ? <><Lock className="h-5 w-5" />Chiuso</> : <><LockOpen className="h-5 w-5" />Aperto</>}</div>
        </div>
        <div className={`rounded-xl border p-5 ${utile ? "border-emerald-200 bg-emerald-50" : "border-rose-200 bg-rose-50"}`}>
          <div className="text-xs text-slate-600">{utile ? "Utile d'esercizio" : "Perdita d'esercizio"}</div>
          <div className="mt-1 text-xl font-extrabold" data-testid="chiusura-risultato">{fmtEUR(Math.abs(d.risultato))}</div>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-5 text-xs text-slate-600">
          {d.chiuso ? "Le registrazioni dell'anno sono bloccate. Per modificarle annulla la chiusura (solo se l'anno successivo è ancora aperto)."
            : "La chiusura salda costi e ricavi sul Conto economico, rileva l'utile o la perdita e chiude i conti patrimoniali; poi li riapre al 1° gennaio dell'anno successivo."}
        </div>
      </div>
      {d.motivo && !d.chiuso && <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800" data-testid="chiusura-motivo">{d.motivo}</div>}
      <div className="mb-5 flex flex-wrap gap-2">
        {!d.chiuso && <Button variant="outline" onClick={() => setShow((v) => !v)} data-testid="chiusura-anteprima-btn"><Eye className="mr-2 h-4 w-4" />{show ? "Nascondi anteprima" : "Anteprima scritture"}</Button>}
        {!d.chiuso && canEdit && <Button onClick={chiudi} disabled={busy || !!d.motivo || !show || !d.scritture.length} data-testid="chiusura-conferma-btn"><Lock className="mr-2 h-4 w-4" />Conferma chiusura {anno}</Button>}
        {d.chiuso && canEdit && <Button variant="outline" onClick={riapri} disabled={busy} data-testid="chiusura-annulla-btn"><LockOpen className="mr-2 h-4 w-4" />Annulla chiusura</Button>}
      </div>
      {!d.chiuso && !show && <p className="text-sm text-slate-500">Apri l'anteprima per controllare le scritture prima di confermare.</p>}
      {(d.chiuso || show) && (
        <div className="space-y-4" data-testid="chiusura-scritture">
          {d.scritture.length === 0 && <div className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-500">Nessun saldo da chiudere nell'esercizio {anno}</div>}
          {d.scritture.map((s, i) => <Scrittura key={s.id || s.ref} s={s} i={i} />)}
        </div>
      )}
    </div>
  );
}

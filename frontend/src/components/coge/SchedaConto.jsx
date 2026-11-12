import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Pencil } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { useAuth, canSend } from "@/context/AuthContext";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useConti, ORIGINE_BADGE } from "@/components/ContoSelect";
import { RegistrazioneDialog } from "@/components/coge/RegistrazioneDialog";

const Saldo = ({ v }) => <span className={v < 0 ? "text-rose-700" : ""}>{fmtEUR(Math.abs(v))} {v > 0 ? "D" : v < 0 ? "A" : ""}</span>;

const Movimento = ({ m, canEdit, onOpen }) => (
  <tr onClick={canEdit ? () => onOpen(m.id) : undefined} className={canEdit ? "cursor-pointer transition-colors hover:bg-blue-50" : ""} data-testid={`scheda-row-${m.id}`}>
    <td className="whitespace-nowrap px-3 py-2 text-xs">{fmtDate(m.data)}<div className="mono text-slate-400">{m.numero}/{m.anno}</div></td>
    <td className="px-3 py-2 text-xs">{m.causale} · {m.descrizione}{m.party_nome && <div className="text-slate-500">{m.party_nome}</div>}
      <div className="mt-0.5 text-slate-400">{m.contropartite.join(", ")} <span className={`rounded px-1 text-[10px] ${ORIGINE_BADGE[m.origine] || ""}`}>{m.origine}</span></div></td>
    <td className="px-3 py-2 text-right text-xs">{m.dare ? fmtEUR(m.dare) : ""}</td>
    <td className="px-3 py-2 text-right text-xs">{m.avere ? fmtEUR(m.avere) : ""}</td>
    <td className="whitespace-nowrap px-3 py-2 text-right text-xs font-semibold"><Saldo v={m.saldo} /></td>
    <td className="px-2 text-slate-400">{canEdit && <Pencil className="h-3.5 w-3.5" />}</td>
  </tr>
);

export const SchedaConto = ({ conto, dal, al, onClose, onChanged }) => {
  const { user } = useAuth();
  const canEdit = canSend(user);
  const [conti] = useConti();
  const [causali, setCausali] = useState([]);
  const [d, setD] = useState(null);
  const [edit, setEdit] = useState(null);
  const load = useCallback(() => {
    if (!conto) return;
    api.get("/contabilita/mastrino", { params: { conto, dal, al } }).then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e)));
  }, [conto, dal, al]);
  useEffect(() => { setD(null); load(); }, [load]);
  useEffect(() => { api.get("/contabilita/causali").then(({ data }) => setCausali(data)).catch(() => {}); }, []);
  const open = (id) => api.get(`/contabilita/registrazioni/${id}`).then(({ data }) => setEdit(data)).catch((e) => toast.error(errMsg(e)));
  return (
    <Sheet open={!!conto} onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent side="right" className="w-full overflow-y-auto bg-white sm:max-w-3xl" data-testid="scheda-conto-sheet">
        <SheetHeader><SheetTitle data-testid="scheda-conto-title">Estratto conto {d ? `${d.conto.codice} ${d.conto.descrizione}` : conto}</SheetTitle></SheetHeader>
        <p className="mt-1 text-xs text-slate-500">Dal {fmtDate(dal)} al {fmtDate(al)}{canEdit && " · clicca una riga per modificare la registrazione"}</p>
        {!d ? <p className="mt-6 text-sm text-slate-500">Caricamento…</p> : (
          <>
            <div className="my-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
              {[["Saldo iniziale", <Saldo v={d.saldo_iniziale} />], ["Dare", fmtEUR(d.dare)], ["Avere", fmtEUR(d.avere)], ["Saldo finale", <Saldo v={d.saldo_finale} />]].map(([l, v], i) => (
                <div key={l} className="rounded-lg border border-slate-200 p-3"><div className="text-[11px] text-slate-500">{l}</div><div className="font-bold" data-testid={`scheda-kpi-${i}`}>{v}</div></div>
              ))}
            </div>
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="w-full text-sm" data-testid="scheda-conto-table">
                <thead className="border-b border-slate-200 bg-slate-50 text-left text-[11px] uppercase tracking-wider text-slate-500">
                  <tr><th className="px-3 py-2">Data / N.</th><th className="px-3 py-2">Descrizione</th><th className="px-3 py-2 text-right">Dare</th><th className="px-3 py-2 text-right">Avere</th><th className="px-3 py-2 text-right">Saldo</th><th /></tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {d.movimenti.length === 0 && <tr><td colSpan={6} className="px-3 py-8 text-center text-xs text-slate-500" data-testid="scheda-empty">Nessun movimento nel periodo</td></tr>}
                  {d.movimenti.map((m) => <Movimento key={m.id} m={m} canEdit={canEdit} onOpen={open} />)}
                </tbody>
              </table>
            </div>
          </>
        )}
        <RegistrazioneDialog open={!!edit} item={edit} conti={conti} causali={causali} onClose={() => setEdit(null)}
          onSaved={() => { setEdit(null); load(); onChanged(); }} onIncasso={() => setEdit(null)} />
      </SheetContent>
    </Sheet>
  );
};

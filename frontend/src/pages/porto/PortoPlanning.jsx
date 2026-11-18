import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NSelect } from "@/components/ui/nselect";
import { STATO_POSTO, Legenda, oggi, addDays } from "@/lib/porto";

const W = 28;
const diff = (a, b) => Math.round((new Date(`${b}T00:00:00Z`) - new Date(`${a}T00:00:00Z`)) / 864e5);

const Riga = ({ p, occ, da, giorni }) => (
  <div className="flex border-b border-slate-100" data-testid={`planning-riga-${p.codice}`}>
    <div className="sticky left-0 z-10 w-28 shrink-0 border-r border-slate-200 bg-white px-2 py-1.5 text-xs">
      <b>{p.codice}</b> <span className="text-slate-400">{p.lunghezza_max}m</span>
    </div>
    <div className={`relative h-8 ${p.fuori_servizio ? "bg-slate-100" : ""}`} style={{ width: giorni * W }}>
      {occ.map((o) => {
        const s = Math.max(diff(da, o.da), 0), e = Math.min(diff(da, o.a), giorni);
        if (e <= s) return null;
        return (
          <div key={o.id} className={`absolute top-1 h-6 truncate rounded px-1.5 text-[11px] font-semibold leading-6 ${STATO_POSTO[o.tipo].cls}`}
            style={{ left: s * W + 1, width: (e - s) * W - 2 }} title={`${o.barca} - ${o.cliente}\n${o.da} → ${o.a}`} data-testid={`planning-occ-${o.id}`}>{o.barca}</div>
        );
      })}
    </div>
  </div>
);

export default function PortoPlanning() {
  const [da, setDa] = useState(addDays(oggi(), -3));
  const [giorni, setGiorni] = useState("31");
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/porto/planning", { params: { da, giorni } }).then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e))); }, [da, giorni]);
  const n = Number(giorni);
  const days = Array.from({ length: n }, (_, i) => addDays(da, i));
  return (
    <div data-testid="porto-planning-page">
      <PageHeader eyebrow="Porto turistico" title="Planning ormeggi">
        <Button variant="outline" size="icon" onClick={() => setDa(addDays(da, -7))} data-testid="planning-prev"><ChevronLeft className="h-4 w-4" /></Button>
        <Input type="date" value={da} onChange={(e) => e.target.value && setDa(e.target.value)} className="w-44" data-testid="planning-da" />
        <Button variant="outline" size="icon" onClick={() => setDa(addDays(da, 7))} data-testid="planning-next"><ChevronRight className="h-4 w-4" /></Button>
        <NSelect value={giorni} onChange={(e) => setGiorni(e.target.value)} className="w-32" data-testid="planning-giorni">
          <option value="14">2 settimane</option><option value="31">1 mese</option><option value="62">2 mesi</option><option value="92">3 mesi</option>
        </NSelect>
      </PageHeader>
      <Legenda />
      {d && (
        <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200 bg-white" data-testid="planning-griglia">
          <div className="min-w-max">
            <div className="flex border-b border-slate-200 bg-slate-50">
              <div className="sticky left-0 z-10 w-28 shrink-0 border-r border-slate-200 bg-slate-50 px-2 py-1 text-xs font-semibold text-slate-500">Posto</div>
              {days.map((x) => {
                const dt = new Date(`${x}T00:00:00Z`), we = [0, 6].includes(dt.getUTCDay());
                return <div key={x} className={`shrink-0 border-r border-slate-100 py-1 text-center text-[10px] ${x === oggi() ? "bg-amber-200 font-bold" : we ? "bg-slate-100" : ""}`} style={{ width: W }}>{dt.getUTCDate()}<br />{dt.toLocaleDateString("it-IT", { month: "short", timeZone: "UTC" })}</div>;
              })}
            </div>
            {d.posti.length === 0 && <p className="p-6 text-sm text-slate-500">Nessun posto barca configurato.</p>}
            {d.posti.map((p, i) => (
              <div key={p.id}>
                {(i === 0 || d.posti[i - 1].pontile !== p.pontile) && <div className="sticky left-0 bg-slate-800 px-2 py-0.5 text-xs font-bold text-white">{p.pontile}</div>}
                <Riga p={p} occ={d.occupazioni.filter((o) => o.posto_id === p.id)} da={da} giorni={n} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

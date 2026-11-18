import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, errMsg } from "@/lib/api";
import { toast } from "sonner";
import { PageHeader } from "@/components/Common";
import { Input } from "@/components/ui/input";
import { STATO_POSTO, Legenda, oggi } from "@/lib/porto";

const Posto = ({ p }) => {
  const s = STATO_POSTO[p.stato];
  const o = p.occupazione;
  return (
    <div className={`flex h-20 w-24 flex-col justify-between rounded-lg p-2 text-xs shadow-sm transition-transform hover:-translate-y-0.5 ${s.cls}`}
      title={o ? `${o.barca} (${o.lunghezza} m) - ${o.cliente}\n${o.da} → ${o.a}` : `Max ${p.lunghezza_max} m`} data-testid={`mappa-posto-${p.codice}`}>
      <div className="flex justify-between font-bold"><span>{p.codice}</span><span className="opacity-80">{p.lunghezza_max}m</span></div>
      <div className="truncate font-medium" data-testid={`mappa-posto-barca-${p.codice}`}>{o ? o.barca : s.label}</div>
    </div>
  );
};

export default function PortoMappa() {
  const [data, setData] = useState(oggi());
  const [m, setM] = useState(null);
  useEffect(() => { api.get("/porto/mappa", { params: { data } }).then(({ data: d }) => setM(d)).catch((e) => toast.error(errMsg(e))); }, [data]);
  return (
    <div data-testid="porto-mappa-page">
      <PageHeader eyebrow="Porto turistico" title="Mappa posti barca">
        <Input type="date" value={data} onChange={(e) => e.target.value && setData(e.target.value)} className="w-44" data-testid="mappa-data" />
      </PageHeader>
      {m && (
        <>
          <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {Object.entries(STATO_POSTO).map(([k, v]) => (
              <div key={k} className="rounded-xl border border-slate-200 bg-white p-4" data-testid={`mappa-conteggio-${k}`}>
                <div className="flex items-center gap-2 text-xs font-semibold uppercase text-slate-500"><span className={`h-2.5 w-2.5 rounded-full ${v.dot}`} />{v.label}</div>
                <div className="mt-1 text-2xl font-extrabold text-slate-900">{m.conteggi[k]}</div>
              </div>
            ))}
          </div>
          <Legenda />
          {m.pontili.length === 0 && <p className="mt-8 text-sm text-slate-500" data-testid="mappa-vuota">Nessun pontile: crealo in <Link className="text-blue-700 underline" to="/porto/configurazione">Configurazione porto</Link>.</p>}
          {m.pontili.map((pt) => (
            <section key={pt.id} className="mt-6 rounded-xl border border-slate-200 bg-white p-4" data-testid={`mappa-pontile-${pt.id}`}>
              <h2 className="mb-3 text-base font-bold text-slate-800">{pt.nome} <span className="text-xs font-normal text-slate-500">({pt.posti.length} posti)</span></h2>
              <div className="flex flex-wrap gap-2">{pt.posti.map((p) => <Posto key={p.id} p={p} />)}</div>
            </section>
          ))}
        </>
      )}
    </div>
  );
}

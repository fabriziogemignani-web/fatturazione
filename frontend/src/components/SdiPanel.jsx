import { Link } from "react-router-dom";
import { fmtEUR, fmtDateTime, NOTIFICHE } from "@/lib/fe";
import { StatusBadge } from "@/components/Common";

const NotificaCard = ({ n, data, total }) => {
  const pct = total ? Math.round((data.count / total) * 100) : 0;
  return (
    <Link to={`/fatture?status=${data.status}`} data-testid={`sdi-card-${n.key}`}
      className="group rounded-xl border border-slate-200/80 bg-white p-5 shadow-sm transition-shadow hover:shadow-md">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className={`mono text-xs font-medium ${n.text}`}>{n.code}</div>
          <div className="mt-1 text-sm font-semibold text-slate-800">{n.label}</div>
        </div>
        <div className="text-3xl font-extrabold tracking-tight text-slate-900" data-testid={`sdi-count-${n.key}`}>{data.count}</div>
      </div>
      <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-slate-100">
        <div className={`h-full rounded-full ${n.bar} transition-[width] duration-700`} style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-3 flex items-center justify-between text-xs">
        <span className="text-slate-500">{n.desc}</span>
        <span className="whitespace-nowrap font-semibold text-slate-700" data-testid={`sdi-total-${n.key}`}>{fmtEUR(data.totale)}</span>
      </div>
    </Link>
  );
};

export const SdiPanel = ({ d }) => (
  <section className="mt-6 rounded-xl border border-slate-200/80 bg-slate-50 p-6" data-testid="sdi-panel">
    <div className="mb-5 flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h3 className="text-lg font-semibold text-slate-800">Cruscotto fatture inviate</h3>
        <p className="text-xs text-slate-500">Suddivise per notifica del Sistema di Interscambio · clicca una voce per vedere le fatture</p>
      </div>
      <div className="text-sm text-slate-600">Inviate in totale: <b className="text-slate-900" data-testid="sdi-sent-total">{d.inviate_totale}</b></div>
    </div>
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {NOTIFICHE.map((n) => <NotificaCard key={n.key} n={n} data={d.notifiche[n.key]} total={d.inviate_totale} />)}
    </div>
    <div className="mt-6 rounded-lg border border-slate-200 bg-white">
      <div className="border-b border-slate-100 px-4 py-3 text-xs font-medium uppercase tracking-wider text-slate-500">Ultime notifiche</div>
      {d.ultime_notifiche.length === 0 ? (
        <div className="px-4 py-6 text-sm text-slate-500" data-testid="sdi-last-empty">Nessuna fattura ancora inviata allo SDI.</div>
      ) : (
        <div className="divide-y divide-slate-100" data-testid="sdi-last-list">
          {d.ultime_notifiche.map((i) => (
            <Link key={i.id} to={`/fatture/${i.id}`} className="flex flex-col gap-1 px-4 py-3 transition-colors hover:bg-slate-50 sm:flex-row sm:items-center sm:justify-between" data-testid={`sdi-last-${i.id}`}>
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-slate-900">N. {i.numero_display} · {i.cliente?.denominazione}</div>
                <div className="truncate text-xs text-slate-500">{i.sdi_message}</div>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <span className="mono text-[10px] text-slate-400">{fmtDateTime(i.updated_at)}</span>
                <StatusBadge status={i.status} testId={`sdi-last-status-${i.id}`} />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  </section>
);

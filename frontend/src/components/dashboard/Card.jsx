export const DCard = ({ title, sub, action, children, className = "", testId }) => (
  <section className={`flex min-w-0 flex-col rounded-2xl border border-slate-200/80 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)] fade-up ${className}`} data-testid={testId}>
    {title && (
      <div className="flex items-start justify-between gap-3 px-5 pt-4">
        <div className="min-w-0">
          <h3 className="text-[15px] font-semibold text-slate-900">{title}</h3>
          {sub && <p className="mt-0.5 text-xs text-slate-500">{sub}</p>}
        </div>
        {action}
      </div>
    )}
    <div className="min-w-0 flex-1 p-5 pt-3">{children}</div>
  </section>
);

export const Delta = ({ v, invert }) => {
  if (v == null) return null;
  const good = invert ? v <= 0 : v >= 0;
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums ${good ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"}`}>{v > 0 ? "+" : ""}{v.toLocaleString("it-IT")}%</span>;
};

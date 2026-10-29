import { STATUS } from "@/lib/fe";

export const StatusBadge = ({ status, testId }) => {
  const s = STATUS[status] || STATUS.bozza;
  return (
    <span data-testid={testId || "sdi-status-pill"} className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${s.cls}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {s.label}
    </span>
  );
};

export const PageHeader = ({ eyebrow, title, children }) => (
  <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between fade-up">
    <div>
      <div className="text-xs font-medium uppercase tracking-wider text-slate-500">{eyebrow}</div>
      <h1 className="mt-1 text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl">{title}</h1>
    </div>
    <div className="flex flex-wrap gap-2">{children}</div>
  </div>
);

export const Field = ({ label, children, className = "" }) => (
  <label className={`flex flex-col gap-1.5 ${className}`}>
    <span className="text-xs font-medium uppercase tracking-wider text-slate-500">{label}</span>
    {children}
  </label>
);

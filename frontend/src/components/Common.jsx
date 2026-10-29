import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { toast } from "sonner";
import { STATUS } from "@/lib/fe";
import { errMsg, errFields } from "@/lib/api";

const ErrCtx = createContext({ errs: new Map(), clear: () => {} });

export const useFieldErrors = () => {
  const [errs, setErrs] = useState(new Map());
  const clear = useCallback((k) => setErrs((m) => { if (!m.has(k)) return m; const n = new Map(m); n.delete(k); return n; }), []);
  const fail = useCallback((e) => {
    const m = errFields(e);
    setErrs(m);
    toast.error(errMsg(e));
    if (m.size) setTimeout(() => document.querySelector(".field-invalid, .field-invalid-el")?.scrollIntoView({ behavior: "smooth", block: "center" }), 80);
  }, []);
  const reset = useCallback(() => setErrs(new Map()), []);
  const value = useMemo(() => ({ errs, clear }), [errs, clear]);
  return { fail, reset, value };
};

export const FieldErrors = ({ value, children }) => <ErrCtx.Provider value={value}>{children}</ErrCtx.Provider>;

export const useInvalid = () => {
  const { errs, clear } = useContext(ErrCtx);
  return [(k) => (errs.has(k) ? "field-invalid-el" : ""), clear];
};

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

export const Field = ({ label, children, className = "", name }) => {
  const { errs, clear } = useContext(ErrCtx);
  const msg = name && errs.get(name);
  return (
    <label className={`flex flex-col gap-1.5 ${msg ? "field-invalid" : ""} ${className}`} onInput={msg ? () => clear(name) : undefined} onClick={msg ? (e) => e.target.closest("button[role='combobox']") && clear(name) : undefined} data-invalid={msg ? "true" : undefined}>
      <span className={`text-xs font-medium uppercase tracking-wider ${msg ? "text-rose-600" : "text-slate-500"}`}>{label}</span>
      {children}
      {msg && <span className="text-xs font-medium text-rose-600" data-testid={`field-error-${name.replace(/[._]/g, "-")}`}>{msg}</span>}
    </label>
  );
};

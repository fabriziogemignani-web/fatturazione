import * as React from "react";
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue, SearchCtx, norm, anyMatch } from "@/components/ui/select";
import { cn } from "@/lib/utils";

const EMPTY = "__vuoto__";
const txt = (n) => (n == null || typeof n === "boolean" ? "" : typeof n === "string" || typeof n === "number" ? String(n)
  : Array.isArray(n) ? n.map(txt).join("") : n.props ? txt(n.props.children) : "");
const enc = (v) => (v === "" || v == null ? EMPTY : String(v));

const Group = ({ label, children }) => {
  const q = React.useContext(SearchCtx);
  if (q && !anyMatch(children, q, label)) return null;
  const inner = q && norm(label).includes(q) ? <SearchCtx.Provider value="">{children}</SearchCtx.Provider> : children;
  return <SelectGroup><SelectLabel className="text-xs text-slate-500">{label}</SelectLabel>{inner}</SelectGroup>;
};

const toItems = (children) => React.Children.toArray(children).map((c, i) => {
  if (c?.type === "optgroup") {
    return <Group key={c.key || i} label={c.props.label} data-label={c.props.label}>{toItems(c.props.children)}</Group>;
  }
  if (c?.type === "option") {
    return <SelectItem key={c.key || i} value={enc(c.props.value)} disabled={c.props.disabled}>{txt(c.props.children) || "\u00a0"}</SelectItem>;
  }
  return null;
});

// Drop-in replacement for a native <select> (with <option>/<optgroup>) that adds a search box on long lists.
export const NSelect = ({ value, defaultValue, onChange, disabled, className, children, "data-testid": testId, title }) => {
  const [inner, setInner] = React.useState(defaultValue ?? "");
  const cur = value !== undefined ? value : inner;
  const change = (v) => {
    const raw = v === EMPTY ? "" : v;
    if (value === undefined) setInner(raw);
    onChange?.({ target: { value: raw } });
  };
  return (
    <Select value={enc(cur)} onValueChange={change} disabled={disabled}>
      <SelectTrigger className={cn("h-9 bg-white text-left", !/(^|\s)(w-|col-span)/.test(className || "") && "w-auto min-w-[10rem]", className, "flex")} data-testid={testId} title={title}><SelectValue placeholder="—" /></SelectTrigger>
      <SelectContent className="max-h-80 max-w-[min(32rem,90vw)] bg-white">{toItems(children)}</SelectContent>
    </Select>
  );
};

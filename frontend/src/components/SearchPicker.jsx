import { useEffect, useMemo, useRef, useState } from "react";
import { Search, X } from "lucide-react";

const norm = (s) => (s || "").toString().toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");

export const SearchPicker = ({ items, value, onPick, onClear, placeholder = "Cerca…", testId = "search-picker", className = "" }) => {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [hi, setHi] = useState(0);
  const box = useRef(null);
  useEffect(() => {
    const f = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", f);
    return () => document.removeEventListener("mousedown", f);
  }, []);
  const res = useMemo(() => {
    const t = norm(q).split(/\s+/).filter(Boolean);
    const out = t.length ? items.filter((i) => { const h = norm(`${i.label} ${i.sub || ""} ${i.search || ""}`); return t.every((w) => h.includes(w)); }) : items;
    return out.slice(0, 60);
  }, [q, items]);
  useEffect(() => { setHi(0); }, [q]);
  const pick = (i) => { onPick(i); setQ(""); setOpen(false); };
  const key = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setHi((h) => Math.min(h + 1, res.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setHi((h) => Math.max(h - 1, 0)); }
    else if (e.key === "Enter" && open && res[hi]) { e.preventDefault(); pick(res[hi]); }
    else if (e.key === "Escape") setOpen(false);
  };
  let last = null;

  return (
    <div ref={box} className={`relative ${className}`}>
      <div className="flex h-9 items-center gap-2 rounded-md border border-slate-200 bg-white px-2 focus-within:ring-2 focus-within:ring-blue-500">
        <Search className="h-4 w-4 shrink-0 text-slate-400" />
        <input value={open ? q : q || value || ""} onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} onKeyDown={key}
          placeholder={value || placeholder} className="h-full min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-slate-500" data-testid={`${testId}-input`} />
        {value && onClear && <button type="button" onClick={() => { onClear(); setQ(""); }} className="rounded p-0.5 text-slate-400 hover:text-slate-700" aria-label="Svuota" data-testid={`${testId}-clear`}><X className="h-4 w-4" /></button>}
      </div>
      {open && (
        <div className="absolute z-50 mt-1 max-h-80 w-full min-w-[18rem] overflow-y-auto rounded-md border border-slate-200 bg-white py-1 shadow-lg" data-testid={`${testId}-results`}>
          {res.length === 0 && <div className="px-3 py-3 text-sm text-slate-500" data-testid={`${testId}-empty`}>Nessun risultato</div>}
          {res.map((i, k) => {
            const head = i.group && i.group !== last ? i.group : null;
            last = i.group;
            return (
              <div key={i.key}>
                {head && <div className="px-3 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400">{head}</div>}
                <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => pick(i)} onMouseEnter={() => setHi(k)}
                  className={`flex w-full items-baseline justify-between gap-3 px-3 py-1.5 text-left text-sm ${k === hi ? "bg-blue-50" : ""}`} data-testid={`${testId}-option-${i.key}`}>
                  <span className={i.strong ? "font-semibold" : ""}>{i.label}</span>{i.sub && <span className="shrink-0 text-xs text-slate-500">{i.sub}</span>}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

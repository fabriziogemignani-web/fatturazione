import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";

const norm = (v) => String(v ?? "").toLowerCase();

export const useColonne = (rows, cols, iniziale = null) => {
  const [sort, setSort] = useState(iniziale);
  const [flt, setFlt] = useState({});
  const shown = useMemo(() => {
    const attivi = Object.entries(flt).filter(([, v]) => v.trim());
    let out = attivi.length ? rows.filter((r) => attivi.every(([k, v]) => norm(cols[k].f(r)).includes(v.trim().toLowerCase()))) : rows;
    if (sort) {
      const s = cols[sort.k].s || cols[sort.k].f;
      out = [...out].sort((a, b) => {
        const x = s(a), y = s(b);
        const c = typeof x === "number" && typeof y === "number" ? x - y : String(x ?? "").localeCompare(String(y ?? ""), "it", { numeric: true });
        return sort.dir === "asc" ? c : -c;
      });
    }
    return out;
  }, [rows, cols, sort, flt]);
  const toggle = (k) => setSort((o) => (o?.k !== k ? { k, dir: "asc" } : o.dir === "asc" ? { k, dir: "desc" } : null));
  const attivi = Object.values(flt).some((v) => v.trim());
  return [shown, { sort, toggle, flt, setFlt, attivi, reset: () => setFlt({}) }];
};

export const ThCol = ({ c, k, label, right, className = "", testPrefix = "col" }) => {
  const Icon = c.sort?.k !== k ? ArrowUpDown : c.sort.dir === "asc" ? ArrowUp : ArrowDown;
  return (
    <th className={`px-3 py-2 align-top font-medium ${right ? "text-right" : ""} ${className}`}>
      <button type="button" onClick={() => c.toggle(k)} className={`inline-flex items-center gap-1 uppercase tracking-wider hover:text-slate-900 ${c.sort?.k === k ? "text-slate-900" : ""}`} data-testid={`${testPrefix}-sort-${k}`}>
        {label}<Icon className={`h-3 w-3 ${c.sort?.k === k ? "" : "opacity-40"}`} />
      </button>
      <input value={c.flt[k] || ""} onChange={(e) => c.setFlt({ ...c.flt, [k]: e.target.value })} onClick={(e) => e.stopPropagation()} placeholder="Filtra"
        className={`mt-1 block h-7 w-full min-w-[70px] rounded border border-slate-200 bg-white px-2 text-xs font-normal normal-case tracking-normal text-slate-700 placeholder:text-slate-400 focus:border-blue-400 focus:outline-none print:hidden ${right ? "text-right" : ""}`}
        data-testid={`${testPrefix}-filter-${k}`} />
    </th>
  );
};

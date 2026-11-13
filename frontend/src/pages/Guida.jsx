import { useMemo, useState } from "react";
import { BookOpen, Download, Search } from "lucide-react";
import { CAPITOLI } from "@/lib/guida";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const norm = (s) => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

const filtra = (q) => {
  const k = norm(q.trim());
  if (!k) return CAPITOLI;
  return CAPITOLI.map((c) => ({ ...c, sezioni: c.sezioni.filter((s) => norm([c.titolo, s.t, ...s.p].join(" ")).includes(k)) })).filter((c) => c.sezioni.length);
};

const Indice = ({ caps }) => (
  <nav className="sticky top-4 hidden max-h-[80vh] overflow-y-auto rounded-xl border border-slate-200 bg-white p-4 text-sm shadow-sm lg:block print:hidden" data-testid="guida-indice">
    <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Indice</div>
    {caps.map((c, i) => (
      <a key={c.id} href={`#${c.id}`} className="block rounded px-2 py-1.5 text-slate-700 transition-colors hover:bg-slate-100" data-testid={`guida-indice-${c.id}`}>{i + 1}. {c.titolo}</a>
    ))}
  </nav>
);

const Capitolo = ({ c, n }) => (
  <section id={c.id} className="scroll-mt-4 break-inside-avoid-page rounded-xl border border-slate-200 bg-white p-6 shadow-sm print:border-0 print:p-0 print:shadow-none" data-testid={`guida-cap-${c.id}`}>
    <h2 className="mb-4 text-lg font-bold text-slate-900">{n}. {c.titolo}</h2>
    <div className="space-y-5">
      {c.sezioni.map((s) => (
        <div key={s.t} className="break-inside-avoid">
          <h3 className="mb-1.5 text-sm font-semibold text-blue-800">{s.t}</h3>
          {s.p.map((p, i) => <p key={i} className="mb-1.5 text-sm leading-relaxed text-slate-700">{p}</p>)}
        </div>
      ))}
    </div>
  </section>
);

export default function Guida() {
  const [q, setQ] = useState("");
  const caps = useMemo(() => filtra(q), [q]);
  return (
    <div>
      <PageHeader eyebrow="Manuale per gli operatori" title="Guida all'uso">
        <Button variant="outline" onClick={() => { setQ(""); setTimeout(() => window.print(), 50); }} className="print:hidden" data-testid="guida-pdf-btn"><Download className="mr-2 h-4 w-4" />Scarica PDF</Button>
      </PageHeader>
      <div className="relative mb-6 max-w-xl print:hidden">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cerca nella guida (es. nota di credito, bollo, DDT)" className="bg-white pl-9" data-testid="guida-search-input" />
      </div>
      <div className="grid gap-6 lg:grid-cols-[240px_1fr] print:block">
        <Indice caps={caps} />
        <div className="min-w-0 space-y-6">
          {caps.length === 0 && (
            <div className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-500" data-testid="guida-empty">
              <BookOpen className="mx-auto mb-2 h-6 w-6 text-slate-400" />Nessun argomento trovato per "{q}". Prova con un'altra parola.
            </div>
          )}
          {caps.map((c) => <Capitolo key={c.id} c={c} n={CAPITOLI.indexOf(CAPITOLI.find((x) => x.id === c.id)) + 1} />)}
        </div>
      </div>
    </div>
  );
}

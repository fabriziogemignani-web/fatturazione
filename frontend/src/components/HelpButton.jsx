import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { HelpCircle, BookOpen } from "lucide-react";
import { CAPITOLI } from "@/lib/guida";
import { Capitolo, capitoliPer } from "@/pages/Guida";
import { useAuth } from "@/context/AuthContext";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";

const ROUTES = [
  [/^\/dashboard/, "dashboard"], [/^\/anagrafiche/, "anagrafiche"], [/^\/articoli/, "articoli"],
  [/^\/(ddt|fatturazione-differita)/, "ddt"], [/^\/passive/, "passive"], [/^\/ordini-(clienti|fornitori)/, "ordini"], [/^\/bem/, "bem"],
  [/^\/(scadenzario|scadenzario-fornitori|comunicazioni)/, "scadenze"], [/^\/(magazzino|corrispettivi)/, "altro"],
  [/^\/contabilita\/prima-nota/, "coge-prima-nota"], [/^\/contabilita\/registrazione-veloce/, "coge-veloce"], [/^\/contabilita\/(mastrini|bilancio)/, "coge-schede"],
  [/^\/contabilita\/chiusura/, "coge-chiusura"], [/^\/contabilita\/piano-conti/, "coge-piano"],
  [/^\/fatture/, "fatture"],
];

const capitoloDi = (path, search) => {
  if (/^\/fatture/.test(path) && search.includes("tipo=TD04")) return "note-credito";
  return (ROUTES.find(([rx]) => rx.test(path)) || [null, "inizio"])[1];
};

export const HelpButton = () => {
  const { pathname, search } = useLocation();
  const [open, setOpen] = useState(false);
  const { user } = useAuth();
  if (pathname.startsWith("/guida")) return null;
  const visibili = capitoliPer(user);
  const id = capitoloDi(pathname, search);
  const cap = visibili.find((c) => c.id === id) || visibili[0];
  const n = CAPITOLI.indexOf(cap);
  return (
    <>
      <button onClick={() => setOpen(true)} title="Aiuto su questa pagina" aria-label="Aiuto"
        className="fixed bottom-5 right-5 z-40 flex h-11 w-11 items-center justify-center rounded-full bg-slate-900 text-white shadow-lg transition-transform hover:scale-105 hover:bg-blue-700 print:hidden"
        data-testid="help-btn"><HelpCircle className="h-5 w-5" /></button>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="right" className="w-full overflow-y-auto bg-slate-50 sm:max-w-xl" data-testid="help-sheet">
          <SheetHeader><SheetTitle data-testid="help-sheet-title">Aiuto · {cap.titolo}</SheetTitle></SheetHeader>
          <div className="mt-4"><Capitolo c={cap} n={n + 1} /></div>
          <Link to={`/guida#${cap.id}`} onClick={() => setOpen(false)} className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-blue-700 hover:underline" data-testid="help-open-guida">
            <BookOpen className="h-4 w-4" />Apri la guida completa
          </Link>
        </SheetContent>
      </Sheet>
    </>
  );
};

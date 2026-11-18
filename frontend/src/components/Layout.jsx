import { useState } from "react";
import { useTheme } from "@/lib/theme";
import { NavLink, Navigate, useNavigate, useLocation } from "react-router-dom";
import { ClipboardList, ShoppingCart, PackageCheck, ChevronDown, Factory, Network, Cog, Send, LifeBuoy, History, Stamp, Wallet, LayoutDashboard, FileText, Users2, Building2, ShieldCheck, LogOut, Menu, X, Package, Building, ListOrdered, CalendarClock, Inbox, CalendarMinus, BookOpenCheck, Calculator, Receipt, KeyRound, Archive, UploadCloud, FileInput, FileOutput, Contact, FileArchive, Landmark, TrendingUp, Warehouse, BookText, FileSpreadsheet, Scale, ListTree, Lock, Mail, Percent, Vault, Truck, FileStack, Banknote, CalendarRange, Pin, PinOff, PanelLeftClose, PanelLeftOpen, CreditCard, Moon, Sun, Sparkles, Anchor, FileSignature, Ship, Sailboat, Settings2 } from "lucide-react";
import { ChangePasswordDialog } from "@/components/ChangePasswordDialog";
import { CompanySwitcher } from "@/components/CompanySwitcher";
import { HelpButton } from "@/components/HelpButton";
import { useAuth, isAdmin, canSend, canAny } from "@/context/AuthContext";
import { useCompany } from "@/context/CompanyContext";
import { mods, pathAllowed, homeFor, menuOff, dirittoFor } from "@/lib/moduli";
import { UpdateBanner } from "@/components/UpdateBanner";
import { FiscalBanner } from "@/components/FiscalBanner";

const NAV = [
  { items: [{ to: "/dashboard", label: "Dashboard", icon: LayoutDashboard, id: "dashboard" }] },
  { title: "Vendite", id: "attive", mod: "fatture_attive", items: [
    { to: "/fatture", label: "Fatture emesse", icon: FileText, id: "fatture" },
    { to: "/ordini-clienti", label: "Ordini clienti", icon: ClipboardList, id: "ordini-clienti" },
    { to: "/invio-sdi", label: "Invio massivo SDI", icon: Send, id: "invio-sdi", accounting: true },
    { to: "/ddt", label: "Documenti di trasporto", icon: Truck, id: "ddt" },
    { to: "/fatturazione-differita", label: "Fatturazione differita", icon: FileStack, id: "fatturazione-differita" },
    { to: "/registro", label: "Registro numerazione", icon: ListOrdered, id: "registro" },
    { to: "/comunicazioni", label: "Comunicazioni ai clienti", icon: Mail, id: "comunicazioni" },
  ] },
  { title: "Acquisti", id: "passive", mod: "fatture_passive", items: [
    { to: "/passive", label: "Fatture ricevute", icon: Inbox, id: "passive" },
    { to: "/ordini-fornitori", label: "Ordini fornitori", icon: ShoppingCart, id: "ordini-fornitori" },
    { to: "/bem", label: "Entrate merce (BEM)", icon: PackageCheck, id: "bem" },
  ] },
  { title: "Fisco e IVA", id: "iva", items: [
    { to: "/stampe-fiscali", label: "Stampe fiscali", icon: BookOpenCheck, id: "stampe-fiscali" },
    { to: "/liquidazione-iva", label: "Liquidazione IVA", icon: Calculator, id: "liquidazione-iva" },
    { to: "/bolli-virtuali", label: "Bolli virtuali", icon: Stamp, id: "bolli-virtuali", mod: "fatture_attive" },
    { to: "/storico-f24", label: "Storico versamenti F24", icon: History, id: "storico-f24" },
    { to: "/codici-tributo", label: "Codici tributo", icon: History, id: "codici-tributo" },
    { to: "/ritenute", label: "Ritenute d'acconto", icon: Percent, id: "ritenute", mod: "fatture_passive" },
    { to: "/corrispettivi", label: "Corrispettivi", icon: Receipt, id: "corrispettivi", mod: "corrispettivi" },
    { to: "/esportazione", label: "Export commercialista", icon: FileArchive, id: "esportazione", accounting: true },
    { to: "/conservazione", label: "Conservazione documenti", icon: Vault, id: "conservazione" },
  ] },
  { title: "Contabilità generale", id: "contabilita", items: [
    { to: "/contabilita/prima-nota", label: "Prima nota e giornale", icon: BookText, id: "prima-nota", mod: "contabilita" },
    { to: "/contabilita/registrazione-veloce", label: "Registrazione veloce", icon: Calculator, id: "registrazione-veloce", accounting: true, mod: "contabilita" },
    { to: "/contabilita/mastrini", label: "Schede contabili", icon: FileSpreadsheet, id: "mastrini", mod: "contabilita" },
    { to: "/contabilita/ratei-risconti", label: "Ratei e risconti", icon: CalendarRange, id: "ratei-risconti", mod: "contabilita" },
    { to: "/consulente-ia", label: "Consulente IA", icon: Sparkles, id: "consulente-ia" },
    { to: "/contabilita/carte", label: "Estratto conto carte", icon: CreditCard, id: "carte", mod: "contabilita" },
    { to: "/contabilita/bilancio", label: "Bilancio di verifica", icon: Scale, id: "bilancio", mod: "contabilita" },
    { to: "/contabilita/chiusura", label: "Chiusura esercizio", icon: Lock, id: "chiusura", mod: "contabilita" },
    { to: "/contabilita/piano-conti", label: "Piano dei conti e tabelle", icon: ListTree, id: "piano-conti", diritto: "tabelle_contabili", mod: "contabilita" },
    { to: "/pagamenti-fornitori", label: "Pagamenti fornitori", icon: Wallet, id: "pagamenti-fornitori", accounting: true, mod: "fatture_passive" },
    { to: "/riba", label: "Effetti Ri.Ba.", icon: Banknote, id: "riba", accounting: true, mod: "fatture_attive" },
  ] },
  { title: "Scadenze", id: "scadenze", items: [
    { to: "/scadenzario", label: "Scadenzario clienti", icon: CalendarClock, id: "scadenzario", mod: "fatture_attive" },
    { to: "/scadenzario-fornitori", label: "Scadenzario fornitori", icon: CalendarMinus, id: "scadenzario-fornitori", mod: "fatture_passive" },
  ] },
  { title: "Tesoreria", id: "tesoreria", items: [
    { to: "/riconciliazione", label: "Riconciliazione bancaria", icon: Landmark, id: "riconciliazione" },
    { to: "/previsione-cassa", label: "Previsione di cassa", icon: TrendingUp, id: "previsione-cassa" },
  ] },
  { title: "Magazzino", id: "magazzino-group", items: [
    { to: "/magazzino", label: "Giacenze e movimenti", icon: Warehouse, id: "magazzino", diritto: "articoli_magazzino" },
  ] },
  { title: "Porto turistico", id: "porto-group", items: [
    { to: "/porto/mappa", label: "Mappa posti barca", icon: Anchor, id: "porto-mappa" },
    { to: "/porto/planning", label: "Planning ormeggi", icon: CalendarRange, id: "porto-planning" },
    { to: "/porto/contratti", label: "Contratti di ormeggio", icon: FileSignature, id: "porto-contratti" },
    { to: "/porto/transiti", label: "Transiti", icon: Ship, id: "porto-transiti" },
    { to: "/porto/barche", label: "Barche e armatori", icon: Sailboat, id: "porto-barche" },
    { to: "/porto/configurazione", label: "Configurazione porto", icon: Settings2, id: "porto-config" },
  ] },
  { title: "Produzione", id: "produzione-group", items: [
    { to: "/produzione", label: "Ordini di produzione", icon: Factory, id: "produzione", end: true, diritto: "articoli_magazzino" },
    { to: "/produzione/distinte", label: "Distinte base e cicli", icon: Network, id: "distinte-base", diritto: "articoli_magazzino" },
    { to: "/produzione/centri", label: "Centri di lavoro", icon: Cog, id: "centri-lavoro", diritto: "articoli_magazzino" },
    { to: "/produzione/mrp", label: "Fabbisogno materiali (MRP)", icon: Calculator, id: "mrp", diritto: "articoli_magazzino" },
  ] },
  { title: "Anagrafiche", id: "archivi", items: [
    { to: "/anagrafiche", label: "Clienti e fornitori", icon: Users2, id: "anagrafiche" },
    { to: "/articoli", label: "Articoli e servizi", icon: Package, id: "articoli", diritto: "articoli_magazzino" },
  ] },
  { title: "Impostazioni", id: "impostazioni", items: [
    { to: "/impostazioni", label: "Dati azienda", icon: Building2, id: "impostazioni", diritto: ["dati_azienda", "banche"] },
    { to: "/aziende", label: "Aziende", icon: Building, id: "aziende", admin: true },
    { to: "/utenti", label: "Gestione utenti", icon: ShieldCheck, id: "utenti", admin: true },
    { to: "/importazione", label: "Importazione di massa", icon: FileSpreadsheet, id: "importazione", admin: true },
  ] },
];

const NAV_ARCHIVIO = [
  { items: [{ to: "/archivio", label: "Dashboard archivio", icon: LayoutDashboard, id: "arch-dashboard", end: true }] },
  { title: "Importazione", id: "arch-import", items: [{ to: "/archivio/carica", label: "Carica fatture", icon: UploadCloud, id: "arch-carica", accounting: true }] },
  { title: "Fatture archiviate", id: "arch-fatture", items: [
    { to: "/archivio/attiva", label: "Fatture attive", icon: FileOutput, id: "arch-attive" },
    { to: "/archivio/passiva", label: "Fatture passive", icon: FileInput, id: "arch-passive" },
  ] },
  { title: "Anagrafiche", id: "arch-anag", items: [{ to: "/archivio/anagrafiche", label: "Clienti e fornitori", icon: Contact, id: "arch-anagrafiche" }] },
];

const AreaSwitch = ({ archivio, onNav, m }) => {
  const navigate = useNavigate();
  const go = (to) => { navigate(to); onNav?.(); };
  if (!m.fatturazione || !m.archivio) return null;
  const cls = (on) => `flex flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-2 text-xs font-semibold transition-colors ${on ? "bg-blue-600 text-white" : "text-slate-400 hover:text-white"}`;
  return (
    <div className="flex gap-1 rounded-lg bg-white/5 p-1" data-testid="area-switch">
      <button className={cls(!archivio)} onClick={() => go("/dashboard")} data-testid="area-fatturazione-btn"><FileText className="h-3.5 w-3.5" />Fatturazione</button>
      <button className={cls(archivio)} onClick={() => go("/archivio")} data-testid="area-archivio-btn"><Archive className="h-3.5 w-3.5" />Archivio fatture</button>
    </div>
  );
};
const Brand = () => (
  <div className="px-2" data-testid="brand-invoix">
    <div className="text-2xl font-black leading-none tracking-tight text-white">Invoi<span className="text-blue-400">x</span></div>
    <div className="mt-1 text-[10px] uppercase tracking-[0.2em] text-slate-400">Fatturazione e contabilità</div>
  </div>
);

const NavGroup = ({ g, onNav, shown, active, onToggle, compact }) => (
    <div className={`flex flex-col gap-1 ${compact ? "items-center border-t border-slate-800 pt-2 first:border-0 first:pt-0" : ""}`} data-testid={g.id ? `nav-group-${g.id}` : undefined}>
      {g.title && !compact && (
        <button type="button" onClick={onToggle} className={`mt-1 flex items-center justify-between gap-2 rounded-md border-l-[3px] px-3 py-2 text-left text-xs font-extrabold uppercase leading-tight tracking-[0.1em] transition-colors hover:bg-white/5 hover:text-white ${active ? "border-blue-400 bg-white/5 text-blue-200" : "border-slate-600 text-slate-100"}`} aria-expanded={shown} data-testid={`nav-toggle-${g.id}`}>
          <span>{g.title}</span><ChevronDown className={`h-4 w-4 shrink-0 transition-transform duration-200 ${shown ? "rotate-180" : ""}`} />
        </button>
      )}
      {(shown || !g.title || compact) && g.items.map(({ to, label, icon: Icon, id, end }) => (
        <NavLink key={to} to={to} end={end} onClick={onNav} data-testid={`nav-${id}`} title={compact ? label : undefined}
          className={({ isActive }) => `flex items-center gap-3 rounded-lg ${compact ? "justify-center p-2.5" : "px-3 py-2.5"} text-sm font-medium transition-colors ${isActive ? "bg-white/10 text-white" : "text-slate-400 hover:bg-white/5 hover:text-white"}`}>
          <Icon className="h-4 w-4 shrink-0" />{!compact && label}
        </NavLink>
      ))}
    </div>
);

const useOpenGroups = () => {
  const [open, setOpen] = useState(() => { try { return JSON.parse(localStorage.getItem("nav_open") || "{}"); } catch { return {}; } });
  const toggle = (id, cur) => { const n = { ...open, [id]: !cur }; setOpen(n); localStorage.setItem("nav_open", JSON.stringify(n)); };
  return [open, toggle];
};

const IconBtn = ({ icon: Icon, label, onClick, testId }) => (
  <button title={label} onClick={onClick} data-testid={testId} className="rounded-lg p-2.5 text-slate-400 transition-colors hover:bg-white/5 hover:text-white"><Icon className="h-4 w-4" /></button>
);

const SideContent = ({ onNav, compact }) => {
  const { company } = useCompany();
  const m = mods(company);
  const path = useLocation().pathname;
  const archivio = path.startsWith("/archivio") || (!m.fatturazione && m.archivio && !path.startsWith("/impostazioni") && !path.startsWith("/aziende") && !path.startsWith("/utenti"));
  const nav = archivio ? [...NAV_ARCHIVIO, ...NAV.filter((g) => g.id === "impostazioni")] : m.fatturazione ? NAV : NAV.filter((g) => g.id === "impostazioni");
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [pw, setPw] = useState(false);
  const off = menuOff(company);
  const [openG, toggleG] = useOpenGroups();
  if (compact) {
    return (
      <div className="flex h-full flex-col items-center gap-4 overflow-y-auto px-2 pb-4 pt-16" data-testid="sidebar-compact-content">
        <div className="grid h-9 w-9 place-items-center rounded-lg bg-blue-600 mono text-xs font-medium text-white" title={company?.denominazione}><span className="text-sm font-black">I<span className="text-blue-200">x</span></span></div>
        <nav className="flex flex-col gap-2">
          {nav.filter((g) => !g.mod || m[g.mod]).map((g) => ({ ...g, items: g.items.filter((n) => !off.has(n.id) && (!n.admin || isAdmin(user)) && (!n.accounting || canSend(user)) && (!n.diritto || canAny(user, n.diritto)) && (!n.mod || m[n.mod])) })).filter((g) => g.items.length)
            .map((g, gi) => <NavGroup key={g.id || gi} g={g} onNav={onNav} compact />)}
        </nav>
        <div className="mt-auto flex flex-col items-center gap-1 border-t border-slate-800 pt-3">
          <IconBtn icon={LifeBuoy} label="Guida all'uso" onClick={() => navigate("/guida")} testId="guida-btn" />
          <ThemeBtn iconOnly />
          <IconBtn icon={KeyRound} label="Cambia password" onClick={() => setPw(true)} testId="change-password-btn" />
          <IconBtn icon={LogOut} label="Esci" onClick={async () => { await logout(); navigate("/login"); }} testId="logout-btn" />
        </div>
        <ChangePasswordDialog open={pw} onOpenChange={setPw} />
      </div>
    );
  }
  return (
    <div className="flex h-full flex-col gap-6 overflow-y-auto p-5">
      <Brand />
      <CompanySwitcher onNav={onNav} />
      <AreaSwitch archivio={archivio} onNav={onNav} m={m} />
      <nav className="flex flex-col gap-2">
        {nav.filter((g) => !g.mod || m[g.mod]).map((g, gi) => ({ ...g, items: g.items.filter((n) => !off.has(n.id) && (!n.admin || isAdmin(user)) && (!n.accounting || canSend(user)) && (!n.diritto || canAny(user, n.diritto)) && (!n.mod || m[n.mod])) })).filter((g) => g.items.length).map((g, gi) => {
          const active = g.items.some((n) => path === n.to || path.startsWith(`${n.to}/`));
          const shown = active || !!openG[g.id];
          return <NavGroup key={g.id || gi} g={g} onNav={onNav} shown={shown} active={active} onToggle={() => toggleG(g.id, shown)} />;
        })}
      </nav>
      <div className="mt-auto rounded-xl border border-slate-800 p-3">
        <div className="flex items-center gap-3">
          {user?.picture ? <img src={user.picture} alt="" className="h-8 w-8 rounded-full" /> : <div className="h-8 w-8 rounded-full bg-slate-700" />}
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-white" data-testid="sidebar-user-name">{user?.name}</div>
            <div className="text-[10px] uppercase tracking-wider text-slate-400" data-testid="sidebar-user-role">{user?.role}</div>
          </div>
        </div>
        <button
          data-testid="guida-btn"
          onClick={() => { navigate("/guida"); onNav?.(); }}
          className="mt-3 flex w-full items-center justify-center gap-2 rounded-md border border-slate-700 py-2 text-xs font-medium text-slate-300 transition-colors hover:bg-white/5 hover:text-white"
        >
          <LifeBuoy className="h-3.5 w-3.5" /> Guida all'uso
        </button>
        <ThemeBtn />
        <button
          data-testid="change-password-btn"
          onClick={() => setPw(true)}
          className="mt-2 flex w-full items-center justify-center gap-2 rounded-md border border-slate-700 py-2 text-xs font-medium text-slate-300 transition-colors hover:bg-white/5 hover:text-white"
        >
          <KeyRound className="h-3.5 w-3.5" /> Cambia password
        </button>
        <ChangePasswordDialog open={pw} onOpenChange={setPw} />
        <button
          data-testid="logout-btn"
          onClick={async () => { await logout(); navigate("/login"); }}
          className="mt-2 flex w-full items-center justify-center gap-2 rounded-md border border-slate-700 py-2 text-xs font-medium text-slate-300 transition-colors hover:bg-white/5 hover:text-white"
        >
          <LogOut className="h-3.5 w-3.5" /> Esci
        </button>
      </div>
    </div>
  );
};

const ThemeBtn = ({ iconOnly }) => {
  const [dark, setDark] = useTheme();
  const Icon = dark ? Sun : Moon;
  return (
    <button data-testid={iconOnly ? "theme-toggle-icon" : "theme-toggle-btn"} onClick={() => setDark(!dark)} title={dark ? "Passa al tema chiaro" : "Passa al tema scuro"}
      className={iconOnly ? "rounded-md p-2 text-amber-300 transition-colors hover:bg-white/10" : "mt-2 flex w-full items-center justify-center gap-2 rounded-md border border-slate-700 py-2 text-xs font-medium text-slate-300 transition-colors hover:bg-white/5 hover:text-white"}>
      <Icon className={iconOnly ? "h-4 w-4" : "h-3.5 w-3.5 text-amber-300"} />{!iconOnly && (dark ? "Tema chiaro" : "Tema scuro")}
    </button>
  );
};

const PinBtn = ({ pinned, onClick }) => (
  <button onClick={onClick} title={pinned ? "Barra a scomparsa" : "Fissa la barra"} className="absolute right-3 top-5 z-10 rounded-md p-1.5 text-slate-400 transition-colors hover:bg-white/10 hover:text-white" data-testid="sidebar-pin-btn">
    {pinned ? <PinOff className="h-4 w-4" /> : <Pin className="h-4 w-4" />}
  </button>
);

const CompactBtn = ({ compact, onClick }) => (
  <button onClick={onClick} title={compact ? "Espandi la barra" : "Solo icone"} className={`absolute top-5 z-10 rounded-md p-1.5 text-slate-400 transition-colors hover:bg-white/10 hover:text-white ${compact ? "left-1/2 -translate-x-1/2" : "right-10"}`} data-testid="sidebar-compact-btn">
    {compact ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
  </button>
);

export default function Layout({ children }) {
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(() => localStorage.getItem("nav_pinned") !== "0");
  const [compact, setCompact] = useState(() => localStorage.getItem("nav_compact") === "1");
  const toggleCompact = () => { const n = !compact; setCompact(n); localStorage.setItem("nav_compact", n ? "1" : "0"); };
  const [peek, setPeek] = useState(false);
  const togglePin = () => { const n = !pinned; setPinned(n); setPeek(false); localStorage.setItem("nav_pinned", n ? "1" : "0"); };
  const { company } = useCompany();
  const { user } = useAuth();
  const path = useLocation().pathname;
  const m = mods(company);
  const need = dirittoFor(path);
  if (company && (!pathAllowed(path, m, menuOff(company)) || (need && user && !canAny(user, need)))) return <Navigate to={homeFor(m)} replace />;
  return (
    <div className="min-h-screen bg-slate-50/70">
      {pinned ? (
        <aside className={`fixed inset-y-0 left-0 hidden ${compact ? "w-16" : "w-64"} bg-slate-900 transition-[width] duration-200 lg:block print:!hidden`} data-testid="sidebar-fixed">
          <CompactBtn compact={compact} onClick={toggleCompact} />
          {!compact && <PinBtn pinned onClick={togglePin} />}
          <SideContent compact={compact} />
        </aside>
      ) : (
        <div className="hidden lg:block print:!hidden" onMouseLeave={() => setPeek(false)}>
          <div className="fixed inset-y-0 left-0 z-40 flex w-12 flex-col items-center bg-slate-900 pt-5" onMouseEnter={() => setPeek(true)} data-testid="sidebar-rail">
            <button onClick={() => setPeek(true)} className="rounded-lg p-2 text-slate-300 transition-colors hover:bg-white/10 hover:text-white" title="Apri il menu" data-testid="sidebar-peek-btn"><Menu className="h-5 w-5" /></button>
          </div>
          <aside className={`fixed inset-y-0 left-0 z-50 w-64 bg-slate-900 shadow-2xl transition-transform duration-200 ${peek ? "translate-x-0" : "-translate-x-full"}`} data-testid="sidebar-floating">
            <PinBtn pinned={false} onClick={togglePin} />
            <SideContent onNav={() => setPeek(false)} />
          </aside>
        </div>
      )}
      <header className="sticky top-0 z-40 flex items-center justify-between bg-slate-900 px-4 py-3 lg:hidden print:hidden">
        <Brand />
        <div className="flex items-center gap-2"><ThemeBtn iconOnly /><button data-testid="mobile-menu-btn" onClick={() => setOpen(true)} className="text-white"><Menu /></button></div>
      </header>
      {open && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-72 bg-slate-900">
            <button data-testid="mobile-menu-close" onClick={() => setOpen(false)} className="absolute right-4 top-5 text-slate-400"><X className="h-5 w-5" /></button>
            <SideContent onNav={() => setOpen(false)} />
          </div>
        </div>
      )}
      <main className={`${pinned ? (compact ? "lg:pl-16" : "lg:pl-64") : "lg:pl-12"} print:!pl-0`}>
        <FiscalBanner />
        <div className="mx-auto max-w-7xl px-4 pb-20 pt-6 sm:px-6 lg:px-10 lg:py-10">{children}</div>
      </main>
      <UpdateBanner />
      <HelpButton />
    </div>
  );
}

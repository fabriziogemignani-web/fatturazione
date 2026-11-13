import { useState } from "react";
import { NavLink, Navigate, useNavigate, useLocation } from "react-router-dom";
import { Send, LifeBuoy, History, Stamp, Wallet, LayoutDashboard, FileText, Users2, Building2, ShieldCheck, LogOut, Menu, X, Package, Building, ListOrdered, CalendarClock, Inbox, CalendarMinus, BookOpenCheck, BookOpen, Calculator, Receipt, KeyRound, Archive, UploadCloud, FileInput, FileOutput, Contact, FileArchive, Landmark, TrendingUp, Warehouse, BookText, FileSpreadsheet, Scale, ListTree, Lock, Mail, Percent, Vault, Truck, FileStack, Banknote } from "lucide-react";
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
    { to: "/invio-sdi", label: "Invio massivo SDI", icon: Send, id: "invio-sdi", accounting: true },
    { to: "/ddt", label: "Documenti di trasporto", icon: Truck, id: "ddt" },
    { to: "/fatturazione-differita", label: "Fatturazione differita", icon: FileStack, id: "fatturazione-differita" },
    { to: "/registro", label: "Registro numerazione", icon: ListOrdered, id: "registro" },
    { to: "/scadenzario", label: "Scadenzario clienti", icon: CalendarClock, id: "scadenzario" },
    { to: "/riba", label: "Effetti Ri.Ba.", icon: Banknote, id: "riba", accounting: true },
    { to: "/comunicazioni", label: "Comunicazioni ai clienti", icon: Mail, id: "comunicazioni" },
  ] },
  { title: "Acquisti", id: "passive", mod: "fatture_passive", items: [
    { to: "/passive", label: "Fatture ricevute", icon: Inbox, id: "passive" },
    { to: "/scadenzario-fornitori", label: "Scadenzario fornitori", icon: CalendarMinus, id: "scadenzario-fornitori" },
    { to: "/pagamenti-fornitori", label: "Pagamenti fornitori", icon: Wallet, id: "pagamenti-fornitori", accounting: true },
  ] },
  { title: "Fisco e IVA", id: "iva", items: [
    { to: "/registro-iva-vendite", label: "Registro IVA vendite", icon: BookOpen, id: "registro-iva-vendite", mod: "fatture_attive" },
    { to: "/registro-iva-acquisti", label: "Registro IVA acquisti", icon: BookOpenCheck, id: "registro-iva-acquisti", mod: "fatture_passive" },
    { to: "/liquidazione-iva", label: "Liquidazione IVA", icon: Calculator, id: "liquidazione-iva" },
    { to: "/bolli-virtuali", label: "Bolli virtuali", icon: Stamp, id: "bolli-virtuali", mod: "fatture_attive" },
    { to: "/storico-f24", label: "Storico versamenti F24", icon: History, id: "storico-f24" },
    { to: "/ritenute", label: "Ritenute d'acconto", icon: Percent, id: "ritenute", mod: "fatture_passive" },
    { to: "/corrispettivi", label: "Corrispettivi", icon: Receipt, id: "corrispettivi", mod: "corrispettivi" },
    { to: "/esportazione", label: "Export commercialista", icon: FileArchive, id: "esportazione", accounting: true },
    { to: "/conservazione", label: "Conservazione documenti", icon: Vault, id: "conservazione" },
  ] },
  { title: "Contabilità generale", id: "contabilita", mod: "contabilita", items: [
    { to: "/contabilita/prima-nota", label: "Prima nota e giornale", icon: BookText, id: "prima-nota" },
    { to: "/contabilita/registrazione-veloce", label: "Registrazione veloce", icon: Calculator, id: "registrazione-veloce", accounting: true },
    { to: "/contabilita/mastrini", label: "Schede contabili", icon: FileSpreadsheet, id: "mastrini" },
    { to: "/contabilita/bilancio", label: "Bilancio di verifica", icon: Scale, id: "bilancio" },
    { to: "/contabilita/chiusura", label: "Chiusura esercizio", icon: Lock, id: "chiusura" },
    { to: "/contabilita/piano-conti", label: "Piano dei conti e tabelle", icon: ListTree, id: "piano-conti", diritto: "tabelle_contabili" },
  ] },
  { title: "Tesoreria", id: "tesoreria", items: [
    { to: "/riconciliazione", label: "Riconciliazione bancaria", icon: Landmark, id: "riconciliazione" },
    { to: "/previsione-cassa", label: "Previsione di cassa", icon: TrendingUp, id: "previsione-cassa" },
  ] },
  { title: "Magazzino", id: "magazzino-group", items: [
    { to: "/magazzino", label: "Giacenze e movimenti", icon: Warehouse, id: "magazzino", diritto: "articoli_magazzino" },
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
  <div className="flex items-center gap-3 px-2">
    <div className="h-9 w-9 rounded-lg bg-blue-600 grid place-items-center mono text-xs font-medium text-white">FE</div>
    <div>
      <div className="text-sm font-bold tracking-tight text-white">Fatturazione</div>
      <div className="text-[10px] uppercase tracking-[0.2em] text-slate-400">Elettronica SDI</div>
    </div>
  </div>
);

const SideContent = ({ onNav }) => {
  const { company } = useCompany();
  const m = mods(company);
  const path = useLocation().pathname;
  const archivio = path.startsWith("/archivio") || (!m.fatturazione && m.archivio && !path.startsWith("/impostazioni") && !path.startsWith("/aziende") && !path.startsWith("/utenti"));
  const nav = archivio ? [...NAV_ARCHIVIO, ...NAV.filter((g) => g.id === "impostazioni")] : m.fatturazione ? NAV : NAV.filter((g) => g.id === "impostazioni");
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [pw, setPw] = useState(false);
  const off = menuOff(company);
  return (
    <div className="flex h-full flex-col gap-6 overflow-y-auto p-5">
      <Brand />
      <CompanySwitcher onNav={onNav} />
      <AreaSwitch archivio={archivio} onNav={onNav} m={m} />
      <nav className="flex flex-col gap-4">
        {nav.filter((g) => !g.mod || m[g.mod]).map((g, gi) => ({ ...g, items: g.items.filter((n) => !off.has(n.id) && (!n.admin || isAdmin(user)) && (!n.accounting || canSend(user)) && (!n.diritto || canAny(user, n.diritto)) && (!n.mod || m[n.mod])) })).filter((g) => g.items.length).map((g, gi) => (
          <div key={g.id || gi} className="flex flex-col gap-1" data-testid={g.id ? `nav-group-${g.id}` : undefined}>
            {g.title && <div className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">{g.title}</div>}
            {g.items.map(({ to, label, icon: Icon, id, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={onNav}
            data-testid={`nav-${id}`}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                isActive ? "bg-white/10 text-white" : "text-slate-400 hover:bg-white/5 hover:text-white"
              }`
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
            ))}
          </div>
        ))}
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

export default function Layout({ children }) {
  const [open, setOpen] = useState(false);
  const { company } = useCompany();
  const { user } = useAuth();
  const path = useLocation().pathname;
  const m = mods(company);
  const need = dirittoFor(path);
  if (company && (!pathAllowed(path, m, menuOff(company)) || (need && user && !canAny(user, need)))) return <Navigate to={homeFor(m)} replace />;
  return (
    <div className="min-h-screen bg-slate-50/70">
      <aside className="fixed inset-y-0 left-0 hidden w-64 bg-slate-900 lg:block print:!hidden">
        <SideContent />
      </aside>
      <header className="sticky top-0 z-40 flex items-center justify-between bg-slate-900 px-4 py-3 lg:hidden print:hidden">
        <Brand />
        <button data-testid="mobile-menu-btn" onClick={() => setOpen(true)} className="text-white"><Menu /></button>
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
      <main className="lg:pl-64 print:!pl-0">
        <FiscalBanner />
        <div className="mx-auto max-w-7xl px-4 pb-20 pt-6 sm:px-6 lg:px-10 lg:py-10">{children}</div>
      </main>
      <UpdateBanner />
      <HelpButton />
    </div>
  );
}

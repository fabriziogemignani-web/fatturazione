import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { LayoutDashboard, FileText, Users2, Building2, ShieldCheck, LogOut, Menu, X, Package } from "lucide-react";
import { useAuth, isAdmin } from "@/context/AuthContext";

const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard, id: "dashboard" },
  { to: "/fatture", label: "Fatture", icon: FileText, id: "fatture" },
  { to: "/anagrafiche", label: "Clienti e fornitori", icon: Users2, id: "anagrafiche" },
  { to: "/articoli", label: "Articoli e servizi", icon: Package, id: "articoli" },
  { to: "/impostazioni", label: "Dati azienda", icon: Building2, id: "impostazioni" },
  { to: "/utenti", label: "Utenti", icon: ShieldCheck, id: "utenti", admin: true },
];

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
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <div className="flex h-full flex-col gap-8 p-5">
      <Brand />
      <nav className="flex flex-col gap-1">
        {NAV.filter((n) => !n.admin || isAdmin(user)).map(({ to, label, icon: Icon, id }) => (
          <NavLink
            key={to}
            to={to}
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
          data-testid="logout-btn"
          onClick={async () => { await logout(); navigate("/login"); }}
          className="mt-3 flex w-full items-center justify-center gap-2 rounded-md border border-slate-700 py-2 text-xs font-medium text-slate-300 transition-colors hover:bg-white/5 hover:text-white"
        >
          <LogOut className="h-3.5 w-3.5" /> Esci
        </button>
      </div>
    </div>
  );
};

export default function Layout({ children }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="min-h-screen bg-slate-50/70">
      <aside className="fixed inset-y-0 left-0 hidden w-64 bg-slate-900 lg:block">
        <SideContent />
      </aside>
      <header className="sticky top-0 z-40 flex items-center justify-between bg-slate-900 px-4 py-3 lg:hidden">
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
      <main className="lg:pl-64">
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-10 lg:py-10">{children}</div>
      </main>
    </div>
  );
}

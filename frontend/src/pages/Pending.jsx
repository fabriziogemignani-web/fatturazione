import { useNavigate } from "react-router-dom";
import { Clock, XCircle } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

export default function Pending() {
  const { user, logout, checkAuth } = useAuth();
  const navigate = useNavigate();
  const rejected = user?.status === "rejected";
  const Icon = rejected ? XCircle : Clock;
  return (
    <div className="grid min-h-screen place-items-center bg-slate-50 p-6">
      <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-8 shadow-sm fade-up" data-testid="pending-screen">
        <Icon className={`h-8 w-8 ${rejected ? "text-rose-600" : "text-amber-600"}`} />
        <h1 className="mt-4 text-2xl font-bold tracking-tight text-slate-900">{rejected ? "Accesso negato" : "In attesa di approvazione"}</h1>
        <p className="mt-2 text-sm text-slate-600">
          {rejected
            ? "Un amministratore ha rifiutato la tua richiesta di accesso."
            : `Ciao ${user?.name || ""}, il tuo account (${user?.email}) è stato registrato. Un amministratore deve approvarlo prima che tu possa accedere ai dati.`}
        </p>
        <div className="mt-6 flex gap-2">
          <button data-testid="pending-refresh-btn" onClick={checkAuth} className="rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800">Verifica di nuovo</button>
          <button data-testid="pending-logout-btn" onClick={async () => { await logout(); navigate("/login"); }} className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">Esci</button>
        </div>
      </div>
    </div>
  );
}

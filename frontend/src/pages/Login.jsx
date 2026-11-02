import { Navigate } from "react-router-dom";
import { FileCode2, ShieldCheck, Send } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { EmailAuthForm } from "@/components/EmailAuthForm";

const FEATURES = [
  [FileCode2, "XML FatturaPA 1.2", "File pronti per lo SDI, con nome conforme."],
  [Send, "Invio tramite intermediario", "Stato di consegna e scarti sempre sotto controllo."],
  [ShieldCheck, "Accesso approvato", "Solo i collaboratori autorizzati entrano."],
];

export default function Login() {
  const { user, loading } = useAuth();
  if (!loading && user) return <Navigate to="/dashboard" replace />;

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="relative hidden flex-col justify-between overflow-hidden bg-slate-900 p-12 text-white lg:flex grid-bg">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-lg bg-blue-600 mono text-sm">FE</div>
          <span className="text-sm font-semibold tracking-tight">Fatturazione Elettronica</span>
        </div>
        <div className="max-w-md fade-up">
          <div className="mono text-xs text-emerald-400">&lt;FatturaElettronica versione="FPR12"&gt;</div>
          <h2 className="mt-4 text-4xl font-extrabold leading-tight tracking-tight">Emetti, trasmetti e archivia le tue fatture elettroniche.</h2>
          <div className="mt-10 space-y-5">
            {FEATURES.map(([Icon, t, d]) => (
              <div key={t} className="flex gap-4">
                <div className="grid h-9 w-9 shrink-0 place-items-center rounded-md border border-slate-700"><Icon className="h-4 w-4 text-blue-400" /></div>
                <div>
                  <div className="text-sm font-semibold">{t}</div>
                  <div className="text-sm text-slate-400">{d}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="mono text-xs text-slate-500">Sistema di Interscambio · Agenzia delle Entrate</div>
      </div>
      <div className="flex items-center justify-center bg-slate-50 p-6">
        <div className="w-full max-w-sm fade-up">
          <div className="text-xs font-medium uppercase tracking-wider text-slate-500">Area riservata</div>
          <h1 className="mt-2 text-3xl font-extrabold tracking-tight text-slate-900">Accedi</h1>
          <p className="mt-2 text-sm text-slate-600">Accedi con email e password. I nuovi utenti devono essere approvati da un amministratore.</p>
          <div className="mt-8"><EmailAuthForm /></div>
        </div>
      </div>
    </div>
  );
}

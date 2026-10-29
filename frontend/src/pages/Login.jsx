import { Navigate } from "react-router-dom";
import { FileCode2, ShieldCheck, Send } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

const FEATURES = [
  [FileCode2, "XML FatturaPA 1.2", "File pronti per lo SDI, con nome conforme."],
  [Send, "Invio tramite intermediario", "Stato di consegna e scarti sempre sotto controllo."],
  [ShieldCheck, "Accesso approvato", "Solo i collaboratori autorizzati entrano."],
];

export default function Login() {
  const { user, loading } = useAuth();
  if (!loading && user) return <Navigate to="/dashboard" replace />;

  const login = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/dashboard";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

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
          <p className="mt-2 text-sm text-slate-600">Usa il tuo account Google aziendale. I nuovi utenti devono essere approvati da un amministratore.</p>
          <button
            data-testid="google-login-btn"
            onClick={login}
            className="mt-8 flex w-full items-center justify-center gap-3 rounded-lg bg-slate-900 px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-slate-800"
          >
            <svg className="h-4 w-4" viewBox="0 0 48 48"><path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3 0 5.8 1.1 7.9 3l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z"/><path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3 0 5.8 1.1 7.9 3l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"/><path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z"/><path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C36.9 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z"/></svg>
            Accedi con Google
          </button>
        </div>
      </div>
    </div>
  );
}

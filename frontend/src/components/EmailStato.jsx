import { CheckCircle2, AlertTriangle, LogIn } from "lucide-react";

const TIPO = { invito: "Invito", reset: "Reset password", benvenuto: "Benvenuto" };
const dt = (s) => (s ? new Date(s).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "");

export const EmailStato = ({ u }) => {
  const e = u.last_email;
  const log = (u.email_log || []).slice().reverse().map((x) => `${dt(x.at)} · ${TIPO[x.tipo] || x.tipo}${x.azienda ? ` (${x.azienda})` : ""}: ${x.ok ? `inviata${x.via === "smtp" ? " con SMTP aziendale" : ""}` : `non inviata – ${x.errore}`}`).join("\n");
  return (
    <div className="space-y-1 text-xs" data-testid={`user-email-stato-${u.user_id}`}>
      {e ? (
        <div className={`flex items-start gap-1 ${e.ok ? "text-emerald-700" : "text-rose-700"}`} title={log} data-testid={`user-last-email-${u.user_id}`}>
          {e.ok ? <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" /> : <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />}
          <span>{TIPO[e.tipo] || e.tipo} {e.ok ? "inviata" : "non inviata"} il {dt(e.at)}{e.ok && e.via === "smtp" ? " (SMTP aziendale)" : ""}</span>
        </div>
      ) : <div className="text-slate-400">Nessuna email inviata</div>}
      <div className={`flex items-center gap-1 ${u.first_login_at ? "text-slate-600" : "text-amber-700"}`} data-testid={`user-first-login-${u.user_id}`}>
        <LogIn className="h-3.5 w-3.5 shrink-0" />
        {u.first_login_at ? <span>Primo accesso {dt(u.first_login_at)}{u.last_login_at && u.last_login_at !== u.first_login_at ? ` · ultimo ${dt(u.last_login_at)}` : ""}</span> : <span>Mai entrato</span>}
      </div>
    </div>
  );
};

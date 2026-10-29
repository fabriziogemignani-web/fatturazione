import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Building2, LogOut } from "lucide-react";
import { useAuth, isAdmin } from "@/context/AuthContext";
import { CompanyProvider, useCompany } from "@/context/CompanyContext";
import { CompanyDialog } from "@/components/CompanyDialog";
import { Button } from "@/components/ui/button";

const NoCompany = () => {
  const { user, logout } = useAuth();
  const { reload, setCurrent } = useCompany();
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const admin = isAdmin(user);
  return (
    <div className="grid min-h-screen place-items-center bg-slate-50 p-6">
      <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-8 shadow-sm fade-up" data-testid="no-company-screen">
        <Building2 className="h-8 w-8 text-blue-600" />
        <h1 className="mt-4 text-2xl font-bold tracking-tight text-slate-900">{admin ? "Crea la prima azienda" : "Nessuna azienda assegnata"}</h1>
        <p className="mt-2 text-sm text-slate-600">
          {admin ? "Per iniziare a fatturare crea un'azienda emittente. Potrai aggiungerne altre e assegnarle agli utenti." : "Un amministratore deve assegnarti almeno un'azienda prima che tu possa lavorare."}
        </p>
        <div className="mt-6 flex gap-2">
          {admin && <Button onClick={() => setOpen(true)} data-testid="first-company-btn">Crea azienda</Button>}
          <Button variant="outline" onClick={reload} data-testid="no-company-refresh-btn">Verifica di nuovo</Button>
          <Button variant="ghost" onClick={async () => { await logout(); navigate("/login"); }} data-testid="no-company-logout-btn"><LogOut className="h-4 w-4" /></Button>
        </div>
      </div>
      <CompanyDialog open={open} onOpenChange={setOpen} onSaved={async (c) => { setCurrent(c.id); await reload(); navigate("/impostazioni"); }} />
    </div>
  );
};

const Gate = ({ children }) => {
  const { companies, current } = useCompany();
  if (!companies) return <div className="grid min-h-screen place-items-center text-sm text-slate-500">Caricamento…</div>;
  if (!current) return <NoCompany />;
  return <div key={current} className="contents">{children}</div>;
};

export const CompanyGate = ({ children }) => (
  <CompanyProvider>
    <Gate>{children}</Gate>
  </CompanyProvider>
);

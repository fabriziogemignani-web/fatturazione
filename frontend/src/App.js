import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import Pending from "@/pages/Pending";
import Dashboard from "@/pages/Dashboard";
import Invoices from "@/pages/Invoices";
import InvoiceEditor from "@/pages/InvoiceEditor";
import InvoicePrint from "@/pages/InvoicePrint";
import Parties from "@/pages/Parties";
import Settings from "@/pages/Settings";
import Users from "@/pages/Users";
import Articles from "@/pages/Articles";
import Companies from "@/pages/Companies";
import Registro from "@/pages/Registro";
import Scadenzario from "@/pages/Scadenzario";
import Passive from "@/pages/Passive";
import PassiveDetail from "@/pages/PassiveDetail";
import RegistroIvaAcquisti from "@/pages/RegistroIvaAcquisti";
import LiquidazioneIva from "@/pages/LiquidazioneIva";
import Esportazione from "@/pages/Esportazione";
import Riconciliazione from "@/pages/Riconciliazione";
import Corrispettivi from "@/pages/Corrispettivi";
import ArchDashboard from "@/pages/archivio/ArchDashboard";
import ArchUpload from "@/pages/archivio/ArchUpload";
import ArchInvoices from "@/pages/archivio/ArchInvoices";
import ArchInvoiceDetail from "@/pages/archivio/ArchInvoiceDetail";
import ArchAnagrafiche from "@/pages/archivio/ArchAnagrafiche";
import ArchAnagraficaDetail from "@/pages/archivio/ArchAnagraficaDetail";
import { CompanyGate } from "@/components/CompanyGate";
import ForgotPassword from "@/pages/ForgotPassword";
import ResetPassword from "@/pages/ResetPassword";

const Loader = () => (
  <div className="min-h-screen grid place-items-center text-slate-500 text-sm" data-testid="app-loading">Caricamento…</div>
);

const Protected = ({ children, admin }) => {
  const { user, loading } = useAuth();
  if (loading) return <Loader />;
  if (!user) return <Navigate to="/login" replace />;
  if (user.status !== "approved") return <Pending />;
  if (admin && user.role !== "admin") return <Navigate to="/dashboard" replace />;
  return children;
};

const inLayout = (el, admin) => (
  <Protected admin={admin}>
    <CompanyGate>
      <Layout>{el}</Layout>
    </CompanyGate>
  </Protected>
);

function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/password-dimenticata" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/articoli" element={inLayout(<Articles />)} />
      <Route path="/dashboard" element={inLayout(<Dashboard />)} />
      <Route path="/fatture" element={inLayout(<Invoices />)} />
      <Route path="/fatture/nuova" element={inLayout(<InvoiceEditor />)} />
      <Route path="/fatture/:id" element={inLayout(<InvoiceEditor />)} />
      <Route path="/fatture/:id/stampa" element={<Protected><CompanyGate><InvoicePrint /></CompanyGate></Protected>} />
      <Route path="/scadenzario" element={inLayout(<Scadenzario key="att" />)} />
      <Route path="/scadenzario-fornitori" element={inLayout(<Scadenzario key="pas" passive />)} />
      <Route path="/registro-iva-acquisti" element={inLayout(<RegistroIvaAcquisti key="acq" />)} />
      <Route path="/registro-iva-vendite" element={inLayout(<RegistroIvaAcquisti key="ven" vendite />)} />
      <Route path="/liquidazione-iva" element={inLayout(<LiquidazioneIva />)} />
      <Route path="/esportazione" element={inLayout(<Esportazione />)} />
      <Route path="/riconciliazione" element={inLayout(<Riconciliazione />)} />
      <Route path="/corrispettivi" element={inLayout(<Corrispettivi />)} />
      <Route path="/archivio" element={inLayout(<ArchDashboard />)} />
      <Route path="/archivio/carica" element={inLayout(<ArchUpload />)} />
      <Route path="/archivio/fatture/:id" element={inLayout(<ArchInvoiceDetail />)} />
      <Route path="/archivio/anagrafiche" element={inLayout(<ArchAnagrafiche />)} />
      <Route path="/archivio/anagrafiche/:id" element={inLayout(<ArchAnagraficaDetail />)} />
      <Route path="/archivio/:tipo" element={inLayout(<ArchInvoices />)} />
      <Route path="/passive" element={inLayout(<Passive />)} />
      <Route path="/passive/:id" element={inLayout(<PassiveDetail />)} />
      <Route path="/registro" element={inLayout(<Registro />)} />
      <Route path="/aziende" element={inLayout(<Companies />, true)} />
      <Route path="/anagrafiche" element={inLayout(<Parties />)} />
      <Route path="/impostazioni" element={inLayout(<Settings />)} />
      <Route path="/utenti" element={inLayout(<Users />, true)} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRouter />
        <Toaster position="bottom-right" richColors />
      </AuthProvider>
    </BrowserRouter>
  );
}

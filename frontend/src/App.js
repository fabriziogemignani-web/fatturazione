import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import AuthCallback from "@/pages/AuthCallback";
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
  const location = useLocation();
  if (location.hash?.includes("session_id=")) return <AuthCallback />;
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
      <Route path="/scadenzario" element={inLayout(<Scadenzario />)} />
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

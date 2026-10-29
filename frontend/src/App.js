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
    <Layout>{el}</Layout>
  </Protected>
);

function AppRouter() {
  const location = useLocation();
  if (location.hash?.includes("session_id=")) return <AuthCallback />;
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/dashboard" element={inLayout(<Dashboard />)} />
      <Route path="/fatture" element={inLayout(<Invoices />)} />
      <Route path="/fatture/nuova" element={inLayout(<InvoiceEditor />)} />
      <Route path="/fatture/:id" element={inLayout(<InvoiceEditor />)} />
      <Route path="/fatture/:id/stampa" element={<Protected><InvoicePrint /></Protected>} />
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
        <Toaster position="top-right" richColors />
      </AuthProvider>
    </BrowserRouter>
  );
}

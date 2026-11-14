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
import Ritenute from "@/pages/Ritenute";
import Conservazione from "@/pages/Conservazione";
import Ddt from "@/pages/Ddt";
import Riba from "@/pages/Riba";
import BolliVirtuali from "@/pages/BolliVirtuali";
import StoricoF24 from "@/pages/StoricoF24";
import Guida from "@/pages/Guida";
import InvioSdi from "@/pages/InvioSdi";
import CodiciTributo from "@/pages/CodiciTributo";
import PagamentiFornitori from "@/pages/PagamentiFornitori";
import Ordini from "@/pages/Ordini";
import Bem from "@/pages/Bem";
import DdtEditor from "@/pages/DdtEditor";
import FatturazioneDifferita from "@/pages/FatturazioneDifferita";
import FirmaDdtPublic from "@/pages/FirmaDdtPublic";
import Importazione from "@/pages/Importazione";
import Esportazione from "@/pages/Esportazione";
import Riconciliazione from "@/pages/Riconciliazione";
import PrevisioneCassa from "@/pages/PrevisioneCassa";
import Magazzino from "@/pages/Magazzino";
import Corrispettivi from "@/pages/Corrispettivi";
import PrimaNota from "@/pages/contabilita/PrimaNota";
import RegistrazioneVeloce from "@/pages/contabilita/RegistrazioneVeloce";
import Mastrini from "@/pages/contabilita/Mastrini";
import Bilancio from "@/pages/contabilita/Bilancio";
import PianoConti from "@/pages/contabilita/PianoConti";
import Chiusura from "@/pages/contabilita/Chiusura";
import Comunicazioni from "@/pages/Comunicazioni";
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
      <Route path="/firma-ddt/:token" element={<FirmaDdtPublic />} />
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
      <Route path="/ritenute" element={inLayout(<Ritenute />)} />
      <Route path="/conservazione" element={inLayout(<Conservazione />)} />
      <Route path="/ddt" element={inLayout(<Ddt />)} />
      <Route path="/riba" element={inLayout(<Riba />)} />
      <Route path="/bolli-virtuali" element={inLayout(<BolliVirtuali />)} />
      <Route path="/storico-f24" element={inLayout(<StoricoF24 />)} />
      <Route path="/guida" element={inLayout(<Guida />)} />
      <Route path="/invio-sdi" element={inLayout(<InvioSdi />)} />
      <Route path="/codici-tributo" element={inLayout(<CodiciTributo />)} />
      <Route path="/pagamenti-fornitori" element={inLayout(<PagamentiFornitori />)} />
      <Route path="/ordini-clienti" element={inLayout(<Ordini tipo="cliente" key="cliente" />)} />
      <Route path="/ordini-fornitori" element={inLayout(<Ordini tipo="fornitore" key="fornitore" />)} />
      <Route path="/bem" element={inLayout(<Bem />)} />
      <Route path="/ddt/nuovo" element={inLayout(<DdtEditor />)} />
      <Route path="/ddt/:id" element={inLayout(<DdtEditor />)} />
      <Route path="/fatturazione-differita" element={inLayout(<FatturazioneDifferita />)} />
      <Route path="/esportazione" element={inLayout(<Esportazione />)} />
      <Route path="/riconciliazione" element={inLayout(<Riconciliazione />)} />
      <Route path="/previsione-cassa" element={inLayout(<PrevisioneCassa />)} />
      <Route path="/magazzino" element={inLayout(<Magazzino />)} />
      <Route path="/corrispettivi" element={inLayout(<Corrispettivi />)} />
      <Route path="/contabilita/prima-nota" element={inLayout(<PrimaNota />)} />
      <Route path="/contabilita/registrazione-veloce" element={inLayout(<RegistrazioneVeloce />)} />
      <Route path="/contabilita/mastrini" element={inLayout(<Mastrini />)} />
      <Route path="/contabilita/bilancio" element={inLayout(<Bilancio />)} />
      <Route path="/contabilita/piano-conti" element={inLayout(<PianoConti />)} />
      <Route path="/contabilita/chiusura" element={inLayout(<Chiusura />)} />
      <Route path="/comunicazioni" element={inLayout(<Comunicazioni />)} />
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
      <Route path="/importazione" element={inLayout(<Importazione />, true)} />
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

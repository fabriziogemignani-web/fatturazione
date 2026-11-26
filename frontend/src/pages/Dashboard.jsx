import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { SdiPanel } from "@/components/SdiPanel";
import { ScadenzePanel } from "@/components/ScadenzePanel";
import { CorrispettiviPanel } from "@/components/CorrispettiviPanel";
import { SdiSchedulePanel } from "@/components/SdiSchedulePanel";
import { BankPanel } from "@/components/BankPanel";
import { MagazzinoPanel } from "@/components/MagazzinoPanel";
import { ScadenzeFiscaliPanel } from "@/components/ScadenzeFiscaliPanel";
import { RitenutePanel } from "@/components/RitenutePanel";
import { RitenuteF24Avviso } from "@/components/RitenuteF24Avviso";
import { IntentiPanel } from "@/components/Intenti";
import { RibaPanel } from "@/components/RibaPanel";
import { PagamentiPanel } from "@/components/PagamentiPanel";
import { RiquadriSezioni } from "@/components/RiquadriSezioni";
import { ComunicazioniPanel } from "@/components/ComunicazioniPanel";
import { SistemaAvvisi } from "@/components/SistemaAvvisi";
import { OrdiniPanel } from "@/components/OrdiniPanel";
import { FornitoriRevisionePanel } from "@/components/FornitoriRevisionePanel";
import { AiDubbiePanel } from "@/components/AiDubbiePanel";
import { AiCreditiBanner } from "@/components/AiCreditiBanner";
import { RateizzazioniPanel } from "@/components/RateizzazioniPanel";
import { useCompany } from "@/context/CompanyContext";
import { mods, vede } from "@/lib/moduli";
import { TopBar } from "@/components/dashboard/TopBar";
import { KpiRow } from "@/components/dashboard/KpiRow";
import { CashFlowWidget } from "@/components/dashboard/CashFlowWidget";
import { SdiDonut } from "@/components/dashboard/SdiDonut";
import { SottoscortaWidget, ScadenzeWidget } from "@/components/dashboard/TablesWidgets";
import { FatturatoMensile, UltimeFatture } from "@/components/dashboard/Legacy";
import { WidgetPicker } from "@/components/dashboard/WidgetPicker";
import { ProposteOrdini } from "@/components/ProposteOrdini";
import { AutoSdiAvviso } from "@/components/dashboard/AutoSdiAvviso";

const SPAN = { full: "lg:col-span-12", wide: "lg:col-span-7", narrow: "lg:col-span-5", half: "lg:col-span-6" };

const registro = (co, m, d) => [
  { id: "kpi", label: "Indicatori principali", span: "full", ok: true, el: (p) => <KpiRow periodo={p} m={{ ...m, magazzino: vede(co, "magazzino") }} /> },
  { id: "ordini_proposti", label: "Nuovi ordini a fornitore da confermare", span: "full", ok: m.fatture_passive && vede(co, "ordini-fornitori") && vede(co, "magazzino"), el: () => <ProposteOrdini compatto /> },
  { id: "auto_sdi", label: "Fatture registrate in automatico da verificare", span: "full", ok: m.fatture_passive && m.contabilita && vede(co, "prima-nota"), el: () => <AutoSdiAvviso /> },
  { id: "cashflow", label: "Flusso di cassa e previsioni", span: "wide", ok: vede(co, "situazione-finanziaria"), el: () => <CashFlowWidget /> },
  { id: "sdi", label: "Stato fatturazione e SDI", span: "narrow", ok: m.fatture_attive, el: () => <SdiDonut counts={d?.counts} /> },
  { id: "sottoscorta", label: "Alert scorte magazzino", span: "half", ok: vede(co, "magazzino"), el: () => <SottoscortaWidget /> },
  { id: "scadenze", label: "Scadenze fatture imminenti", span: "half", ok: m.fatture_attive && vede(co, "scadenzario"), el: () => <ScadenzeWidget /> },
  { id: "avvisi", label: "Avvisi di sistema e crediti IA", span: "full", ok: true, el: () => <><AiCreditiBanner />{m.fatture_passive && vede(co, "ritenute") && <RitenuteF24Avviso />}<SistemaAvvisi /></> },
  { id: "riquadri", label: "Riquadri di riepilogo per sezione", span: "full", ok: true, el: () => <RiquadriSezioni /> },
  { id: "fatturato_mensile", label: "Fatturato mensile", span: "wide", ok: m.fatture_attive, el: () => d && <FatturatoMensile d={d} /> },
  { id: "ultime_fatture", label: "Ultime fatture", span: "narrow", ok: m.fatture_attive, el: () => d && <UltimeFatture d={d} /> },
  { id: "scadenze_fiscali", label: "Scadenze fiscali e IVA", span: "half", ok: vede(co, "liquidazione-iva") || vede(co, "passive"), el: () => <ScadenzeFiscaliPanel /> },
  { id: "rateizzazioni", label: "Rate rateizzazioni, finanziamenti e leasing", span: "half", ok: vede(co, "rateizzazioni") || vede(co, "finanziamenti"), el: () => <RateizzazioniPanel /> },
  { id: "notifiche_sdi", label: "Notifiche SDI", span: "half", ok: m.fatture_attive && vede(co, "fatture"), el: () => d && <SdiPanel d={d} /> },
  { id: "invii_sdi", label: "Invii SDI programmati", span: "half", ok: m.fatture_attive || m.fatture_passive, el: () => <SdiSchedulePanel /> },
  { id: "banca", label: "Riconciliazione bancaria", span: "half", ok: vede(co, "riconciliazione"), el: () => <BankPanel /> },
  { id: "magazzino", label: "Riepilogo magazzino", span: "half", ok: vede(co, "magazzino"), el: () => <MagazzinoPanel /> },
  { id: "scadenzario_clienti", label: "Scadenzario clienti", span: "half", ok: m.fatture_attive && vede(co, "scadenzario"), el: () => <ScadenzePanel /> },
  { id: "scadenzario_fornitori", label: "Scadenzario fornitori", span: "half", ok: m.fatture_passive && vede(co, "scadenzario-fornitori"), el: () => <ScadenzePanel passive /> },
  { id: "pagamenti", label: "Pagamenti fornitori", span: "half", ok: m.fatture_passive && vede(co, "pagamenti-fornitori"), el: () => <PagamentiPanel /> },
  { id: "ritenute", label: "Ritenute d'acconto", span: "half", ok: m.fatture_passive && vede(co, "ritenute"), el: () => <RitenutePanel /> },
  { id: "riba", label: "Ri.Ba.", span: "half", ok: m.fatture_attive && m.contabilita && vede(co, "riba"), el: () => <RibaPanel /> },
  { id: "ordini", label: "Ordini clienti e fornitori", span: "half", ok: (m.fatture_attive && vede(co, "ordini-clienti")) || (m.fatture_passive && vede(co, "ordini-fornitori")),
    el: () => <OrdiniPanel clienti={m.fatture_attive && vede(co, "ordini-clienti")} fornitori={m.fatture_passive && vede(co, "ordini-fornitori")} /> },
  { id: "comunicazioni", label: "Comunicazioni ai clienti", span: "half", ok: m.fatture_attive && vede(co, "comunicazioni"), el: () => <ComunicazioniPanel /> },
  { id: "intenti", label: "Dichiarazioni d'intento", span: "half", ok: m.fatture_attive, el: () => <IntentiPanel /> },
  { id: "corrispettivi", label: "Corrispettivi", span: "half", ok: m.corrispettivi && vede(co, "corrispettivi"), el: () => <CorrispettiviPanel /> },
  { id: "fornitori_revisione", label: "Fornitori da verificare", span: "half", ok: m.fatture_passive && vede(co, "passive"), el: () => <FornitoriRevisionePanel /> },
  { id: "ai_dubbie", label: "Fatture dubbie dall'IA", span: "half", ok: m.fatture_passive && vede(co, "passive"), el: () => <AiDubbiePanel /> },
];
const DEFAULT = ["auto_sdi", "ordini_proposti", "kpi", "cashflow", "sdi", "sottoscorta", "scadenze"];
const NUOVI = [["ordini_proposti", "_op"], ["auto_sdi", "_as"]];
const MARK = NUOVI.map((x) => x[1]);

export default function Dashboard() {
  const co = useCompany().company;
  const m = mods(co);
  const [d, setD] = useState(null);
  const [periodo, setPeriodo] = useState(() => localStorage.getItem("dash-periodo") || "mese");
  const [layout, setLayout] = useState(null);
  const [pick, setPick] = useState(false);
  useEffect(() => { api.get("/dashboard").then(({ data }) => setD(data)).catch(() => {}); }, []);
  useEffect(() => {
    api.get("/dashboard/layout").then(({ data }) => {
      const w = data.widgets;
      const add = w ? NUOVI.filter(([id, mk]) => !w.includes(id) && !w.includes(mk)) : [];
      const vis = w ? [...add.map((x) => x[0]), ...w.filter((x) => !MARK.includes(x))] : DEFAULT;
      if (add.length) api.put("/dashboard/layout", { widgets: [...vis, ...MARK] }).catch(() => {});
      setLayout(vis);
    }).catch(() => setLayout(DEFAULT));
  }, [co?.id]);
  useEffect(() => { localStorage.setItem("dash-periodo", periodo); }, [periodo]);
  const reg = registro(co, m, d);
  const disponibili = reg.filter((w) => w.ok);
  const save = (w) => api.put("/dashboard/layout", { widgets: [...w.filter((x) => !MARK.includes(x)), ...MARK] }).then(({ data }) => { setLayout(data.widgets.filter((x) => !MARK.includes(x))); toast.success("Dashboard salvata"); }).catch((e) => toast.error(errMsg(e)));
  const attivi = (layout || []).map((id) => disponibili.find((w) => w.id === id)).filter(Boolean);
  return (
    <div className="dash-pro" data-testid="dashboard-pro">
      <TopBar periodo={periodo} setPeriodo={setPeriodo} onPersonalizza={() => setPick(true)} nuova={m.fatture_attive && vede(co, "fatture")} />
      {!layout ? <div className="text-sm text-slate-500">Caricamento…</div> : (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-12" data-testid="dashboard-panels">
          {attivi.length === 0 && <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-500 lg:col-span-12" data-testid="dash-vuota">Dashboard vuota: usa “Personalizza” per aggiungere i riquadri.</div>}
          {attivi.map((w) => <div key={w.id} className={`min-w-0 ${SPAN[w.span]} [&>*]:h-full empty:hidden`} data-testid={`widget-${w.id}`}>{w.el(periodo)}</div>)}
        </div>
      )}
      <WidgetPicker open={pick} onClose={() => setPick(false)} attivi={layout || DEFAULT} disponibili={disponibili} onSave={save} onReset={() => save(DEFAULT)} />
    </div>
  );
}

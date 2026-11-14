import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ClipboardList, ShoppingCart } from "lucide-react";
import { api } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";

const oggi = () => new Date().toISOString().slice(0, 10);
const aperti = (rows) => rows.filter((o) => ["aperto", "parziale"].includes(o.status));
const giorni = (d) => Math.round((new Date(oggi()) - new Date(d)) / 86400000);
const residuo = (o) => Math.round(o.lines.reduce((s, l) => s + Math.max(l.quantita - (l.evasa || 0), 0), 0) * 100) / 100;

const Riga = ({ o, tipo }) => {
  const late = o.data_consegna && o.data_consegna < oggi();
  return (
    <li className="flex justify-between gap-2" data-testid={`ordini-panel-${tipo}-row-${o.id}`}>
      <Link to={`/ordini-${tipo === "cliente" ? "clienti" : "fornitori"}`} className="min-w-0 break-words hover:underline">
        <span className="mono font-semibold">{o.numero_display}</span> · {o.party.denominazione}
        {o.status === "parziale" && <span className="ml-1 text-amber-700">(parziale)</span>}
        <span className={late ? "ml-1 font-semibold text-rose-700" : "ml-1 text-slate-500"}>{o.data_consegna ? `consegna ${fmtDate(o.data_consegna)}${late ? ` · ${giorni(o.data_consegna)} gg di ritardo` : ""}` : "senza data di consegna"}</span>
      </Link>
      <span className="shrink-0 text-slate-600">residuo {residuo(o)} · {fmtEUR(o.imponibile)}</span>
    </li>
  );
};

const Box = ({ tipo, titolo, icon: Icon, righe, vuoto, extra }) => (
  <div className="rounded-xl border border-slate-200 bg-white shadow-sm" data-testid={`ordini-panel-${tipo}`}>
    <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
      <div className="flex items-center gap-2"><Icon className="h-4 w-4 text-blue-600" /><h3 className="font-semibold text-slate-900">{titolo}</h3></div>
      <b data-testid={`ordini-panel-${tipo}-count`}>{righe.length}</b>
    </div>
    <div className="px-5 py-4">
      {righe.length === 0 ? <p className="text-xs text-slate-500" data-testid={`ordini-panel-${tipo}-empty`}>{vuoto}</p> : (
        <ul className="space-y-1 text-xs">
          {righe.slice(0, 8).map((o) => <Riga key={o.id} o={o} tipo={tipo} />)}
          {righe.length > 8 && <li className="text-slate-400">e altri {righe.length - 8}…</li>}
        </ul>
      )}
      {extra}
    </div>
  </div>
);

const ordina = (a, b) => (a.data_consegna || "9999") .localeCompare(b.data_consegna || "9999") || a.data.localeCompare(b.data);

export const OrdiniPanel = ({ clienti, fornitori }) => {
  const [c, setC] = useState(null);
  const [f, setF] = useState(null);
  useEffect(() => {
    if (clienti) api.get("/ordini/cliente").then(({ data }) => setC(aperti(data).sort(ordina))).catch(() => {});
    if (fornitori) api.get("/ordini/fornitore").then(({ data }) => setF(aperti(data).sort(ordina))).catch(() => {});
  }, [clienti, fornitori]);
  if (!c && !f) return null;
  const ritardoF = (f || []).filter((o) => o.data_consegna && o.data_consegna < oggi());
  const inArrivo = (f || []).length - ritardoF.length;
  return (
    <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2" data-testid="ordini-panel">
      {c && <Box tipo="cliente" titolo="Ordini clienti da evadere" icon={ClipboardList} righe={c} vuoto="Nessun ordine cliente da evadere." />}
      {f && <Box tipo="fornitore" titolo="Ordini fornitori in ritardo sulla consegna" icon={ShoppingCart} righe={ritardoF} vuoto="Nessun ordine fornitore in ritardo."
        extra={inArrivo > 0 && <p className="mt-3 text-xs text-slate-500" data-testid="ordini-panel-fornitore-in-arrivo">{inArrivo === 1 ? "1 altro ordine" : `${inArrivo} altri ordini`} in arrivo nei tempi previsti.</p>} />}
    </div>
  );
};

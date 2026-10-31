import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Printer } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const PERIODI = [["anno", "Anno intero"], ["T1", "1° trimestre"], ["T2", "2° trimestre"], ["T3", "3° trimestre"], ["T4", "4° trimestre"],
  ...["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"].map((m, i) => [`M${i + 1}`, m])];

const range = (anno, p) => {
  const end = (m) => new Date(Date.UTC(anno, m, 0)).toISOString().slice(0, 10);
  const pad = (m) => String(m).padStart(2, "0");
  if (p.startsWith("T")) { const q = Number(p[1]); return [`${anno}-${pad(q * 3 - 2)}-01`, end(q * 3)]; }
  if (p.startsWith("M")) { const m = Number(p.slice(1)); return [`${anno}-${pad(m)}-01`, end(m)]; }
  return [`${anno}-01-01`, `${anno}-12-31`];
};

const Totali = ({ d }) => (
  <div className="mt-6 break-inside-avoid rounded-xl border border-slate-200 bg-white p-5 shadow-sm print:shadow-none" data-testid="riva-totali">
    <h3 className="mb-3 font-semibold text-slate-800">Riepilogo per aliquota / natura</h3>
    <table className="w-full max-w-2xl text-sm">
      <thead className="border-b border-slate-200 text-left text-xs uppercase tracking-wider text-slate-500"><tr><th className="py-2">Aliquota / Natura</th><th className="py-2 text-right">Documenti</th><th className="py-2 text-right">Imponibile</th><th className="py-2 text-right">Imposta</th></tr></thead>
      <tbody className="divide-y divide-slate-100">{d.totali.map((v) => (
        <tr key={v.codice} data-testid={`riva-tot-${v.codice}`}><td className="py-2 font-medium">{v.natura ? `Natura ${v.natura}` : `IVA ${v.codice}`}</td><td className="py-2 text-right">{v.documenti}</td><td className="py-2 text-right">{fmtEUR(v.imponibile)}</td><td className="py-2 text-right font-semibold">{fmtEUR(v.imposta)}</td></tr>
      ))}</tbody>
      <tfoot className="border-t-2 border-slate-900 font-bold"><tr><td className="py-2">Totale</td><td /><td className="py-2 text-right" data-testid="riva-imponibile">{fmtEUR(d.imponibile)}</td><td className="py-2 text-right" data-testid="riva-imposta">{fmtEUR(d.imposta)}</td></tr></tfoot>
    </table>
  </div>
);

export default function RegistroIvaAcquisti() {
  const [anno, setAnno] = useState(null);
  const [per, setPer] = useState("anno");
  const [d, setD] = useState(null);
  const y = anno || new Date().getFullYear();
  useEffect(() => {
    const [dal, al] = range(y, per);
    api.get("/registro-iva-acquisti", { params: { anno: y, dal, al } }).then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e)));
  }, [y, per]);
  if (!d) return <div className="text-sm text-slate-500">Caricamento…</div>;
  const [dal, al] = range(y, per);

  return (
    <div>
      <div className="print:hidden">
        <PageHeader eyebrow="Fatture passive" title="Registro IVA acquisti">
          <Select value={String(y)} onValueChange={(v) => setAnno(Number(v))}>
            <SelectTrigger className="w-28 bg-white" data-testid="riva-anno-select"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-white">{d.anni.map((a) => <SelectItem key={a} value={String(a)} data-testid={`riva-anno-${a}`}>{a}</SelectItem>)}</SelectContent>
          </Select>
          <Select value={per} onValueChange={setPer}>
            <SelectTrigger className="w-44 bg-white" data-testid="riva-periodo-select"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-white">{PERIODI.map(([k, l]) => <SelectItem key={k} value={k} data-testid={`riva-periodo-${k}`}>{l}</SelectItem>)}</SelectContent>
          </Select>
          <Button onClick={() => window.print()} data-testid="riva-print-btn"><Printer className="mr-2 h-4 w-4" />Stampa / PDF</Button>
        </PageHeader>
        <p className="-mt-4 mb-4 text-xs text-slate-500">Contiene le fatture ricevute in stato "Registrata", in ordine di protocollo. Il protocollo viene assegnato quando segni la fattura come registrata.</p>
      </div>
      <div className="mb-4 hidden print:block">
        <div className="text-lg font-bold">{d.azienda.denominazione} · P.IVA {d.azienda.partita_iva}</div>
        <div className="text-sm">Registro IVA acquisti dal {fmtDate(dal)} al {fmtDate(al)}</div>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm print:overflow-visible print:shadow-none">
        <table className="w-full text-sm print:text-[10px]" data-testid="riva-table">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr><th className="px-3 py-3 font-medium">Prot.</th><th className="px-3 py-3 font-medium">Data reg.</th><th className="px-3 py-3 font-medium">Documento</th><th className="px-3 py-3 font-medium">Fornitore</th><th className="px-3 py-3 font-medium">Aliquota</th><th className="px-3 py-3 text-right font-medium">Imponibile</th><th className="px-3 py-3 text-right font-medium">Imposta</th><th className="px-3 py-3 text-right font-medium">Totale doc.</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {d.rows.length === 0 && <tr><td colSpan={8} className="px-4 py-10 text-center text-slate-500" data-testid="riva-empty">Nessuna fattura registrata nel periodo</td></tr>}
            {d.rows.map((r) => r.riepilogo.map((x, i) => (
              <tr key={`${r.id}-${i}`} className={i ? "border-t-0" : ""} data-testid={i ? undefined : `riva-row-${r.protocollo}`}>
                {i === 0 ? <>
                  <td className="mono px-3 py-2 font-semibold" rowSpan={r.riepilogo.length}>{r.protocollo}</td>
                  <td className="px-3 py-2" rowSpan={r.riepilogo.length}>{fmtDate(r.data_registrazione)}</td>
                  <td className="px-3 py-2" rowSpan={r.riepilogo.length}><Link to={`/passive/${r.id}`} className="text-blue-600 hover:underline print:text-slate-900">{r.tipo_documento === "TD04" ? "NC " : ""}{r.numero}</Link><div className="text-xs text-slate-500">del {fmtDate(r.data)}</div></td>
                  <td className="px-3 py-2" rowSpan={r.riepilogo.length}>{r.fornitore}<div className="text-xs text-slate-500">{r.partita_iva}</div></td>
                </> : null}
                <td className="px-3 py-2">{x.natura || `${x.aliquota}%`}{r.split_payment && " (split)"}</td>
                <td className="px-3 py-2 text-right">{fmtEUR(x.imponibile)}</td>
                <td className="px-3 py-2 text-right">{fmtEUR(x.imposta)}</td>
                {i === 0 ? <td className="px-3 py-2 text-right font-semibold" rowSpan={r.riepilogo.length}>{fmtEUR(r.totale)}</td> : null}
              </tr>
            )))}
          </tbody>
        </table>
      </div>
      <Totali d={d} />
    </div>
  );
}

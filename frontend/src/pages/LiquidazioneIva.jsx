import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Printer, FileDown } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR } from "@/lib/fe";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { LiquidazioneCoge } from "@/components/coge/LiquidazioneCoge";
import { F24Dialog } from "@/components/F24Dialog";
import { useCompany } from "@/context/CompanyContext";
import { mods } from "@/lib/moduli";

const Cell = ({ v, tone = "", testId }) => <td className={`px-3 py-2.5 text-right ${tone}`} data-testid={testId}>{v ? fmtEUR(v) : "—"}</td>;

export default function LiquidazioneIva() {
  const now = new Date().getFullYear();
  const [anno, setAnno] = useState(now);
  const { company } = useCompany();
  const [per, setPer] = useState(company?.periodicita_iva || "mensile");
  const [d, setD] = useState(null);
  const [f24, setF24] = useState(null);
  const coge = mods(company).contabilita;
  useEffect(() => {
    api.get("/liquidazione-iva", { params: { anno, periodicita: per } }).then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e)));
  }, [anno, per]);
  if (!d) return <div className="text-sm text-slate-500">Caricamento…</div>;
  const anni = Array.from({ length: 5 }, (_, i) => now - i);
  const quarterly = per === "trimestrale";

  return (
    <div>
      <div className="print:hidden">
        <PageHeader eyebrow="IVA" title="Liquidazione IVA">
          <Select value={String(anno)} onValueChange={(v) => setAnno(Number(v))}>
            <SelectTrigger className="w-28 bg-white" data-testid="liq-anno-select"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-white">{anni.map((a) => <SelectItem key={a} value={String(a)} data-testid={`liq-anno-${a}`}>{a}</SelectItem>)}</SelectContent>
          </Select>
          <Select value={per} onValueChange={setPer}>
            <SelectTrigger className="w-40 bg-white" data-testid="liq-periodicita-select"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-white"><SelectItem value="mensile" data-testid="liq-mensile">Mensile</SelectItem><SelectItem value="trimestrale" data-testid="liq-trimestrale">Trimestrale</SelectItem></SelectContent>
          </Select>
          <Button onClick={() => window.print()} data-testid="liq-print-btn"><Printer className="mr-2 h-4 w-4" />Stampa / PDF</Button>
        </PageHeader>
        <p className="-mt-4 mb-4 text-xs text-slate-500">IVA a debito dalle fatture emesse e inviate (per data documento, esclusa l'IVA in split payment) e dai corrispettivi giornalieri meno IVA a credito dalle fatture ricevute registrate (per data di registrazione). Il credito si riporta al periodo successivo.{quarterly && " Per i trimestrali si aggiungono gli interessi dell'1% sui primi tre trimestri."} Gli importi fino a 25,82 € non si versano e passano al periodo successivo. Il credito di fine anno precedente viene riportato a gennaio. L'IVA delle fatture ricevute in reverse charge (N6.x), integrata all'aliquota scelta in registrazione, entra sia a debito sia a credito (detrazione piena). Prospetto indicativo: verifica sempre con il tuo consulente.</p>
      </div>
      <div className="mb-4 hidden print:block">
        <div className="text-lg font-bold">{d.azienda.denominazione} · P.IVA {d.azienda.partita_iva}</div>
        <div className="text-sm">Prospetto liquidazione IVA {per} · anno {d.anno}</div>
      </div>
      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-3 print:hidden">
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div className="text-xs uppercase tracking-wider text-slate-500">Totale da versare {d.anno}</div><div className="mt-1 text-xl font-bold text-rose-700" data-testid="liq-totale-versare">{fmtEUR(d.totale_versare)}</div></div>
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div className="text-xs uppercase tracking-wider text-slate-500">Credito a fine periodo</div><div className="mt-1 text-xl font-bold text-emerald-700" data-testid="liq-credito-finale">{fmtEUR(d.credito_finale)}</div></div>
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div className="text-xs uppercase tracking-wider text-slate-500">Credito da anno precedente</div><div className="mt-1 text-xl font-bold text-slate-700" data-testid="liq-credito-prec-anno">{fmtEUR(d.credito_anno_precedente)}</div></div>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm print:overflow-visible print:shadow-none">
        <table className="w-full text-sm print:text-[10px]" data-testid="liq-table">
          <thead className="border-b border-slate-200 bg-slate-50 text-right text-xs uppercase tracking-wider text-slate-500">
            <tr><th className="px-3 py-3 text-left font-medium">Periodo</th><th className="px-3 py-3 font-medium">IVA vendite</th><th className="px-3 py-3 font-medium">di cui split</th><th className="px-3 py-3 font-medium">IVA corrispettivi</th><th className="px-3 py-3 font-medium">Reverse charge a debito</th><th className="px-3 py-3 font-medium">IVA acquisti (incl. RC)</th><th className="px-3 py-3 font-medium">Credito prec.</th>{quarterly && <th className="px-3 py-3 font-medium">Interessi 1%</th>}<th className="px-3 py-3 font-medium">Da versare</th><th className="px-3 py-3 font-medium">Credito a riporto</th><th className="px-3 py-3 font-medium print:hidden">F24</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {d.periodi.map((p) => (
              <tr key={p.periodo} className={p.da_versare > 0 ? "bg-rose-50/40" : ""} data-testid={`liq-row-${p.periodo}`}>
                <td className="px-3 py-2.5 font-medium text-slate-800">{p.label}<div className="text-[11px] font-normal text-slate-500">{p.documenti_vendite} vendite · {p.documenti_acquisti} acquisti{p.documenti_corrispettivi ? ` · ${p.documenti_corrispettivi} gg corrispettivi` : ""}</div></td>
                <Cell v={p.iva_debito + p.iva_split - p.iva_rc - p.iva_corrispettivi} testId={`liq-vendite-${p.periodo}`} />
                <Cell v={p.iva_split} tone="text-slate-500" />
                <Cell v={p.iva_corrispettivi} tone="text-emerald-700" testId={`liq-corr-${p.periodo}`} />
                <Cell v={p.iva_rc} tone="text-indigo-700" testId={`liq-rc-${p.periodo}`} />
                <Cell v={p.iva_credito} testId={`liq-acquisti-${p.periodo}`} />
                <Cell v={p.credito_precedente} tone="text-emerald-700" />
                {quarterly && <Cell v={p.interessi} />}
                <td className="px-3 py-2.5 text-right font-bold text-rose-700" data-testid={`liq-versare-${p.periodo}`}>{p.da_versare ? fmtEUR(p.da_versare) : p.sotto_soglia ? <span className="text-xs font-medium text-amber-700" data-testid={`liq-soglia-${p.periodo}`}>{fmtEUR(p.saldo + p.interessi + p.debito_precedente)} sotto 25,82 € · rinviato</span> : "—"}{p.debito_precedente > 0 && p.da_versare > 0 && <div className="text-[10px] font-normal text-amber-700">incl. {fmtEUR(p.debito_precedente)} rinviati</div>}</td>
                <Cell v={p.credito_riporto} tone="font-semibold text-emerald-700" testId={`liq-riporto-${p.periodo}`} />
                <td className="px-3 py-2.5 text-right print:hidden">{p.da_versare > 0 && <Button size="sm" variant="outline" onClick={() => setF24({ anno, periodicita: per, periodo: p.periodo })} data-testid={`liq-f24-btn-${p.periodo}`}><FileDown className="mr-1 h-3.5 w-3.5" />F24</Button>}</td>
              </tr>
            ))}
          </tbody>
          <tfoot className="border-t-2 border-slate-900 font-bold"><tr><td className="px-3 py-2.5">Totale anno</td><td className="px-3 py-2.5 text-right">{fmtEUR(d.periodi.reduce((s, p) => s + p.iva_debito + p.iva_split - p.iva_rc - p.iva_corrispettivi, 0))}</td><td className="px-3 py-2.5 text-right">{fmtEUR(d.periodi.reduce((s, p) => s + p.iva_split, 0))}</td><td className="px-3 py-2.5 text-right" data-testid="liq-corr-totale">{fmtEUR(d.periodi.reduce((s, p) => s + p.iva_corrispettivi, 0))}</td><td className="px-3 py-2.5 text-right" data-testid="liq-rc-totale">{fmtEUR(d.periodi.reduce((s, p) => s + p.iva_rc, 0))}</td><td className="px-3 py-2.5 text-right">{fmtEUR(d.periodi.reduce((s, p) => s + p.iva_credito, 0))}</td><td />{quarterly && <td className="px-3 py-2.5 text-right">{fmtEUR(d.periodi.reduce((s, p) => s + p.interessi, 0))}</td>}<td className="px-3 py-2.5 text-right text-rose-700">{fmtEUR(d.totale_versare)}</td><td className="px-3 py-2.5 text-right text-emerald-700">{fmtEUR(d.credito_finale)}</td><td className="print:hidden" /></tr></tfoot>
        </table>
      </div>
      {coge && <LiquidazioneCoge anno={anno} per={per} />}
      <F24Dialog req={f24} onClose={() => setF24(null)} />
    </div>
  );
}

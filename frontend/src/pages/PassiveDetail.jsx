import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, Printer, FileCode, Trash2, Save } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { useAuth, canSend } from "@/context/AuthContext";
import { FieldErrors, useFieldErrors } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { PaymentsPanel } from "@/components/PaymentsPanel";
import { RateCard } from "@/components/RateCard";
import { STATI_REG, StatoReg } from "@/pages/Passive";

const Party = ({ title, p }) => (
  <div className="rounded-lg border border-slate-200 p-4 text-sm">
    <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">{title}</div>
    <div className="font-semibold text-slate-900">{p.denominazione}</div>
    <div className="text-slate-600">{p.indirizzo}<br />{p.cap} {p.comune} {p.provincia && `(${p.provincia})`} {p.nazione}<br />
      {p.partita_iva && <>P.IVA {p.paese_iva || "IT"}{p.partita_iva}<br /></>}{p.codice_fiscale && <>C.F. {p.codice_fiscale}</>}</div>
  </div>
);

const Doc = ({ d, company }) => (
  <div className="rounded-xl border border-slate-200 bg-white p-8 shadow-sm print:border-0 print:p-0 print:shadow-none" data-testid="passive-document">
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4 border-b-2 border-slate-900 pb-4">
      <div><div className="text-xs uppercase tracking-wider text-slate-500">{d.tipo_documento === "TD04" ? "Nota di credito ricevuta" : "Fattura ricevuta"} · {d.tipo_documento}</div>
        <div className="text-2xl font-bold text-slate-900" data-testid="passive-numero">N. {d.numero}</div><div className="text-sm text-slate-600">del {fmtDate(d.data)}</div></div>
    </div>
    <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2"><Party title="Cedente / Prestatore" p={d.fornitore} /><Party title="Cessionario / Committente" p={company} /></div>
    <table className="mb-6 w-full text-sm">
      <thead className="border-y border-slate-200 text-left text-xs uppercase tracking-wider text-slate-500"><tr><th className="p-2">Descrizione</th><th className="p-2 text-right">Q.tà</th><th className="p-2 text-right">Prezzo</th><th className="p-2 text-right">IVA</th><th className="p-2 text-right">Importo</th></tr></thead>
      <tbody>{d.lines.map((l, i) => (
        <tr key={i} className="border-b border-slate-100" data-testid={`passive-line-${i}`}><td className="p-2">{l.descrizione}</td><td className="p-2 text-right">{l.quantita} {l.unita_misura}</td><td className="p-2 text-right">{fmtEUR(l.prezzo_unitario)}</td><td className="p-2 text-right">{l.natura || `${l.aliquota}%`}</td><td className="p-2 text-right font-medium">{fmtEUR(l.prezzo_totale)}</td></tr>
      ))}</tbody>
    </table>
    <div className="flex flex-wrap justify-end">
      <div className="w-full max-w-xs space-y-1 text-sm">
        {d.riepilogo.map((r, i) => <div key={i} className="flex justify-between text-slate-600"><span>Imponibile {r.natura || `${r.aliquota}%`}</span><span>{fmtEUR(r.imponibile)} · IVA {fmtEUR(r.imposta)}</span></div>)}
        {(d.reverse_charge || []).map((r) => <div key={r.natura} className="flex justify-between text-indigo-700" data-testid={`passive-rc-${r.natura}`}><span>Reverse charge {r.natura} · IVA {r.aliquota}%</span><span>{fmtEUR(r.imposta)}</span></div>)}
        <div className="flex justify-between border-t-2 border-slate-900 pt-2 text-base font-bold"><span>Totale documento</span><span data-testid="passive-totale">{fmtEUR(d.totale)}</span></div>
        {d.ritenuta_importo > 0 && <div className="flex justify-between text-slate-600"><span>Ritenuta d'acconto</span><span>- {fmtEUR(d.ritenuta_importo)}</span></div>}
        {d.split_payment && <div className="flex justify-between text-slate-600"><span>IVA split payment</span><span>- {fmtEUR(d.iva)}</span></div>}
        <div className="flex justify-between font-semibold"><span>Netto da pagare</span><span data-testid="passive-netto">{fmtEUR(d.netto)}</span></div>
      </div>
    </div>
    {d.rate.length > 0 && <div className="mt-6 text-xs text-slate-600"><b>Pagamento:</b> {d.rate.map((r) => `${fmtDate(r.scadenza)} ${fmtEUR(r.importo)}${r.iban ? ` · IBAN ${r.iban}` : ""}`).join(" — ")}</div>}
    {d.causale && <p className="mt-2 text-xs text-slate-600"><b>Causale:</b> {d.causale}</p>}
  </div>
);

export default function PassiveDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [d, setD] = useState(null);
  const [company, setCompany] = useState({});
  const [form, setForm] = useState({ note: "", rate: [] });
  const { fail, reset, value } = useFieldErrors();
  const load = () => api.get(`/passive/${id}`).then(({ data }) => { setD(data); setForm({ note: data.note || "", rate: data.rate.map(({ scadenza, importo }) => ({ scadenza, importo })), data: data.data }); }).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); api.get("/company").then(({ data }) => setCompany(data)).catch(() => {}); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  const patch = async (body, msg) => {
    reset();
    try { await api.patch(`/passive/${id}`, body); toast.success(msg); load(); } catch (e) { fail(e); }
  };
  const remove = async () => {
    if (!window.confirm("Eliminare questa fattura ricevuta?")) return;
    try { await api.delete(`/passive/${id}`); toast.success("Eliminata"); navigate("/passive"); } catch (e) { toast.error(errMsg(e)); }
  };
  const downloadXml = async () => {
    try {
      const { data } = await api.get(`/passive/${id}/xml`, { responseType: "blob" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(data);
      a.download = `${d.fornitore.denominazione}_${d.numero}.xml`.replace(/[^A-Za-z0-9._-]+/g, "_");
      a.click();
    } catch (e) { toast.error(errMsg(e)); }
  };

  if (!d) return <div className="text-sm text-slate-500">Caricamento…</div>;
  const edit = canSend(user);
  return (
    <FieldErrors value={value}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3 print:hidden">
        <Link to="/passive" className="inline-flex items-center gap-1 text-sm text-slate-600 hover:text-slate-900" data-testid="passive-back-link"><ArrowLeft className="h-4 w-4" />Fatture ricevute</Link>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={downloadXml} data-testid="passive-xml-btn"><FileCode className="mr-2 h-4 w-4" />XML</Button>
          <Button variant="outline" onClick={() => window.print()} data-testid="passive-print-btn"><Printer className="mr-2 h-4 w-4" />Stampa / PDF</Button>
          {edit && <Button variant="ghost" className="text-rose-600" onClick={remove} data-testid="passive-delete-btn"><Trash2 className="h-4 w-4" /></Button>}
        </div>
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="space-y-6 lg:col-span-8"><Doc d={d} company={company} />
          {edit && d.tipo_documento !== "TD04" && <div className="print:hidden">
            <RateCard form={form} setForm={setForm} netto={d.netto} />
            <Button className="mt-2" variant="outline" onClick={() => patch({ rate: form.rate.map((r) => ({ ...r, importo: Number(r.importo) })) }, "Scadenze aggiornate")} data-testid="passive-save-rate-btn"><Save className="mr-2 h-4 w-4" />Salva scadenze</Button>
          </div>}
        </div>
        <div className="space-y-6 print:hidden lg:col-span-4">
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm" data-testid="passive-reg-card">
            <h3 className="mb-3 flex items-center justify-between text-lg font-semibold text-slate-800">Registrazione <StatoReg s={d.stato_reg} testId="passive-stato" /></h3>
            {edit && d.stato_reg !== "registrata" && (
              <label className="mb-3 flex items-center gap-2 text-xs text-slate-600">Data registrazione
                <input type="date" className="rounded-md border border-slate-200 px-2 py-1 text-xs" min={d.data} max={new Date().toISOString().slice(0, 10)} value={form.data_reg || ""} onChange={(e) => setForm({ ...form, data_reg: e.target.value })} data-testid="passive-data-reg-input" />
                <span className="text-slate-400">(vuota = oggi)</span>
              </label>
            )}
            {edit && d.stato_reg !== "registrata" && d.riepilogo.some((r) => (r.natura || "").startsWith("N6")) && (
              <label className="mb-3 flex items-center gap-2 text-xs text-slate-600" data-field="aliquota_rc">Aliquota IVA reverse charge
                <select className="rounded-md border border-slate-200 px-2 py-1 text-xs" value={form.aliquota_rc ?? 22} onChange={(e) => setForm({ ...form, aliquota_rc: Number(e.target.value) })} data-testid="passive-aliquota-rc-select">
                  {[22, 10, 5, 4].map((a) => <option key={a} value={a}>{a}%</option>)}
                </select>
              </label>
            )}
            {edit && <div className="mb-3 flex flex-wrap gap-2">{Object.entries(STATI_REG).map(([k, [l]]) => (
              <Button key={k} size="sm" variant={d.stato_reg === k ? "default" : "outline"} onClick={() => patch({ stato_reg: k, ...(k === "registrata" && form.data_reg ? { data_registrazione: form.data_reg } : {}), ...(k === "registrata" && form.aliquota_rc ? { aliquota_rc: form.aliquota_rc } : {}) }, `Segnata come ${l.toLowerCase()}`)} data-testid={`passive-set-${k}`}>{l}</Button>
            ))}</div>}
            <Textarea disabled={!edit} rows={3} maxLength={1000} placeholder="Note (es. protocollo registrazione, motivo contestazione)" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} data-testid="passive-note-input" />
            {edit && <Button size="sm" className="mt-2" variant="outline" onClick={() => patch({ note: form.note }, "Note salvate")} data-testid="passive-save-note-btn">Salva note</Button>}
            <p className="mt-3 text-xs text-slate-500">Ricevuta il {fmtDate(d.ricevuta_at)} · {d.origine === "upload" ? `file ${d.file_name}` : "SDI (simulato)"}</p>
            {d.protocollo && <p className="mt-1 text-xs font-semibold text-emerald-700" data-testid="passive-protocollo">Protocollo n. {d.protocollo}/{d.anno_registrazione} del {fmtDate(d.data_registrazione)}</p>}
            {d.stato_reg === "contestata" && <p className="mt-2 text-xs text-rose-700">Le fatture contestate sono escluse dallo scadenzario fornitori.</p>}
          </div>
          {d.tipo_documento !== "TD04" && d.stato_reg !== "contestata" && <PaymentsPanel key={`${d.id}-${d.rate.length}-${d.scadenza}`} invoiceId={d.id} kind="passive" />}
        </div>
      </div>
    </FieldErrors>
  );
}

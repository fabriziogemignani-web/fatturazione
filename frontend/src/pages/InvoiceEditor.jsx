import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { toast } from "sonner";
import { Plus, Save, Send, RefreshCw, FileCode2, Download, Printer, Trash2, ArrowLeft } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { computeTotals, fmtEUR, fmtDateTime, today, TIPI_DOC, MODALITA } from "@/lib/fe";
import { useAuth, canSend } from "@/context/AuthContext";
import { PageHeader, StatusBadge, Field } from "@/components/Common";
import { LineRow } from "@/components/LineRow";
import { PartyDialog } from "@/components/PartyDialog";
import { XmlDialog, downloadXml } from "@/components/XmlDialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const NEW_LINE = { descrizione: "", quantita: 1, prezzo_unitario: "", aliquota: 22, natura: null };
const EMPTY = { tipo_documento: "TD01", data: today(), party_id: "", lines: [NEW_LINE], causale: "", modalita_pagamento: "MP05", scadenza: "", note: "" };

const Sel = ({ value, onChange, options, testId, disabled, placeholder }) => (
  <Select value={value || undefined} onValueChange={onChange} disabled={disabled}>
    <SelectTrigger className="bg-white" data-testid={testId}><SelectValue placeholder={placeholder} /></SelectTrigger>
    <SelectContent className="bg-white">
      {options.map(([k, l]) => <SelectItem key={k} value={k} data-testid={`${testId}-option-${k}`}>{l}</SelectItem>)}
    </SelectContent>
  </Select>
);

const Card = ({ title, children }) => (
  <div className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm">
    {title && <h3 className="mb-4 text-lg font-semibold text-slate-800">{title}</h3>}
    {children}
  </div>
);

const Row = ({ label, value, strong, testId }) => (
  <div className={`flex justify-between py-1.5 ${strong ? "border-t border-slate-200 pt-3 text-lg font-extrabold text-slate-900" : "text-sm text-slate-600"}`}>
    <span>{label}</span><span data-testid={testId}>{value}</span>
  </div>
);

export default function InvoiceEditor() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [form, setForm] = useState(EMPTY);
  const [inv, setInv] = useState(null);
  const [clients, setClients] = useState([]);
  const [busy, setBusy] = useState(false);
  const [xmlOpen, setXmlOpen] = useState(false);
  const [partyOpen, setPartyOpen] = useState(false);

  useEffect(() => {
    api.get("/parties", { params: { tipo: "cliente" } }).then(({ data }) => setClients(data));
  }, []);

  useEffect(() => {
    if (!id) { setInv(null); setForm(EMPTY); return; }
    api.get(`/invoices/${id}`).then(({ data }) => {
      setInv(data);
      setForm({ ...EMPTY, ...data, lines: data.lines.map((l) => ({ ...l })) });
    }).catch(() => navigate("/fatture"));
  }, [id, navigate]);

  const locked = inv && !["bozza", "scartata"].includes(inv.status);
  const totals = useMemo(() => computeTotals(form.lines), [form.lines]);
  const client = clients.find((c) => c.id === form.party_id) || inv?.cliente;
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const setLine = (i, l) => setForm((f) => ({ ...f, lines: f.lines.map((x, j) => (j === i ? l : x)) }));

  const run = async (fn, ok) => {
    setBusy(true);
    try { const r = await fn(); if (ok) toast.success(ok); return r; }
    catch (e) { toast.error(errMsg(e)); }
    finally { setBusy(false); }
  };

  const save = () => run(async () => {
    const body = { ...form, lines: form.lines.map((l) => ({ ...l, quantita: Number(l.quantita), prezzo_unitario: Number(l.prezzo_unitario || 0) })) };
    const { data } = id ? await api.put(`/invoices/${id}`, body) : await api.post("/invoices", body);
    setInv(data);
    if (!id) navigate(`/fatture/${data.id}`, { replace: true });
    return data;
  }, "Fattura salvata");

  const action = (path, ok) => run(async () => { const { data } = await api.post(`/invoices/${id}/${path}`); setInv(data); setForm((f) => ({ ...f, ...data })); return data; }, ok);

  const send = async () => {
    if (!locked) { const saved = await save(); if (!saved) return; }
    const r = await action("send", "Fattura trasmessa all'intermediario (simulato)");
    if (r) toast.info("Usa \"Aggiorna stato SDI\" per ricevere l'esito");
  };

  const remove = () => run(async () => { await api.delete(`/invoices/${id}`); navigate("/fatture"); }, "Bozza eliminata");

  return (
    <div>
      <Link to="/fatture" className="mb-4 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900" data-testid="back-to-invoices"><ArrowLeft className="h-4 w-4" />Fatture</Link>
      <PageHeader eyebrow={inv ? `Fattura ${inv.numero_display}` : "Nuova fattura"} title={inv ? `N. ${inv.numero_display}` : "Crea fattura"}>
        {inv && <StatusBadge status={inv.status} testId="editor-status-pill" />}
      </PageHeader>
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-12">
        <div className="space-y-6 lg:col-span-8">
          <Card title="Documento">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <Field label="Tipo documento"><Sel disabled={locked} value={form.tipo_documento} onChange={(v) => set("tipo_documento", v)} options={TIPI_DOC} testId="invoice-tipo-select" /></Field>
              <Field label="Data"><Input disabled={locked} type="date" value={form.data} onChange={(e) => set("data", e.target.value)} data-testid="invoice-date-input" /></Field>
              <Field label="Numero"><Input disabled value={inv?.numero_display || "Automatico"} data-testid="invoice-number-display" /></Field>
            </div>
          </Card>
          <Card title="Cliente (cessionario/committente)">
            <div className="flex gap-2">
              <div className="flex-1"><Sel disabled={locked} value={form.party_id} onChange={(v) => set("party_id", v)} options={clients.map((c) => [c.id, c.denominazione])} testId="invoice-client-select" placeholder="Seleziona un cliente" /></div>
              {!locked && <Button variant="outline" onClick={() => setPartyOpen(true)} data-testid="invoice-new-client-btn"><Plus className="h-4 w-4" /></Button>}
            </div>
            {client && (
              <div className="mt-4 grid grid-cols-2 gap-3 rounded-lg bg-slate-50 p-4 text-xs sm:grid-cols-4" data-testid="invoice-client-details">
                <div><div className="text-slate-500">P.IVA</div><div className="mono">{client.partita_iva || "—"}</div></div>
                <div><div className="text-slate-500">Cod. destinatario</div><div className="mono">{client.codice_destinatario}</div></div>
                <div><div className="text-slate-500">PEC</div><div className="truncate">{client.pec || "—"}</div></div>
                <div><div className="text-slate-500">Sede</div><div className="truncate">{client.comune} {client.provincia && `(${client.provincia})`}</div></div>
              </div>
            )}
          </Card>
          <Card title="Righe">
            <div className="space-y-3">
              {form.lines.map((l, i) => (
                <LineRow key={i} idx={i} line={l} onChange={setLine} disabled={locked} canRemove={form.lines.length > 1} onRemove={(j) => set("lines", form.lines.filter((_, k) => k !== j))} />
              ))}
            </div>
            {!locked && <Button variant="outline" className="mt-4" onClick={() => set("lines", [...form.lines, { ...NEW_LINE }])} data-testid="add-line-btn"><Plus className="mr-2 h-4 w-4" />Aggiungi riga</Button>}
          </Card>
          <Card title="Pagamento e note">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Modalità di pagamento"><Sel disabled={locked} value={form.modalita_pagamento} onChange={(v) => set("modalita_pagamento", v)} options={MODALITA} testId="invoice-payment-select" /></Field>
              <Field label="Scadenza"><Input disabled={locked} type="date" value={form.scadenza || ""} onChange={(e) => set("scadenza", e.target.value)} data-testid="invoice-due-input" /></Field>
              <Field label="Causale" className="sm:col-span-2"><Textarea disabled={locked} value={form.causale || ""} onChange={(e) => set("causale", e.target.value)} data-testid="invoice-causale-input" /></Field>
            </div>
          </Card>
        </div>
        <div className="space-y-6 lg:col-span-4">
          <div className="lg:sticky lg:top-6 space-y-6">
            <Card title="Riepilogo">
              {totals.riepilogo.map((r) => (
                <Row key={`${r.aliquota}${r.natura}`} label={r.aliquota ? `Imponibile IVA ${r.aliquota}%` : `Imponibile ${r.natura}`} value={fmtEUR(r.imponibile)} />
              ))}
              <Row label="Totale imponibile" value={fmtEUR(totals.imponibile)} testId="summary-imponibile" />
              <Row label="Totale IVA" value={fmtEUR(totals.iva)} testId="summary-iva" />
              <Row label="Totale documento" value={fmtEUR(totals.totale)} strong testId="summary-totale" />
            </Card>
            <Card title="Azioni">
              <div className="grid gap-2">
                {!locked && <Button onClick={save} disabled={busy} data-testid="save-invoice-btn"><Save className="mr-2 h-4 w-4" />Salva</Button>}
                {inv && !locked && canSend(user) && <Button onClick={send} disabled={busy} className="bg-blue-600 hover:bg-blue-700" data-testid="send-sdi-btn"><Send className="mr-2 h-4 w-4" />{inv.status === "scartata" ? "Reinvia allo SDI" : "Invia allo SDI"}</Button>}
                {inv?.status === "inviata" && <Button onClick={() => action("refresh", "Esito SDI aggiornato")} disabled={busy} className="bg-emerald-600 hover:bg-emerald-700" data-testid="refresh-sdi-btn"><RefreshCw className="mr-2 h-4 w-4" />Aggiorna stato SDI</Button>}
                {inv && (
                  <div className="grid grid-cols-3 gap-2">
                    <Button variant="outline" onClick={() => setXmlOpen(true)} data-testid="preview-xml-btn" title="Anteprima XML"><FileCode2 className="h-4 w-4" /></Button>
                    <Button variant="outline" onClick={() => downloadXml(id)} data-testid="download-xml-btn" title="Scarica XML"><Download className="h-4 w-4" /></Button>
                    <Button variant="outline" asChild data-testid="print-pdf-btn" title="Stampa PDF"><Link to={`/fatture/${id}/stampa`}><Printer className="h-4 w-4" /></Link></Button>
                  </div>
                )}
                {inv?.status === "bozza" && <Button variant="ghost" className="text-rose-600 hover:bg-rose-50 hover:text-rose-700" onClick={remove} disabled={busy} data-testid="delete-invoice-btn"><Trash2 className="mr-2 h-4 w-4" />Elimina bozza</Button>}
                {inv && !canSend(user) && !locked && <p className="text-xs text-slate-500">L'invio allo SDI è riservato ad Admin e Contabile.</p>}
              </div>
              {inv?.sdi_message && <p className={`mt-4 rounded-md p-3 text-xs ${inv.status === "scartata" ? "bg-rose-50 text-rose-700" : "bg-slate-50 text-slate-600"}`} data-testid="sdi-message">{inv.sdi_message}</p>}
            </Card>
            {inv?.sdi_history?.length > 0 && (
              <Card title="Cronologia SDI">
                <ol className="space-y-4 border-l border-slate-200 pl-4" data-testid="sdi-history">
                  {[...inv.sdi_history].reverse().map((h, i) => (
                    <li key={i} className="relative">
                      <span className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full bg-slate-300" />
                      <StatusBadge status={h.status} testId={`history-status-${i}`} />
                      <div className="mt-1 text-xs text-slate-600">{h.message}</div>
                      <div className="mono text-[10px] text-slate-400">{fmtDateTime(h.at)}</div>
                    </li>
                  ))}
                </ol>
              </Card>
            )}
          </div>
        </div>
      </div>
      {inv && <XmlDialog open={xmlOpen} onOpenChange={setXmlOpen} invoiceId={id} />}
      <PartyDialog open={partyOpen} onOpenChange={setPartyOpen} tipo="cliente" onSaved={(p) => { setClients((c) => [...c, p]); set("party_id", p.id); }} />
    </div>
  );
}

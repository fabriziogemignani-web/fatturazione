import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams, Link } from "react-router-dom";
import { toast } from "sonner";
import { Plus, Save, Send, RefreshCw, FileCode2, Download, Printer, Trash2, ArrowLeft, FileMinus, Mail } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { computeTotals, fmtEUR, fmtDate, fmtDateTime, today, TIPI_DOC, MODALITA } from "@/lib/fe";
import { useAuth, canSend } from "@/context/AuthContext";
import { PageHeader, StatusBadge, Field, FieldErrors, useFieldErrors } from "@/components/Common";
import { LineRow } from "@/components/LineRow";
import { PartyDialog } from "@/components/PartyDialog";
import { XmlDialog, downloadXml } from "@/components/XmlDialog";
import { CassaRitenutaCard, defaultCassa, defaultRitenuta } from "@/components/CassaRitenuta";
import { CreditNoteDialog, partialLines } from "@/components/CreditNoteDialog";
import { PaCard } from "@/components/PaCard";
import { RateCard } from "@/components/RateCard";
import { BankSelect } from "@/components/BankSelect";
import { PaymentsPanel } from "@/components/PaymentsPanel";
import { CortesiaDialog } from "@/components/CortesiaDialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PlafondHint } from "@/components/Intenti";
import { AutofatturaView } from "@/components/AutofatturaView";
import { BolloCard, BOLLO_LINE, bolloState } from "@/components/BolloCard";

const NEW_LINE = { descrizione: "", quantita: 1, prezzo_unitario: "", aliquota: 22, natura: null, sconto: "" };
const EMPTY = { tipo_documento: "TD01", data: today(), party_id: "", lines: [NEW_LINE], causale: "", modalita_pagamento: "MP05", scadenza: "", note: "", cassa: null, ritenuta: null, rif_tipo: "ordine", rif_documento: "", rif_data: "", cig: "", cup: "", rate: [], banca_id: null };

const exempt = (line, client) => (client?.natura_default ? { ...line, aliquota: 0, natura: client.natura_default } : line);
const unexempt = (line, prev) => (prev?.natura_default && Number(line.aliquota) === 0 && line.natura === prev.natura_default ? { ...line, aliquota: 22, natura: null } : line);
const num = (o, keys) => (o ? { ...o, ...Object.fromEntries(keys.map((k) => [k, Number(o[k] || 0)])) } : null);
const SENT = ["inviata", "consegnata", "mancata_consegna"];

const creditFrom = (o, righe, perc) => ({
  ...EMPTY, tipo_documento: "TD04", party_id: o.party_id, fattura_collegata_id: o.id,
  lines: partialLines(o.lines, righe, perc).map((l) => ({ descrizione: l.descrizione, quantita: l.quantita, unita_misura: l.unita_misura, prezzo_unitario: l.prezzo_unitario, aliquota: l.aliquota, natura: l.natura, sconto: l.sconto || "", bollo: !!l.bollo })),
  cassa: o.cassa, ritenuta: o.ritenuta, modalita_pagamento: o.modalita_pagamento,
  causale: `${righe || perc ? `Storno parziale${perc ? ` ${perc}%` : ""}` : "Storno"} fattura n. ${o.numero_display} del ${o.data.split("-").reverse().join("/")}`,
});

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
    <span>{label}</span><span className="whitespace-nowrap pl-3" data-testid={testId}>{value}</span>
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
  const { fail, reset, value: errValue } = useFieldErrors();
  const [xmlOpen, setXmlOpen] = useState(false);
  const [partyOpen, setPartyOpen] = useState(false);
  const [articles, setArticles] = useState([]);
  const [company, setCompany] = useState({});
  const [params] = useSearchParams();
  const fromId = params.get("da");
  const [sentInvoices, setSentInvoices] = useState([]);

  useEffect(() => {
    api.get("/invoices").then(({ data }) => setSentInvoices(data.filter((i) => i.tipo_documento !== "TD04" && SENT.includes(i.status))));
  }, []);

  useEffect(() => {
    api.get("/articles").then(({ data }) => setArticles(data));
    api.get("/company").then(({ data }) => {
      setCompany(data);
      if (!id && !fromId) setForm((f) => ({ ...f, cassa: data.cassa_tipo ? defaultCassa(data) : null, ritenuta: data.ritenuta_tipo ? defaultRitenuta(data) : null }));
    });
  }, [id, fromId]);

  useEffect(() => {
    if (id || !fromId) return;
    const righe = params.get("righe") ? params.get("righe").split(",").map(Number) : null;
    const perc = params.get("perc") ? Number(params.get("perc")) : null;
    api.get(`/invoices/${fromId}`).then(({ data }) => setForm(creditFrom(data, righe, perc))).catch(() => toast.error("Fattura da stornare non trovata"));
  }, [id, fromId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    api.get("/parties", { params: { tipo: "cliente" } }).then(({ data }) => setClients(data));
  }, []);

  useEffect(() => {
    if (!id) {
      setInv(null);
      if (!fromId) setForm({ ...EMPTY, ...(params.get("tipo") === "TD04" ? { tipo_documento: "TD04" } : {}), ...(params.get("numero") ? { numero: params.get("numero"), data: params.get("data") || EMPTY.data } : {}) });
      return;
    }
    api.get(`/invoices/${id}`).then(({ data }) => {
      setInv(data);
      setForm({ ...EMPTY, ...data, lines: data.lines.map((l) => ({ ...l })) });
    }).catch(() => { toast.error("Fattura non trovata nell'azienda attiva"); navigate("/fatture"); });
  }, [id, navigate]); // eslint-disable-line react-hooks/exhaustive-deps

  const isNC = form.tipo_documento === "TD04";
  const docName = isNC ? "Nota di credito" : "Fattura";
  const linkable = sentInvoices.filter((i) => i.party_id === form.party_id);
  const [linkedInfo, setLinkedInfo] = useState(null);
  const [stornoOpen, setStornoOpen] = useState(false);
  const [cortesiaOpen, setCortesiaOpen] = useState(false);

  useEffect(() => {
    if (!form.fattura_collegata_id) { setLinkedInfo(null); return; }
    api.get(`/invoices/${form.fattura_collegata_id}`).then(({ data }) => {
      const own = (data.note_credito || []).find((n) => n.id === id && n.status !== "scartata");
      setLinkedInfo({ ...data, residuo: Math.round((data.residuo_stornabile + (own ? own.totale : 0)) * 100) / 100 });
    }).catch(() => setLinkedInfo(null));
  }, [form.fattura_collegata_id, id]);

  const locked = inv && !["bozza", "scartata"].includes(inv.status);
  const rejected = inv?.status === "scartata";
  const client = clients.find((c) => c.id === form.party_id) || inv?.cliente;
  const isPA = !!client?.pubblica_amministrazione;
  const split = isPA && !!client?.split_payment;
  const baseLines = useMemo(() => form.lines.filter((l) => !l.bollo), [form.lines]);
  const bollo = bolloState(baseLines, form.bollo, client);
  const totals = useMemo(() => computeTotals(locked ? form.lines : bollo.add ? [...baseLines, BOLLO_LINE] : baseLines, form.cassa, form.ritenuta, split), [locked, form.lines, baseLines, bollo.add, form.cassa, form.ritenuta, split]);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const setLine = (i, l) => setForm((f) => ({ ...f, lines: f.lines.map((x, j) => (j === i ? l : x)) }));

  const selectClient = (pid, list = clients) => {
    const c = list.find((x) => x.id === pid);
    setForm((f) => {
      const prev = list.find((x) => x.id === f.party_id);
      const fix = (l) => exempt(unexempt(l, prev), c);
      const cassa = f.cassa && fix({ ...f.cassa, aliquota: f.cassa.aliquota_iva });
      return {
        ...f, party_id: pid,
        fattura_collegata_id: sentInvoices.some((i) => i.id === f.fattura_collegata_id && i.party_id === pid) ? f.fattura_collegata_id : null,
        lines: f.lines.map(fix),
        cassa: f.cassa ? { ...f.cassa, aliquota_iva: cassa.aliquota, natura: cassa.natura } : null,
      };
    });
  };

  const addArticle = (aid) => {
    const a = articles.find((x) => x.id === aid);
    if (!a) return;
    const line = exempt({ descrizione: a.descrizione, quantita: 1, unita_misura: a.unita_misura, prezzo_unitario: a.prezzo, aliquota: a.aliquota, natura: a.natura, article_id: a.id }, client);
    setForm((f) => {
      const blank = f.lines.length === 1 && !f.lines[0].descrizione && !f.lines[0].prezzo_unitario;
      return { ...f, lines: blank ? [line] : [...f.lines, line] };
    });
  };

  const run = async (fn, ok) => {
    setBusy(true);
    try { const r = await fn(); if (ok) toast.success(ok); return r; }
    catch (e) { fail(e); }
    finally { setBusy(false); }
  };

  const save = () => run(async () => {
    reset();
    const body = { ...form, banca_id: (company.banche || []).some((b) => b.id === form.banca_id) ? form.banca_id : null, numero: form.numero ? Number(form.numero) : null, cassa: num(form.cassa, ["aliquota", "aliquota_iva"]), ritenuta: num(form.ritenuta, ["aliquota"]), lines: baseLines.map((l) => ({ ...l, quantita: Number(l.quantita), prezzo_unitario: Number(l.prezzo_unitario || 0) })) };
    const { data } = id ? await api.put(`/invoices/${id}`, body) : await api.post("/invoices", body);
    if (!id) { navigate(`/fatture/${data.id}`, { replace: true }); return data; }
    const full = (await api.get(`/invoices/${data.id}`)).data;
    setInv(full);
    return full;
  }, `${docName} salvata`);

  const action = (path, ok) => run(async () => { await api.post(`/invoices/${id}/${path}`); const { data } = await api.get(`/invoices/${id}`); setInv(data); setForm((f) => ({ ...f, ...data })); return data; }, ok);

  const send = async () => {
    if (!locked) { const saved = await save(); if (!saved) return; }
    const r = await action("send", `${docName} trasmessa all'intermediario (simulato)`);
    if (r) toast.info("Usa \"Aggiorna stato SDI\" per ricevere l'esito");
  };

  const remove = () => run(async () => { await api.delete(`/invoices/${id}`); navigate("/fatture"); }, "Bozza eliminata");

  if (inv?.autofattura) {
    return <AutofatturaView inv={inv} busy={busy} canSend={canSend(user)} onSend={async () => { const r = await action("send", "Autofattura trasmessa allo SDI (simulato)"); if (r) toast.info("Usa \"Aggiorna stato SDI\" per ricevere l'esito"); }}
      onRefresh={() => action("refresh", "Esito SDI aggiornato")} onDelete={remove} />;
  }

  return (
    <FieldErrors value={errValue}>
    <div>
      <Link to="/fatture" className="mb-4 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900" data-testid="back-to-invoices"><ArrowLeft className="h-4 w-4" />Fatture</Link>
      <PageHeader eyebrow={inv ? `${docName} ${inv.numero_display}` : `Nuova ${docName.toLowerCase()}`} title={inv ? `${docName} N. ${inv.numero_display}` : isNC ? "Crea nota di credito" : "Crea fattura"}>
        {isNC && <span className="rounded-full border border-violet-300 bg-violet-100 px-2.5 py-0.5 text-xs font-semibold text-violet-800" data-testid="editor-nc-badge">Nota di credito</span>}
        {inv && <StatusBadge status={inv.status} testId="editor-status-pill" />}
      </PageHeader>
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-12">
        <div className="space-y-6 lg:col-span-8">
          {rejected && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800" data-testid="rejected-banner">
              <b>Documento scartato dallo SDI.</b> Correggi i dati indicati nella notifica di scarto (i dati del cliente vengono ripresi aggiornati dall'anagrafica), salva e reinvialo: il numero {inv.numero_display} resta invariato.
            </div>
          )}
          <Card title="Documento">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <Field label="Tipo documento" name="tipo_documento"><Sel disabled={locked || !!inv} value={form.tipo_documento} onChange={(v) => setForm((f) => ({ ...f, tipo_documento: v, fattura_collegata_id: v === "TD04" ? f.fattura_collegata_id : null }))} options={TIPI_DOC} testId="invoice-tipo-select" /></Field>
              <Field label="Data" name="data"><Input disabled={locked} type="date" value={form.data} onChange={(e) => set("data", e.target.value)} data-testid="invoice-date-input" /></Field>
              <Field label={`Numero${isNC ? " (registro NC)" : ""}`} name="numero">
                {locked || rejected
                  ? <Input disabled value={inv.numero_display} data-testid="invoice-number-display" />
                  : <Input type="number" min="1" value={form.numero ?? ""} placeholder="Automatico" onChange={(e) => set("numero", e.target.value)} data-testid="invoice-number-input" />}
              </Field>
            </div>
            {isNC && (
              <div className="mt-4 rounded-lg border border-violet-200 bg-violet-50 p-4" data-testid="linked-invoice-section">
                <Field label="Fattura stornata (DatiFattureCollegate)" name="fattura_collegata_id">
                  <Sel disabled={locked || !form.party_id} value={form.fattura_collegata_id || ""} onChange={(v) => set("fattura_collegata_id", v === "none" ? null : v)}
                    options={[["none", "Nessuna (storno generico)"], ...linkable.map((i) => [i.id, `N. ${i.numero_display} del ${fmtDate(i.data)} · ${fmtEUR(i.totale)}`])]}
                    testId="linked-invoice-select" placeholder={form.party_id ? "Seleziona la fattura da stornare" : "Scegli prima il cliente"} />
                </Field>
                <p className="mt-2 text-xs text-violet-800">Gli importi vanno indicati in positivo: la nota di credito viene sottratta dal fatturato. Il totale non può superare il residuo della fattura stornata.</p>
                {linkedInfo && (
                  <p className={`mt-2 text-xs font-semibold ${totals.totale > linkedInfo.residuo + 0.005 ? "text-rose-700" : "text-violet-900"}`} data-testid="linked-residuo">
                    Residuo stornabile: {fmtEUR(linkedInfo.residuo)} su {fmtEUR(linkedInfo.totale)}
                    {totals.totale > linkedInfo.residuo + 0.005 && " — riduci gli importi prima di salvare"}
                  </p>
                )}
              </div>
            )}
          </Card>
          <Card title="Cliente (cessionario/committente)">
            <div className="flex gap-2">
              <div className={`flex-1 ${errValue.errs.has("party_id") ? "field-invalid" : ""}`} data-testid="invoice-client-field"><Sel disabled={locked} value={form.party_id} onChange={(v) => { errValue.clear("party_id"); selectClient(v); }} options={clients.map((c) => [c.id, c.denominazione])} testId="invoice-client-select" placeholder="Seleziona un cliente" /></div>
              {!locked && <Button variant="outline" onClick={() => setPartyOpen(true)} data-testid="invoice-new-client-btn"><Plus className="h-4 w-4" /></Button>}
            </div>
            {errValue.errs.has("party_id") && <p className="mt-1.5 text-xs font-medium text-rose-600" data-testid="field-error-party-id">{errValue.errs.get("party_id")}</p>}
            {client && (
              <div className="mt-4 grid grid-cols-2 gap-3 rounded-lg bg-slate-50 p-4 text-xs sm:grid-cols-4" data-testid="invoice-client-details">
                <div><div className="text-slate-500">P.IVA / C.F.</div><div className="mono">{client.partita_iva || client.codice_fiscale || "—"}</div></div>
                <div><div className="text-slate-500">{isPA ? "Cod. univoco ufficio PA" : "Cod. destinatario"}</div><div className="mono">{client.codice_destinatario}</div></div>
                <div><div className="text-slate-500">PEC</div><div className="truncate">{client.pec || "—"}</div></div>
                <div><div className="text-slate-500">Sede</div><div className="truncate">{client.comune} {client.provincia && `(${client.provincia})`}</div></div>
                {client.natura_default && (
                  <div className="col-span-2 sm:col-span-4 text-amber-800" data-testid="invoice-client-exemption">
                    Cliente in regime {client.natura_default}: le righe vengono impostate a IVA 0% con natura {client.natura_default}
                    {client.intento_protocollo && <> · Dich. intento <span className="mono">{client.intento_protocollo}</span> del {fmtDate(client.intento_data)}</>}
                  </div>
                )}
              </div>
            )}
          </Card>
          {isPA && <PaCard form={form} set={set} disabled={locked} client={client} />}
          <Card title="Righe">
            <div className="space-y-3">
              {form.lines.map((l, i) => (l.bollo && !locked ? null : (
                <LineRow key={i} idx={i} line={l} onChange={setLine} disabled={locked || l.bollo} canRemove={baseLines.length > 1 && !l.bollo} onRemove={(j) => set("lines", form.lines.filter((_, k) => k !== j))} />
              )))}
              {!locked && bollo.add && <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800" data-testid="bollo-line-hint">Verrà aggiunta la riga "Imposta di bollo assolta in modo virtuale" di 2,00 € (N1) addebitata al cliente.</p>}
            </div>
            <PlafondHint partyId={form.party_id} data={form.data} invoiceId={id} nc={form.tipo_documento === "TD04"}
              imponibile={Math.round(totals.riepilogo.filter((r) => r.natura === "N3.5").reduce((s, r) => s + r.imponibile, 0) * 100) / 100} />
            {!locked && (
              <div className="mt-4 flex flex-col gap-2 sm:flex-row">
                <Button variant="outline" onClick={() => set("lines", [...form.lines, exempt({ ...NEW_LINE }, client)])} data-testid="add-line-btn"><Plus className="mr-2 h-4 w-4" />Aggiungi riga</Button>
                {articles.length > 0 && (
                  <div className="sm:w-72" key={form.lines.length}><Sel value="" onChange={addArticle} options={articles.map((a) => [a.id, `${a.codice} · ${a.descrizione}`])} testId="add-article-select" placeholder="Aggiungi da archivio articoli" /></div>
                )}
              </div>
            )}
          </Card>
          <CassaRitenutaCard form={form} setForm={setForm} disabled={locked} company={company} client={client} />
          <Card title="Pagamento e note">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Modalità di pagamento" name="modalita_pagamento"><Sel disabled={locked} value={form.modalita_pagamento} onChange={(v) => set("modalita_pagamento", v)} options={MODALITA} testId="invoice-payment-select" /></Field>
              {["MP05", "MP12"].includes(form.modalita_pagamento) && <BankSelect form={form} set={set} company={company} locked={locked} inv={inv} />}
              <Field label={form.rate?.length ? "Scadenza (ultima rata)" : "Scadenza"} name="scadenza"><Input disabled={locked || form.rate?.length > 0} type="date" value={form.scadenza || ""} onChange={(e) => set("scadenza", e.target.value)} data-testid="invoice-due-input" /></Field>
              <Field label="Causale" name="causale" className="sm:col-span-2"><Textarea disabled={locked} value={form.causale || ""} onChange={(e) => set("causale", e.target.value)} data-testid="invoice-causale-input" /></Field>
            </div>
          </Card>
          {!isNC && !locked && <RateCard form={form} setForm={setForm} netto={totals.netto} />}
          {inv && !isNC && SENT.includes(inv.status) && <PaymentsPanel invoiceId={id} />}
        </div>
        <div className="space-y-6 lg:col-span-4">
          <div className="lg:sticky lg:top-6 space-y-6">
            <Card title="Riepilogo">
              {totals.riepilogo.map((r) => (
                <Row key={`${r.aliquota}${r.natura}`} label={r.aliquota ? `Imponibile IVA ${r.aliquota}%` : `Imponibile ${r.natura}`} value={fmtEUR(r.imponibile)} />
              ))}
              <Row label="Totale imponibile" value={fmtEUR(totals.imponibile)} testId="summary-imponibile" />
              {form.cassa && <Row label={`di cui contributo cassa ${form.cassa.aliquota}%`} value={fmtEUR(totals.cassa_importo)} testId="summary-cassa" />}
              <Row label="Totale IVA" value={fmtEUR(totals.iva)} testId="summary-iva" />
              <Row label="Totale documento" value={fmtEUR(totals.totale)} strong testId="summary-totale" />
              {(locked ? inv?.bollo_virtuale : bollo.on) && <Row label={`Bollo virtuale${(locked ? inv?.bollo_addebitato : bollo.add) ? " (addebitato)" : " (a tuo carico)"}`} value={fmtEUR(2)} testId="summary-bollo" />}
              {!locked && <BolloCard state={bollo} scelta={form.bollo} onChange={(v) => set("bollo", v)} />}
              {split && <Row label="IVA split payment (versata dall'ente)" value={`- ${fmtEUR(totals.iva_split)}`} testId="summary-split" />}
              {(form.ritenuta || split) && (
                <>
                  {form.ritenuta && <Row label={`Ritenuta d'acconto ${form.ritenuta.aliquota}%`} value={`- ${fmtEUR(totals.ritenuta_importo)}`} testId="summary-ritenuta" />}
                  <Row label="Netto a pagare" value={fmtEUR(totals.netto)} strong testId="summary-netto" />
                </>
              )}
            </Card>
            <Card title="Azioni">
              <div className="grid gap-2">
                {!locked && <Button onClick={save} disabled={busy} data-testid="save-invoice-btn"><Save className="mr-2 h-4 w-4" />{rejected ? "Salva correzioni" : "Salva"}</Button>}
                {inv && !locked && canSend(user) && <Button onClick={send} disabled={busy} className="bg-blue-600 hover:bg-blue-700" data-testid="send-sdi-btn"><Send className="mr-2 h-4 w-4" />{inv.status === "scartata" ? "Reinvia allo SDI" : "Invia allo SDI"}</Button>}
                {inv?.status === "inviata" && <Button onClick={() => action("refresh", "Esito SDI aggiornato")} disabled={busy} className="bg-emerald-600 hover:bg-emerald-700" data-testid="refresh-sdi-btn"><RefreshCw className="mr-2 h-4 w-4" />Aggiorna stato SDI</Button>}
                {inv && (
                  <div className="grid grid-cols-3 gap-2">
                    <Button variant="outline" onClick={() => setXmlOpen(true)} data-testid="preview-xml-btn" title="Anteprima XML"><FileCode2 className="h-4 w-4" /></Button>
                    <Button variant="outline" onClick={() => downloadXml(id)} data-testid="download-xml-btn" title="Scarica XML"><Download className="h-4 w-4" /></Button>
                    <Button variant="outline" asChild data-testid="print-pdf-btn" title="Stampa PDF"><Link to={`/fatture/${id}/stampa`}><Printer className="h-4 w-4" /></Link></Button>
                  </div>
                )}
                {inv && locked && canSend(user) && (
                  <Button variant="outline" onClick={() => setCortesiaOpen(true)} data-testid="send-cortesia-btn"><Mail className="mr-2 h-4 w-4" />Invia fattura di cortesia</Button>
                )}
                {inv && !isNC && SENT.includes(inv.status) && inv.residuo_stornabile > 0 && (
                  <Button variant="outline" className="border-violet-300 text-violet-700 hover:bg-violet-50" onClick={() => setStornoOpen(true)} data-testid="create-credit-note-btn"><FileMinus className="mr-2 h-4 w-4" />Crea nota di credito</Button>
                )}
                {inv?.status === "bozza" && <Button variant="ghost" className="text-rose-600 hover:bg-rose-50 hover:text-rose-700" onClick={remove} disabled={busy} data-testid="delete-invoice-btn"><Trash2 className="mr-2 h-4 w-4" />Elimina bozza</Button>}
                {inv && !canSend(user) && !locked && <p className="text-xs text-slate-500">L'invio allo SDI è riservato ad Admin e Contabile.</p>}
              </div>
              {inv?.sdi_message && <p className={`mt-4 rounded-md p-3 text-xs ${inv.status === "scartata" ? "bg-rose-50 text-rose-700" : "bg-slate-50 text-slate-600"}`} data-testid="sdi-message">{inv.sdi_message}</p>}
            </Card>
            {inv && !isNC && inv.note_credito?.length > 0 && (
              <Card title="Note di credito collegate">
                <div className="space-y-2" data-testid="linked-credit-notes">
                  {inv.note_credito.map((n) => (
                    <Link key={n.id} to={`/fatture/${n.id}`} className="flex items-center justify-between rounded-md border border-slate-200 px-3 py-2 text-sm hover:bg-slate-50" data-testid={`linked-nc-${n.id}`}>
                      <span className="mono text-xs">N. {n.numero_display}</span>
                      <span className="font-semibold text-violet-700">- {fmtEUR(n.totale)}</span>
                      <StatusBadge status={n.status} testId={`linked-nc-status-${n.id}`} />
                    </Link>
                  ))}
                  <div className="flex justify-between pt-2 text-sm"><span className="text-slate-500">Residuo stornabile</span><b data-testid="residuo-stornabile">{fmtEUR(inv.residuo_stornabile)}</b></div>
                </div>
              </Card>
            )}
            {inv?.fattura_collegata && (
              <Card title="Fattura stornata">
                <Link to={`/fatture/${inv.fattura_collegata.id}`} className="text-sm font-medium text-blue-600 hover:text-blue-700" data-testid="linked-original-link">N. {inv.fattura_collegata.numero_display} del {fmtDate(inv.fattura_collegata.data)} · {fmtEUR(inv.fattura_collegata.totale)}</Link>
              </Card>
            )}
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
      {inv && locked && <CortesiaDialog inv={inv} open={cortesiaOpen} onOpenChange={setCortesiaOpen} />}
      {inv && !isNC && <CreditNoteDialog open={stornoOpen} onOpenChange={setStornoOpen} inv={inv} />}
      <PartyDialog open={partyOpen} onOpenChange={setPartyOpen} tipo="cliente" onSaved={(p) => { const list = [...clients, p]; setClients(list); selectClient(p.id, list); }} />
    </div>
    </FieldErrors>
  );
}

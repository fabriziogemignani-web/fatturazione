import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, Plus, Save, CheckCircle2, Printer, Trash2, Ban, Truck, Receipt, FileText } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate, today, lineTotal } from "@/lib/fe";
import { PageHeader, FieldErrors, useFieldErrors } from "@/components/Common";
import { LineRow } from "@/components/LineRow";
import { SearchPicker } from "@/components/SearchPicker";
import { DdtTrasporto } from "@/components/DdtTrasporto";
import { CarenzeDialog } from "@/components/CarenzeDialog";
import { DdtStato } from "@/pages/Ddt";
import { FirmeDdt } from "@/components/FirmeDdt";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";

const NEW_LINE = { descrizione: "", quantita: 1, unita_misura: "", prezzo_unitario: 0, aliquota: 22, natura: null, note: "", article_id: null, codice: "", sconto: "" };
const EMPTY = { data: today(), party_id: "", causale: "Vendita", porto: "franco", trasporto_a_cura: "mittente", vettore: null, destinazione: null, colli: "", peso_kg: "", aspetto_beni: "", inizio_trasporto: "", prezzi_in_stampa: false, note: "", lines: [NEW_LINE] };

export const openPdf = async (url) => {
  try { const { data } = await api.get(url, { responseType: "blob" }); window.open(URL.createObjectURL(data), "_blank"); } catch (e) { toast.error(errMsg(e)); }
};

export default function DdtEditor() {
  const { id } = useParams();
  const nav = useNavigate();
  const [d, setD] = useState(null);
  const [f, setF] = useState(EMPTY);
  const [clients, setClients] = useState([]);
  const [articles, setArticles] = useState([]);
  const [carenze, setCarenze] = useState(null);
  const [busy, setBusy] = useState(false);
  const { fail, value: errValue } = useFieldErrors();
  const locked = !!d && d.status !== "bozza";
  useEffect(() => {
    api.get("/parties", { params: { tipo: "cliente" } }).then(({ data }) => setClients(data));
    api.get("/articles").then(({ data }) => setArticles(data));
  }, []);
  useEffect(() => {
    if (id) reload();
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps
  const reload = () => api.get(`/ddt/${id}`).then(({ data }) => { setD(data); setF({ ...EMPTY, ...data, colli: data.colli ?? "", peso_kg: data.peso_kg ?? "" }); }).catch((e) => toast.error(errMsg(e)));
  const set = (k, v) => { errValue.clear(k); setF((x) => ({ ...x, [k]: v })); };
  const items = useMemo(() => clients.map((c) => ({ key: c.id, label: c.denominazione, sub: c.partita_iva || c.codice_fiscale })), [clients]);
  const artItems = useMemo(() => articles.map((a) => ({ key: a.id, label: `${a.codice} · ${a.descrizione}`, sub: a.gestione_magazzino ? `giac. ${a.giacenza ?? 0} ${a.unita_misura || ""}` : "" })), [articles]);
  const addArticle = async (it) => {
    const a = articles.find((x) => x.id === it.key);
    let ln = { ...NEW_LINE, article_id: a.id, codice: a.codice, descrizione: a.descrizione, unita_misura: a.unita_misura || "", prezzo_unitario: a.prezzo ?? a.prezzo_unitario ?? 0, aliquota: a.aliquota ?? 22, natura: a.natura || null };
    if (f.party_id) {
      try {
        const { data } = await api.get(`/parties/${f.party_id}/prezzo`, { params: { article_id: a.id } });
        ln = { ...ln, prezzo_unitario: data.prezzo, sconto: data.sconto || "" };
        if (data.fonte !== "articolo") toast.info(data.fonte === "listino" ? "Prezzo dal listino del cliente" : `Prezzo dell'ultima vendita (${data.riferimento})`);
      } catch (e) { toast.error(errMsg(e)); }
    }
    setF((x) => ({ ...x, lines: [...x.lines.filter((l) => l.descrizione), ln] }));
  };
  const payload = () => ({ ...f, colli: f.colli === "" ? null : Number(f.colli), peso_kg: f.peso_kg === "" ? null : Number(f.peso_kg),
    lines: f.lines.map((l) => ({ ...l, quantita: Number(l.quantita), prezzo_unitario: Number(l.prezzo_unitario || 0) })) });
  const save = async () => {
    setBusy(true);
    try {
      const { data } = id ? await api.put(`/ddt/${id}`, payload()) : await api.post("/ddt", payload());
      toast.success("DDT salvato");
      setD(data);
      if (!id) nav(`/ddt/${data.id}`, { replace: true });
      setBusy(false);
      return data;
    } catch (e) { fail(e); setBusy(false); return null; }
  };
  const conferma = async (forza = false) => {
    const saved = forza ? d : await save();
    if (!saved) return;
    setBusy(true);
    try {
      const { data } = await api.post(`/ddt/${saved.id}/conferma`, { forza });
      setCarenze(null); setD(data); setF((x) => ({ ...x, ...data }));
      toast.success(`DDT n. ${data.numero_display} confermato: magazzino scaricato`);
    } catch (e) {
      const det = e?.response?.data?.detail;
      if (det?.carenze) setCarenze({ list: det.carenze, blocca: e.response.status === 400 });
      else toast.error(errMsg(e));
    }
    setBusy(false);
  };
  const act = async (path, msg, after) => {
    if (!window.confirm(msg)) return;
    try { const { data } = await api[path === "delete" ? "delete" : "post"](path === "delete" ? `/ddt/${id}` : `/ddt/${id}/${path}`); toast.success("Fatto"); after(data); } catch (e) { toast.error(errMsg(e)); }
  };
  const pickClient = async (pid) => {
    set("party_id", pid);
    const arts = f.lines.filter((l) => l.article_id);
    if (!arts.length || !window.confirm("Aggiornare prezzi e sconti delle righe con quelli abituali del nuovo cliente?")) return;
    try {
      const res = await Promise.all(arts.map((l) => api.get(`/parties/${pid}/prezzo`, { params: { article_id: l.article_id } })));
      const map = Object.fromEntries(arts.map((l, i) => [l.article_id, res[i].data]));
      setF((x) => ({ ...x, lines: x.lines.map((l) => (map[l.article_id] ? { ...l, prezzo_unitario: map[l.article_id].prezzo, sconto: map[l.article_id].sconto || "" } : l)) }));
      toast.success("Prezzi aggiornati");
    } catch (e) { toast.error(errMsg(e)); }
  };
  const fattura = async (tipo, forza = false) => {
    const msg = tipo === "fattura" ? "Creare subito la fattura immediata di questo DDT con data di oggi?" : "Emettere una fattura accompagnatoria al posto del DDT? Il magazzino verrà scaricato e il DDT non sarà numerato.";
    if (!forza && !window.confirm(msg)) return;
    const saved = tipo === "accompagnatoria" && !forza ? await save() : d;
    if (!saved) return;
    setBusy(true);
    try {
      const { data } = await api.post(`/ddt/${saved.id}/${tipo}`, tipo === "fattura" ? {} : { forza });
      setCarenze(null);
      toast.success(`Creata la fattura ${data.invoice.numero_display} (bozza da inviare allo SDI)`);
      nav(`/fatture/${data.invoice.id}`);
    } catch (e) {
      const det = e?.response?.data?.detail;
      if (det?.carenze) setCarenze({ list: det.carenze, blocca: e.response.status === 400, tipo });
      else toast.error(errMsg(e));
    }
    setBusy(false);
  };
  const client = clients.find((c) => c.id === f.party_id) || d?.cliente;
  const imponibile = f.lines.reduce((s, l) => s + lineTotal(l), 0);
  return (
    <FieldErrors value={errValue}>
      <div className="mb-3"><Link to="/ddt" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800" data-testid="ddt-back-link"><ArrowLeft className="h-4 w-4" />Documenti di trasporto</Link></div>
      <PageHeader eyebrow="Documento di trasporto" title={d?.numero_display ? `DDT n. ${d.numero_display}` : "Nuovo DDT"}>
        {d && <span className="self-center"><DdtStato d={d} /></span>}
        {d && <Button variant="outline" onClick={() => openPdf(`/ddt/${d.id}/pdf`)} data-testid="ddt-pdf-btn"><Printer className="mr-2 h-4 w-4" />Stampa</Button>}
        {!locked && <Button variant="outline" onClick={save} disabled={busy} data-testid="ddt-save-btn"><Save className="mr-2 h-4 w-4" />Salva bozza</Button>}
        {!locked && <Button onClick={() => conferma(false)} disabled={busy} data-testid="ddt-conferma-btn"><CheckCircle2 className="mr-2 h-4 w-4" />Conferma e scarica</Button>}
        {!locked && f.causale === "Vendita" && <Button variant="outline" onClick={() => fattura("accompagnatoria")} disabled={busy} data-testid="ddt-accompagnatoria-btn"><FileText className="mr-2 h-4 w-4" />Fattura accompagnatoria</Button>}
        {d?.status === "confermato" && d.causale === "Vendita" && <Button onClick={() => fattura("fattura")} disabled={busy} data-testid="ddt-fattura-subito-btn"><Receipt className="mr-2 h-4 w-4" />Fattura subito</Button>}
        {d?.status === "bozza" && <Button variant="outline" onClick={() => act("delete", "Eliminare la bozza di DDT?", () => nav("/ddt"))} data-testid="ddt-delete-btn"><Trash2 className="h-4 w-4" /></Button>}
        {d?.status === "confermato" && <Button variant="outline" className="text-rose-600" onClick={() => act("annulla", "Annullare il DDT? I movimenti di scarico verranno stornati.", (x) => { setD(x); setF((y) => ({ ...y, ...x })); })} data-testid="ddt-annulla-btn"><Ban className="mr-2 h-4 w-4" />Annulla DDT</Button>}
      </PageHeader>
      {d?.status === "fatturato" && <p className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-800" data-testid="ddt-fatturato-note">{d.tipo === "accompagnatoria" ? "Emesso come fattura accompagnatoria" : "Fatturato con la fattura"} <Link className="font-semibold underline" to={`/fatture/${d.invoice_id}`}>{d.invoice_numero}</Link></p>}
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <div className="rounded-xl border border-slate-200 bg-white p-5">
            <div className="grid gap-3 sm:grid-cols-3">
              <label className="block text-xs text-slate-600">Data<Input disabled={locked} type="date" value={f.data} onChange={(e) => set("data", e.target.value)} data-testid="ddt-data-input" /></label>
              <div className={`sm:col-span-2 ${errValue.errs.has("party_id") ? "field-invalid" : ""}`}><span className="text-xs text-slate-600">Cliente</span>
                {locked ? <div className="flex h-9 items-center text-sm font-semibold">{client?.denominazione}</div>
                  : <SearchPicker items={items} value={client?.denominazione} onPick={(i) => pickClient(i.key)} onClear={() => set("party_id", "")} placeholder="Cerca cliente" testId="ddt-cliente-picker" />}
              </div>
            </div>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-5">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <h3 className="flex items-center gap-2 font-semibold text-slate-800"><Truck className="h-4 w-4" />Merce trasportata</h3>
              {!locked && <div className="flex w-full gap-2 sm:w-auto"><SearchPicker items={artItems} onPick={addArticle} placeholder="Aggiungi articolo" testId="ddt-articolo-picker" className="min-w-0 flex-1 sm:w-72" />
                <Button size="sm" variant="outline" onClick={() => setF((x) => ({ ...x, lines: [...x.lines, NEW_LINE] }))} data-testid="ddt-add-line"><Plus className="h-4 w-4" /></Button></div>}
            </div>
            <div className="space-y-2">
              {f.lines.map((l, i) => (
                <div key={i}>
                  {l.codice && <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">{l.codice}</div>}
                  <LineRow line={l} idx={i} disabled={locked} canRemove={f.lines.length > 1} onChange={(k, v) => setF((x) => ({ ...x, lines: x.lines.map((y, j) => (j === k ? v : y)) }))} onRemove={(k) => setF((x) => ({ ...x, lines: x.lines.filter((_, j) => j !== k) }))} />
                </div>
              ))}
            </div>
            <div className="mt-3 text-right text-sm text-slate-600">Imponibile merce <span className="font-semibold text-slate-900" data-testid="ddt-imponibile">{fmtEUR(imponibile)}</span></div>
          </div>
        </div>
        <div className="space-y-6">
          {d && ["confermato", "fatturato"].includes(d.status) && <FirmeDdt d={d} onChanged={reload} />}
          <div className="rounded-xl border border-slate-200 bg-white p-5"><h3 className="mb-3 font-semibold text-slate-800">Trasporto</h3><DdtTrasporto f={f} set={set} disabled={locked} /></div>
          <div className="rounded-xl border border-slate-200 bg-white p-5"><h3 className="mb-2 font-semibold text-slate-800">Note</h3><Textarea disabled={locked} rows={3} value={f.note || ""} onChange={(e) => set("note", e.target.value)} data-testid="ddt-note-input" />
            {d?.confermato_at && <p className="mt-3 text-xs text-slate-500">Confermato il {fmtDate(d.confermato_at)} · {d.stock_move_ids?.length || 0} movimenti di scarico</p>}
          </div>
        </div>
      </div>
      <CarenzeDialog carenze={carenze?.list} blocca={carenze?.blocca} onClose={() => setCarenze(null)} onForza={() => (carenze?.tipo ? fattura(carenze.tipo, true) : conferma(true))} />
    </FieldErrors>
  );
}

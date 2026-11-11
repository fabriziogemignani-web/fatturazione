import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, Loader2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate, ALIQUOTE, NATURE } from "@/lib/fe";
import { PageHeader } from "@/components/Common";
import { SearchPicker } from "@/components/SearchPicker";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const TIPI = [["vendita", "Fattura di vendita", "cliente"], ["nc_vendita", "Nota di credito a cliente", "cliente"], ["acquisto", "Fattura di acquisto", "fornitore"], ["nc_acquisto", "Nota di credito da fornitore", "fornitore"]];
const today = () => new Date().toISOString().slice(0, 10);
const r2 = (v) => Math.round(v * 100) / 100;
const NEW = () => ({ tipo: "vendita", party_id: "", numero: "", data_documento: today(), data_registrazione: today(), scadenza: "", righe: [{ aliquota: 22, natura: "", totale: "" }] });

const calc = (righe) => righe.map((x) => {
  const tot = Number(x.totale) || 0;
  const imp = r2(tot / (1 + Number(x.aliquota) / 100));
  return { ...x, imponibile: imp, imposta: r2(tot - imp), tot };
});

const Righe = ({ f, setF }) => {
  const rows = calc(f.righe);
  const set = (i, k, v) => setF({ ...f, righe: f.righe.map((x, j) => (j === i ? { ...x, [k]: v } : x)) });
  return (
    <div className="mt-4">
      <table className="w-full text-sm" data-testid="regv-righe">
        <thead className="text-left text-xs uppercase tracking-wider text-slate-500"><tr><th className="py-2">Aliquota IVA</th><th>Totale ivato €</th><th className="text-right">Imponibile</th><th className="text-right">IVA</th><th /></tr></thead>
        <tbody>
          {rows.map((x, i) => (
            <tr key={i} className="border-t border-slate-100" data-testid={`regv-riga-${i}`}>
              <td className="py-2 pr-2">
                <div className="flex gap-2">
                  <Select value={String(x.aliquota)} onValueChange={(v) => set(i, "aliquota", Number(v))}>
                    <SelectTrigger className="w-24 bg-white" data-testid={`regv-aliquota-${i}`}><SelectValue /></SelectTrigger>
                    <SelectContent className="bg-white">{ALIQUOTE.map((a) => <SelectItem key={a} value={String(a)}>{a}%</SelectItem>)}</SelectContent>
                  </Select>
                  {Number(x.aliquota) === 0 && (
                    <Select value={x.natura || ""} onValueChange={(v) => set(i, "natura", v)}>
                      <SelectTrigger className="w-48 bg-white" data-testid={`regv-natura-${i}`}><SelectValue placeholder="Natura" /></SelectTrigger>
                      <SelectContent className="max-h-72 bg-white">{NATURE.map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent>
                    </Select>
                  )}
                </div>
              </td>
              <td className="pr-2"><Input type="number" step="0.01" value={x.totale} onChange={(e) => set(i, "totale", e.target.value)} className="w-36 text-right" data-testid={`regv-totale-${i}`} /></td>
              <td className="text-right" data-testid={`regv-imponibile-${i}`}>{fmtEUR(x.imponibile)}</td>
              <td className="text-right" data-testid={`regv-iva-${i}`}>{fmtEUR(x.imposta)}</td>
              <td className="pl-2 text-right">{f.righe.length > 1 && <button onClick={() => setF({ ...f, righe: f.righe.filter((_, j) => j !== i) })} className="text-rose-600" data-testid={`regv-remove-${i}`}><Trash2 className="h-4 w-4" /></button>}</td>
            </tr>
          ))}
        </tbody>
        <tfoot className="border-t-2 border-slate-200 font-semibold">
          <tr><td className="py-2"><Button size="sm" variant="outline" onClick={() => setF({ ...f, righe: [...f.righe, { aliquota: 22, natura: "", totale: "" }] })} disabled={f.righe.length >= 10} data-testid="regv-add-riga"><Plus className="mr-1 h-3.5 w-3.5" />Aliquota</Button></td>
            <td data-testid="regv-totale">{fmtEUR(r2(rows.reduce((s, x) => s + x.tot, 0)))}</td>
            <td className="text-right" data-testid="regv-imponibile">{fmtEUR(r2(rows.reduce((s, x) => s + x.imponibile, 0)))}</td>
            <td className="text-right" data-testid="regv-iva">{fmtEUR(r2(rows.reduce((s, x) => s + x.imposta, 0)))}</td><td /></tr>
        </tfoot>
      </table>
    </div>
  );
};

const Elenco = ({ rows, onDel }) => (
  <div className="mt-6 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
    <table className="w-full text-sm" data-testid="regv-elenco">
      <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500"><tr><th className="px-4 py-3">Data</th><th className="px-4 py-3">Documento</th><th className="px-4 py-3">Anagrafica</th><th className="px-4 py-3 text-right">Imponibile</th><th className="px-4 py-3 text-right">IVA</th><th className="px-4 py-3 text-right">Totale</th><th /></tr></thead>
      <tbody className="divide-y divide-slate-100">
        {rows.length === 0 && <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-500">Nessuna registrazione veloce</td></tr>}
        {rows.map((x) => (
          <tr key={x.id} data-testid={`regv-row-${x.id}`}>
            <td className="px-4 py-3">{fmtDate(x.data)}</td>
            <td className="px-4 py-3">{x.kind === "vendita" ? (x.tipo_documento === "TD04" ? "NC cliente" : "Fatt. vendita") : (x.tipo_documento === "TD04" ? "NC fornitore" : "Fatt. acquisto")} <span className="mono">{x.numero_display}</span>{x.protocollo && <span className="text-xs text-slate-400"> prot. {x.protocollo}</span>}</td>
            <td className="px-4 py-3">{x.anagrafica}</td>
            <td className="px-4 py-3 text-right">{fmtEUR(x.imponibile)}</td><td className="px-4 py-3 text-right">{fmtEUR(x.iva)}</td><td className="px-4 py-3 text-right font-semibold">{fmtEUR(x.totale)}</td>
            <td className="px-4 py-3 text-right"><button onClick={() => onDel(x)} className="text-rose-600" data-testid={`regv-del-${x.id}`}><Trash2 className="h-4 w-4" /></button></td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

export default function RegistrazioneVeloce() {
  const [f, setF] = useState(NEW());
  const [parties, setParties] = useState([]);
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(false);
  const ruolo = TIPI.find((x) => x[0] === f.tipo)[2];
  const load = () => api.get("/reg-veloce").then(({ data }) => setRows(data)).catch(() => {});
  useEffect(() => { api.get("/parties").then(({ data }) => setParties(data)).catch(() => {}); load(); }, []);
  const items = useMemo(() => parties.filter((p) => p.tipo === ruolo).map((p) => ({ key: p.id, label: p.denominazione, sub: p.partita_iva || p.codice_fiscale })), [parties, ruolo]);
  const nome = parties.find((p) => p.id === f.party_id)?.denominazione || "";
  const save = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/reg-veloce", { ...f, righe: f.righe.map((x) => ({ aliquota: Number(x.aliquota), natura: Number(x.aliquota) === 0 ? x.natura : null, totale: Number(x.totale) })) });
      toast.success(`Registrato ${data.numero}: imponibile ${fmtEUR(data.imponibile)}, IVA ${fmtEUR(data.iva)}`);
      setF({ ...NEW(), tipo: f.tipo, data_registrazione: f.data_registrazione });
      load();
    } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };
  const del = async (x) => {
    if (!window.confirm(`Eliminare la registrazione del documento ${x.numero_display}?`)) return;
    try { await api.delete(`/reg-veloce/${x.kind}/${x.id}`); toast.success("Registrazione eliminata"); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div>
      <PageHeader eyebrow="Contabilità generale" title="Registrazione veloce documenti" />
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" data-testid="regv-form">
        <div className="mb-4 flex flex-wrap gap-2">
          {TIPI.map(([k, l]) => <button key={k} onClick={() => setF({ ...f, tipo: k, party_id: TIPI.find((x) => x[0] === k)[2] === ruolo ? f.party_id : "" })} className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${f.tipo === k ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 text-slate-600 hover:bg-slate-50"}`} data-testid={`regv-tipo-${k}`}>{l}</button>)}
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <label className="text-xs text-slate-600 lg:col-span-2">{ruolo === "cliente" ? "Cliente" : "Fornitore"}
            <SearchPicker items={items} value={nome} onPick={(i) => setF({ ...f, party_id: i.key })} onClear={() => setF({ ...f, party_id: "" })} placeholder={`Cerca ${ruolo} (nome o P.IVA)…`} testId="regv-party" className="w-full" />
          </label>
          <label className="text-xs text-slate-600">Numero documento<Input value={f.numero} onChange={(e) => setF({ ...f, numero: e.target.value })} data-testid="regv-numero" /></label>
          <label className="text-xs text-slate-600">Data documento<Input type="date" value={f.data_documento} onChange={(e) => setF({ ...f, data_documento: e.target.value })} data-testid="regv-data-doc" /></label>
          <label className="text-xs text-slate-600">Data registrazione<Input type="date" value={f.data_registrazione} onChange={(e) => setF({ ...f, data_registrazione: e.target.value })} data-testid="regv-data-reg" /></label>
          <label className="text-xs text-slate-600">Scadenza pagamento<Input type="date" value={f.scadenza} onChange={(e) => setF({ ...f, scadenza: e.target.value })} data-testid="regv-scadenza" /></label>
        </div>
        <Righe f={f} setF={setF} />
        <div className="mt-4 flex items-center justify-between gap-3">
          <p className="text-xs text-slate-500">Imponibile e IVA vengono scorporati dal totale; la registrazione va in prima nota, nel registro IVA e nello scadenzario.</p>
          <Button onClick={save} disabled={busy || !f.party_id || !f.numero || f.righe.some((x) => !Number(x.totale))} data-testid="regv-save">{busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Registra</Button>
        </div>
      </div>
      <Elenco rows={rows} onDel={del} />
    </div>
  );
}

import { Plus, Trash2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Field } from "@/components/Common";
import { MODALITA } from "@/lib/fe";

const sel = "h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm";

export const PersonaFisica = ({ form, setForm }) => {
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const fisica = form.persona === "fisica";
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-4" data-testid="party-persona">
      <div className="flex flex-wrap gap-2">
        {[["giuridica", "Persona giuridica (società, ente)"], ["fisica", "Persona fisica"]].map(([k, l]) => (
          <button key={k} type="button" onClick={() => setForm({ ...form, persona: k })}
            className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${form.persona === k || (!form.persona && k === "giuridica") ? "border-slate-900 bg-slate-900 text-white" : "border-slate-300 bg-white text-slate-600 hover:bg-slate-100"}`}
            data-testid={`party-persona-${k}`}>{l}</button>
        ))}
      </div>
      {fisica && (
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-6">
          <Field label="Cognome *" name="cognome" className="sm:col-span-3"><Input value={form.cognome || ""} onChange={set("cognome")} data-testid="party-cognome-input" /></Field>
          <Field label="Nome *" name="nome" className="sm:col-span-3"><Input value={form.nome || ""} onChange={set("nome")} data-testid="party-nome-input" /></Field>
          <Field label="Data di nascita" name="data_nascita" className="sm:col-span-2"><Input type="date" value={form.data_nascita || ""} onChange={set("data_nascita")} data-testid="party-data-nascita-input" /></Field>
          <Field label="Comune di nascita" name="comune_nascita" className="sm:col-span-3"><Input value={form.comune_nascita || ""} onChange={set("comune_nascita")} data-testid="party-comune-nascita-input" /></Field>
          <Field label="Prov." name="provincia_nascita"><Input maxLength={2} value={form.provincia_nascita || ""} onChange={(e) => setForm({ ...form, provincia_nascita: e.target.value.toUpperCase() })} data-testid="party-provincia-nascita-input" /></Field>
          <p className="text-[11px] text-slate-500 sm:col-span-6">La ragione sociale viene composta come "Cognome Nome".</p>
        </div>
      )}
    </div>
  );
};

export const BancheFornitore = ({ form, setForm }) => {
  const list = form.banche_fornitore?.length ? form.banche_fornitore : form.iban ? [{ nome: "", iban: form.iban, predefinita: true }] : [];
  const put = (l) => setForm({ ...form, banche_fornitore: l, iban: (l.find((b) => b.predefinita) || l[0] || {}).iban || "" });
  const upd = (i, k, v) => put(list.map((b, j) => (j === i ? { ...b, [k]: v } : k === "predefinita" ? { ...b, predefinita: false } : b)));
  return (
    <Field label="Banche del fornitore (IBAN per i bonifici)" name="banche_fornitore">
      <div className="space-y-2 rounded-lg border border-slate-200 p-3" data-testid="party-banche-fornitore">
        {list.length === 0 && <p className="text-xs text-slate-500">Nessuna banca: aggiungine una, oppure inserisci l'IBAN quando prepari il pagamento.</p>}
        {list.map((b, i) => (
          <div key={i} className="grid grid-cols-12 items-center gap-2" data-testid={`party-banca-row-${i}`}>
            <Input className="col-span-4" placeholder="Banca" value={b.nome || ""} onChange={(e) => upd(i, "nome", e.target.value)} data-testid={`party-banca-nome-${i}`} />
            <Input className="mono col-span-5" placeholder="IT60X0542811101000000123456" value={b.iban || ""} onChange={(e) => upd(i, "iban", e.target.value.replace(/\s+/g, "").toUpperCase())} data-testid={`party-banca-iban-${i}`} />
            <label className="col-span-2 flex items-center gap-1 text-[11px] text-slate-600"><input type="radio" checked={!!b.predefinita || (list.length === 1)} onChange={() => upd(i, "predefinita", true)} data-testid={`party-banca-pref-${i}`} />Predef.</label>
            <button type="button" className="col-span-1 text-rose-600" onClick={() => { const l = list.filter((_, j) => j !== i); if (b.predefinita && l[0]) l[0] = { ...l[0], predefinita: true }; put(l); }} data-testid={`party-banca-del-${i}`}><Trash2 className="h-4 w-4" /></button>
          </div>
        ))}
        <button type="button" className="inline-flex items-center gap-1 text-xs font-semibold text-blue-700 hover:underline" onClick={() => put([...list, { nome: "", iban: "", predefinita: !list.length }])} data-testid="party-banca-add"><Plus className="h-3.5 w-3.5" />Aggiungi banca</button>
      </div>
    </Field>
  );
};

export const PagamentoPredefinito = ({ form, setForm }) => {
  const num = (k, max) => (e) => setForm({ ...form, [k]: Math.max(k === "pagamento_rate" ? 1 : 0, Math.min(max, Number(e.target.value) || 0)) });
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-4" data-testid="party-pagamento">
      <div className="mb-3 text-sm font-semibold text-slate-800">Pagamento predefinito</div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Field label="Modalità" name="pagamento_modalita" className="col-span-2 sm:col-span-1">
          <select value={form.pagamento_modalita || ""} onChange={(e) => setForm({ ...form, pagamento_modalita: e.target.value })} className={sel} data-testid="party-pagamento-modalita">
            <option value="">Nessuna</option>{MODALITA.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </Field>
        <Field label="N. rate" name="pagamento_rate"><Input type="number" min={1} max={12} value={form.pagamento_rate ?? 1} onChange={num("pagamento_rate", 12)} data-testid="party-pagamento-rate" /></Field>
        <Field label="Ogni (giorni)" name="pagamento_giorni"><Input type="number" min={0} max={365} value={form.pagamento_giorni ?? 30} onChange={num("pagamento_giorni", 365)} data-testid="party-pagamento-giorni" /></Field>
        <label className="flex items-end gap-2 pb-2 text-xs text-slate-600"><Switch checked={!!form.pagamento_fine_mese} onCheckedChange={(v) => setForm({ ...form, pagamento_fine_mese: v })} data-testid="party-pagamento-fm" />Fine mese</label>
      </div>
      <p className="mt-2 text-[11px] text-slate-500">Viene proposto in ogni nuova fattura: es. Ri.Ba. 3 rate ogni 30 giorni fine mese = 30-60-90 gg f.m.</p>
    </div>
  );
};

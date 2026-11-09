import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ContoSelect } from "@/components/ContoSelect";

const Opt = ({ label, value, onChange, options, testId, disabled }) => (
  <label className="text-xs font-medium text-slate-600">{label}
    <select value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} className="mt-1 block h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm" data-testid={testId}>
      {options.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
    </select>
  </label>
);

export const ParametriTab = ({ conti, canEdit }) => {
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.get("/contabilita/parametri").then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e))); }, []);
  if (!d) return <div className="text-sm text-slate-500">Caricamento…</div>;
  const p = d.parametri;
  const set = (k, v) => setD({ ...d, parametri: { ...p, [k]: v } });
  const save = async () => {
    setBusy(true);
    const conti_ = Object.fromEntries(d.ruoli.map(([k]) => [k, p[k]]));
    try {
      const { data } = await api.put("/contabilita/parametri", { conti: conti_, contropartita_vendite: p.contropartita_vendite, contropartita_acquisti: p.contropartita_acquisti, aliquota_rc: Number(p.aliquota_rc || 0), categorie: p.categorie });
      setD(data);
      toast.success("Parametri contabili salvati");
    } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };

  return (
    <div className="max-w-4xl space-y-6" data-testid="parametri-tab">
      <div className="rounded-xl border border-slate-200 bg-white p-5">
        <h3 className="font-semibold text-slate-800">Contropartite di vendita e acquisto</h3>
        <p className="mb-4 text-xs text-slate-500">Scegli se usare un solo conto per tutti i ricavi/costi oppure quello indicato nell'articolo (vendite) o nel fornitore (acquisti). Se l'articolo o il fornitore non ha un conto, si usa quello unico.</p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Opt label="Contropartita vendite" value={p.contropartita_vendite} onChange={(v) => set("contropartita_vendite", v)} disabled={!canEdit} testId="param-contropartita-vendite"
            options={[["unica", "Un solo conto (dai parametri)"], ["articolo", "Dal conto dell'articolo"]]} />
          <Opt label="Contropartita acquisti" value={p.contropartita_acquisti} onChange={(v) => set("contropartita_acquisti", v)} disabled={!canEdit} testId="param-contropartita-acquisti"
            options={[["unica", "Un solo conto (dai parametri)"], ["fornitore", "Dal conto del fornitore"]]} />
          <label className="text-xs font-medium text-slate-600">Aliquota IVA reverse charge %<Input type="number" step="0.01" disabled={!canEdit} value={p.aliquota_rc} onChange={(e) => set("aliquota_rc", e.target.value)} className="mt-1" data-testid="param-aliquota-rc" /></label>
        </div>
      </div>
      <div className="rounded-xl border border-slate-200 bg-white p-5">
        <h3 className="mb-4 font-semibold text-slate-800">Conti usati nelle registrazioni automatiche</h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {d.ruoli.map(([k, l]) => (
            <label key={k} className="text-xs font-medium text-slate-600">{l}
              <ContoSelect conti={conti} value={p[k]} onChange={(v) => set(k, v)} disabled={!canEdit} testId={`param-conto-${k}`} className="mt-1" />
            </label>
          ))}
        </div>
      </div>
      <div className="rounded-xl border border-slate-200 bg-white p-5">
        <h3 className="font-semibold text-slate-800">Movimenti bancari senza fattura</h3>
        <p className="mb-4 text-xs text-slate-500">Conto usato quando in riconciliazione un movimento viene classificato in una di queste categorie.</p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {d.categorie.map((c) => (
            <label key={c} className="text-xs font-medium text-slate-600">{c}
              <ContoSelect conti={conti} value={p.categorie[c]} onChange={(v) => set("categorie", { ...p.categorie, [c]: v })} disabled={!canEdit} testId={`param-categoria-${c.replace(/[^a-z0-9]/gi, "-").toLowerCase()}`} className="mt-1" />
            </label>
          ))}
        </div>
      </div>
      {canEdit && <Button onClick={save} disabled={busy} data-testid="parametri-save-btn">{busy ? "Salvataggio…" : "Salva parametri"}</Button>}
    </div>
  );
};

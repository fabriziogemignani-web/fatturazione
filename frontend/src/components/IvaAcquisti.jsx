import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Field } from "@/components/Common";

const sel = "h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm";

export const useCodiciIva = (on = true) => {
  const [c, setC] = useState([]);
  useEffect(() => {
    if (!on) return;
    api.get("/contabilita/codici-iva").then(({ data }) => setC(data.filter((x) => x.aliquota > 0 && x.attivo !== false))).catch(() => {});
  }, [on]);
  return c;
};

export const IvaAcquisti = ({ form, setForm }) => {
  const codici = useCodiciIva();
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2" data-testid="party-iva-acquisti">
      <Field label="Codice IVA acquisti (con % di detraibilità)" name="codice_iva">
        <select value={form.codice_iva || ""} onChange={(e) => setForm({ ...form, codice_iva: e.target.value })} className={sel} data-testid="party-codice-iva-select">
          <option value="">Nessuno (IVA detraibile % qui sopra)</option>
          {codici.map((c) => <option key={c.codice} value={c.codice}>{c.codice} · {c.descrizione} · detraibile {c.detraibilita}%</option>)}
        </select>
      </Field>
      <Field label="Aliquota reverse charge predefinita" name="aliquota_rc">
        <select value={form.aliquota_rc ?? 22} onChange={(e) => setForm({ ...form, aliquota_rc: Number(e.target.value) })} className={sel} data-testid="party-aliquota-rc-select">
          {[22, 10, 5, 4].map((a) => <option key={a} value={a}>IVA {a}%</option>)}
        </select>
      </Field>
      <p className="text-xs text-slate-500 sm:col-span-2">Il codice IVA si applica in registrazione alle righe con la stessa aliquota: l'IVA viene divisa tra detraibile (IVA c/acquisti) e indetraibile (conto IVA indetraibile).</p>
    </div>
  );
};

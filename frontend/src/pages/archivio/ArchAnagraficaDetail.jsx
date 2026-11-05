import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Download } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { DocBadge, downloadBlob } from "@/lib/archivio";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";

const Info = ({ a }) => (
  <div className="grid gap-4 rounded-xl border border-slate-200/80 bg-white p-5 text-sm shadow-sm sm:grid-cols-3" data-testid="arch-anag-info">
    <div><div className="text-xs text-slate-500">P.IVA / CF</div><div className="mono">{a.piva ? `${a.paese || ""}${a.piva}` : a.codice_fiscale}</div></div>
    <div><div className="text-xs text-slate-500">Indirizzo</div><div>{[a.indirizzo, a.cap, a.comune, a.provincia && `(${a.provincia})`].filter(Boolean).join(" ") || "—"}</div></div>
    <div><div className="text-xs text-slate-500">Contatti</div><div>{[a.email, a.telefono, a.pec].filter(Boolean).join(" · ") || "—"}</div></div>
  </div>
);

export default function ArchAnagraficaDetail() {
  const { id } = useParams();
  const [a, setA] = useState(null);
  const [inv, setInv] = useState([]);
  const [err, setErr] = useState("");
  useEffect(() => {
    api.get(`/archivio/anagrafiche/${id}`).then(({ data }) => {
      setA(data);
      api.get("/archivio/invoices", { params: { anagrafica_id: id, tipo: data.ruolo === "cliente" ? "attiva" : "passiva", order: "desc", limit: 200 } }).then((r) => setInv(r.data.items));
    }).catch((e) => setErr(errMsg(e)));
  }, [id]);
  if (err) return <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-600" data-testid="arch-anag-error">{err}. <Link to="/archivio/anagrafiche" className="font-semibold text-blue-600">Torna alle anagrafiche</Link></div>;
  if (!a) return <div className="text-sm text-slate-500">Caricamento…</div>;
  const tipo = a.ruolo === "cliente" ? "attiva" : "passiva";

  return (
    <div>
      <PageHeader eyebrow={`Archivio · ${a.ruolo}`} title={a.denominazione || a.chiave}>
        <Button variant="outline" onClick={() => downloadBlob("/archivio/export", { anagrafica_id: id, tipo }, "anagrafica.csv").catch((e) => toast.error(errMsg(e)))} data-testid="arch-anag-export-btn"><Download className="mr-2 h-4 w-4" />Esporta CSV</Button>
      </PageHeader>
      <Info a={a} />
      <div className="mt-4 flex flex-wrap gap-3" data-testid="arch-anag-per-anno">
        <span className="rounded-lg bg-slate-900 px-3 py-2 text-sm text-white">Totale: {a.n_fatture} documenti · <b>{fmtEUR(a.totale_fatture)}</b></span>
        {a.per_anno.map((y) => <span key={y.anno} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm">{y.anno}: {y.n} doc. · {fmtEUR(y.totale)}</span>)}
      </div>
      <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200/80 bg-white shadow-sm">
        <table className="w-full text-sm" data-testid="arch-anag-invoices">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500"><tr><th className="px-4 py-3 font-medium">Numero</th><th className="px-4 py-3 font-medium">Data</th><th className="px-4 py-3 font-medium">Tipo</th><th className="px-4 py-3 text-right font-medium">Totale</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {inv.map((r) => (
              <tr key={r.id} className="hover:bg-slate-50">
                <td className="px-4 py-2.5 font-semibold"><Link to={`/archivio/fatture/${r.id}`} className="text-blue-700 hover:underline">{r.numero}</Link></td>
                <td className="px-4 py-2.5">{fmtDate(r.data)}</td><td className="px-4 py-2.5"><DocBadge code={r.tipo_documento} /></td>
                <td className="px-4 py-2.5 text-right font-semibold">{fmtEUR(r.totale)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {a.n_fatture > inv.length && inv.length > 0 && <p className="mt-2 text-xs text-slate-500" data-testid="arch-anag-partial">Mostrati gli ultimi {inv.length} documenti: per l'elenco completo usa Esporta CSV o l'elenco fatture con la ricerca.</p>}
    </div>
  );
}

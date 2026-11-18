import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, LogOut } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NSelect } from "@/components/ui/nselect";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { fmtEUR, fmtDate } from "@/lib/fe";
import { usePortoBase, oggi, addDays } from "@/lib/porto";

const ArrivoDialog = ({ open, base, onClose, onSaved }) => {
  const [f, setF] = useState({});
  useEffect(() => { if (open) { setF({ barca_id: "", posto_id: "", arrivo: oggi(), partenza_prevista: addDays(oggi(), 3), note: "" }); } }, [open]);
  const s = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const barca = base.barche.find((b) => b.id === f.barca_id);
  const posti = base.posti.filter((p) => !p.fuori_servizio && (!barca || p.lunghezza_max >= barca.lunghezza));
  const save = async () => { try { await api.post("/porto/transiti", f); toast.success("Arrivo registrato"); onSaved(); onClose(); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="arrivo-dialog">
        <DialogHeader><DialogTitle>Registra arrivo in transito</DialogTitle></DialogHeader>
        <div className="grid grid-cols-2 gap-3 text-sm">
          <label className="col-span-2">Barca<NSelect value={f.barca_id} onChange={s("barca_id")} data-testid="arrivo-barca"><option value="">Seleziona...</option>{base.barche.map((b) => <option key={b.id} value={b.id}>{b.nome} ({b.lunghezza} m) - {b.armatore}</option>)}</NSelect></label>
          <label className="col-span-2">Posto<NSelect value={f.posto_id} onChange={s("posto_id")} data-testid="arrivo-posto"><option value="">Seleziona...</option>{posti.map((p) => <option key={p.id} value={p.id}>{p.codice} (max {p.lunghezza_max} m)</option>)}</NSelect></label>
          <label>Arrivo<Input type="date" value={f.arrivo || ""} onChange={s("arrivo")} data-testid="arrivo-data" /></label>
          <label>Partenza prevista<Input type="date" value={f.partenza_prevista || ""} onChange={s("partenza_prevista")} data-testid="arrivo-partenza-prevista" /></label>
          <label className="col-span-2">Note<Input value={f.note || ""} onChange={s("note")} data-testid="arrivo-note" /></label>
        </div>
        <DialogFooter><Button onClick={save} data-testid="arrivo-save">Registra arrivo</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const PartenzaDialog = ({ tr, onClose, onSaved }) => {
  const [data, setData] = useState(oggi());
  const [imp, setImp] = useState("");
  const [calc, setCalc] = useState(null);
  useEffect(() => { if (tr) { setData(oggi() < tr.arrivo ? tr.arrivo : oggi()); setImp(""); } }, [tr]);
  useEffect(() => {
    if (!tr) { return; }
    api.get("/porto/prezzo", { params: { barca_id: tr.barca.id, da: tr.arrivo, a: data, tipo: "transito" } }).then(({ data: d }) => setCalc(d)).catch((e) => setCalc({ errore: errMsg(e) }));
  }, [tr, data]);
  const save = async () => {
    try {
      const { data: r } = await api.post(`/porto/transiti/${tr.id}/partenza`, { partenza: data, importo: imp === "" ? null : Number(imp) });
      toast.success(r.fattura_numero ? `Partenza registrata: fattura ${r.fattura_numero} in bozza` : "Partenza registrata"); onSaved(); onClose();
    } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Dialog open={!!tr} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="partenza-dialog">
        <DialogHeader><DialogTitle>Partenza di {tr?.barca.nome}</DialogTitle><DialogDescription>Alla conferma viene creata la fattura in bozza per le notti di sosta.</DialogDescription></DialogHeader>
        <div className="grid grid-cols-2 gap-3 text-sm">
          <label>Data partenza<Input type="date" value={data} max={oggi()} onChange={(e) => e.target.value && setData(e.target.value)} data-testid="partenza-data" /></label>
          <label>Importo IVA esclusa (vuoto = listino)<Input type="number" step="0.01" value={imp} onChange={(e) => setImp(e.target.value)} placeholder={calc?.imponibile != null ? String(calc.imponibile) : ""} data-testid="partenza-importo" /></label>
          <p className="col-span-2 text-xs text-slate-600" data-testid="partenza-prezzo">{calc?.errore ? <span className="text-rose-600">{calc.errore}</span> : calc && `Da listino: ${fmtEUR(calc.imponibile)} + IVA ${calc.aliquota}% = ${fmtEUR(calc.totale)}`}</p>
        </div>
        <DialogFooter><Button onClick={save} data-testid="partenza-conferma">Conferma partenza e fattura</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default function PortoTransiti() {
  const [base] = usePortoBase();
  const [rows, setRows] = useState([]);
  const [stato, setStato] = useState("presente");
  const [arr, setArr] = useState(false);
  const [part, setPart] = useState(null);
  const load = () => api.get("/porto/transiti", { params: stato ? { stato } : {} }).then(({ data }) => setRows(data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, [stato]); // eslint-disable-line react-hooks/exhaustive-deps
  const del = async (x) => { if (!window.confirm("Eliminare il transito?")) return; try { await api.delete(`/porto/transiti/${x.id}`); load(); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <div data-testid="porto-transiti-page">
      <PageHeader eyebrow="Porto turistico" title="Transiti">
        <NSelect value={stato} onChange={(e) => setStato(e.target.value)} className="w-40" data-testid="transiti-filtro"><option value="presente">In porto</option><option value="partito">Partiti</option><option value="">Tutti</option></NSelect>
        <Button onClick={() => setArr(true)} data-testid="transiti-arrivo"><Plus className="mr-1 h-4 w-4" />Registra arrivo</Button>
      </PageHeader>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-sm" data-testid="transiti-table">
          <thead className="border-b bg-slate-50 text-left text-xs uppercase text-slate-500"><tr><th className="px-4 py-3">Barca / cliente</th><th className="px-4 py-3">Posto</th><th className="px-4 py-3">Arrivo</th><th className="px-4 py-3">Partenza</th><th className="px-4 py-3 text-right">Importo</th><th className="px-4 py-3">Fattura</th><th /></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {rows.length === 0 && <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-500">Nessun transito.</td></tr>}
            {rows.map((x) => (
              <tr key={x.id} data-testid={`transito-row-${x.id}`}>
                <td className="px-4 py-3 font-semibold">{x.barca.nome} <span className="text-xs font-normal text-slate-500">{x.barca.lunghezza} m</span><div className="text-xs font-normal text-slate-500">{x.cliente}</div></td>
                <td className="px-4 py-3 font-semibold">{x.posto.codice}</td>
                <td className="px-4 py-3">{fmtDate(x.arrivo)}</td>
                <td className="px-4 py-3">{x.partenza ? fmtDate(x.partenza) : <span className="text-slate-500">prevista {fmtDate(x.partenza_prevista)}</span>}</td>
                <td className="px-4 py-3 text-right">{x.importo != null ? fmtEUR(x.importo) : "—"}</td>
                <td className="px-4 py-3" data-testid={`transito-fattura-${x.id}`}>{x.fattura_numero || "—"}</td>
                <td className="whitespace-nowrap px-4 py-3 text-right">
                  {x.stato === "presente" && <Button size="sm" variant="outline" onClick={() => setPart(x)} data-testid={`transito-partenza-${x.id}`}><LogOut className="mr-1 h-3.5 w-3.5" />Partenza</Button>}
                  {!x.fattura_id && <Button size="sm" variant="ghost" onClick={() => del(x)} data-testid={`transito-del-${x.id}`}><Trash2 className="h-3.5 w-3.5 text-rose-600" /></Button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ArrivoDialog open={arr} base={base} onClose={() => setArr(false)} onSaved={load} />
      <PartenzaDialog tr={part} onClose={() => setPart(null)} onSaved={load} />
    </div>
  );
}

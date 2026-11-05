import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Download, Send, FileArchive, History } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { downloadBlob } from "@/lib/archivio";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { fmtEUR, fmtDate, fmtDateTime } from "@/lib/fe";

const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const PRESETS = (() => {
  const n = new Date(), y = n.getFullYear(), m = n.getMonth(), q = Math.floor(m / 3);
  return [
    ["mese", "Mese scorso", iso(new Date(y, m - 1, 1)), iso(new Date(y, m, 0))],
    ["trimestre", "Trimestre scorso", iso(new Date(y, (q - 1) * 3, 1)), iso(new Date(y, q * 3, 0))],
    ["anno", "Anno in corso", `${y}-01-01`, iso(n)],
    ["anno-prec", "Anno scorso", `${y - 1}-01-01`, `${y - 1}-12-31`],
  ];
})();

const Count = ({ label, n, tot, testId }) => (
  <div className="rounded-lg border border-slate-200 p-4">
    <div className="text-xs uppercase tracking-wider text-slate-500">{label}</div>
    <div className="mt-1 text-2xl font-extrabold text-slate-900" data-testid={testId}>{n ?? "—"}</div>
    {n != null && <div className="text-xs text-slate-500">{fmtEUR(tot)}</div>}
    {n == null && <div className="text-xs text-slate-400">modulo non attivo</div>}
  </div>
);

const Log = ({ log }) => !log?.length ? null : (
  <section className="mt-6 rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm" data-testid="export-log">
    <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-800"><History className="h-4 w-4" />Ultimi invii</h3>
    <div className="divide-y divide-slate-100 text-sm">
      {log.map((l) => (
        <div key={l.id} className="flex flex-wrap justify-between gap-2 py-2" data-testid={`export-log-${l.id}`}>
          <span>{fmtDateTime(l.at)} · a <b>{l.to}</b></span>
          <span className="text-slate-500">{fmtDate(l.dal)} – {fmtDate(l.al)} · {l.attive} emesse, {l.passive} ricevute · {l.size_kb} KB · {l.by}</span>
        </div>
      ))}
    </div>
  </section>
);

export default function Esportazione() {
  const [p, setP] = useState({ dal: PRESETS[0][2], al: PRESETS[0][3] });
  const [info, setInfo] = useState(null);
  const [to, setTo] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");
  const load = () => api.get("/export/commercialista", { params: p }).then(({ data }) => { setInfo(data); setTo((v) => v || data.email); }).catch((e) => { setInfo(null); toast.error(errMsg(e)); });
  useEffect(() => { load(); }, [p.dal, p.al]); // eslint-disable-line react-hooks/exhaustive-deps
  const empty = !info || !((info.attive || 0) + (info.passive || 0));

  const download = async () => {
    setBusy("zip");
    try { await downloadBlob("/export/commercialista.zip", p, "fatture.zip"); } catch (e) { toast.error(e.response?.data instanceof Blob ? JSON.parse(await e.response.data.text()).detail : errMsg(e)); }
    setBusy("");
  };
  const send = async () => {
    setBusy("send");
    try { const { data } = await api.post("/export/commercialista/send", { ...p, to, note }); toast.success(`File inviato a ${data.to} (${data.size_kb} KB)`); load(); } catch (e) { toast.error(errMsg(e)); }
    setBusy("");
  };

  return (
    <div>
      <PageHeader eyebrow="Fatturazione" title="Esporta per il commercialista" />
      <section className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm" data-testid="export-card">
        <p className="mb-4 text-sm text-slate-600">Un file ZIP con gli XML e le copie PDF di cortesia delle fatture emesse (inviate allo SDI, escluse bozze e scartate) e di quelle ricevute, più un riepilogo Excel.</p>
        <div className="flex flex-wrap items-end gap-3">
          {PRESETS.map(([k, l, dal, al]) => (
            <button key={k} onClick={() => setP({ dal, al })} data-testid={`export-preset-${k}`}
              className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${p.dal === dal && p.al === al ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 text-slate-600 hover:border-slate-400"}`}>{l}</button>
          ))}
          <label className="text-xs text-slate-500">Dal<Input type="date" value={p.dal} onChange={(e) => setP({ ...p, dal: e.target.value })} data-testid="export-dal-input" /></label>
          <label className="text-xs text-slate-500">Al<Input type="date" value={p.al} onChange={(e) => setP({ ...p, al: e.target.value })} data-testid="export-al-input" /></label>
        </div>
        <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Count label="Fatture emesse" n={info?.attive} tot={info?.totale_attive} testId="export-count-attive" />
          <Count label="Fatture ricevute" n={info?.passive} tot={info?.totale_passive} testId="export-count-passive" />
        </div>
        <div className="mt-5">
          <Button variant="outline" onClick={download} disabled={empty || busy === "zip"} data-testid="export-download-btn"><Download className="mr-2 h-4 w-4" />{busy === "zip" ? "Preparazione…" : "Scarica ZIP"}</Button>
        </div>
      </section>
      <section className="mt-6 rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm" data-testid="export-send-card">
        <h3 className="mb-3 flex items-center gap-2 text-lg font-semibold text-slate-800"><FileArchive className="h-5 w-5 text-blue-600" />Invia via email</h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="text-sm text-slate-600">Email del commercialista<Input type="email" value={to} onChange={(e) => setTo(e.target.value)} placeholder="studio@esempio.it" data-testid="export-to-input" /></label>
          <label className="text-sm text-slate-600 sm:col-span-2">Messaggio (facoltativo)<Textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} data-testid="export-note-input" /></label>
        </div>
        <p className="mt-2 text-xs text-slate-500">Parte dal server email dell'azienda (Dati azienda → Email in uscita). Allegato massimo 20 MB.</p>
        <Button className="mt-4" onClick={send} disabled={empty || !to || busy === "send"} data-testid="export-send-btn"><Send className="mr-2 h-4 w-4" />{busy === "send" ? "Invio…" : "Invia al commercialista"}</Button>
      </section>
      <Log log={info?.log} />
    </div>
  );
}

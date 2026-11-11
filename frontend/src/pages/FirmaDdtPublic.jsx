import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import { CheckCircle2, PenLine } from "lucide-react";
import { Button } from "@/components/ui/button";
import { FirmaDialog, RUOLI_FIRMA } from "@/components/SignaturePad";

const API = `${process.env.REACT_APP_BACKEND_URL}/api/public/ddt-firma`;
const msg = (e) => (typeof e?.response?.data?.detail === "string" ? e.response.data.detail : "Operazione non riuscita");
const itd = (s) => (s ? s.split("-").reverse().join("/") : "");

export default function FirmaDdtPublic() {
  const { token } = useParams();
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const [ruolo, setRuolo] = useState(null);
  const [esito, setEsito] = useState("");
  const load = () => axios.get(`${API}/${token}`).then(({ data }) => setD(data)).catch((e) => setErr(msg(e)));
  useEffect(() => { load(); }, [token]); // eslint-disable-line react-hooks/exhaustive-deps
  const save = async (body) => {
    try { await axios.post(`${API}/${token}`, body); setEsito("Firma registrata, grazie."); load(); return true; } catch (e) { setEsito(msg(e)); return false; }
  };
  if (err) return <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6 text-center text-slate-700" data-testid="firma-public-error">{err}</div>;
  if (!d) return <div className="p-6 text-sm text-slate-500">Caricamento…</div>;
  return (
    <div className="min-h-screen bg-slate-50 px-4 py-8">
      <div className="mx-auto max-w-2xl space-y-5">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">{d.azienda}</div>
          <h1 className="text-3xl font-extrabold text-slate-900" data-testid="firma-public-title">DDT n. {d.numero_display} del {itd(d.data)}</h1>
          <p className="text-sm text-slate-600">Destinatario: <b>{d.cliente}</b>{d.destinazione?.indirizzo && ` · consegna ${d.destinazione.indirizzo} ${d.destinazione.comune || ""}`} · causale {d.causale}{d.colli ? ` · colli ${d.colli}` : ""}</p>
        </div>
        <div className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
          {d.lines.map((l, i) => <div key={i} className="flex justify-between px-4 py-2 text-sm"><span>{l.descrizione}</span><span className="tabular-nums text-slate-600">{l.quantita} {l.unita_misura}</span></div>)}
        </div>
        {esito && <p className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm text-slate-700" data-testid="firma-public-esito">{esito}</p>}
        <div className="grid gap-3 sm:grid-cols-3">
          {RUOLI_FIRMA.map(([k, label]) => (
            <div key={k} className="rounded-xl border border-slate-200 bg-white p-4 text-center" data-testid={`firma-public-${k}`}>
              <div className="mb-2 text-sm font-semibold text-slate-700">{label}</div>
              {d.firme[k] ? <div className="text-xs text-emerald-700"><CheckCircle2 className="mx-auto mb-1 h-6 w-6" />Firmato da {d.firme[k].nome}</div>
                : <Button className="w-full" onClick={() => setRuolo(k)} data-testid={`firma-public-btn-${k}`}><PenLine className="mr-2 h-4 w-4" />Firma</Button>}
            </div>
          ))}
        </div>
        <p className="text-center text-xs text-slate-400">Link valido fino al {new Date(d.expires_at).toLocaleString("it-IT")}</p>
      </div>
      <FirmaDialog ruolo={ruolo} onClose={() => setRuolo(null)} onSave={save} />
    </div>
  );
}

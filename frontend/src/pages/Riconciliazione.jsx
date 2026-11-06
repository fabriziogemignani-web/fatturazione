import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Landmark, RefreshCw, Upload, Plus, Wand2, Link2, Undo2, EyeOff, Settings2, AlertTriangle, Trash2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { MatchDialog } from "@/components/MatchDialog";
import { BancaConfigDialog } from "@/components/BancaConfigDialog";
import { useAuth, canSend, isAdmin } from "@/context/AuthContext";
import { fmtEUR, fmtDate, fmtDateTime } from "@/lib/fe";

const STATI = [["da_riconciliare", "Da riconciliare"], ["riconciliato", "Riconciliati"], ["ignorato", "Ignorati"], ["tutti", "Tutti"]];

const AccountCard = ({ a, active, onSelect, onImport, onReconnect, onDelete, admin, acc }) => (
  <div onClick={onSelect} className={`cursor-pointer rounded-xl border bg-white p-4 shadow-sm transition-colors ${active ? "border-blue-600 ring-1 ring-blue-600" : "border-slate-200 hover:border-slate-400"}`} data-testid={`bank-account-${a.id}`}>
    <div className="flex items-start justify-between gap-2">
      <div className="min-w-0">
        <div className="truncate font-semibold text-slate-900">{a.nome}</div>
        <div className="truncate text-xs text-slate-500">{a.banca || "—"} · {a.iban || "IBAN non indicato"}</div>
      </div>
      <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${a.fonte === "psd2" ? "bg-blue-50 text-blue-700" : "bg-slate-100 text-slate-600"}`}>{a.fonte === "psd2" ? "PSD2" : "File"}</span>
    </div>
    <div className="mt-3 flex items-end justify-between">
      <div>
        <div className="text-xl font-extrabold text-slate-900" data-testid={`bank-saldo-${a.id}`}>{a.saldo != null ? fmtEUR(a.saldo) : "—"}</div>
        <div className="text-xs text-slate-500">{a.da_riconciliare} da riconciliare · {a.movimenti} movimenti</div>
      </div>
      <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
        {a.fonte === "file" && acc && <Button size="sm" variant="outline" onClick={onImport} data-testid={`bank-import-btn-${a.id}`}><Upload className="h-3.5 w-3.5" /></Button>}
        {admin && <Button size="sm" variant="outline" onClick={onDelete} data-testid={`bank-delete-btn-${a.id}`}><Trash2 className="h-3.5 w-3.5" /></Button>}
      </div>
    </div>
    {a.consenso_in_scadenza && (
      <button onClick={(e) => { e.stopPropagation(); onReconnect(); }} className="mt-2 flex items-center gap-1 text-xs font-semibold text-amber-700" data-testid={`bank-reconnect-btn-${a.id}`}>
        <AlertTriangle className="h-3.5 w-3.5" />Consenso in scadenza il {fmtDate(a.consent_expires_at)}: rinnova
      </button>
    )}
  </div>
);

const NewAccount = ({ open, onClose, onSaved }) => {
  const [f, setF] = useState({ nome: "", iban: "", banca: "" });
  const save = async () => {
    try { await api.post("/banca/conti", f); toast.success("Conto aggiunto"); setF({ nome: "", iban: "", banca: "" }); onSaved(); onClose(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-white sm:max-w-md" data-testid="new-account-dialog">
        <DialogHeader><DialogTitle>Conto per import da file</DialogTitle></DialogHeader>
        {[["nome", "Nome del conto"], ["banca", "Banca"], ["iban", "IBAN"]].map(([k, l]) => (
          <label key={k} className="block text-sm text-slate-600">{l}<Input value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} data-testid={`new-account-${k}-input`} /></label>
        ))}
        <DialogFooter><Button onClick={save} disabled={!f.nome.trim()} data-testid="new-account-save-btn">Aggiungi</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const Row = ({ m, acc, onMatch, onConfirm, onUndo, onIgnore }) => (
  <tr className="border-b border-slate-100 align-top" data-testid={`tx-row-${m.id}`}>
    <td className="whitespace-nowrap px-4 py-3 text-sm">{fmtDate(m.data)}</td>
    <td className="px-4 py-3 text-sm text-slate-700"><div className="line-clamp-2">{m.descrizione}</div>{m.controparte && <div className="text-xs text-slate-400">{m.controparte}</div>}</td>
    <td className={`whitespace-nowrap px-4 py-3 text-right text-sm font-bold ${m.importo > 0 ? "text-emerald-700" : "text-rose-700"}`}>{fmtEUR(m.importo)}</td>
    <td className="px-4 py-3 text-sm">
      {m.stato === "da_riconciliare" && m.proposta && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-md bg-blue-50 px-2 py-1 text-xs text-blue-800" data-testid={`tx-proposta-${m.id}`}>{m.proposta.label} · {m.proposta.score}%</span>
          {acc && <Button size="sm" onClick={onConfirm} data-testid={`tx-confirm-btn-${m.id}`}>Conferma</Button>}
        </div>
      )}
      {m.stato !== "da_riconciliare" && (
        <span className={`text-xs ${m.stato === "ignorato" ? "text-slate-400" : "text-emerald-800"}`} data-testid={`tx-match-${m.id}`}>
          {m.match?.label}{m.match?.auto ? " · automatica" : ""}{m.match?.non_abbinato > 0 ? ` · ${fmtEUR(m.match.non_abbinato)} non abbinati` : ""}
        </span>
      )}
    </td>
    <td className="whitespace-nowrap px-4 py-3 text-right">
      {acc && m.stato === "da_riconciliare" && <>
        <Button size="sm" variant="outline" onClick={onMatch} data-testid={`tx-match-btn-${m.id}`}><Link2 className="mr-1 h-3.5 w-3.5" />Abbina</Button>
        <Button size="sm" variant="ghost" onClick={onIgnore} title="Ignora" data-testid={`tx-ignore-btn-${m.id}`}><EyeOff className="h-3.5 w-3.5" /></Button>
      </>}
      {acc && m.stato !== "da_riconciliare" && <Button size="sm" variant="ghost" onClick={onUndo} data-testid={`tx-undo-btn-${m.id}`}><Undo2 className="mr-1 h-3.5 w-3.5" />Annulla</Button>}
    </td>
  </tr>
);

export default function Riconciliazione() {
  const { user } = useAuth();
  const acc = canSend(user), admin = isAdmin(user);
  const [params, setParams] = useSearchParams();
  const [cfg, setCfg] = useState(null);
  const [conti, setConti] = useState([]);
  const [sel, setSel] = useState(null);
  const [stato, setStato] = useState("da_riconciliare");
  const [q, setQ] = useState("");
  const [data, setData] = useState({ movimenti: [], conteggi: {} });
  const [busy, setBusy] = useState("");
  const [matchTx, setMatchTx] = useState(null);
  const [dlg, setDlg] = useState("");
  const file = useRef(null);
  const importTo = useRef(null);

  const loadConti = () => api.get("/banca/conti").then(({ data: d }) => setConti(d)).catch((e) => toast.error(errMsg(e)));
  const loadCfg = () => api.get("/banca/config").then(({ data: d }) => setCfg(d)).catch(() => {});
  const loadTx = () => api.get("/banca/movimenti", { params: { stato, account_id: sel || undefined, q: q || undefined } }).then(({ data: d }) => setData(d)).catch((e) => toast.error(errMsg(e)));
  const reload = () => { loadConti(); loadTx(); };
  useEffect(() => { loadConti(); loadCfg(); }, []);
  useEffect(() => { loadTx(); }, [stato, sel]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (params.get("psd2")) { toast.success("Autorizzazione inviata alla banca: premi Sincronizza tra qualche minuto"); setParams({}); }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const run = async (key, fn, ok) => {
    setBusy(key);
    try { const r = await fn(); if (ok) toast.success(ok(r.data)); reload(); } catch (e) { toast.error(errMsg(e)); }
    setBusy("");
  };
  const connect = () => run("connect", async () => { const r = await api.post("/banca/psd2/connect"); window.open(r.data.url, "_blank", "noopener"); return r; }, () => "Pagina della banca aperta in una nuova scheda");
  const sync = () => run("sync", () => api.post("/banca/psd2/sync"), (d) => `${d.conti} conti, ${d.nuovi} nuovi movimenti, ${d.auto} riconciliati in automatico`);
  const auto = () => run("auto", () => api.post("/banca/auto"), (d) => `${d.riconciliati} movimenti riconciliati in automatico`);
  const onFile = (e) => {
    const f = e.target.files?.[0]; e.target.value = "";
    if (!f) return;
    const fd = new FormData(); fd.append("file", f);
    run("import", () => api.post(`/banca/conti/${importTo.current}/import`, fd), (d) => `${d.formato}: ${d.nuovi} nuovi movimenti, ${d.duplicati} già presenti, ${d.auto} riconciliati in automatico`);
  };
  const reconnect = (a) => run("rec", async () => { const r = await api.get(`/banca/conti/${a.id}/reconnect`); window.open(r.data.url, "_blank", "noopener"); return r; });
  const del = (a) => window.confirm(`Eliminare il conto ${a.nome} e i suoi movimenti non riconciliati?`) && run("del", () => api.delete(`/banca/conti/${a.id}`), () => "Conto eliminato");
  const act = (m, path, body) => run(m.id, () => api.post(`/banca/movimenti/${m.id}/${path}`, body));

  return (
    <div>
      <PageHeader eyebrow="Fatturazione" title="Riconciliazione bancaria">
        {admin && <Button variant="outline" onClick={() => setDlg("cfg")} data-testid="banca-config-btn"><Settings2 className="mr-2 h-4 w-4" />Open Banking</Button>}
        {admin && <Button variant="outline" onClick={connect} disabled={!cfg?.configurato || busy === "connect"} data-testid="psd2-connect-btn"><Landmark className="mr-2 h-4 w-4" />Collega banca</Button>}
        {acc && <Button variant="outline" onClick={sync} disabled={!cfg?.configurato || busy === "sync"} data-testid="psd2-sync-btn"><RefreshCw className={`mr-2 h-4 w-4 ${busy === "sync" ? "animate-spin" : ""}`} />Sincronizza</Button>}
        {acc && <Button variant="outline" onClick={() => setDlg("new")} data-testid="add-file-account-btn"><Plus className="mr-2 h-4 w-4" />Conto da file</Button>}
        {acc && <Button onClick={auto} disabled={busy === "auto"} data-testid="auto-match-btn"><Wand2 className="mr-2 h-4 w-4" />Riconcilia automaticamente</Button>}
      </PageHeader>
      <input ref={file} type="file" accept=".csv,.txt,.cbi,.rh" className="hidden" onChange={onFile} data-testid="bank-file-input" />
      {cfg && (
        <p className={`-mt-4 mb-4 text-xs ${cfg.last_sync_error ? "text-rose-600" : "text-slate-500"}`} data-testid="banca-status">
          {cfg.configurato ? `A-Cube Open Banking · ${cfg.ambiente === "sandbox" ? "ambiente di prova" : "ambiente reale"}${cfg.usa_sdi ? " (credenziali SDI)" : ""}${cfg.auto ? " · sincronizzazione automatica ogni 6 ore" : ""}` : "Open Banking non configurato: puoi importare gli estratti conto da file CSV o CBI."}
          {cfg.last_sync_at && ` · ultima sincronizzazione ${fmtDateTime(cfg.last_sync_at)}`}{cfg.last_sync_error && ` · errore: ${cfg.last_sync_error}`}
        </p>
      )}
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3" data-testid="bank-accounts">
        {conti.length === 0 && <p className="text-sm text-slate-500" data-testid="bank-no-accounts">Nessun conto: collega la banca o aggiungi un conto per importare un file.</p>}
        {conti.map((a) => (
          <AccountCard key={a.id} a={a} active={sel === a.id} acc={acc} admin={admin} onSelect={() => setSel(sel === a.id ? null : a.id)}
            onImport={() => { importTo.current = a.id; file.current?.click(); }} onReconnect={() => reconnect(a)} onDelete={() => del(a)} />
        ))}
      </div>
      <section className="rounded-xl border border-slate-200/80 bg-white shadow-sm">
        <div className="flex flex-col gap-3 border-b border-slate-100 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap gap-2">
            {STATI.map(([k, l]) => (
              <button key={k} onClick={() => setStato(k)} data-testid={`tx-filter-${k}`}
                className={`rounded-full px-3 py-1 text-xs font-semibold ${stato === k ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}>
                {l}{k !== "tutti" && data.conteggi[k] != null ? ` (${data.conteggi[k]})` : ""}
              </button>
            ))}
          </div>
          <form onSubmit={(e) => { e.preventDefault(); loadTx(); }}><Input placeholder="Cerca nella descrizione…" value={q} onChange={(e) => setQ(e.target.value)} className="sm:w-64" data-testid="tx-search-input" /></form>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead><tr className="border-b border-slate-200 text-xs uppercase tracking-wider text-slate-500">
              <th className="px-4 py-3">Data</th><th className="px-4 py-3">Descrizione</th><th className="px-4 py-3 text-right">Importo</th><th className="px-4 py-3">Abbinamento</th><th className="px-4 py-3" />
            </tr></thead>
            <tbody>
              {data.movimenti.length === 0 && <tr><td colSpan={5} className="px-4 py-10 text-center text-sm text-slate-500" data-testid="tx-empty">Nessun movimento</td></tr>}
              {data.movimenti.map((m) => (
                <Row key={m.id} m={m} acc={acc} onMatch={() => setMatchTx(m)} onIgnore={() => act(m, "ignora")} onUndo={() => act(m, "annulla")}
                  onConfirm={() => act(m, "riconcilia", { tipo: m.proposta.tipo, ref_ids: [m.proposta.ref_id] })} />
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <MatchDialog tx={matchTx} onClose={() => setMatchTx(null)} onDone={() => { setMatchTx(null); reload(); }} />
      {dlg === "cfg" && <BancaConfigDialog cfg={cfg} open onClose={() => setDlg("")} onSaved={loadCfg} />}
      <NewAccount open={dlg === "new"} onClose={() => setDlg("")} onSaved={loadConti} />
    </div>
  );
}

import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { UploadCloud, FolderUp, FileUp, CheckCircle2, XCircle, Copy } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";

const OK_EXT = /\.(xml|p7m|zip)$/i;
const BATCH = 10;
const ICON = { ok: <CheckCircle2 className="h-4 w-4 text-emerald-600" />, duplicate: <Copy className="h-4 w-4 text-amber-600" />, error: <XCircle className="h-4 w-4 text-rose-600" /> };

const readEntry = (entry) => new Promise((resolve) => {
  if (entry.isFile) { entry.file((f) => resolve([f]), () => resolve([])); return; }
  const reader = entry.createReader();
  const all = [];
  const next = () => reader.readEntries(async (ents) => {
    if (!ents.length) { resolve((await Promise.all(all.map(readEntry))).flat()); return; }
    all.push(...ents); next();
  }, () => resolve([]));
  next();
});

const Results = ({ results }) => {
  const count = (s) => results.filter((r) => r.status === s).length;
  return (
    <div className="mt-6 rounded-xl border border-slate-200/80 bg-white shadow-sm" data-testid="arch-upload-results">
      <div className="flex flex-wrap gap-4 border-b border-slate-100 px-5 py-3 text-sm">
        <span className="text-emerald-700" data-testid="arch-res-ok">Importate: <b>{count("ok")}</b></span>
        <span className="text-amber-700" data-testid="arch-res-dup">Già presenti: <b>{count("duplicate")}</b></span>
        <span className="text-rose-700" data-testid="arch-res-err">Errori: <b>{count("error")}</b></span>
      </div>
      <div className="max-h-96 divide-y divide-slate-100 overflow-y-auto">
        {results.map((r, i) => (
          <div key={`${r.filename}-${i}`} className="flex items-start gap-3 px-5 py-2 text-sm">
            {ICON[r.status]}
            <div className="min-w-0 flex-1">
              <div className="truncate mono text-xs text-slate-500">{r.filename}</div>
              <div>{r.numero && <b>{r.numero} · </b>}{r.message}{r.id && <Link to={`/archivio/fatture/${r.id}`} className="ml-2 text-xs font-semibold text-blue-600">apri</Link>}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default function ArchUpload() {
  const fileRef = useRef(null);
  const dirRef = useRef(null);
  const [drag, setDrag] = useState(false);
  const [prog, setProg] = useState(null);
  const [results, setResults] = useState([]);

  const send = async (list) => {
    const files = list.filter((f) => OK_EXT.test(f.name));
    if (!files.length) { toast.error("Nessun file .xml, .p7m o .zip trovato"); return; }
    setResults([]);
    const out = [];
    for (let i = 0; i < files.length; i += BATCH) {
      setProg({ done: i, total: files.length });
      const fd = new FormData();
      files.slice(i, i + BATCH).forEach((f) => fd.append("files", f, f.webkitRelativePath || f.name));
      try { const { data } = await api.post("/archivio/upload", fd); out.push(...data.results); } catch (e) {
        files.slice(i, i + BATCH).forEach((f) => out.push({ filename: f.name, status: "error", message: errMsg(e) }));
      }
      setResults([...out]);
    }
    setProg(null);
    toast.success(`Elaborati ${files.length} file`);
  };

  const onDrop = async (e) => {
    e.preventDefault(); setDrag(false);
    const items = [...(e.dataTransfer.items || [])].map((it) => it.webkitGetAsEntry?.()).filter(Boolean);
    send(items.length ? (await Promise.all(items.map(readEntry))).flat() : [...e.dataTransfer.files]);
  };

  return (
    <div>
      <PageHeader eyebrow="Archivio fatture" title="Carica fatture" />
      <div onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={onDrop}
        className={`rounded-xl border-2 border-dashed p-10 text-center transition-colors ${drag ? "border-blue-500 bg-blue-50" : "border-slate-300 bg-white"}`} data-testid="arch-dropzone">
        <UploadCloud className="mx-auto h-10 w-10 text-slate-400" />
        <p className="mt-3 font-semibold text-slate-800">Trascina qui file o cartelle</p>
        <p className="mt-1 text-sm text-slate-500">XML FatturaPA, file firmati .p7m e archivi .zip (anche annidati). Le fatture vengono divise in attive e passive in base alla Partita IVA dell'azienda.</p>
        <div className="mt-5 flex flex-wrap justify-center gap-3">
          <Button onClick={() => fileRef.current.click()} disabled={!!prog} data-testid="arch-pick-files-btn"><FileUp className="mr-2 h-4 w-4" />Scegli file</Button>
          <Button variant="outline" onClick={() => dirRef.current.click()} disabled={!!prog} data-testid="arch-pick-folder-btn"><FolderUp className="mr-2 h-4 w-4" />Carica da cartella</Button>
        </div>
        <input ref={fileRef} type="file" multiple accept=".xml,.p7m,.zip" className="hidden" onChange={(e) => { send([...e.target.files]); e.target.value = ""; }} data-testid="arch-file-input" />
        <input ref={dirRef} type="file" webkitdirectory="" directory="" multiple className="hidden" onChange={(e) => { send([...e.target.files]); e.target.value = ""; }} data-testid="arch-folder-input" />
      </div>
      {prog && <div className="mt-4" data-testid="arch-upload-progress"><Progress value={(prog.done / prog.total) * 100} /><p className="mt-1 text-xs text-slate-500">{prog.done} di {prog.total} file…</p></div>}
      {results.length > 0 && <Results results={results} />}
    </div>
  );
}

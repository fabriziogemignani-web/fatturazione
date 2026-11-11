import { useEffect, useRef, useState } from "react";
import { Eraser } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";

export const RUOLI_FIRMA = [["destinatario", "Destinatario"], ["conducente", "Conducente"], ["vettore", "Vettore"]];

const Pad = ({ onChange }) => {
  const ref = useRef(null);
  const drawing = useRef(false);
  useEffect(() => {
    const c = ref.current;
    const setup = () => {
      const r = window.devicePixelRatio || 1;
      c.width = c.offsetWidth * r;
      c.height = c.offsetHeight * r;
      const ctx = c.getContext("2d");
      ctx.scale(r, r);
      ctx.lineWidth = 2.2;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.strokeStyle = "#0f172a";
      onChange(null);
    };
    setup();
    window.addEventListener("resize", setup);
    return () => window.removeEventListener("resize", setup);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const pos = (e) => { const b = ref.current.getBoundingClientRect(); return [e.clientX - b.left, e.clientY - b.top]; };
  const down = (e) => { e.preventDefault(); ref.current.setPointerCapture(e.pointerId); drawing.current = true; const ctx = ref.current.getContext("2d"); ctx.beginPath(); ctx.moveTo(...pos(e)); };
  const move = (e) => { if (!drawing.current) return; const ctx = ref.current.getContext("2d"); ctx.lineTo(...pos(e)); ctx.stroke(); };
  const up = () => { if (drawing.current) { drawing.current = false; onChange(ref.current.toDataURL("image/png")); } };
  const clear = () => { const c = ref.current; c.getContext("2d").clearRect(0, 0, c.width, c.height); onChange(null); };
  return (
    <div className="relative">
      <canvas ref={ref} className="h-48 w-full touch-none rounded-lg border-2 border-dashed border-slate-300 bg-white" onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerLeave={up} data-testid="firma-canvas" />
      <span className="pointer-events-none absolute bottom-2 left-3 text-[11px] text-slate-400">Firma qui con il dito o la penna</span>
      <button type="button" onClick={clear} className="absolute right-2 top-2 inline-flex items-center gap-1 rounded bg-slate-100 px-2 py-1 text-xs text-slate-600 hover:bg-slate-200" data-testid="firma-clear-btn"><Eraser className="h-3.5 w-3.5" />Cancella</button>
    </div>
  );
};

export const FirmaDialog = ({ ruolo, nomeDefault, onClose, onSave }) => {
  const [nome, setNome] = useState("");
  const [img, setImg] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => { if (ruolo) { setNome(nomeDefault || ""); setImg(null); setErr(""); } }, [ruolo, nomeDefault]);
  const label = RUOLI_FIRMA.find(([k]) => k === ruolo)?.[1];
  const save = async () => { setBusy(true); setErr(""); const ok = await onSave({ ruolo, nome, immagine: img }); setBusy(false); if (ok === true) onClose(); else if (typeof ok === "string") setErr(ok); };
  return (
    <Dialog open={!!ruolo} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="bg-white sm:max-w-xl" data-testid="firma-dialog">
        <DialogHeader>
          <DialogTitle>Firma {label?.toLowerCase()}</DialogTitle>
          <DialogDescription>La firma viene riportata nel PDF del DDT con nome, data e ora.</DialogDescription>
        </DialogHeader>
        <label className="block text-xs text-slate-600">Nome e cognome di chi firma<Input value={nome} onChange={(e) => setNome(e.target.value)} data-testid="firma-nome-input" /></label>
        {ruolo && <Pad key={ruolo} onChange={setImg} />}
        {err && <p className="text-sm text-rose-600" data-testid="firma-dialog-error">{err}</p>}
        <DialogFooter>
          <Button variant="outline" onClick={onClose} data-testid="firma-cancel-btn">Annulla</Button>
          <Button onClick={save} disabled={busy || !img || nome.trim().length < 2} data-testid="firma-save-btn">Conferma firma</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";

export const MenuDialog = ({ target, endpoint, title, desc, onClose, onSaved }) => {
  const [voci, setVoci] = useState([]);
  const [off, setOff] = useState(new Set());
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!target) return;
    setOff(new Set(target.menu_off || []));
    api.get("/menu-voci").then(({ data }) => setVoci(data)).catch((e) => toast.error(errMsg(e)));
  }, [target]);
  const gruppi = [...new Set(voci.map((v) => v.gruppo))];
  const toggle = (id, on) => setOff((s) => { const n = new Set(s); on ? n.delete(id) : n.add(id); return n; });
  const setGroup = (g, on) => setOff((s) => { const n = new Set(s); voci.filter((v) => v.gruppo === g).forEach((v) => (on ? n.delete(v.id) : n.add(v.id))); return n; });
  const save = async () => {
    setBusy(true);
    try { await api.put(endpoint, { off: [...off] }); toast.success("Menu aggiornato"); onSaved?.(); onClose(); } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };
  return (
    <Dialog open={!!target} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto bg-white sm:max-w-2xl" data-testid="menu-dialog">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{desc}</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {gruppi.map((g) => {
            const items = voci.filter((v) => v.gruppo === g);
            const allOn = items.every((v) => !off.has(v.id));
            return (
              <div key={g} className="rounded-lg border border-slate-200 p-3" data-testid={`menu-group-${g.replace(/\W+/g, "-").toLowerCase()}`}>
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">{g}</span>
                  <button onClick={() => setGroup(g, !allOn)} className="text-xs font-medium text-blue-600 hover:underline">{allOn ? "Spegni tutte" : "Accendi tutte"}</button>
                </div>
                {items.map((v) => (
                  <label key={v.id} className="flex items-center justify-between gap-3 py-1.5 text-sm text-slate-700">
                    {v.label}
                    <Switch checked={!off.has(v.id)} onCheckedChange={(on) => toggle(v.id, on)} data-testid={`menu-switch-${v.id}`} />
                  </label>
                ))}
              </div>
            );
          })}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} data-testid="menu-cancel-btn">Annulla</Button>
          <Button onClick={save} disabled={busy} data-testid="menu-save-btn">{busy ? "Salvataggio…" : "Salva"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

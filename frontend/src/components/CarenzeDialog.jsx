import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

export const CarenzeDialog = ({ carenze, blocca, onClose, onForza }) => (
  <Dialog open={!!carenze} onOpenChange={(v) => !v && onClose()}>
    <DialogContent className="bg-white sm:max-w-lg" data-testid="ddt-carenze-dialog">
      <DialogHeader>
        <DialogTitle>Giacenza insufficiente</DialogTitle>
        <DialogDescription>{blocca ? "Le impostazioni dell'azienda non permettono di confermare il DDT finché manca la merce." : "Confermando, la giacenza di questi articoli andrà sotto zero."}</DialogDescription>
      </DialogHeader>
      <div className="divide-y divide-slate-100 rounded-lg border border-slate-200">
        {(carenze || []).map((c) => (
          <div key={c.article_id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm" data-testid={`ddt-carenza-${c.codice}`}>
            <span className="text-slate-800">{c.codice} · {c.descrizione}</span>
            <span className="text-xs text-rose-600">richiesti {c.richiesta} · disponibili {c.disponibile} {c.unita_misura}</span>
          </div>
        ))}
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={onClose} data-testid="ddt-carenze-chiudi">{blocca ? "Chiudi" : "Annulla"}</Button>
        {!blocca && <Button onClick={onForza} className="bg-amber-600 hover:bg-amber-700" data-testid="ddt-carenze-forza">Conferma comunque</Button>}
      </DialogFooter>
    </DialogContent>
  </Dialog>
);

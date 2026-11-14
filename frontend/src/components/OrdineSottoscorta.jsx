import { useState } from "react";
import { toast } from "sonner";
import { ShoppingCart } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { OrdineDialog } from "@/components/OrdineDialog";

export const OrdineSottoscorta = ({ onDone }) => {
  const [gruppi, setGruppi] = useState(null);
  const [bozza, setBozza] = useState(null);
  const apri = async () => {
    try {
      const { data } = await api.get("/magazzino/proposta-ordine");
      if (!data.gruppi.length) { toast.info("Nessun articolo da riordinare: le disponibilità (giacenza − impegnato + ordinato) coprono le scorte minime"); return; }
      if (data.gruppi.length === 1) setBozza(data.gruppi[0]); else setGruppi(data.gruppi);
    } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <>
      <Button variant="outline" className="border-amber-300 text-amber-800 hover:bg-amber-50" onClick={apri} data-testid="ordina-sottoscorta-btn"><ShoppingCart className="mr-2 h-4 w-4" />Ordina sottoscorta</Button>
      <Dialog open={!!gruppi} onOpenChange={(v) => !v && setGruppi(null)}>
        <DialogContent className="bg-white sm:max-w-xl" data-testid="sottoscorta-gruppi">
          <DialogHeader><DialogTitle>Articoli da riordinare per fornitore</DialogTitle></DialogHeader>
          {gruppi?.map((g, i) => (
            <div key={i} className="flex items-center gap-3 border-t border-slate-100 py-2 text-sm" data-testid={`sottoscorta-gruppo-${i}`}>
              <div className="flex-1"><div className="font-medium">{g.fornitore || "Fornitore abituale non indicato"}{!g.party_id && g.fornitore && <span className="ml-1 text-xs text-amber-700">(non in anagrafica)</span>}</div><div className="text-xs text-slate-500">{g.lines.map((l) => `${l.codice} × ${l.quantita}`).join(", ")}</div></div>
              <Button size="sm" onClick={() => { setBozza(g); setGruppi(null); }} data-testid={`sottoscorta-crea-${i}`}>Crea ordine</Button>
            </div>
          ))}
        </DialogContent>
      </Dialog>
      <OrdineDialog tipo="fornitore" bozza={bozza} open={!!bozza} onOpenChange={(v) => !v && setBozza(null)} onSaved={(o) => { setBozza(null); onDone?.(o); }} />
    </>
  );
};

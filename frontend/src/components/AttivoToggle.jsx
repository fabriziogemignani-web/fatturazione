import { toast } from "sonner";
import { Power } from "lucide-react";
import { api, errMsg } from "@/lib/api";

export const AttivoBadge = ({ x }) => (x.attivo === false ? (
  <span className={`ml-2 rounded px-1.5 py-0.5 text-[10px] font-semibold ${x.sospeso ? "bg-amber-100 text-amber-800" : "bg-slate-200 text-slate-600"}`} title={x.sospeso_motivo || ""} data-testid={`attivo-badge-${x.id}`}>
    {x.sospeso ? "Sospeso" : "Disattivato"}
  </span>
) : null);

export const AttivoToggle = ({ x, url, onDone }) => {
  const off = x.attivo === false;
  const toggle = async () => {
    try { await api.put(`${url}/${x.id}/attivo`, { attivo: off }); toast.success(off ? "Riattivato" : "Disattivato: non compare più nelle scelte"); onDone(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <button onClick={toggle} title={off ? "Riattiva" : "Disattiva (resta nello storico, non compare più nelle scelte)"} data-testid={`attivo-toggle-${x.id}`}
      className={`rounded p-1.5 ${off ? "text-emerald-600 hover:bg-emerald-50" : "text-slate-500 hover:bg-amber-50 hover:text-amber-700"}`}>
      <Power className="h-4 w-4" />
    </button>
  );
};

export const rimuoviODisattiva = async (x, url, nome, onDone) => {
  if (!window.confirm(`Eliminare ${nome}?`)) return;
  try { await api.delete(`${url}/${x.id}`); toast.success("Eliminato"); onDone(); } catch (e) {
    const msg = errMsg(e);
    if (/movimentat|usat/i.test(msg) && window.confirm(`${msg}.\n\nVuoi disattivarlo? Resta nei documenti ma non compare più nelle scelte.`)) {
      try { await api.put(`${url}/${x.id}/attivo`, { attivo: false }); toast.success("Disattivato"); onDone(); } catch (e2) { toast.error(errMsg(e2)); }
    } else toast.error(msg);
  }
};

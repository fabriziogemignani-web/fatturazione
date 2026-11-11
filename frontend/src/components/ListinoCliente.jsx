import { useEffect, useMemo, useState } from "react";
import { Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { SearchPicker } from "@/components/SearchPicker";

export const ListinoCliente = ({ form, setForm }) => {
  const [articles, setArticles] = useState([]);
  useEffect(() => { api.get("/articles").then(({ data }) => setArticles(data)).catch(() => {}); }, []);
  const listino = useMemo(() => form.listino || [], [form.listino]);
  const byId = useMemo(() => Object.fromEntries(articles.map((a) => [a.id, a])), [articles]);
  const items = useMemo(() => articles.filter((a) => !listino.some((x) => x.article_id === a.id)).map((a) => ({ key: a.id, label: `${a.codice} · ${a.descrizione}`, sub: `listino base ${a.prezzo ?? 0}` })), [articles, listino]);
  const set = (l) => setForm({ ...form, listino: l });
  const upd = (i, k, v) => set(listino.map((x, j) => (j === i ? { ...x, [k]: v } : x)));
  return (
    <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-4" data-testid="party-listino-section">
      <div>
        <div className="text-sm font-semibold text-slate-800">Listino personalizzato</div>
        <p className="text-xs text-slate-500">Prezzo e sconto proposti in automatico sui DDT. Per gli articoli non in elenco si usa l'ultima vendita al cliente.</p>
      </div>
      <SearchPicker items={items} onPick={(it) => set([...listino, { article_id: it.key, prezzo: byId[it.key]?.prezzo ?? 0, sconto: "" }])} placeholder="Aggiungi articolo al listino" testId="party-listino-picker" />
      {listino.map((x, i) => (
        <div key={x.article_id} className="grid grid-cols-12 items-center gap-2" data-testid={`party-listino-row-${i}`}>
          <span className="col-span-12 truncate text-sm text-slate-800 sm:col-span-6">{byId[x.article_id] ? `${byId[x.article_id].codice} · ${byId[x.article_id].descrizione}` : "Articolo eliminato"}</span>
          <Input className="col-span-5 sm:col-span-3" type="number" min="0" step="0.01" value={x.prezzo} onChange={(e) => upd(i, "prezzo", e.target.value === "" ? 0 : Number(e.target.value))} data-testid={`party-listino-prezzo-${i}`} />
          <Input className="col-span-5 sm:col-span-2" placeholder="Sc.% es. 10+5" value={x.sconto || ""} onChange={(e) => upd(i, "sconto", e.target.value)} data-testid={`party-listino-sconto-${i}`} />
          <button type="button" onClick={() => set(listino.filter((_, j) => j !== i))} className="col-span-2 justify-self-end rounded p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600 sm:col-span-1" data-testid={`party-listino-remove-${i}`}><Trash2 className="h-4 w-4" /></button>
        </div>
      ))}
    </div>
  );
};

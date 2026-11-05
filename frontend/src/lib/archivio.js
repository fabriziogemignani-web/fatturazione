import { api } from "@/lib/api";

export const TD_LABEL = { TD01: "Fattura", TD02: "Acconto su fattura", TD03: "Acconto su parcella", TD04: "Nota di credito", TD05: "Nota di debito", TD06: "Parcella", TD16: "Integrazione reverse charge interno", TD17: "Autofattura servizi estero", TD18: "Acquisto beni intra UE", TD19: "Acquisto beni art.17", TD20: "Autofattura regolarizzazione", TD24: "Fattura differita", TD25: "Fattura differita art.21", TD26: "Cessione beni ammortizzabili", TD27: "Autoconsumo / cessioni gratuite" };
export const TD_TONE = { TD01: "bg-slate-100 text-slate-700", TD04: "bg-rose-50 text-rose-700", TD05: "bg-amber-50 text-amber-700", TD24: "bg-blue-50 text-blue-700" };

export const downloadBlob = async (url, params, fallbackName) => {
  const res = await api.get(url, { params, responseType: "blob" });
  const cd = res.headers["content-disposition"] || "";
  const name = (cd.match(/filename="([^"]+)"/) || [])[1] || fallbackName;
  const href = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = href;
  a.download = name;
  a.click();
  URL.revokeObjectURL(href);
};

export const DocBadge = ({ code }) => code ? (
  <span title={TD_LABEL[code] || code} className={`mono rounded px-1.5 py-0.5 text-[11px] font-semibold ${TD_TONE[code] || "bg-violet-50 text-violet-700"}`}>{code}</span>
) : null;

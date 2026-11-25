import axios from "axios";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const api = axios.create({ baseURL: API, withCredentials: true, headers: { "X-Requested-With": "invoix" } });

api.interceptors.request.use((cfg) => {
  const cid = localStorage.getItem("fe_company_id");
  if (cid) cfg.headers["X-Company-Id"] = cid;
  return cfg;
});

export const ultimiErrori = [];
const ricorda = (s) => { if (s && ultimiErrori[0] !== s) { ultimiErrori.unshift(s); ultimiErrori.length = Math.min(ultimiErrori.length, 5); } };

api.interceptors.response.use((r) => r, (e) => {
  if (!String(e?.config?.url || "").startsWith("/ai/assistente")) ricorda(`${e?.response?.status || "rete"} ${e?.config?.method?.toUpperCase() || ""} ${e?.config?.url || ""}: ${typeof e?.response?.data?.detail === "string" ? e.response.data.detail : JSON.stringify(e?.response?.data?.detail || e?.message || "")}`.slice(0, 300));
  return Promise.reject(e);
});
if (typeof window !== "undefined") window.addEventListener("error", (ev) => ricorda(`Errore nella pagina: ${ev.message}`));

export const ver = (doc) => ({ headers: { "If-Match": String(doc?.version ?? 0) } });

export const errMsg = (e) => {
  const d = e?.response?.data?.detail;
  if (Array.isArray(d)) {
    if (d.length > 1) return `Correggi i ${d.length} campi evidenziati in rosso`;
    const msg = (d[0]?.msg || "").replace("Value error, ", "");
    const loc = d[0]?.loc || [];
    return loc[1] === "lines" && Number.isInteger(loc[2]) ? `Riga ${loc[2] + 1}: ${msg}` : msg;
  }
  return d || e?.message || "Errore imprevisto";
};

export const errFields = (e) => {
  const d = e?.response?.data?.detail;
  const m = new Map();
  if (Array.isArray(d)) d.forEach((x) => {
    const k = (x.loc || []).slice(1).join(".");
    if (k && !m.has(k)) m.set(k, (x.msg || "").replace("Value error, ", ""));
  });
  return m;
};

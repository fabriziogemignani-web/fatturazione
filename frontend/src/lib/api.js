import axios from "axios";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const api = axios.create({ baseURL: API, withCredentials: true });

api.interceptors.request.use((cfg) => {
  const cid = localStorage.getItem("fe_company_id");
  if (cid) cfg.headers["X-Company-Id"] = cid;
  return cfg;
});

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

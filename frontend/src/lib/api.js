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
  if (Array.isArray(d)) return d.map((x) => (x.msg || "").replace("Value error, ", "")).join(" · ");
  return d || e?.message || "Errore imprevisto";
};

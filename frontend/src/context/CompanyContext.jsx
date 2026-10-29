import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";

const KEY = "fe_company_id";
const CompanyCtx = createContext(null);

export const CompanyProvider = ({ children }) => {
  const [companies, setCompanies] = useState(null);
  const [current, setCurrentState] = useState(localStorage.getItem(KEY));

  const setCurrent = (id) => {
    if (id) localStorage.setItem(KEY, id);
    else localStorage.removeItem(KEY);
    setCurrentState(id);
  };

  const reload = useCallback(async () => {
    const { data } = await api.get("/companies");
    setCompanies(data);
    const saved = localStorage.getItem(KEY);
    if (!data.some((c) => c.id === saved)) setCurrent(data[0]?.id || null);
    return data;
  }, []);

  useEffect(() => { reload(); }, [reload]);

  useEffect(() => {
    const onStorage = (e) => {
      if (e.key === KEY) setCurrentState(e.newValue);
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const company = companies?.find((c) => c.id === current) || null;
  return <CompanyCtx.Provider value={{ companies, current, company, setCurrent, reload }}>{children}</CompanyCtx.Provider>;
};

export const useCompany = () => useContext(CompanyCtx);

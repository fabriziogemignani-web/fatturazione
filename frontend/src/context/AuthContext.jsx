import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";

const AuthCtx = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const checkAuth = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  const logout = async () => {
    await api.post("/auth/logout").catch(() => {});
    setUser(null);
  };

  return <AuthCtx.Provider value={{ user, setUser, loading, checkAuth, logout }}>{children}</AuthCtx.Provider>;
};

export const useAuth = () => useContext(AuthCtx);

export const canSend = (u) => ["admin", "contabile"].includes(u?.role);
export const isAdmin = (u) => u?.role === "admin";
export const can = (u, k) => u?.role === "admin" || !!u?.diritti?.[k];
export const canAny = (u, ks) => [].concat(ks).some((k) => can(u, k));

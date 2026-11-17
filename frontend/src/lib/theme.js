import { useEffect, useState } from "react";

const KEY = "fe_dash_dark";
const EVT = "fe-theme";
const isDark = () => localStorage.getItem(KEY) === "1";

export const applyTheme = () => document.body.classList.toggle("dash-dark", isDark());

export const useTheme = () => {
  const [dark, setDarkState] = useState(isDark);
  useEffect(() => {
    const on = () => setDarkState(isDark());
    window.addEventListener(EVT, on);
    return () => window.removeEventListener(EVT, on);
  }, []);
  const setDark = (v) => {
    localStorage.setItem(KEY, v ? "1" : "0");
    applyTheme();
    window.dispatchEvent(new Event(EVT));
  };
  return [dark, setDark];
};

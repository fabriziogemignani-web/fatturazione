import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const cache = {};

export const useCapitoli = (uid) => {
  const [c, setC] = useState(cache[uid] || []);
  useEffect(() => {
    if (!uid || cache[uid]) { setC(cache[uid] || []); return; }
    api.get("/guida").then(({ data }) => { cache[uid] = data; setC(data); }).catch(() => {});
  }, [uid]);
  return c;
};

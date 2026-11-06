export const MODULI = ["fatturazione", "archivio", "fatture_attive", "fatture_passive", "corrispettivi"];

export const mods = (c) => Object.fromEntries(MODULI.map((k) => [k, c?.moduli?.[k] !== false]));

const RULES = [
  [/^\/archivio/, ["archivio"]],
  [/^\/(passive|registro-iva-acquisti|scadenzario-fornitori)/, ["fatturazione", "fatture_passive"]],
  [/^\/(fatture|registro|scadenzario$|registro-iva-vendite)/, ["fatturazione", "fatture_attive"]],
  [/^\/corrispettivi/, ["fatturazione", "corrispettivi"]],
  [/^\/(dashboard|liquidazione-iva|anagrafiche|articoli|esportazione|riconciliazione)/, ["fatturazione"]],
];

export const pathAllowed = (path, m) => {
  const rule = RULES.find(([rx]) => rx.test(path));
  return !rule || rule[1].every((k) => m[k]);
};

const MOD_LABEL = { fatture_attive: "Attive", fatture_passive: "Passive", corrispettivi: "Corrispettivi", archivio: "Archivio" };
export const modSummary = (c) => {
  const m = mods(c);
  const on = Object.keys(MOD_LABEL).filter((k) => m[k] && (k === "archivio" || m.fatturazione));
  return on.map((k) => MOD_LABEL[k]).join(" · ") || "nessuno";
};

export const homeFor = (m) => (m.fatturazione ? "/dashboard" : m.archivio ? "/archivio" : "/impostazioni");

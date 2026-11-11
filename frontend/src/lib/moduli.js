export const MODULI = ["fatturazione", "archivio", "fatture_attive", "fatture_passive", "corrispettivi", "contabilita"];

export const mods = (c) => Object.fromEntries(MODULI.map((k) => [k, c?.moduli?.[k] !== false]));

const RULES = [
  [/^\/archivio/, ["archivio"]],
  [/^\/(passive|registro-iva-acquisti|scadenzario-fornitori|ritenute)/, ["fatturazione", "fatture_passive"]],
  [/^\/(fatture|registro|scadenzario$|registro-iva-vendite|comunicazioni|ddt|fatturazione-differita)/, ["fatturazione", "fatture_attive"]],
  [/^\/corrispettivi/, ["fatturazione", "corrispettivi"]],
  [/^\/contabilita/, ["fatturazione", "contabilita"]],
  [/^\/(dashboard|liquidazione-iva|anagrafiche|articoli|esportazione|riconciliazione|previsione-cassa|magazzino|conservazione)/, ["fatturazione"]],
];

export const pathAllowed = (path, m, off) => {
  const rule = RULES.find(([rx]) => rx.test(path));
  if (rule && !rule[1].every((k) => m[k])) return false;
  const item = MENU_ROUTES.find(([, rx]) => rx.test(path));
  return !item || !off?.has(item[0]);
};

const MENU_ROUTES = [
  ["fatture", /^\/fatture/], ["fatturazione-differita", /^\/fatturazione-differita/], ["ddt", /^\/ddt/], ["registro", /^\/registro$/], ["scadenzario", /^\/scadenzario$/], ["comunicazioni", /^\/comunicazioni/], ["passive", /^\/passive/],
  ["scadenzario-fornitori", /^\/scadenzario-fornitori/], ["registro-iva-vendite", /^\/registro-iva-vendite/], ["registro-iva-acquisti", /^\/registro-iva-acquisti/],
  ["liquidazione-iva", /^\/liquidazione-iva/], ["ritenute", /^\/ritenute/], ["corrispettivi", /^\/corrispettivi/], ["esportazione", /^\/esportazione/], ["conservazione", /^\/conservazione/],
  ["prima-nota", /^\/contabilita\/prima-nota/], ["mastrini", /^\/contabilita\/mastrini/], ["bilancio", /^\/contabilita\/bilancio/],
  ["chiusura", /^\/contabilita\/chiusura/], ["piano-conti", /^\/contabilita\/piano-conti/], ["riconciliazione", /^\/riconciliazione/],
  ["previsione-cassa", /^\/previsione-cassa/], ["magazzino", /^\/magazzino/], ["anagrafiche", /^\/anagrafiche/], ["articoli", /^\/articoli/],
  ["arch-carica", /^\/archivio\/carica/], ["arch-attive", /^\/archivio\/attiva/], ["arch-passive", /^\/archivio\/passiva/], ["arch-anagrafiche", /^\/archivio\/anagrafiche/],
];

const DIRITTO_ROUTES = [[/^\/contabilita\/piano-conti/, "tabelle_contabili"], [/^\/(articoli|magazzino)/, "articoli_magazzino"], [/^\/impostazioni/, ["dati_azienda", "banche"]]];
export const dirittoFor = (path) => DIRITTO_ROUTES.find(([rx]) => rx.test(path))?.[1];

export const menuOff = (c) => new Set(c?.menu_off || []);
export const vede = (c, id) => !menuOff(c).has(id);

const MOD_LABEL = { fatture_attive: "Attive", fatture_passive: "Passive", corrispettivi: "Corrispettivi", contabilita: "Contabilità", archivio: "Archivio" };
export const modSummary = (c) => {
  const m = mods(c);
  const on = Object.keys(MOD_LABEL).filter((k) => m[k] && (k === "archivio" || m.fatturazione));
  return on.map((k) => MOD_LABEL[k]).join(" · ") || "nessuno";
};

export const homeFor = (m) => (m.fatturazione ? "/dashboard" : m.archivio ? "/archivio" : "/impostazioni");

export const MODULI = ["fatturazione", "archivio", "fatture_attive", "fatture_passive", "corrispettivi", "contabilita"];

export const mods = (c) => Object.fromEntries(MODULI.map((k) => [k, c?.moduli?.[k] !== false]));

const RULES = [
  [/^\/archivio/, ["archivio"]],
  [/^\/(passive|registro-iva-acquisti|scadenzario-fornitori|pagamenti-fornitori|ritenute|ordini-fornitori|bem)/, ["fatturazione", "fatture_passive"]],
  [/^\/(fatture|invio-sdi|registro|scadenzario$|registro-iva-vendite|bolli-virtuali|comunicazioni|ddt|fatturazione-differita|ordini-clienti)/, ["fatturazione", "fatture_attive"]],
  [/^\/corrispettivi/, ["fatturazione", "corrispettivi"]],
  [/^\/contabilita/, ["fatturazione", "contabilita"]],
  [/^\/(dashboard|liquidazione-iva|storico-f24|codici-tributo|anagrafiche|articoli|esportazione|riconciliazione|previsione-cassa|situazione-finanziaria|rateizzazioni|finanziamenti|magazzino|conservazione|produzione|porto)/, ["fatturazione"]],
];

export const pathAllowed = (path, m, off) => {
  const rule = RULES.find(([rx]) => rx.test(path));
  if (rule && !rule[1].every((k) => m[k])) return false;
  const item = MENU_ROUTES.find(([, rx]) => rx.test(path));
  return !item || !off?.has(item[0]);
};

const MENU_ROUTES = [
  ["fatture", /^\/fatture/], ["invio-sdi", /^\/invio-sdi/], ["fatturazione-differita", /^\/fatturazione-differita/], ["ddt", /^\/ddt/], ["ordini-clienti", /^\/ordini-clienti/], ["ordini-fornitori", /^\/ordini-fornitori/], ["bem", /^\/bem/], ["registro", /^\/registro$/], ["scadenzario", /^\/scadenzario$/], ["comunicazioni", /^\/comunicazioni/], ["passive", /^\/passive/],
  ["scadenzario-fornitori", /^\/scadenzario-fornitori/], ["pagamenti-fornitori", /^\/pagamenti-fornitori/], ["registro-iva-vendite", /^\/registro-iva-vendite/], ["bolli-virtuali", /^\/bolli-virtuali/], ["registro-iva-acquisti", /^\/registro-iva-acquisti/], ["stampe-fiscali", /^\/stampe-fiscali/], ["consulente-ia", /^\/consulente-ia/],
  ["liquidazione-iva", /^\/liquidazione-iva/], ["storico-f24", /^\/storico-f24/], ["codici-tributo", /^\/codici-tributo/], ["ritenute", /^\/ritenute/], ["corrispettivi", /^\/corrispettivi/], ["esportazione", /^\/esportazione/], ["conservazione", /^\/conservazione/],
  ["prima-nota", /^\/contabilita\/prima-nota/], ["mastrini", /^\/contabilita\/mastrini/], ["bilancio", /^\/contabilita\/bilancio/], ["ratei-risconti", /^\/contabilita\/ratei-risconti/], ["carte", /^\/contabilita\/carte/],
  ["chiusura", /^\/contabilita\/chiusura/], ["piano-conti", /^\/contabilita\/piano-conti/], ["riconciliazione", /^\/riconciliazione/],
  ["previsione-cassa", /^\/previsione-cassa/], ["situazione-finanziaria", /^\/situazione-finanziaria/], ["rateizzazioni", /^\/rateizzazioni/], ["finanziamenti", /^\/finanziamenti/], ["magazzino", /^\/magazzino/], ["distinte-base", /^\/produzione\/distinte/], ["centri-lavoro", /^\/produzione\/centri/], ["mrp", /^\/produzione\/mrp/], ["produzione", /^\/produzione/], ["anagrafiche", /^\/anagrafiche/], ["articoli", /^\/articoli/],
  ["porto-mappa", /^\/porto\/mappa/], ["porto-planning", /^\/porto\/planning/], ["porto-contratti", /^\/porto\/contratti/], ["porto-transiti", /^\/porto\/transiti/], ["porto-barche", /^\/porto\/barche/], ["porto-config", /^\/porto\/configurazione/],
  ["arch-carica", /^\/archivio\/carica/], ["arch-attive", /^\/archivio\/attiva/], ["arch-passive", /^\/archivio\/passiva/], ["arch-anagrafiche", /^\/archivio\/anagrafiche/],
];

const DIRITTO_ROUTES = [[/^\/contabilita\/piano-conti/, "tabelle_contabili"], [/^\/(articoli|magazzino|produzione)/, "articoli_magazzino"], [/^\/impostazioni/, ["dati_azienda", "banche"]]];
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

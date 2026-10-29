export const STATUS = {
  bozza: { label: "Bozza", cls: "bg-amber-100 text-amber-800 border-amber-300" },
  inviata: { label: "Inviata allo SDI", cls: "bg-blue-100 text-blue-800 border-blue-300" },
  consegnata: { label: "Consegnata", cls: "bg-emerald-100 text-emerald-800 border-emerald-300" },
  scartata: { label: "Scartata dallo SDI", cls: "bg-rose-100 text-rose-800 border-rose-300" },
};

export const ALIQUOTE = [22, 10, 5, 4, 0];

export const NATURE = [
  ["N1", "N1 - Escluse art. 15"],
  ["N2.1", "N2.1 - Non soggette art. 7"],
  ["N2.2", "N2.2 - Non soggette altri casi"],
  ["N3.1", "N3.1 - Esportazioni"],
  ["N3.2", "N3.2 - Cessioni intracomunitarie"],
  ["N3.5", "N3.5 - Dichiarazioni d'intento"],
  ["N4", "N4 - Esenti"],
  ["N5", "N5 - Regime del margine"],
  ["N6.1", "N6.1 - Reverse charge rottami"],
  ["N6.9", "N6.9 - Reverse charge altri casi"],
  ["N7", "N7 - IVA assolta in altro stato UE"],
];

export const TIPI_DOC = [
  ["TD01", "TD01 - Fattura"],
  ["TD04", "TD04 - Nota di credito"],
  ["TD05", "TD05 - Nota di debito"],
  ["TD06", "TD06 - Parcella"],
];

export const MODALITA = [
  ["MP05", "Bonifico"],
  ["MP01", "Contanti"],
  ["MP02", "Assegno"],
  ["MP08", "Carta di pagamento"],
  ["MP12", "RIBA"],
];

export const REGIMI = [
  ["RF01", "RF01 - Ordinario"],
  ["RF02", "RF02 - Contribuenti minimi"],
  ["RF04", "RF04 - Agricoltura"],
  ["RF19", "RF19 - Forfettario"],
];

export const ROLES = [
  ["admin", "Admin"],
  ["contabile", "Contabile"],
  ["operatore", "Operatore"],
];

const eur = new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" });
export const fmtEUR = (v) => eur.format(Number(v || 0));

export const fmtDate = (s) => {
  if (!s) return "—";
  const d = new Date(s.length === 10 ? `${s}T00:00:00` : s);
  return d.toLocaleDateString("it-IT");
};

export const fmtDateTime = (s) => (s ? new Date(s).toLocaleString("it-IT") : "—");

const r2 = (n) => Math.round((n + Number.EPSILON) * 100) / 100;

export const computeTotals = (lines) => {
  const groups = {};
  lines.forEach((l) => {
    const tot = r2(Number(l.quantita || 0) * Number(l.prezzo_unitario || 0));
    const aliq = Number(l.aliquota);
    const key = `${aliq}|${aliq === 0 ? l.natura || "" : ""}`;
    groups[key] = groups[key] || { aliquota: aliq, natura: aliq === 0 ? l.natura : null, imponibile: 0 };
    groups[key].imponibile += tot;
  });
  const riepilogo = Object.values(groups).map((g) => ({ ...g, imponibile: r2(g.imponibile), imposta: r2((g.imponibile * g.aliquota) / 100) }));
  const imponibile = r2(riepilogo.reduce((a, g) => a + g.imponibile, 0));
  const iva = r2(riepilogo.reduce((a, g) => a + g.imposta, 0));
  return { riepilogo, imponibile, iva, totale: r2(imponibile + iva) };
};

export const today = () => new Date().toISOString().slice(0, 10);

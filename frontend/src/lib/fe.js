export const STATUS = {
  bozza: { label: "Bozza", cls: "bg-amber-100 text-amber-800 border-amber-300" },
  inviata: { label: "Inviata allo SDI", cls: "bg-blue-100 text-blue-800 border-blue-300" },
  consegnata: { label: "Consegnata", cls: "bg-emerald-100 text-emerald-800 border-emerald-300" },
  mancata_consegna: { label: "Mancata consegna", cls: "bg-orange-100 text-orange-800 border-orange-300" },
  scartata: { label: "Scartata dallo SDI", cls: "bg-rose-100 text-rose-800 border-rose-300" },
};

export const NOTIFICHE = [
  { key: "attesa", code: "—", label: "In attesa di esito", desc: "Trasmesse, nessuna notifica SDI ancora ricevuta", bar: "bg-blue-500", text: "text-blue-700" },
  { key: "RC", code: "RC", label: "Ricevuta di consegna", desc: "Recapitate al destinatario", bar: "bg-emerald-500", text: "text-emerald-700" },
  { key: "MC", code: "MC", label: "Mancata consegna", desc: "Disponibili nell'area riservata del cliente", bar: "bg-orange-500", text: "text-orange-700" },
  { key: "NS", code: "NS", label: "Notifica di scarto", desc: "Da correggere e reinviare entro 5 giorni", bar: "bg-rose-500", text: "text-rose-700" },
];

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

export const computeTotals = (lines, cassa, ritenuta, split = false) => {
  const groups = {};
  const add = (aliquota, natura, amount) => {
    const aliq = Number(aliquota);
    const key = `${aliq}|${aliq === 0 ? natura || "" : ""}`;
    groups[key] = groups[key] || { aliquota: aliq, natura: aliq === 0 ? natura : null, imponibile: 0 };
    groups[key].imponibile += amount;
  };
  let base = 0;
  lines.forEach((l) => {
    const tot = r2(Number(l.quantita || 0) * Number(l.prezzo_unitario || 0));
    base += tot;
    add(l.aliquota, l.natura, tot);
  });
  const cassa_importo = cassa ? r2((base * Number(cassa.aliquota || 0)) / 100) : 0;
  if (cassa) add(cassa.aliquota_iva, cassa.natura, cassa_importo);
  const ritBase = ritenuta ? base + (cassa?.ritenuta ? cassa_importo : 0) : 0;
  const ritenuta_importo = ritenuta ? r2((ritBase * Number(ritenuta.aliquota || 0)) / 100) : 0;
  const riepilogo = Object.values(groups).map((g) => ({ ...g, imponibile: r2(g.imponibile), imposta: r2((g.imponibile * g.aliquota) / 100) }));
  const imponibile = r2(riepilogo.reduce((a, g) => a + g.imponibile, 0));
  const iva = r2(riepilogo.reduce((a, g) => a + g.imposta, 0));
  const totale = r2(imponibile + iva);
  const iva_split = split ? iva : 0;
  return { riepilogo, imponibile, iva, totale, cassa_importo, ritenuta_importo, iva_split, netto: r2(totale - ritenuta_importo - iva_split) };
};

export const CASSE = [
  ["TC01", "TC01 - Avvocati e procuratori"], ["TC02", "TC02 - Dottori commercialisti"], ["TC03", "TC03 - Geometri"],
  ["TC04", "TC04 - Ingegneri e architetti"], ["TC05", "TC05 - Notariato"], ["TC06", "TC06 - Ragionieri"],
  ["TC07", "TC07 - ENASARCO"], ["TC08", "TC08 - ENPACL consulenti del lavoro"], ["TC09", "TC09 - ENPAM medici"],
  ["TC10", "TC10 - ENPAF farmacisti"], ["TC11", "TC11 - ENPAV veterinari"], ["TC12", "TC12 - ENPAIA"],
  ["TC13", "TC13 - Fondo spedizionieri"], ["TC14", "TC14 - INPGI giornalisti"], ["TC15", "TC15 - ONAOSI"],
  ["TC16", "TC16 - CASAGIT"], ["TC17", "TC17 - EPPI periti industriali"], ["TC18", "TC18 - EPAP"],
  ["TC19", "TC19 - ENPAB biologi"], ["TC20", "TC20 - ENPAPI infermieri"], ["TC21", "TC21 - ENPAP psicologi"],
  ["TC22", "TC22 - INPS (gestione separata)"],
];

export const RITENUTE = [
  ["RT01", "RT01 - Persone fisiche"], ["RT02", "RT02 - Persone giuridiche"], ["RT03", "RT03 - Contributo INPS"],
  ["RT04", "RT04 - Contributo ENASARCO"], ["RT05", "RT05 - Contributo ENPAM"], ["RT06", "RT06 - Altro contributo previdenziale"],
];

export const CAUSALI = [
  ["A", "A - Lavoro autonomo abituale"], ["B", "B - Diritti d'autore"], ["C", "C - Utili da contratti di associazione"],
  ["D", "D - Utili soci promotori"], ["L", "L - Diritti d'autore (non autore)"], ["M", "M - Lavoro autonomo occasionale"],
  ["O", "O - Occasionale senza obbligo di iscrizione"], ["Q", "Q - Provvigioni agente monomandatario"],
  ["R", "R - Provvigioni agente plurimandatario"], ["S", "S - Provvigioni commissionario"], ["T", "T - Provvigioni mediatore"],
  ["U", "U - Procacciatore d'affari"], ["V", "V - Vendita a domicilio"], ["W", "W - Contratti d'appalto"],
  ["ZO", "ZO - Titolo diverso"],
];

export const UNITA = ["", "pz", "h", "gg", "kg", "m", "mq", "lt", "forfait"];

export const today = () => new Date().toISOString().slice(0, 10);

export const METODI_INCASSO = [
  ["bonifico", "Bonifico"], ["riba", "RiBa"], ["rid", "SDD / RID"], ["carta", "Carta"], ["contanti", "Contanti"],
  ["assegno", "Assegno"], ["altro", "Altro"], ["compensazione", "Compensazione con nota di credito"],
];

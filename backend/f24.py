from datetime import date, timedelta
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

CREDITI_SUGGERITI = [
    ("6099", "Credito IVA da dichiarazione annuale"), ("1627", "Eccedenza versamenti ritenute lavoro dipendente"),
    ("1631", "Somme a credito rimborsate dal sostituto (730)"), ("1655", "Recupero versamenti in eccesso"),
    ("2003", "IRES - credito da dichiarazione"), ("3800", "IRAP - credito da dichiarazione"),
]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]


def _lavorativo(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def tributo(anno: int, periodicita: str, periodo: int) -> dict:
    if periodicita == "mensile":
        y, m = (anno + 1, 1) if periodo == 12 else (anno, periodo + 1)
        return {"codice": f"60{periodo:02d}", "descrizione": f"Versamento IVA mensile {MESI[periodo - 1]}", "anno_riferimento": anno,
                "scadenza": _lavorativo(date(y, m, 16)).isoformat()}
    if periodo == 4:
        return {"codice": "6099", "descrizione": "Versamento IVA sulla base della dichiarazione annuale (saldo 4° trimestre)",
                "anno_riferimento": anno, "scadenza": _lavorativo(date(anno + 1, 3, 16)).isoformat()}
    return {"codice": f"603{periodo}", "descrizione": f"Versamento IVA trimestrale {periodo}° trimestre", "anno_riferimento": anno,
            "scadenza": _lavorativo(date(anno, (5, 8, 11)[periodo - 1], (16, 20, 16)[periodo - 1])).isoformat()}


def eur(v: float) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def itd(d: str) -> str:
    return "/".join(reversed(d[:10].split("-"))) if d else ""


def build_pdf(company: dict, banca: dict, debito: dict, crediti: list, data_versamento: str) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
                            title=f"F24 IVA {debito['codice']} {debito['anno_riferimento']}")
    st = ParagraphStyle("b", fontName="Helvetica", fontSize=8.5, leading=11)
    sm = ParagraphStyle("s", parent=st, fontSize=7, leading=9, textColor=colors.HexColor("#475569"))
    lab = ParagraphStyle("l", parent=st, fontSize=6.5, leading=8, textColor=colors.HexColor("#475569"))
    blue = colors.HexColor("#1e3a8a")
    grid = [("GRID", (0, 0), (-1, -1), 0.6, blue), ("VALIGN", (0, 0), (-1, -1), "TOP")]
    p = lambda t, s=st: Paragraph(escape(str(t or "")), s)  # noqa: E731
    w = doc.width
    el = []
    el.append(Table([[Paragraph("<b>MODELLO DI PAGAMENTO UNIFICATO</b>", ParagraphStyle("t", parent=st, fontSize=11, textColor=blue)),
                      Paragraph("<b>F24</b>", ParagraphStyle("f", parent=st, fontSize=22, leading=24, textColor=blue, alignment=2))]],
                    colWidths=[w * 0.75, w * 0.25]))
    el.append(Table([[p("DELEGA IRREVOCABILE A:", lab), p(banca.get("nome") or "", st), p("PER L'ACCREDITO ALLA TESORERIA COMPETENTE", lab)]],
                    colWidths=[w * 0.22, w * 0.43, w * 0.35], style=grid))
    el.append(Spacer(1, 3 * mm))
    cf = company.get("codice_fiscale") or company.get("partita_iva") or ""
    dom = f"{company.get('indirizzo') or ''} - {company.get('cap') or ''} {company.get('comune') or ''} {('(' + company['provincia'] + ')') if company.get('provincia') else ''}"
    el.append(Table([
        [p("CONTRIBUENTE", ParagraphStyle("h", parent=st, textColor=colors.white, fontName="Helvetica-Bold")), "", ""],
        [p("CODICE FISCALE", lab), p("COGNOME, DENOMINAZIONE O RAGIONE SOCIALE", lab), p("PARTITA IVA", lab)],
        [Paragraph(f"<font name='Courier-Bold' size='11'>{escape(cf)}</font>", st), p(company.get("denominazione")), p(company.get("partita_iva"))],
        [p("DOMICILIO FISCALE", lab), p(dom), ""],
    ], colWidths=[w * 0.28, w * 0.5, w * 0.22], style=grid + [("BACKGROUND", (0, 0), (-1, 0), blue), ("SPAN", (0, 0), (-1, 0)), ("SPAN", (1, 3), (2, 3))]))
    el.append(Spacer(1, 3 * mm))
    head = [p(x, lab) for x in ("codice tributo", "rateazione/regione/prov./mese rif.", "anno di riferimento", "importi a debito versati", "importi a credito compensati")]
    rows = [[p(debito["codice"]), p(""), p(debito["anno_riferimento"]), Paragraph(f"<para alignment='right'>{eur(debito['importo'])}</para>", st), p("")]]
    rows += [[p(c["codice"]), p(""), p(c["anno"]), p(""), Paragraph(f"<para alignment='right'>{eur(c['importo'])}</para>", st)] for c in crediti]
    while len(rows) < 6:
        rows.append([""] * 5)
    tot_c = round(sum(c["importo"] for c in crediti), 2)
    saldo = round(debito["importo"] - tot_c, 2)
    rows.append([p("", st), p("", st), p("TOTALE", lab), Paragraph(f"<para alignment='right'><b>A</b> {eur(debito['importo'])}</para>", st),
                 Paragraph(f"<para alignment='right'><b>B</b> {eur(tot_c)}</para>", st)])
    rows.append(["", "", p("+/- SALDO (A-B)", lab), Paragraph(f"<para alignment='right'><b>{eur(saldo)}</b></para>", st), ""])
    n = len(rows)
    el.append(Table([[p("SEZIONE ERARIO", ParagraphStyle("h2", parent=st, textColor=colors.white, fontName="Helvetica-Bold")), "", "", "", ""], head] + rows,
                    colWidths=[w * 0.15, w * 0.22, w * 0.15, w * 0.24, w * 0.24],
                    style=grid + [("BACKGROUND", (0, 0), (-1, 0), blue), ("SPAN", (0, 0), (-1, 0)), ("SPAN", (3, n + 1), (4, n + 1)),
                                  ("BACKGROUND", (0, n), (-1, n + 1), colors.HexColor("#eff6ff"))]))
    el.append(Spacer(1, 2 * mm))
    el.append(p(f"Codice {debito['codice']}: {debito['descrizione']}." + "".join(f" Codice {c['codice']}: {c.get('descrizione') or 'credito compensato'}." for c in crediti), sm))
    el.append(Spacer(1, 4 * mm))
    el.append(Table([[p("SALDO FINALE", ParagraphStyle("h3", parent=st, fontName="Helvetica-Bold")), p("EURO", lab),
                      Paragraph(f"<para alignment='right'><font size='13'><b>{eur(saldo)}</b></font></para>", st)]],
                    colWidths=[w * 0.5, w * 0.15, w * 0.35], style=grid))
    el.append(Spacer(1, 3 * mm))
    el.append(Table([
        [p("ESTREMI DEL VERSAMENTO (DA COMPILARE A CURA DI BANCA/POSTE/AGENTE DELLA RISCOSSIONE)", lab), "", "", ""],
        [p("DATA", lab), p("CODICE BANCA/POSTE (ABI)", lab), p("CAB/SPORTELLO", lab), p("PAGAMENTO EFFETTUATO CON ADDEBITO SU C/C IBAN", lab)],
        [p(itd(data_versamento)), p(banca.get("abi")), p(banca.get("cab")), Paragraph(f"<font name='Courier' size='8'>{escape(banca.get('iban') or '')}</font>", st)],
        [p("FIRMA", lab), "", "", ""], ["", "", "", ""],
    ], colWidths=[w * 0.18, w * 0.2, w * 0.17, w * 0.45], rowHeights=[None, None, None, None, 12 * mm],
        style=grid + [("SPAN", (0, 0), (-1, 0)), ("SPAN", (0, 3), (-1, 3)), ("SPAN", (0, 4), (-1, 4))]))
    el.append(Spacer(1, 5 * mm))
    note = (f"Scadenza del versamento: {itd(debito['scadenza'])}. Documento predisposto dal programma di fatturazione sulla base della liquidazione IVA: "
            "verificare i dati prima del pagamento.")
    if crediti:
        note += (" Con importi a credito compensati l'F24 va presentato esclusivamente in via telematica (servizi dell'Agenzia delle Entrate "
                 "o home banking/intermediario abilitato).")
        if any(c["codice"] == "6099" for c in crediti) and sum(c["importo"] for c in crediti if c["codice"] == "6099") > 5000:
            note += " La compensazione del credito IVA annuale oltre 5.000 € richiede la preventiva presentazione della dichiarazione con visto di conformità."
    el.append(p(note, sm))
    doc.build(el)
    return buf.getvalue()

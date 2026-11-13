from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, PageBreak

from estratto import eur as _eur, _tbl


def eur(v) -> str:
    return _eur(round(v or 0, 2) + 0.0)


def _det(titolo: str, blocco: dict, col: str, sm, extra=()) -> list:
    tot = blocco.get("totali") or []
    if not tot:
        return [Paragraph(f"<b>{titolo}</b>: nessun movimento", sm), Spacer(1, 4)]
    rows = [["Aliquota / Natura", "Documenti", "Imponibile", "Imposta"]]
    for x in tot:
        cod = f"{x['natura']} reverse charge {x['aliquota']:g}%" if x.get("rc") else x["natura"] or f"{x['aliquota']:g}%"
        rows.append([cod, str(x["documenti"]), eur(x["imponibile"]), eur(x["imposta"])])
    rows.append(["Totale", "", eur(blocco["imponibile"]), eur(sum(x["imposta"] for x in tot))])
    rows += [[k, "", "", eur(v)] for k, v in extra if v]
    t = _tbl(rows, [w * mm for w in (70, 26, 43, 43)], header_bg=col, right_cols=(1, 2, 3))
    t.setStyle(TableStyle([("FONTNAME", (0, len(tot) + 1), (-1, len(tot) + 1), "Helvetica-Bold"),
                           ("LINEABOVE", (0, len(tot) + 1), (-1, len(tot) + 1), 0.8, colors.HexColor(col))]))
    return [Paragraph(f"<b>{titolo}</b>", sm), Spacer(1, 2), t, Spacer(1, 6)]


def _riepilogo(p: dict, trimestrale: bool, col: str) -> Table:
    vend = p["iva_debito"] + p["iva_split"] - p["iva_rc"] - p["iva_corrispettivi"]
    rows = [["Riepilogo liquidazione", "Importo"],
            ["IVA sulle vendite (fatture emesse)", eur(vend)],
            ["  di cui in split payment (non versata)", eur(-p["iva_split"])],
            ["IVA sui corrispettivi", eur(p["iva_corrispettivi"])],
            ["IVA a debito da reverse charge / autofatture", eur(p["iva_rc"])],
            ["Totale IVA a debito", eur(p["iva_debito"])],
            ["IVA sugli acquisti detraibile (incl. reverse charge)", eur(-p["iva_credito"])],
            ["IVA indetraibile (non entra nel calcolo)", eur(p.get("iva_indetraibile") or 0)],
            ["Credito del periodo precedente", eur(-p["credito_precedente"])]]
    if p.get("debito_precedente"):
        rows.append(["Debito rinviato (periodo precedente sotto 25,82 €)", eur(p["debito_precedente"])])
    if trimestrale:
        rows.append(["Interessi 1% (trimestrali)", eur(p["interessi"])])
    esito = ("IVA da versare", eur(p["da_versare"])) if p["da_versare"] > 0 else \
        ("Importo sotto 25,82 €: rinviato al periodo successivo", eur(p["saldo"] + p["interessi"] + p["debito_precedente"])) if p["sotto_soglia"] else \
        ("Credito IVA a riporto", eur(p["credito_riporto"]))
    rows.append(list(esito))
    t = _tbl(rows, [140 * mm, 42 * mm], header_bg=col, right_cols=(1,))
    t.setStyle(TableStyle([("FONTNAME", (0, 5), (-1, 5), "Helvetica-Bold"), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                           ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor(col)),
                           ("TEXTCOLOR", (1, -1), (1, -1), colors.HexColor("#be123c" if p["da_versare"] > 0 else "#047857"))]))
    return t


def build(comp: dict, liq: dict, periodo: int = 0) -> bytes:
    col = (comp.get("layout") or {}).get("colore") or "#0f172a"
    ss = getSampleStyleSheet()
    sm = ParagraphStyle("sm", parent=ss["Normal"], fontSize=8.5, leading=11)
    h = ParagraphStyle("h", parent=sm, fontSize=11, leading=14, spaceAfter=6, fontName="Helvetica-Bold", textColor=colors.HexColor(col))
    e = lambda s: escape(str(s or ""))  # noqa: E731
    trim = liq["periodicita"] == "trimestrale"
    periodi = [p for p in liq["periodi"] if not periodo or p["periodo"] == periodo]
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f"Liquidazione IVA {liq['anno']}")
    head = Paragraph(f"<b>{e(comp.get('denominazione'))}</b> · P.IVA {e(comp.get('partita_iva'))}<br/>"
                     f"Liquidazione IVA {liq['periodicita']} · anno {liq['anno']}" + (f" · {e(periodi[0]['label'])}" if periodo and periodi else ""), sm)
    story = []
    for i, p in enumerate(periodi):
        if i:
            story.append(PageBreak())
        story += [head, Spacer(1, 6), Paragraph(f"{e(p['label'])} {liq['anno']}", h),
                  Paragraph(f"{p['documenti_vendite']} documenti di vendita · {p['documenti_acquisti']} documenti di acquisto"
                            + (f" · {p['documenti_corrispettivi']} giorni di corrispettivi" if p.get("documenti_corrispettivi") else ""), sm), Spacer(1, 6),
                  KeepTogether([_riepilogo(p, trim, col)]), Spacer(1, 10), Paragraph("Dettaglio IVA per aliquota", h)]
        story += _det("IVA vendite (registro fatture emesse)", p["vendite"], col, sm, [("di cui split payment", p["iva_split"])])
        story += _det("IVA corrispettivi", p.get("corrispettivi") or {}, col, sm)
        story += _det("IVA acquisti (registro fatture ricevute)", p["acquisti"], col, sm, [("di cui indetraibile", p.get("iva_indetraibile") or 0)])
    if not periodo and len(periodi) > 1:
        rows = [["Periodo", "IVA debito", "IVA credito", "Credito prec.", "Interessi", "Da versare", "Credito riporto"]]
        for p in periodi:
            rows.append([p["label"], eur(p["iva_debito"]), eur(p["iva_credito"]), eur(p["credito_precedente"]), eur(p["interessi"]), eur(p["da_versare"]), eur(p["credito_riporto"])])
        rows.append(["Totale anno", eur(sum(p["iva_debito"] for p in periodi)), eur(sum(p["iva_credito"] for p in periodi)), "", eur(sum(p["interessi"] for p in periodi)),
                     eur(liq["totale_versare"]), eur(liq["credito_finale"])])
        t = _tbl(rows, [w * mm for w in (30, 26, 26, 26, 22, 26, 26)], header_bg=col, right_cols=(1, 2, 3, 4, 5, 6))
        t.setStyle(TableStyle([("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor(col))]))
        story += [PageBreak(), head, Spacer(1, 6), Paragraph(f"Riepilogo annuale {liq['anno']}", h), t, Spacer(1, 6),
                  Paragraph(f"Credito IVA dall'anno precedente: {eur(liq.get('credito_anno_precedente') or 0)}", sm)]
    story += [Spacer(1, 10), Paragraph("Prospetto indicativo predisposto dal programma: verificare sempre con il proprio consulente.", sm)]
    doc.build(story)
    return buf.getvalue()

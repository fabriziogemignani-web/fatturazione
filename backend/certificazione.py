from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

from estratto import eur as _eur, itd, _tbl


def eur(v) -> str:
    return _eur(round(v or 0, 2) + 0.0)


def _box(titolo: str, righe: list, sm, col: str) -> Table:
    t = Table([[Paragraph(f"<b>{titolo}</b>", sm)]] + [[Paragraph(r, sm)] for r in righe], colWidths=[88 * mm])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor(col)), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                           ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    return t


def build_pdf(comp: dict, anno: int, fornitori: list) -> bytes:
    col = (comp.get("layout") or {}).get("colore") or "#0f172a"
    ss = getSampleStyleSheet()
    sm = ParagraphStyle("sm", parent=ss["Normal"], fontSize=8.5, leading=11)
    h = ParagraphStyle("h", parent=sm, fontSize=12, leading=15, fontName="Helvetica-Bold", textColor=colors.HexColor(col), spaceAfter=2)
    e = lambda s: escape(str(s or ""))  # noqa: E731
    sost_ind = " ".join(x for x in (comp.get("indirizzo"), comp.get("cap"), comp.get("comune"), f"({comp['provincia']})" if comp.get("provincia") else "") if x)
    sost = [e(comp.get("denominazione")), f"C.F. {e(comp.get('codice_fiscale') or comp.get('partita_iva'))} · P.IVA {e(comp.get('partita_iva'))}", e(sost_ind)]
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f"Certificazione compensi {anno}")
    story = []
    for n, f in enumerate(fornitori):
        if n:
            story.append(PageBreak())
        perc = [e(f["fornitore"]), f"C.F. {e(f['codice_fiscale'] or '—')} · P.IVA {e(f['partita_iva'] or '—')}", e(f["indirizzo"])]
        story += [Paragraph(f"Certificazione dei compensi e delle ritenute d'acconto · anno {anno}", h),
                  Paragraph("Redditi di lavoro autonomo, provvigioni e redditi diversi (art. 4, commi 6-ter e 6-quater, D.P.R. 322/1998)", sm), Spacer(1, 6)]
        boxes = Table([[_box("Sostituto d'imposta", sost, sm, col), _box("Percipiente", perc, sm, col)]], colWidths=[91 * mm, 91 * mm])
        boxes.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        story += [boxes, Spacer(1, 8)]
        rows = [["Mese di pagamento", "Fatture", "Compenso lordo", "Imponibile ritenuta", "Ritenuta", "Versata il"]]
        for m in f["mesi"]:
            rows.append([m["label"], Paragraph(e(", ".join(m["documenti"])), sm), eur(m["compenso"]), eur(m["imponibile_ritenuta"]), eur(m["ritenuta"]),
                         itd(m["versato_il"]) if m["versato_il"] else "da versare"])
        rows.append(["Totale anno", "", eur(f["compenso"]), eur(f["imponibile_ritenuta"]), eur(f["ritenuta"]), ""])
        t = _tbl(rows, [w * mm for w in (30, 46, 27, 29, 25, 25)], header_bg=col, right_cols=(2, 3, 4))
        t.setStyle(TableStyle([("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor(col)), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        story += [t, Spacer(1, 8)]
        riep = [["Riepilogo", "Importo"], ["Ammontare lordo corrisposto", eur(f["compenso"])], ["Somme non soggette a ritenuta", eur(f["non_soggette"])],
                ["Imponibile", eur(f["imponibile_ritenuta"])], ["Ritenute a titolo di acconto operate", eur(f["ritenuta"])],
                ["Ritenute versate con F24", eur(f["versata"])]]
        if f["da_versare"]:
            riep.append(["Ritenute ancora da versare", eur(f["da_versare"])])
        r = _tbl(riep, [130 * mm, 52 * mm], header_bg=col, right_cols=(1,))
        r.setStyle(TableStyle([("FONTNAME", (0, 4), (-1, 4), "Helvetica-Bold")]))
        story += [r, Spacer(1, 6),
                  Paragraph(f"Causale {e(f['causale'])} · codice tributo F24 {e(f['codice'])} - {e(f['descrizione_codice'])}. "
                            "Le ritenute sono operate al momento del pagamento dei compensi (principio di cassa) e si versano entro il giorno 16 del mese successivo."
                            + (" Alcune ritenute risultano ancora da versare." if f["da_versare"] else ""), sm),
                  Spacer(1, 22),
                  Table([["Luogo e data ______________________", "Il sostituto d'imposta ______________________"]], colWidths=[91 * mm, 91 * mm],
                        style=[("FONTSIZE", (0, 0), (-1, -1), 9), ("ALIGN", (1, 0), (1, 0), "RIGHT")]),
                  Spacer(1, 14),
                  Paragraph("Riepilogo predisposto dal programma da consegnare al percipiente. Non sostituisce la Certificazione Unica da trasmettere "
                            "all'Agenzia delle Entrate: verificare con il proprio consulente.", ParagraphStyle("n", parent=sm, fontSize=7.5, textColor=colors.HexColor("#64748b")))]
    doc.build(story)
    return buf.getvalue()

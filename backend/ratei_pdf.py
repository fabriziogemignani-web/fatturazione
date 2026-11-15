from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from estratto import eur, itd, _tbl

STATI = {"da_contabilizzare": "Da contabilizzare", "simulata": "Simulazione", "definitiva": "Definitiva"}


def build(comp: dict, anno: int, rows: list, conti: dict, oggi: str) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm, topMargin=10 * mm, bottomMargin=10 * mm,
                            title=f"Ratei e risconti {anno}")
    ss = getSampleStyleSheet()
    sm = ParagraphStyle("sm", parent=ss["Normal"], fontSize=8, leading=10)
    e = lambda s: escape(str(s or ""))  # noqa: E731
    col = (comp.get("layout") or {}).get("colore") or "#0f172a"
    h = ParagraphStyle("h", parent=ss["Normal"], fontSize=13, leading=17, spaceBefore=2, spaceAfter=2)
    story = [Paragraph(f"<b>{e(comp.get('denominazione'))}</b> · P.IVA {e(comp.get('partita_iva'))}", sm),
             Paragraph(f"<font color='{col}'><b>Prospetto ratei e risconti al 31/12/{anno}</b></font>", h),
             Paragraph(f"Quote di competenza calcolate a giorni effettivi · scrittura al 31/12/{anno} e storno all'1/1/{anno + 1} · stampato il {itd(oggi)}", sm),
             Spacer(1, 6)]
    data = [["Documento", "Data reg.", "Anagrafica", "Tipo", "Competenza", "Conti", "Giorni", "Imponibile", f"Quota {anno}", "Stato"]]
    for x in rows:
        q = x["quota"]
        data.append([Paragraph(e(x["documento"]), sm), itd(x["data_registrazione"]), Paragraph(e(x["party_nome"]), sm), Paragraph(e(x["nome_tipo"]), sm),
                     f"{itd(x['competenza_dal'])} - {itd(x['competenza_al'])}", Paragraph("<br/>".join(e(f"{r['conto']} {conti.get(r['conto'], '')}") for r in x["righe"]), sm),
                     f"{q['giorni']}/{q['giorni_totali']}", eur(x["importo"]), eur(q["importo"]), Paragraph(STATI.get(x["stato"], x["stato"]), sm)])
    if len(data) == 1:
        story.append(Paragraph(f"Nessun rateo o risconto di competenza dell'esercizio {anno}.", sm))
    else:
        story.append(_tbl(data, [w * mm for w in (28, 17, 42, 24, 34, 47, 15, 22, 22, 26)], header_bg=col, right_cols=(6, 7, 8)))
    tot = {}
    for x in rows:
        k = (x["nome_tipo"], x["conto_rr"])
        t = tot.setdefault(k, [0, 0.0, 0.0])
        t[0] += 1
        t[1] += x["quota"]["importo"] if x["stato"] == "definitiva" else 0
        t[2] += x["quota"]["importo"]
    if tot:
        tr = [["Tipo", "Conto di stato patrimoniale", "Documenti", "Contabilizzato in definitiva", f"Totale quote {anno}"]]
        for (n, c), (cnt, d, q) in sorted(tot.items()):
            tr.append([n, f"{c} {conti.get(c, '')}", str(cnt), eur(d), eur(q)])
        attivi = sum(q for (n, _), (_, _, q) in tot.items() if "attivo" in n)
        passivi = sum(q for (n, _), (_, _, q) in tot.items() if "passivo" in n)
        tr += [["Totale ratei e risconti attivi", "", "", "", eur(attivi)], ["Totale ratei e risconti passivi", "", "", "", eur(passivi)]]
        t = _tbl(tr, [w * mm for w in (70, 82, 25, 55, 45)], header_bg=col, right_cols=(2, 3, 4))
        t.setStyle(TableStyle([("FONTNAME", (0, -2), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -2), (-1, -2), 1, colors.HexColor(col))]))
        story += [Spacer(1, 10), Paragraph("<b>Riepilogo per tipo</b>", ss["Normal"]), Spacer(1, 4), t]
        if any(x["stato"] != "definitiva" for x in rows):
            story += [Spacer(1, 6), Paragraph("Attenzione: alcune quote non sono ancora contabilizzate in definitiva; il prospetto è provvisorio.", sm)]
    story += [Spacer(1, 18), Table([["", "Firma ______________________"]], colWidths=[180 * mm, 97 * mm], style=[("ALIGN", (1, 0), (1, 0), "RIGHT"), ("FONTSIZE", (0, 0), (-1, -1), 9)])]
    doc.build(story)
    return buf.getvalue()

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
import base64

from estratto import eur, itd, _tbl
from fatturapa import line_total


def titolo(o: dict, conferma: bool) -> str:
    if o["tipo"] == "fornitore":
        return "ORDINE DI ACQUISTO"
    return "CONFERMA D'ORDINE" if conferma else "ORDINE CLIENTE"


def build(comp: dict, o: dict, conferma: bool = False) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=12 * mm, title=f"{titolo(o, conferma)} {o['numero_display']}")
    ss = getSampleStyleSheet()
    sm = ParagraphStyle("sm", parent=ss["Normal"], fontSize=8.5, leading=11)
    e = lambda s: escape(str(s or ""))  # noqa: E731
    lay = comp.get("layout") or {}
    col = lay.get("colore") or "#0f172a"

    def addr(x):
        return f"<b>{e(x.get('denominazione'))}</b><br/>{e(x.get('indirizzo'))}<br/>{e(x.get('cap'))} {e(x.get('comune'))} {('(' + e(x.get('provincia')) + ')') if x.get('provincia') else ''}"
    extra = "".join(f"<br/>{e(x)}" for x in (lay.get("telefono") and f"Tel. {lay['telefono']}", lay.get("email"), lay.get("pec") and f"PEC {lay['pec']}") if x)
    p = o["party"]
    dest = o.get("destinazione") or {}
    rif = f"<br/>Vs. riferimento: <b>{e(o['riferimento'])}</b>" if o.get("riferimento") else ""
    cons = f"<br/>Consegna prevista: <b>{itd(o['data_consegna'])}</b>" if o.get("data_consegna") else ""
    head = Table([[Paragraph(f"{addr(comp)}<br/>P.IVA {e(comp.get('partita_iva'))}{extra}", sm),
                   Paragraph(f"<font color='{col}' size=11><b>{titolo(o, conferma)}</b></font><br/><br/>N. <b>{e(o['numero_display'])}</b> del <b>{itd(o['data'])}</b>{rif}{cons}", sm)],
                  [Paragraph(f"<font size=7 color='#64748b'>{'FORNITORE' if o['tipo'] == 'fornitore' else 'CLIENTE'}</font><br/>{addr(p)}<br/>P.IVA {e(p.get('partita_iva') or p.get('codice_fiscale'))}", sm),
                   Paragraph(f"<font size=7 color='#64748b'>LUOGO DI CONSEGNA</font><br/>{addr(dest) if dest.get('indirizzo') else ('Nostra sede' if o['tipo'] == 'fornitore' else 'Sede del cliente')}", sm)]],
                 colWidths=[91 * mm, 91 * mm])
    head.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 1, colors.HexColor(col)), ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                              ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    rows = [["Codice", "Descrizione", "U.M.", "Quantità", "Prezzo", "Sconto", "Importo", "IVA"]]
    for ln in o["lines"]:
        desc = Paragraph(e(ln["descrizione"]) + (f"<br/><font size=7 color='#64748b'>{e(ln['note'])}</font>" if ln.get("note") else ""), sm)
        rows.append([ln.get("codice") or "", desc, ln.get("unita_misura") or "", f"{ln['quantita']:g}".replace(".", ","), eur(ln["prezzo_unitario"]),
                     f"{ln['sconto']}%" if ln.get("sconto") else "", eur(float(line_total(ln))), f"{ln['aliquota']:g}%"])
    imp = round(sum(float(line_total(ln)) for ln in o["lines"]), 2)
    iva = round(sum(float(line_total(ln)) * ln["aliquota"] / 100 for ln in o["lines"]), 2)
    tot = Table([["Imponibile", eur(imp)], ["IVA", eur(iva)], ["Totale", eur(imp + iva)]], colWidths=[40 * mm, 35 * mm], hAlign="RIGHT")
    tot.setStyle(TableStyle([("ALIGN", (1, 0), (1, -1), "RIGHT"), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor(col)), ("FONTSIZE", (0, 0), (-1, -1), 9)]))
    story = [head, Spacer(1, 8), _tbl(rows, [w * mm for w in (22, 66, 12, 18, 18, 14, 20, 12)], header_bg=col, right_cols=(3, 4, 5, 6, 7)), Spacer(1, 6), tot]
    if o.get("note"):
        story += [Spacer(1, 6), Paragraph(f"<b>Note:</b> {e(o['note'])}", sm)]
    if conferma and o["tipo"] == "cliente":
        story += [Spacer(1, 10), Paragraph("Confermiamo l'ordine alle condizioni sopra indicate. Vi preghiamo di segnalarci entro 2 giorni eventuali discordanze.", sm)]
    if o["tipo"] == "fornitore":
        story += [Spacer(1, 10), Paragraph("Vi preghiamo di confermare l'ordine, i prezzi e la data di consegna e di indicare il numero del presente ordine sul DDT e sulla fattura.", sm)]
    story += [Spacer(1, 24), Table([["", "Timbro e firma ______________________"]], colWidths=[91 * mm, 91 * mm], style=[("ALIGN", (1, 0), (1, 0), "RIGHT"), ("FONTSIZE", (0, 0), (-1, -1), 9)])]
    if lay.get("logo"):
        try:
            story.insert(0, Image(BytesIO(base64.b64decode(lay["logo"].split(",", 1)[1])), width=45 * mm, height=16 * mm, kind="proportional", hAlign="LEFT"))
            story.insert(1, Spacer(1, 4))
        except Exception:
            pass
    doc.build(story)
    return buf.getvalue()

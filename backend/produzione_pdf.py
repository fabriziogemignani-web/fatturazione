import base64
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image

from estratto import itd, _tbl

STATI = {"pianificato": "Pianificato", "lanciato": "Lanciato", "in_corso": "In corso", "completato": "Completato", "chiuso": "Chiuso"}


def _n(x) -> str:
    return f"{round(float(x or 0), 4):g}".replace(".", ",")


def build(comp: dict, o: dict, giacenze: dict) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm, title=f"Scheda di lavoro {o['numero_display']}")
    ss = getSampleStyleSheet()
    sm = ParagraphStyle("sm", parent=ss["Normal"], fontSize=8.5, leading=11)
    h = ParagraphStyle("h", parent=ss["Heading4"], fontSize=10, spaceBefore=8, spaceAfter=4)
    e = lambda s: escape(str(s or ""))  # noqa: E731
    lay = comp.get("layout") or {}
    col = lay.get("colore") or "#0f172a"
    rif = f"<br/>Ordine cliente: <b>{e(o['ordine_cliente'])}</b> · {e(o.get('cliente'))}" if o.get("ordine_cliente") else ""
    cons = f"<br/>Consegna richiesta: <b>{itd(o['data_consegna'])}</b>" if o.get("data_consegna") else ""
    head = Table([[Paragraph(f"<b>{e(comp.get('denominazione'))}</b><br/>{e(comp.get('indirizzo'))}<br/>{e(comp.get('cap'))} {e(comp.get('comune'))}", sm),
                   Paragraph(f"<font color='{col}' size=11><b>SCHEDA DI LAVORO</b></font><br/><br/>N. <b>{e(o['numero_display'])}</b> del <b>{itd(o['data'])}</b>"
                             f"<br/>Stato: <b>{STATI.get(o['status'], o['status'])}</b>{cons}{rif}", sm)],
                  [Paragraph(f"<font size=7 color='#64748b'>PRODOTTO DA REALIZZARE</font><br/><b>{e(o['codice'])}</b> {e(o['descrizione'])}", sm),
                   Paragraph(f"<font size=7 color='#64748b'>QUANTITÀ</font><br/><font size=12><b>{_n(o['quantita'])} {e(o.get('unita_misura'))}</b></font>"
                             f"  già prodotti {_n(o.get('prodotta'))}", sm)]], colWidths=[93 * mm, 93 * mm])
    head.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 1, colors.HexColor(col)), ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                              ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    comps = [["Codice", "Descrizione", "U.M.", "Per pezzo", "Da prelevare", "Giacenza", "Prelevato"]]
    for c in o["componenti"]:
        comps.append([c["codice"], Paragraph(e(c["descrizione"]), sm), c.get("unita_misura") or "", _n(c["quantita"]), _n(c["quantita"] * o["quantita"]),
                      _n(giacenze.get(c["article_id"])) if c["article_id"] in giacenze else "—", "[   ]"])
    fasi = [["Fase", "Descrizione", "Centro di lavoro", "Attrezz. min", "Min/pz", "Previsti", "Effettivi", "Operatore / firma"]]
    for i, f in enumerate(o["fasi"]):
        eff = f.get("minuti_effettivi")
        fasi.append([str((i + 1) * 10), Paragraph(e(f["descrizione"]), sm), Paragraph(e(f.get("centro")), sm), _n(f["setup_min"]), _n(f["minuti_pezzo"]),
                     _n(f["minuti_previsti"]), _n(eff) if eff else "", ""])
    story = [head, Paragraph("Componenti da prelevare", h),
             _tbl(comps, [w * mm for w in (24, 70, 12, 18, 22, 20, 20)], header_bg=col, right_cols=(3, 4, 5))]
    story += [Paragraph("Fasi da eseguire", h)]
    if o["fasi"]:
        t = _tbl(fasi, [w * mm for w in (11, 50, 34, 17, 14, 16, 17, 27)], header_bg=col, right_cols=(3, 4, 5, 6))
        t.setStyle(TableStyle([("BOTTOMPADDING", (0, 1), (-1, -1), 9), ("TOPPADDING", (0, 1), (-1, -1), 9)]))
        story.append(t)
    else:
        story.append(Paragraph("Nessuna fase di lavoro nel ciclo.", sm))
    if o.get("note"):
        story += [Spacer(1, 6), Paragraph(f"<b>Note:</b> {e(o['note'])}", sm)]
    story += [Spacer(1, 18), Table([["Inizio lavori ____/____/______", "Fine lavori ____/____/______", "Responsabile ______________"]], colWidths=[62 * mm] * 3,
                                   style=[("FONTSIZE", (0, 0), (-1, -1), 9)])]
    if lay.get("logo"):
        try:
            story.insert(0, Image(BytesIO(base64.b64decode(lay["logo"].split(",", 1)[1])), width=45 * mm, height=16 * mm, kind="proportional", hAlign="LEFT"))
            story.insert(1, Spacer(1, 4))
        except Exception:
            pass
    doc.build(story)
    return buf.getvalue()

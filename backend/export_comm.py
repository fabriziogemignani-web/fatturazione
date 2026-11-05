import io
import re
import zipfile
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from estratto import eur, itd

TIPI = {"TD01": "Fattura", "TD02": "Acconto su fattura", "TD04": "Nota di credito", "TD05": "Nota di debito", "TD06": "Parcella",
        "TD24": "Fattura differita", "TD16": "Integrazione reverse charge interno", "TD17": "Autofattura servizi estero"}
STATI = {"inviata": "Inviata", "consegnata": "Consegnata", "mancata_consegna": "Mancata consegna"}
_ss = getSampleStyleSheet()
SMALL = ParagraphStyle("s", parent=_ss["Normal"], fontSize=8, leading=10)
BOLD = ParagraphStyle("b", parent=SMALL, fontName="Helvetica-Bold", fontSize=9, leading=11)


def safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s or "").strip("_")[:80] or "doc"


def _p(t, st=SMALL):
    return Paragraph(escape(str(t or "")).replace("\n", "<br/>"), st)


def _party(title, p):
    rows = [title.upper(), p.get("denominazione") or "", p.get("indirizzo") or "",
            " ".join(x for x in (p.get("cap"), p.get("comune"), f"({p['provincia']})" if p.get("provincia") else "") if x)]
    if p.get("partita_iva"):
        rows.append(f"P.IVA {p.get('paese_iva') or 'IT'}{p['partita_iva']}" if not str(p["partita_iva"]).startswith(("IT", "it")) else f"P.IVA {p['partita_iva']}")
    if p.get("codice_fiscale"):
        rows.append(f"C.F. {p['codice_fiscale']}")
    return [Paragraph(f"<font size=7 color='#64748b'>{escape(rows[0])}</font>", SMALL), _p(rows[1], BOLD)] + [_p(r) for r in rows[2:] if r]


def courtesy_pdf(cedente: dict, cessionario: dict, d: dict, ricevuta: bool = False) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm)
    tipo = TIPI.get(d.get("tipo_documento"), d.get("tipo_documento") or "Fattura")
    head = Table([[_party("Cedente / Prestatore", cedente), _party("Cessionario / Committente", cessionario),
                   [_p(tipo.upper(), SMALL), _p(f"N. {d.get('numero_display') or d.get('numero')}", ParagraphStyle("n", parent=BOLD, fontSize=13, leading=16)), _p(f"del {itd(d.get('data'))}")]]],
                 colWidths=[65 * mm, 65 * mm, 50 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 1.2, colors.HexColor("#0f172a")), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    el = [head, Spacer(1, 6 * mm)]
    if d.get("causale"):
        el += [_p(f"Causale: {d['causale']}"), Spacer(1, 3 * mm)]
    rows = [["Descrizione", "Q.tà", "Prezzo", "IVA", "Importo"]]
    for ln in d.get("lines") or []:
        desc = ln.get("descrizione") or ""
        if ln.get("note"):
            desc += f"\n{ln['note']}"
        rows.append([_p(desc), f"{ln.get('quantita') or 0:g}", eur(ln.get("prezzo_unitario") or 0),
                     f"{ln['aliquota']:g}%" if ln.get("aliquota") else (ln.get("natura") or "-"), eur(ln.get("prezzo_totale") or 0)])
    t = Table(rows, colWidths=[90 * mm, 15 * mm, 27 * mm, 18 * mm, 30 * mm], repeatRows=1)
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                           ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0"))]))
    el += [t, Spacer(1, 5 * mm)]
    riep = [["Aliquota", "Imponibile", "Imposta"]] + [[f"{r['aliquota']:g}%" if r.get("aliquota") else (r.get("natura") or "-"), eur(r.get("imponibile") or 0), eur(r.get("imposta") or 0)]
                                                     for r in d.get("riepilogo") or []]
    tot = [["Imponibile", eur(d.get("imponibile") or 0)], ["IVA", eur(d.get("iva") or 0)], ["Totale documento", eur(d.get("totale") or 0)]]
    if d.get("ritenuta_importo"):
        tot.append(["Ritenuta d'acconto", f"- {eur(d['ritenuta_importo'])}"])
    if d.get("netto") is not None and abs((d.get("netto") or 0) - (d.get("totale") or 0)) > 0.004:
        tot.append(["Netto a pagare", eur(d["netto"])])
    rt = Table(riep, colWidths=[25 * mm, 30 * mm, 30 * mm])
    rt.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8), ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("LINEBELOW", (0, 0), (-1, 0), 0.4, colors.grey)]))
    tt = Table(tot, colWidths=[45 * mm, 35 * mm])
    tt.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
                            ("LINEABOVE", (0, 2), (-1, 2), 1, colors.HexColor("#0f172a"))]))
    el += [Table([[rt, tt]], colWidths=[95 * mm, 85 * mm], style=[("VALIGN", (0, 0), (-1, -1), "TOP")]), Spacer(1, 6 * mm)]
    if d.get("scadenza"):
        el.append(_p(f"Scadenza pagamento: {itd(d['scadenza'])}"))
    iban = (d.get("banca") or {}).get("iban") or next((r.get("iban") for r in d.get("rate") or [] if r.get("iban")), None)
    if iban:
        el.append(_p(f"IBAN: {iban}"))
    nota = "Copia di cortesia della fattura ricevuta, generata dal file XML." if ricevuta else "Copia di cortesia. Il documento fiscalmente valido è il file XML trasmesso tramite Sistema di Interscambio."
    el += [Spacer(1, 8 * mm), Paragraph(f"<font size=7 color='#94a3b8'>{escape(nota)}</font>", SMALL)]
    doc.build(el)
    return buf.getvalue()


def _sheet(ws, title, head, rows):
    ws.title = title
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="0F172A")
    for r in rows:
        ws.append(r)
    for i, w in enumerate([14, 14, 12, 40, 16, 14, 14, 14, 18, 44], start=1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = w
    for row in ws.iter_rows(min_row=2, min_col=6, max_col=8):
        for c in row:
            c.number_format = "#,##0.00"
    ws.freeze_panes = "A2"


def _sign(d):
    return -1 if d.get("tipo_documento") == "TD04" else 1


def summary_xlsx(attive: list, passive: list) -> bytes:
    wb = Workbook()
    head = ["Tipo", "Numero", "Data", "Controparte", "P.IVA / C.F.", "Imponibile", "IVA", "Totale", "Stato", "File XML"]
    sheets = []
    if attive is not None:
        sheets.append(("Fatture emesse", [[TIPI.get(x["tipo_documento"], x["tipo_documento"]), x["numero_display"], itd(x["data"]), x["cliente"].get("denominazione"),
                                           x["cliente"].get("partita_iva") or x["cliente"].get("codice_fiscale"), _sign(x) * x["imponibile"], _sign(x) * x["iva"], _sign(x) * x["totale"],
                                           STATI.get(x["status"], x["status"]), x["_xml_name"]] for x in attive]))
    if passive is not None:
        sheets.append(("Fatture ricevute", [[TIPI.get(x["tipo_documento"], x["tipo_documento"]), x["numero_display"], itd(x["data"]), x["fornitore"].get("denominazione"),
                                             x["fornitore"].get("partita_iva") or x["fornitore"].get("codice_fiscale"), _sign(x) * x["imponibile"], _sign(x) * x["iva"], _sign(x) * x["totale"],
                                             "Registrata" if x.get("stato_reg") == "registrata" else "Da registrare", x["_xml_name"]] for x in passive]))
    for i, (title, rows) in enumerate(sheets):
        _sheet(wb.active if i == 0 else wb.create_sheet(), title, head, rows)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_zip(company: dict, attive, passive, xml_for_active, root: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for x in attive or []:
            xml, name = xml_for_active(x)
            x["_xml_name"] = name
            z.writestr(f"{root}/Fatture_emesse/XML/{name}", xml)
            z.writestr(f"{root}/Fatture_emesse/PDF/{name.rsplit('.', 1)[0]}.pdf", courtesy_pdf(company, x["cliente"], x))
        for x in passive or []:
            base = safe(f"{x['data']}_{x['fornitore'].get('denominazione')}_{x['numero_display']}")
            x["_xml_name"] = f"{base}.xml"
            z.writestr(f"{root}/Fatture_ricevute/XML/{base}.xml", x["_xml"])
            z.writestr(f"{root}/Fatture_ricevute/PDF/{base}.pdf", courtesy_pdf(x["fornitore"], company, x, ricevuta=True))
        z.writestr(f"{root}/Riepilogo.xlsx", summary_xlsx(attive, passive))
    return buf.getvalue()

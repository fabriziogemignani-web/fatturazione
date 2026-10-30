from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

METODI = {"bonifico": "Bonifico", "riba": "RiBa", "rid": "SDD / RID", "carta": "Carta", "contanti": "Contanti",
          "assegno": "Assegno", "altro": "Altro", "compensazione": "Compensazione"}


def eur(v: float) -> str:
    return f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def itd(d: str) -> str:
    return "/".join(reversed(d[:10].split("-"))) if d else "—"


def movimenti(invs: list, pays: list) -> list:
    nums = {i["id"]: i["numero_display"] for i in invs}
    rows = []
    for i in invs:
        netto = i.get("netto", i["totale"])
        if i.get("tipo_documento") == "TD04":
            rif = nums.get(i.get("fattura_collegata_id"))
            rows.append((i["data"], f"Nota di credito {i['numero_display']}" + (f" (storno fatt. {rif})" if rif else ""), 0.0, netto))
        else:
            rows.append((i["data"], f"Fattura {i['numero_display']}", netto, 0.0))
    for p in pays:
        if p.get("nc_id"):
            rows.append((p["data"], f"Compensazione NC {p.get('nc_numero')} su fatt. {p['numero_display']} ({eur(p['importo'])})", 0.0, 0.0))
        else:
            rows.append((p["data"], f"Incasso {METODI.get(p['metodo'], p['metodo'])} fatt. {p['numero_display']}" + (f" - {p['note']}" if p.get("note") else ""), 0.0, p["importo"]))
    return sorted(rows, key=lambda r: r[0])


def _tbl(data, widths, header_bg="#0f172a", right_cols=()):
    t = Table(data, colWidths=widths, repeatRows=1)
    st = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_bg)), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
          ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
          ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
          ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    st += [("ALIGN", (c, 0), (c, -1), "RIGHT") for c in right_cols]
    t.setStyle(TableStyle(st))
    return t


def build_pdf(company: dict, party: dict, invs: list, pays: list, doc: list, crediti: list, today: str) -> bytes:
    buf = BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"Estratto conto {party.get('denominazione', '')}")
    ss = getSampleStyleSheet()
    sm = ParagraphStyle("sm", parent=ss["Normal"], fontSize=8.5, leading=11)
    h = ParagraphStyle("h", parent=ss["Heading2"], fontSize=11, spaceBefore=10, spaceAfter=6)
    cell = ParagraphStyle("c", parent=sm, fontSize=8.5, leading=10)
    e = lambda s: escape(str(s or ""))  # noqa: E731
    addr = lambda x: f"{e(x.get('indirizzo'))} {e(x.get('cap'))} {e(x.get('comune'))} {e(x.get('provincia'))}".strip()  # noqa: E731
    story = [
        Table([[Paragraph(f"<b>{e(company.get('denominazione'))}</b><br/>{addr(company)}<br/>P.IVA {e(company.get('partita_iva'))}", sm),
                Paragraph(f"<b>Spett.le {e(party.get('denominazione'))}</b><br/>{addr(party)}<br/>"
                          f"{'P.IVA ' + e(party.get('partita_iva')) if party.get('partita_iva') else 'C.F. ' + e(party.get('codice_fiscale'))}", sm)]],
              colWidths=[90 * mm, 88 * mm]),
        Spacer(1, 8 * mm),
        Paragraph(f"<b>Estratto conto al {itd(today)}</b>", ParagraphStyle("t", parent=ss["Title"], fontSize=15, alignment=0)),
    ]
    rows = movimenti(invs, pays)
    saldo = 0.0
    data = [["Data", "Descrizione", "Dare", "Avere", "Saldo"]]
    for d, desc, dare, avere in rows:
        saldo += dare - avere
        info = not dare and not avere
        data.append([itd(d), Paragraph(f"<i>{e(desc)}</i>" if info else e(desc), cell), eur(dare) if dare else "", eur(avere) if avere else "", "" if info else eur(saldo)])
    story += [Paragraph("Movimenti", h), _tbl(data, [20 * mm, 92 * mm, 22 * mm, 22 * mm, 22 * mm], right_cols=(2, 3, 4)) if rows else Paragraph("Nessun movimento.", sm)]
    aperte = [(d, r) for d in doc for r in d["rate"] if r["residuo"] > 0.005]
    scaduto = sum(r["residuo"] for _, r in aperte if r["scaduta"])
    if aperte:
        rd = [["Scadenza", "Documento", "Importo rata", "Residuo", "Stato"]]
        for d, r in sorted(aperte, key=lambda x: x[1]["scadenza"]):
            rd.append([itd(r["scadenza"]), f"{d['numero_display']}" + (f" rata {r['n']}/{r['di']}" if r["di"] > 1 else ""), eur(r["importo"]), eur(r["residuo"]),
                       f"Scaduta da {r['giorni_ritardo']} gg" if r["scaduta"] else "A scadere"])
        t = _tbl(rd, [24 * mm, 56 * mm, 30 * mm, 30 * mm, 38 * mm], right_cols=(2, 3))
        t.setStyle(TableStyle([("TEXTCOLOR", (4, i), (4, i), colors.HexColor("#be123c")) for i, (_, r) in enumerate(sorted(aperte, key=lambda x: x[1]["scadenza"]), 1) if r["scaduta"]]))
        story += [Paragraph("Partite aperte", h), t]
    cred = sum(c["residuo"] for c in crediti)
    tot = [["Totale da incassare", eur(sum(r["residuo"] for _, r in aperte))], ["di cui scaduto", eur(scaduto)]]
    if cred:
        tot.append(["Crediti da note di credito non compensati", f"- {eur(cred)}"])
    tot.append(["Saldo a vostro debito", eur(saldo)])
    tt = Table(tot, colWidths=[120 * mm, 58 * mm])
    tt.setStyle(TableStyle([("ALIGN", (1, 0), (1, -1), "RIGHT"), ("FONTSIZE", (0, 0), (-1, -1), 9.5), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                            ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.HexColor("#0f172a")), ("TEXTCOLOR", (1, 1), (1, 1), colors.HexColor("#be123c"))]))
    story += [Spacer(1, 6 * mm), tt]
    if company.get("iban"):
        story += [Spacer(1, 6 * mm), Paragraph(f"Coordinate per il pagamento: IBAN <b>{e(company['iban'])}</b> intestato a {e(company.get('denominazione'))}.", sm)]
    story += [Spacer(1, 4 * mm), Paragraph("Se il pagamento è già stato effettuato, vi preghiamo di non considerare le partite indicate.", sm)]
    pdf.build(story)
    return buf.getvalue()

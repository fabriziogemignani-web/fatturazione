from decimal import Decimal, ROUND_HALF_UP
import xml.etree.ElementTree as ET

NS_P = "http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2"
NS_DS = "http://www.w3.org/2000/09/xmldsig#"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"

NATURE_RIF = {
    "N1": "Escluse ex art. 15 DPR 633/72",
    "N2.1": "Non soggette art. 7-7septies DPR 633/72",
    "N2.2": "Non soggette - altri casi",
    "N3.1": "Non imponibili - esportazioni",
    "N3.2": "Non imponibili - cessioni intracomunitarie",
    "N3.5": "Non imponibili - a seguito di dichiarazioni d'intento",
    "N4": "Esenti art. 10 DPR 633/72",
    "N5": "Regime del margine",
    "N6.1": "Inversione contabile - rottami",
    "N6.9": "Inversione contabile - altri casi",
    "N7": "IVA assolta in altro stato UE",
}


def d2(v) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _add(riepilogo, aliquota, natura, amount):
    aliq = d2(aliquota)
    natura = natura if aliq == 0 else None
    r = riepilogo.setdefault((str(aliq), natura or ""), {"aliquota": float(aliq), "natura": natura, "imponibile": Decimal("0")})
    r["imponibile"] += amount
    return natura


def compute_totals(lines: list, cassa: dict = None, ritenuta: dict = None) -> dict:
    riepilogo = {}
    out_lines = []
    base = Decimal("0")
    for ln in lines:
        tot = d2(Decimal(str(ln["quantita"])) * Decimal(str(ln["prezzo_unitario"])))
        base += tot
        natura = _add(riepilogo, ln["aliquota"], ln.get("natura"), tot)
        out_lines.append({**ln, "prezzo_totale": float(tot), "natura": natura})
    cassa_imp = Decimal("0")
    if cassa:
        cassa_imp = d2(base * Decimal(str(cassa["aliquota"])) / 100)
        _add(riepilogo, cassa["aliquota_iva"], cassa.get("natura"), cassa_imp)
    rit_base = rit_imp = Decimal("0")
    if ritenuta:
        rit_base = base + (cassa_imp if cassa and cassa.get("ritenuta") else 0)
        rit_imp = d2(rit_base * Decimal(str(ritenuta["aliquota"])) / 100)
    imponibile = Decimal("0")
    iva = Decimal("0")
    riep_list = []
    for r in riepilogo.values():
        imposta = d2(r["imponibile"] * Decimal(str(r["aliquota"])) / 100)
        imponibile += r["imponibile"]
        iva += imposta
        riep_list.append({"aliquota": r["aliquota"], "natura": r["natura"],
                          "imponibile": float(d2(r["imponibile"])), "imposta": float(imposta)})
    totale = d2(imponibile + iva)
    return {
        "lines": out_lines,
        "riepilogo": riep_list,
        "imponibile": float(d2(imponibile)),
        "iva": float(d2(iva)),
        "totale": float(totale),
        "cassa_imponibile": float(d2(base)) if cassa else 0.0,
        "cassa_importo": float(cassa_imp),
        "ritenuta_imponibile": float(d2(rit_base)),
        "ritenuta_importo": float(rit_imp),
        "netto": float(totale - rit_imp),
    }


def _sub(parent, tag, text=None):
    el = ET.SubElement(parent, tag)
    if text is not None:
        el.text = str(text)
    return el


def _fmt(v, places="0.01"):
    return str(Decimal(str(v)).quantize(Decimal(places), rounding=ROUND_HALF_UP))


def _sede(parent, src):
    sede = _sub(parent, "Sede")
    _sub(sede, "Indirizzo", src.get("indirizzo") or "")
    _sub(sede, "CAP", src.get("cap") or "00000")
    _sub(sede, "Comune", src.get("comune") or "")
    if src.get("provincia"):
        _sub(sede, "Provincia", src["provincia"].upper())
    _sub(sede, "Nazione", (src.get("nazione") or "IT").upper())


def riferimento_normativo(natura: str, party: dict) -> str:
    if natura == "N3.5" and party.get("intento_protocollo"):
        return f"Non imp. art. 8 c.1 lett. c DPR 633/72 - Dich. intento prot. {party['intento_protocollo']} del {party['intento_data']}"
    if natura == party.get("natura_default") and party.get("riferimento_normativo"):
        return party["riferimento_normativo"]
    return NATURE_RIF.get(natura, "")


def file_name(company: dict, invoice: dict) -> str:
    return f"IT{company.get('partita_iva', '')}_{invoice['progressivo_invio']}.xml"


def build_xml(company: dict, invoice: dict) -> str:
    party = invoice["cliente"]
    ET.register_namespace("p", NS_P)
    ET.register_namespace("ds", NS_DS)
    ET.register_namespace("xsi", NS_XSI)
    root = ET.Element(f"{{{NS_P}}}FatturaElettronica", {"versione": "FPR12"})
    root.set(f"{{{NS_XSI}}}schemaLocation", f"{NS_P} http://www.fatturapa.gov.it/export/fatturazione/sdi/fatturapa/v1.2/Schema_del_file_xml_FatturaPA_versione_1.2.xsd")

    header = _sub(root, "FatturaElettronicaHeader")
    dt = _sub(header, "DatiTrasmissione")
    idt = _sub(dt, "IdTrasmittente")
    _sub(idt, "IdPaese", "IT")
    _sub(idt, "IdCodice", company.get("codice_fiscale") or company.get("partita_iva", ""))
    _sub(dt, "ProgressivoInvio", invoice["progressivo_invio"])
    _sub(dt, "FormatoTrasmissione", "FPR12")
    codice = (party.get("codice_destinatario") or "0000000").upper()
    _sub(dt, "CodiceDestinatario", codice)
    if codice == "0000000" and party.get("pec"):
        _sub(dt, "PECDestinatario", party["pec"])

    ced = _sub(header, "CedentePrestatore")
    da = _sub(ced, "DatiAnagrafici")
    idf = _sub(da, "IdFiscaleIVA")
    _sub(idf, "IdPaese", "IT")
    _sub(idf, "IdCodice", company.get("partita_iva", ""))
    if company.get("codice_fiscale"):
        _sub(da, "CodiceFiscale", company["codice_fiscale"].upper())
    ana = _sub(da, "Anagrafica")
    _sub(ana, "Denominazione", company.get("denominazione", ""))
    _sub(da, "RegimeFiscale", company.get("regime_fiscale") or "RF01")
    _sede(ced, company)

    ces = _sub(header, "CessionarioCommittente")
    da2 = _sub(ces, "DatiAnagrafici")
    if party.get("partita_iva"):
        idf2 = _sub(da2, "IdFiscaleIVA")
        _sub(idf2, "IdPaese", (party.get("nazione") or "IT").upper())
        _sub(idf2, "IdCodice", party["partita_iva"])
    if party.get("codice_fiscale"):
        _sub(da2, "CodiceFiscale", party["codice_fiscale"].upper())
    ana2 = _sub(da2, "Anagrafica")
    _sub(ana2, "Denominazione", party.get("denominazione", ""))
    _sede(ces, party)

    body = _sub(root, "FatturaElettronicaBody")
    dg = _sub(_sub(body, "DatiGenerali"), "DatiGeneraliDocumento")
    _sub(dg, "TipoDocumento", invoice.get("tipo_documento") or "TD01")
    _sub(dg, "Divisa", "EUR")
    _sub(dg, "Data", invoice["data"])
    _sub(dg, "Numero", invoice["numero_display"])
    rit = invoice.get("ritenuta")
    if rit:
        dr = _sub(dg, "DatiRitenuta")
        _sub(dr, "TipoRitenuta", rit["tipo"])
        _sub(dr, "ImportoRitenuta", _fmt(invoice["ritenuta_importo"]))
        _sub(dr, "AliquotaRitenuta", _fmt(rit["aliquota"]))
        _sub(dr, "CausalePagamento", rit.get("causale") or "A")
    cassa = invoice.get("cassa")
    if cassa:
        dc = _sub(dg, "DatiCassaPrevidenziale")
        _sub(dc, "TipoCassa", cassa["tipo"])
        _sub(dc, "AlCassa", _fmt(cassa["aliquota"]))
        _sub(dc, "ImportoContributoCassa", _fmt(invoice["cassa_importo"]))
        _sub(dc, "ImponibileCassa", _fmt(invoice["cassa_imponibile"]))
        _sub(dc, "AliquotaIVA", _fmt(cassa["aliquota_iva"]))
        if rit and cassa.get("ritenuta"):
            _sub(dc, "Ritenuta", "SI")
        if float(cassa["aliquota_iva"]) == 0 and cassa.get("natura"):
            _sub(dc, "Natura", cassa["natura"])
    _sub(dg, "ImportoTotaleDocumento", _fmt(invoice["totale"]))
    if invoice.get("causale"):
        _sub(dg, "Causale", invoice["causale"][:200])

    dbs = _sub(body, "DatiBeniServizi")
    intento_done = False
    for i, ln in enumerate(invoice["lines"], start=1):
        det = _sub(dbs, "DettaglioLinee")
        _sub(det, "NumeroLinea", i)
        _sub(det, "Descrizione", ln["descrizione"])
        _sub(det, "Quantita", _fmt(ln["quantita"], "0.00000000"))
        if ln.get("unita_misura"):
            _sub(det, "UnitaMisura", ln["unita_misura"])
        _sub(det, "PrezzoUnitario", _fmt(ln["prezzo_unitario"], "0.00000000"))
        _sub(det, "PrezzoTotale", _fmt(ln["prezzo_totale"], "0.00000000"))
        _sub(det, "AliquotaIVA", _fmt(ln["aliquota"]))
        if rit:
            _sub(det, "Ritenuta", "SI")
        if ln.get("natura"):
            _sub(det, "Natura", ln["natura"])
        if ln.get("natura") == "N3.5" and party.get("intento_protocollo") and not intento_done:
            adg = _sub(det, "AltriDatiGestionali")
            _sub(adg, "TipoDato", "INTENTO")
            _sub(adg, "RiferimentoTesto", party["intento_protocollo"])
            _sub(adg, "RiferimentoData", party["intento_data"])
            intento_done = True
    for r in invoice["riepilogo"]:
        rp = _sub(dbs, "DatiRiepilogo")
        _sub(rp, "AliquotaIVA", _fmt(r["aliquota"]))
        if r.get("natura"):
            _sub(rp, "Natura", r["natura"])
        _sub(rp, "ImponibileImporto", _fmt(r["imponibile"]))
        _sub(rp, "Imposta", _fmt(r["imposta"]))
        if r.get("natura"):
            _sub(rp, "RiferimentoNormativo", riferimento_normativo(r["natura"], party)[:100])
        else:
            _sub(rp, "EsigibilitaIVA", "I")

    dp = _sub(body, "DatiPagamento")
    _sub(dp, "CondizioniPagamento", "TP02")
    det = _sub(dp, "DettaglioPagamento")
    _sub(det, "ModalitaPagamento", invoice.get("modalita_pagamento") or "MP05")
    if invoice.get("scadenza"):
        _sub(det, "DataScadenzaPagamento", invoice["scadenza"])
    _sub(det, "ImportoPagamento", _fmt(invoice.get("netto", invoice["totale"])))
    if (invoice.get("modalita_pagamento") or "MP05") == "MP05" and company.get("iban"):
        _sub(det, "IBAN", company["iban"].replace(" ", "").upper())

    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")

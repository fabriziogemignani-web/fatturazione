import base64
import hashlib
import random
from datetime import date, timedelta

from asn1crypto import cms
from defusedxml import ElementTree as DET

from fatturapa import build_xml, compute_totals


def extract_xml(data: bytes) -> bytes:
    s = data.lstrip(b"\xef\xbb\xbf \r\n\t")
    if s.startswith(b"<"):
        return s
    for raw in (data, None):
        if raw is None:
            try:
                raw = base64.b64decode(b"".join(data.split()), validate=True)
            except ValueError:
                break
        try:
            content = cms.ContentInfo.load(raw)["content"]["encap_content_info"]["content"].native
            if content:
                return content.lstrip(b"\xef\xbb\xbf \r\n\t")
        except (ValueError, TypeError, KeyError):
            continue
    raise ValueError("File non riconosciuto: carica un XML FatturaPA o un file firmato .p7m")


def _strip(root):
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def _t(el, path):
    x = el.find(path) if el is not None else None
    return x.text.strip() if x is not None and x.text else ""


def _f(el, path, default=0.0):
    v = _t(el, path)
    try:
        return float(v) if v else default
    except ValueError:
        return default


def _anagrafica(node):
    da = node.find("DatiAnagrafici")
    den = _t(da, "Anagrafica/Denominazione") or f"{_t(da, 'Anagrafica/Nome')} {_t(da, 'Anagrafica/Cognome')}".strip()
    sede = node.find("Sede")
    via = " ".join(x for x in (_t(sede, "Indirizzo"), _t(sede, "NumeroCivico")) if x)
    return {"denominazione": den, "partita_iva": _t(da, "IdFiscaleIVA/IdCodice"), "paese_iva": _t(da, "IdFiscaleIVA/IdPaese") or "IT",
            "codice_fiscale": _t(da, "CodiceFiscale"), "indirizzo": via, "cap": _t(sede, "CAP"), "comune": _t(sede, "Comune"),
            "provincia": _t(sede, "Provincia"), "nazione": _t(sede, "Nazione") or "IT", "email": _t(node, "Contatti/Email"),
            "regime_fiscale": _t(da, "RegimeFiscale")}


def parse_fattura(xml: bytes) -> dict:
    try:
        root = _strip(DET.fromstring(xml))
    except Exception:
        raise ValueError("XML non valido o non leggibile")
    if root.tag != "FatturaElettronica":
        raise ValueError("Il file non è una FatturaPA (manca FatturaElettronica)")
    head = root.find("FatturaElettronicaHeader")
    if head is None or head.find("CedentePrestatore") is None:
        raise ValueError("Intestazione della fattura mancante")
    fornitore = _anagrafica(head.find("CedentePrestatore"))
    cess = _anagrafica(head.find("CessionarioCommittente")) if head.find("CessionarioCommittente") is not None else {}
    docs = []
    for body in root.findall("FatturaElettronicaBody"):
        dg = body.find("DatiGenerali/DatiGeneraliDocumento")
        numero, data = _t(dg, "Numero"), _t(dg, "Data")
        if not numero or not data:
            raise ValueError("Numero o data del documento mancanti")
        lines = [{"n": int(_f(ln, "NumeroLinea", i + 1)), "descrizione": _t(ln, "Descrizione"), "quantita": _f(ln, "Quantita", 1.0),
                  "unita_misura": _t(ln, "UnitaMisura"), "prezzo_unitario": _f(ln, "PrezzoUnitario"), "prezzo_totale": _f(ln, "PrezzoTotale"),
                  "aliquota": _f(ln, "AliquotaIVA"), "natura": _t(ln, "Natura") or None}
                 for i, ln in enumerate(body.findall("DatiBeniServizi/DettaglioLinee"))]
        riep = [{"aliquota": _f(r, "AliquotaIVA"), "natura": _t(r, "Natura") or None, "imponibile": _f(r, "ImponibileImporto"),
                 "imposta": _f(r, "Imposta"), "esigibilita": _t(r, "EsigibilitaIVA") or "I"} for r in body.findall("DatiBeniServizi/DatiRiepilogo")]
        imponibile = round(sum(r["imponibile"] for r in riep), 2)
        iva = round(sum(r["imposta"] for r in riep), 2)
        totale = _f(dg, "ImportoTotaleDocumento", None)
        totale = round(totale if totale is not None else imponibile + iva, 2)
        ritenuta = round(sum(_f(r, "ImportoRitenuta") for r in dg.findall("DatiRitenuta")), 2)
        split = any(r["esigibilita"] == "S" for r in riep)
        rate = [{"scadenza": _t(p, "DataScadenzaPagamento") or data, "importo": round(_f(p, "ImportoPagamento"), 2),
                 "modalita": _t(p, "ModalitaPagamento"), "iban": _t(p, "IBAN")}
                for p in body.findall("DatiPagamento/DettaglioPagamento") if _f(p, "ImportoPagamento") > 0]
        netto = round(sum(r["importo"] for r in rate), 2) if rate else round(totale - ritenuta - (iva if split else 0), 2)
        docs.append({"tipo_documento": _t(dg, "TipoDocumento") or "TD01", "numero": numero, "data": data, "totale": totale,
                     "imponibile": imponibile, "iva": iva, "ritenuta_importo": ritenuta, "split_payment": split, "netto": netto,
                     "rate": sorted(rate, key=lambda r: r["scadenza"]), "lines": lines, "riepilogo": riep,
                     "causale": " ".join(_t(c, ".") for c in dg.findall("Causale"))[:1000],
                     "collegate": [_t(c, "IdDocumento") for c in body.findall("DatiGenerali/DatiFattureCollegate") if _t(c, "IdDocumento")]})
    if not docs:
        raise ValueError("Nessun documento presente nel file")
    return {"fornitore": fornitore, "cessionario": cess, "progressivo": _t(head, "DatiTrasmissione/ProgressivoInvio"), "docs": docs}


def sha(xml: bytes) -> str:
    return hashlib.sha256(xml).hexdigest()


DEMO_SUPPLIERS = [
    {"denominazione": "DEMO Forniture Ufficio Srl", "partita_iva": "01987650463", "codice_fiscale": "01987650463", "indirizzo": "Via del Commercio 12",
     "cap": "56121", "comune": "Pisa", "provincia": "PI", "nazione": "IT", "iban": "IT60X0542811101000000123456",
     "righe": [("Carta A4 80g - risme", 20, 4.2, 22), ("Toner stampante laser", 3, 68.0, 22), ("Consegna", 1, 15.0, 22)]},
    {"denominazione": "DEMO Energia Toscana SpA", "partita_iva": "02345670481", "codice_fiscale": "02345670481", "indirizzo": "Viale Europa 45",
     "cap": "50126", "comune": "Firenze", "provincia": "FI", "nazione": "IT", "iban": "IT02A0306902887100000001234",
     "righe": [("Fornitura energia elettrica - periodo bimestrale", 1, 412.35, 22), ("Oneri di sistema", 1, 58.9, 22)]},
    {"denominazione": "DEMO Studio Tecnico Bianchi", "partita_iva": "03456780466", "codice_fiscale": "BNCMRA70A01E715X", "indirizzo": "Piazza Napoleone 3",
     "cap": "55100", "comune": "Lucca", "provincia": "LU", "nazione": "IT", "iban": "IT75P0200813701000101234567",
     "righe": [("Consulenza tecnica sicurezza impianti", 8, 55.0, 22)]},
    {"denominazione": "DEMO Telecomunicazioni Italia Srl", "partita_iva": "04567890159", "codice_fiscale": "04567890159", "indirizzo": "Via Torino 101",
     "cap": "20123", "comune": "Milano", "provincia": "MI", "nazione": "IT", "iban": "IT40S0542811101000000654321",
     "righe": [("Canone fibra business", 1, 49.9, 22), ("Linea mobile aziendale x3", 3, 12.0, 22)]},
]


def demo_xmls(company: dict, n: int) -> list:
    out = []
    today = date.today()
    for k in range(n):
        s = random.choice(DEMO_SUPPLIERS)
        d = today - timedelta(days=random.randint(0, 20))
        lines = [{"descrizione": a, "quantita": q, "unita_misura": "", "prezzo_unitario": p, "aliquota": al, "natura": None} for a, q, p, al in s["righe"]]
        tot = compute_totals(lines)
        nrate = random.choice([1, 1, 2])
        per = round(tot["netto"] / nrate, 2)
        rate = [{"scadenza": (d + timedelta(days=30 * (i + 1))).isoformat(), "importo": per if i < nrate - 1 else round(tot["netto"] - per * (nrate - 1), 2)}
                for i in range(nrate)]
        num = f"{random.randint(100, 9999)}/{d.year}"
        inv = {**tot, "tipo_documento": "TD01", "data": d.isoformat(), "numero_display": num, "progressivo_invio": f"D{random.randint(1000, 99999)}",
               "modalita_pagamento": "MP05", "rate": rate, "scadenza": rate[-1]["scadenza"], "causale": "",
               "cliente": {**{k2: company.get(k2) for k2 in ("denominazione", "partita_iva", "codice_fiscale", "indirizzo", "cap", "comune", "provincia", "nazione")},
                           "codice_destinatario": "0000000"}}
        out.append(build_xml(s, inv).encode("utf-8"))
    return out

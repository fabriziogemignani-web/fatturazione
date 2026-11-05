import io
import re
import zipfile
from typing import Iterator, Optional

from defusedxml import ElementTree as DET

from passive import extract_xml

MAX_ZIP_DEPTH = 3
MAX_ZIP_MEMBERS = 5000
MAX_MEMBER_BYTES = 20 * 1024 * 1024
MAX_ZIP_TOTAL_BYTES = 300 * 1024 * 1024


class _Budget:
    def __init__(self) -> None:
        self.members = 0
        self.total = 0


def _zip_members(zf: zipfile.ZipFile):
    for info in zf.infolist():
        hidden = info.filename.startswith("__MACOSX") or "/." in "/" + info.filename
        if not info.is_dir() and not hidden and info.filename.lower().endswith((".xml", ".p7m", ".zip")):
            yield info


def _read_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int):
    out = bytearray()
    try:
        with zf.open(info) as fh:
            while chunk := fh.read(65536):
                out += chunk
                if len(out) > limit:
                    return None, "File troppo grande (max 20 MB)"
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, ValueError, OSError, EOFError):
        return None, "File dell'archivio illeggibile, corrotto o protetto da password"
    return bytes(out), None


def extract_xml_files(filename: str, data: bytes, depth: int = 0, budget: Optional[_Budget] = None) -> Iterator[tuple]:
    budget = budget or _Budget()
    low = filename.lower()
    if low.endswith(".zip"):
        if depth >= MAX_ZIP_DEPTH:
            yield filename, None, "Troppi archivi ZIP annidati"
            return
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            yield filename, None, "Archivio ZIP non valido"
            return
        for info in _zip_members(zf):
            budget.members += 1
            remaining = MAX_ZIP_TOTAL_BYTES - budget.total
            if budget.members > MAX_ZIP_MEMBERS or info.file_size > remaining:
                yield filename, None, "Archivio troppo grande: dividilo in più parti"
                return
            name = f"{filename}/{info.filename}"
            if info.file_size > MAX_MEMBER_BYTES:
                yield name, None, "File troppo grande (max 20 MB)"
                continue
            member, err = _read_member(zf, info, min(MAX_MEMBER_BYTES, remaining))
            if err:
                yield name, None, err
                continue
            budget.total += len(member)
            yield from extract_xml_files(name, member, depth + 1, budget)
        return
    if low.endswith((".p7m", ".xml")):
        try:
            yield filename, extract_xml(data), None
        except ValueError as e:
            yield filename, None, str(e)
        return
    yield filename, None, "Formato non supportato (usa .xml, .p7m, .zip)"


def _t(el, path: str) -> str:
    if el is None:
        return ""
    f = el.find(path)
    return (f.text or "").strip() if f is not None and f.text else ""


def _num(v: str) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _party(el, with_contacts: bool = False) -> dict:
    da = el.find("DatiAnagrafici") if el is not None else None
    sede = el.find("Sede") if el is not None else None
    p = {
        "piva": _t(da, "IdFiscaleIVA/IdCodice"), "paese": _t(da, "IdFiscaleIVA/IdPaese"),
        "codice_fiscale": _t(da, "CodiceFiscale"),
        "denominazione": _t(da, "Anagrafica/Denominazione") or " ".join(x for x in [_t(da, "Anagrafica/Nome"), _t(da, "Anagrafica/Cognome")] if x),
        "regime_fiscale": _t(da, "RegimeFiscale"),
        "indirizzo": " ".join(x for x in [_t(sede, "Indirizzo"), _t(sede, "NumeroCivico")] if x),
        "cap": _t(sede, "CAP"), "comune": _t(sede, "Comune"), "provincia": _t(sede, "Provincia"), "nazione": _t(sede, "Nazione"),
    }
    if with_contacts:
        p["telefono"] = _t(el, "Contatti/Telefono")
        p["email"] = _t(el, "Contatti/Email")
    return p


def natural_key(numero: str) -> str:
    return re.sub(r"\d+", lambda m: m.group(0).zfill(12), (numero or "").upper())


def _root(xml_bytes: bytes):
    try:
        root = DET.fromstring(xml_bytes)
    except DET.ParseError as e:
        raise ValueError(f"XML non valido: {e}")
    except Exception:
        raise ValueError("XML non valido: dichiarazioni DTD/ENTITY non ammesse")
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    if root.tag != "FatturaElettronica":
        raise ValueError("Il file non è una FatturaElettronica")
    return root


def _body(body) -> dict:
    dgd = body.find("DatiGenerali/DatiGeneraliDocumento")
    numero, data = _t(dgd, "Numero"), _t(dgd, "Data")
    if not numero or not data:
        raise ValueError("Numero o data della fattura mancanti")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data):
        raise ValueError(f"Data della fattura non valida: {data} (formato atteso AAAA-MM-GG)")
    riepilogo = [{"aliquota_iva": _num(_t(r, "AliquotaIVA")), "natura": _t(r, "Natura"), "imponibile": _num(_t(r, "ImponibileImporto")),
                  "imposta": _num(_t(r, "Imposta")), "esigibilita": _t(r, "EsigibilitaIVA"), "riferimento_normativo": _t(r, "RiferimentoNormativo")}
                 for r in body.findall("DatiBeniServizi/DatiRiepilogo")]
    imponibile = round(sum(r["imponibile"] for r in riepilogo), 2)
    imposta = round(sum(r["imposta"] for r in riepilogo), 2)
    tot = _t(dgd, "ImportoTotaleDocumento")
    return {
        "numero": numero, "numero_key": natural_key(numero), "data": data, "anno": int(data[:4]) if data[:4].isdigit() else 0,
        "tipo_documento": _t(dgd, "TipoDocumento"), "divisa": _t(dgd, "Divisa") or "EUR",
        "causale": " ".join(c.text.strip() for c in dgd.findall("Causale") if c.text),
        "imponibile": imponibile, "imposta": imposta, "totale": _num(tot) if tot else round(imponibile + imposta, 2),
        "righe": [{"numero_linea": _t(x, "NumeroLinea"), "descrizione": _t(x, "Descrizione"), "quantita": _t(x, "Quantita"),
                   "unita_misura": _t(x, "UnitaMisura"), "prezzo_unitario": _num(_t(x, "PrezzoUnitario")),
                   "prezzo_totale": _num(_t(x, "PrezzoTotale")), "aliquota_iva": _num(_t(x, "AliquotaIVA")), "natura": _t(x, "Natura")}
                  for x in body.findall("DatiBeniServizi/DettaglioLinee")],
        "riepilogo": riepilogo,
        "pagamenti": [{"condizioni": _t(dp, "CondizioniPagamento"), "modalita": _t(d, "ModalitaPagamento"), "scadenza": _t(d, "DataScadenzaPagamento"),
                       "importo": _num(_t(d, "ImportoPagamento")), "iban": _t(d, "IBAN"), "istituto": _t(d, "IstitutoFinanziario")}
                      for dp in body.findall("DatiPagamento") for d in dp.findall("DettaglioPagamento")],
    }


def parse_fattura(xml_bytes: bytes) -> tuple:
    xml_bytes = xml_bytes.lstrip(b"\xef\xbb\xbf").strip()
    root = _root(xml_bytes)
    header = root.find("FatturaElettronicaHeader")
    if header is None:
        raise ValueError("Header della fattura mancante")
    dt = header.find("DatiTrasmissione")
    tr = {"formato": _t(dt, "FormatoTrasmissione"), "codice_destinatario": _t(dt, "CodiceDestinatario"),
          "pec_destinatario": _t(dt, "PECDestinatario"), "progressivo_invio": _t(dt, "ProgressivoInvio")}
    ced = _party(header.find("CedentePrestatore"), with_contacts=True)
    ces = _party(header.find("CessionarioCommittente"))
    ces["codice_destinatario"], ces["pec"] = tr["codice_destinatario"], tr["pec_destinatario"]
    invoices = [{**_body(b), "cedente": ced, "cessionario": ces, "trasmissione": tr} for b in root.findall("FatturaElettronicaBody")]
    if not invoices:
        raise ValueError("Nessun corpo fattura trovato")
    return invoices, xml_bytes.decode("utf-8", errors="replace")

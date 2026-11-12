import asyncio
import base64
import re
import unicodedata
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from zoneinfo import ZoneInfo
from typing import List, Optional
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image

import contabilita as coge
from contabilita_dati import tipo_conto
from estratto import eur, itd, _tbl

DATE_RX = r"^\d{4}-\d{2}-\d{2}$"
NS = "urn:CBI:xsd:CBIPaymentRequest.00.04.00"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _r2(v):
    return round(float(v or 0) + 0.0, 2)


def _sepa(s, n):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9/?:().,'+ -]", " ", s).strip()[:n] or "-"


def cbi_bonifici(comp: dict, banca: dict, dist: dict) -> str:
    cuc = banca.get("cuc") or ""
    righe = dist["disposizioni"]
    tot = _r2(sum(x["importo"] for x in righe))
    piva = comp.get("partita_iva") or comp.get("codice_fiscale") or ""
    msg = f"PAG{dist['anno']}{dist['numero']:05d}"
    x = [f'<?xml version="1.0" encoding="UTF-8"?>', f'<CBIPaymentRequest xmlns="{NS}">',
         "<GrpHdr>", f"<MsgId>{msg}</MsgId>", f"<CreDtTm>{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')}</CreDtTm>",
         f"<NbOfTxs>{len(righe)}</NbOfTxs>", f"<CtrlSum>{tot:.2f}</CtrlSum>",
         f"<InitgPty><Nm>{escape(_sepa(comp.get('denominazione'), 70))}</Nm><Id><OrgId><Othr><Id>{escape(cuc)}</Id><Issr>CBI</Issr></Othr></OrgId></Id></InitgPty>",
         "</GrpHdr>", "<PmtInf>", f"<PmtInfId>{msg}</PmtInfId>", "<PmtMtd>TRF</PmtMtd>",
         "<PmtTpInf><InstrPrty>NORM</InstrPrty><SvcLvl><Cd>SEPA</Cd></SvcLvl></PmtTpInf>",
         f"<ReqdExctnDt>{dist['data']}</ReqdExctnDt>",
         f"<Dbtr><Nm>{escape(_sepa(comp.get('denominazione'), 70))}</Nm>"
         + (f"<Id><OrgId><Othr><Id>{escape(piva)}</Id><Issr>ADE</Issr></Othr></OrgId></Id>" if piva else "") + "</Dbtr>",
         f"<DbtrAcct><Id><IBAN>{banca['iban']}</IBAN></Id></DbtrAcct>",
         f"<DbtrAgt><FinInstnId><ClrSysMmbId><MmbId>{banca.get('abi') or banca['iban'][5:10]}</MmbId></ClrSysMmbId></FinInstnId></DbtrAgt>",
         "<ChrgBr>SLEV</ChrgBr>"]
    for k, r in enumerate(righe, 1):
        x += ["<CdtTrfTxInf>", f"<PmtId><InstrId>{k}</InstrId><EndToEndId>{msg}-{k:04d}</EndToEndId></PmtId>",
              "<PmtTpInf><CtgyPurp><Cd>SUPP</Cd></CtgyPurp></PmtTpInf>",
              f'<Amt><InstdAmt Ccy="EUR">{r["importo"]:.2f}</InstdAmt></Amt>',
              f"<Cdtr><Nm>{escape(_sepa(r['fornitore'], 70))}</Nm></Cdtr>",
              f"<CdtrAcct><Id><IBAN>{r['iban']}</IBAN></Id></CdtrAcct>",
              f"<RmtInf><Ustrd>{escape(_sepa(r['causale'], 140))}</Ustrd></RmtInf>", "</CdtTrfTxInf>"]
    x += ["</PmtInf>", "</CBIPaymentRequest>"]
    return "\n".join(x) + "\n"


def distinta_pdf(comp: dict, banca: dict, dist: dict) -> bytes:
    lay = comp.get("layout") or {}
    col = lay.get("colore") or "#0f172a"
    ss = getSampleStyleSheet()
    sm = ParagraphStyle("sm", parent=ss["Normal"], fontSize=8.5, leading=11)
    h = ParagraphStyle("h", parent=sm, fontSize=10, leading=13, spaceBefore=10, spaceAfter=4, fontName="Helvetica-Bold", textColor=colors.HexColor(col))
    e = lambda s: escape(str(s or ""))  # noqa: E731
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f"Distinta bonifici {dist['numero_display']}")
    story = []
    if lay.get("logo"):
        try:
            story += [Image(BytesIO(base64.b64decode(lay["logo"].split(",", 1)[1])), width=45 * mm, height=16 * mm, kind="proportional", hAlign="LEFT"), Spacer(1, 4)]
        except Exception:
            pass
    ord_ = (f"<b>{e(comp.get('denominazione'))}</b><br/>{e(comp.get('indirizzo'))}<br/>{e(comp.get('cap'))} {e(comp.get('comune'))} {e(comp.get('provincia'))}"
            f"<br/>P.IVA {e(comp.get('partita_iva'))}")
    bank = (f"<font color='{col}'><b>DISTINTA DI BONIFICI A FORNITORI N. {e(dist['numero_display'])}</b></font><br/>Data esecuzione {itd(dist['data'])}<br/>"
            f"Banca ordinante: <b>{e(banca.get('nome'))}</b><br/>IBAN addebito {e(banca.get('iban'))}<br/>ABI {e(banca.get('abi'))} CAB {e(banca.get('cab'))}"
            + (f" CUC {e(banca.get('cuc'))}" if banca.get("cuc") else "") + (f"<br/>{e(dist['coge_rif'])}" if dist.get("coge_rif") else ""))
    head = Table([[Paragraph(ord_, sm), Paragraph(bank, sm)]], colWidths=[88 * mm, 94 * mm])
    head.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 1, colors.HexColor(col)), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("PADDING", (0, 0), (-1, -1), 6)]))
    rows = [["N.", "Beneficiario", "IBAN", "Causale", "Importo"]]
    for k, x in enumerate(dist["disposizioni"], 1):
        rows.append([str(k), Paragraph(e(x["fornitore"]), sm), Paragraph(f"<font name='Courier'>{e(x['iban'])}</font>", sm), Paragraph(e(x["causale"]), sm), eur(x["importo"])])
    rows.append(["", Paragraph(f"<b>Totale {len(dist['disposizioni'])} bonifici</b>", sm), "", "", eur(dist["totale"])])
    tb = _tbl(rows, [w * mm for w in (8, 44, 56, 52, 22)], header_bg=col, right_cols=(4,))
    tb.setStyle(TableStyle([("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.HexColor(col))]))
    det = [["Fornitore", "Documento", "Data doc.", "Scadenza", "Pagato"]]
    for p in dist["partite"]:
        det.append([Paragraph(e(p.get("fornitore")), sm), Paragraph(e(p["numero_display"] + (f" rata {p['rata_n']}/{p['rate_totali']}" if (p.get("rate_totali") or 1) > 1 else "")), sm),
                    itd(p.get("data_doc") or "") if p.get("data_doc") else "", itd(p["scadenza"]) if p.get("scadenza") else "", eur(p["importo"])])
    td = _tbl(det, [w * mm for w in (56, 50, 24, 24, 28)], header_bg=col, right_cols=(4,))
    firma = Table([["", Paragraph("Timbro e firma dell'ordinante<br/><br/><br/>______________________________", sm)]], colWidths=[100 * mm, 82 * mm])
    story += [head, Spacer(1, 8), Paragraph("Disposizioni di bonifico", h), tb, Paragraph("Dettaglio fatture pagate", h), td, Spacer(1, 18), firma]
    doc.build(story)
    return buf.getvalue()


async def ricalcola(db, cid: str, did: str, data: str):
    d = await db.pag_distinte.find_one({"id": did, "company_id": cid}, {"_id": 0})
    if not d:
        return
    pays = await db.passive_payments.find({"company_id": cid, "distinta_pag_id": did}, {"_id": 0}).to_list(5000)
    old = {(p["invoice_id"]): p for p in d["partite"]}
    ibans = {x["party_id"]: (x["iban"], x["fornitore"]) for x in d["disposizioni"]}
    agg = {}
    for p in pays:
        o = old.get(p["invoice_id"]) or {}
        a = agg.setdefault(p["invoice_id"], {**o, "invoice_id": p["invoice_id"], "numero_display": p["numero_display"], "party_id": p["party_id"], "importo": 0})
        a["importo"] = _r2(a["importo"] + p["importo"])
    partite = list(agg.values())
    pids = [x["party_id"] for x in partite if x["party_id"] not in ibans]
    for pt in await db.parties.find({"company_id": cid, "id": {"$in": pids}}, {"_id": 0, "id": 1, "iban": 1, "denominazione": 1}).to_list(len(pids) + 1):
        ibans[pt["id"]] = (pt.get("iban") or "", pt["denominazione"])
    by = defaultdict(list)
    for x in partite:
        x["iban"], x["fornitore"] = x.get("iban") or ibans.get(x["party_id"], ("", ""))[0], x.get("fornitore") or ibans.get(x["party_id"], ("", ""))[1]
        by[(x["party_id"], x["iban"])].append(x)
    disp = [{"party_id": pid, "fornitore": cs[0]["fornitore"], "iban": iban, "importo": _r2(sum(c["importo"] for c in cs)),
             "causale": "Saldo fatt. " + ", ".join(dict.fromkeys(c["numero_display"] for c in cs))} for (pid, iban), cs in by.items()]
    await db.pag_distinte.update_one({"id": did}, {"$set": {"data": data, "partite": partite, "disposizioni": disp, "totale": _r2(sum(x["importo"] for x in partite)),
                                                          "n_partite": len(partite), "n_bonifici": len(disp), "modificata_prima_nota": True, "updated_at": _now()}})


class VoceIn(BaseModel):
    key: str = Field(max_length=80)
    importo: float = Field(gt=0, le=100_000_000)


class DistintaIn(BaseModel):
    banca_iban: str
    data: str = Field(pattern=DATE_RX)
    voci: List[VoceIn] = Field(min_length=1, max_length=1000)

    @field_validator("data")
    @classmethod
    def _d(cls, v):
        try:
            date.fromisoformat(v)
        except ValueError:
            raise ValueError("Data non valida")
        return v


def build(db, tenant, tenant_accounting, deps) -> APIRouter:
    r = APIRouter(prefix="/api/pagamenti-fornitori")
    ledger, ferr, check_tx, unlink = deps["ledger"], deps["ferr"], deps["check_tx"], deps["unlink"]
    locks = defaultdict(asyncio.Lock)

    def _banca(comp: dict, iban: str) -> dict:
        b = next((x for x in comp.get("banche") or [] if x.get("iban") == iban), None)
        if not b:
            raise ferr(400, "banca_iban", "Seleziona una banca dell'azienda")
        return b

    async def _conto_banca(cid: str, p: dict, banca: dict) -> str:
        if banca.get("conto_coge") and await db.coa_accounts.find_one({"company_id": cid, "codice": banca["conto_coge"], "livello": 3}, {"_id": 1}):
            return banca["conto_coge"]
        if banca.get("predefinita"):
            return p["banca"]
        codes = [a["codice"] for a in await db.coa_accounts.find({"company_id": cid, "codice": {"$regex": r"^06\.01\.\d{3}$"}}, {"_id": 0, "codice": 1}).to_list(1000)]
        code = f"06.01.{max([int(c[-3:]) for c in codes if int(c[-3:]) > 100] + [100]) + 1:03d}"
        await db.coa_accounts.insert_one({"id": str(uuid.uuid4()), "company_id": cid, "codice": code, "descrizione": f"Banca c/c - {banca['nome']}"[:80],
                                          "livello": 3, "tipo": tipo_conto(code), "sistema": False, "created_at": _now()})
        await db.companies.update_one({"id": cid, "banche.iban": banca["iban"]}, {"$set": {"banche.$.conto_coge": code}})
        return code

    async def _scadenze(cid: str) -> list:
        docs, _, _, _ = await ledger(cid)
        ids = [d["id"] for d in docs]
        src = {x["id"]: x for x in await db.passive_invoices.find({"company_id": cid, "id": {"$in": ids}}, {"_id": 0, "id": 1, "rate": 1}).to_list(len(ids) + 1)}
        pids = list({d["party_id"] for d in docs if d.get("party_id")})
        parties = {p["id"]: p for p in await db.parties.find({"company_id": cid, "id": {"$in": pids}}, {"_id": 0, "id": 1, "denominazione": 1, "iban": 1}).to_list(len(pids) + 1)}
        out = []
        for d in docs:
            pt = parties.get(d["party_id"]) or {}
            iban = pt.get("iban") or next((x.get("iban") for x in (src.get(d["id"]) or {}).get("rate") or [] if x.get("iban")), "") or ""
            for x in d["rate"]:
                if x["residuo"] > 0.005:
                    out.append({"key": f"{d['id']}:{x['n']}", "invoice_id": d["id"], "rata_n": x["n"], "rate_totali": x["di"], "scadenza": x["scadenza"],
                                "importo": x["importo"], "residuo": x["residuo"], "scaduta": x["scaduta"], "numero_display": d["numero_display"], "data_doc": d["data"],
                                "party_id": d["party_id"], "fornitore": pt.get("denominazione") or d["cliente"], "iban": re.sub(r"\s+", "", iban).upper()})
        return sorted(out, key=lambda e: (e["scadenza"], e["fornitore"], e["numero_display"]))

    @r.get("/scadenze")
    async def scadenze(dal: Optional[str] = None, al: Optional[str] = None, t: dict = Depends(tenant)):
        rows = await _scadenze(t["cid"])
        return [x for x in rows if (not dal or x["scadenza"] >= dal) and (not al or x["scadenza"] <= al)]

    @r.get("/riepilogo")
    async def riepilogo(giorni: int = 10, t: dict = Depends(tenant)):
        oggi = datetime.now(ZoneInfo("Europe/Rome")).date()
        fino = (oggi + timedelta(days=max(1, min(giorni, 60)))).isoformat()
        rows = await _scadenze(t["cid"])
        prossime = [x for x in rows if oggi.isoformat() <= x["scadenza"] <= fino]
        scadute = [x for x in rows if x["scadenza"] < oggi.isoformat()]
        lite = lambda x: {k: x[k] for k in ("key", "invoice_id", "numero_display", "scadenza", "residuo", "fornitore", "rata_n", "rate_totali")} | {"manca_iban": not x["iban"]}  # noqa: E731
        return {"dal": oggi.isoformat(), "al": fino, "in_scadenza": [lite(x) for x in prossime], "in_scadenza_totale": _r2(sum(x["residuo"] for x in prossime)),
                "scadute_n": len(scadute), "scadute_totale": _r2(sum(x["residuo"] for x in scadute))}

    @r.get("/distinte")
    async def distinte(t: dict = Depends(tenant)):
        return await db.pag_distinte.find({"company_id": t["cid"]}, {"_id": 0}).sort([("data", -1), ("numero", -1)]).to_list(1000)

    async def _get(did: str, cid: str) -> dict:
        d = await db.pag_distinte.find_one({"id": did, "company_id": cid}, {"_id": 0})
        if not d:
            raise HTTPException(404, "Distinta non trovata")
        return d

    @r.get("/distinte/{did}")
    async def distinta(did: str, t: dict = Depends(tenant)):
        return await _get(did, t["cid"])

    @r.post("/distinte")
    async def crea(body: DistintaIn, t: dict = Depends(tenant_accounting)):
        async with locks[t["cid"]]:
            return await _crea(body, t)

    async def _crea(body: DistintaIn, t: dict):
        cid, comp = t["cid"], t["company"]
        banca = _banca(comp, body.banca_iban)
        cand = {c["key"]: c for c in await _scadenze(cid)}
        voci = {v.key: _r2(v.importo) for v in body.voci}
        sel = []
        for k, imp in voci.items():
            c = cand.get(k)
            if not c:
                raise HTTPException(400, "Una o più scadenze non sono più da pagare: aggiorna l'elenco")
            if imp > c["residuo"] + 0.005:
                raise ferr(400, "voci", f"Fattura {c['numero_display']}: importo superiore al residuo ({c['residuo']:.2f} €)".replace(".", ","))
            prima = [x for x in cand.values() if x["invoice_id"] == c["invoice_id"] and x["rata_n"] < c["rata_n"]]
            if any(voci.get(x["key"], 0) < x["residuo"] - 0.005 for x in prima):
                raise ferr(400, "voci", f"Fattura {c['numero_display']}: paga per intero prima la rata {prima[0]['rata_n']}")
            if body.data < c["data_doc"]:
                raise ferr(400, "data", f"La data di pagamento non può precedere la fattura {c['numero_display']}")
            if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", c["iban"]):
                raise ferr(400, "voci", f"Fornitore {c['fornitore']}: manca l'IBAN per il bonifico (inseriscilo nell'anagrafica fornitore)")
            sel.append({**c, "pagato": imp})
        anno = int(body.data[:4])
        did = str(uuid.uuid4())
        tot = _r2(sum(c["pagato"] for c in sel))
        by_forn = defaultdict(list)
        for c in sel:
            by_forn[(c["party_id"], c["iban"])].append(c)
        disp = [{"party_id": pid, "fornitore": cs[0]["fornitore"], "iban": iban, "importo": _r2(sum(c["pagato"] for c in cs)),
                 "causale": "Saldo fatt. " + ", ".join(dict.fromkeys(c["numero_display"] for c in cs))} for (pid, iban), cs in by_forn.items()]
        p = await coge._ready(db, cid, "pagamenti", did)
        conto = await _conto_banca(cid, p, banca) if p else ""
        cnt = await db.counters.find_one_and_update({"key": f"pagforn_{cid}_{anno}"}, {"$inc": {"v": 1}}, upsert=True, return_document=True)
        num = cnt["v"]
        by = t["user"].get("name") or t["user"]["email"]
        dist = {"id": did, "company_id": cid, "numero": num, "anno": anno, "numero_display": f"{num}/{anno}", "data": body.data, "banca_iban": banca["iban"],
                "banca_nome": banca["nome"], "conto_banca": conto, "totale": tot, "n_partite": len(sel), "n_bonifici": len(disp), "disposizioni": disp,
                "partite": [{k: c[k] for k in ("invoice_id", "rata_n", "rate_totali", "scadenza", "numero_display", "data_doc", "party_id", "fornitore", "iban")} | {"importo": c["pagato"]} for c in sel],
                "created_by": by, "created_at": _now()}
        entry = None
        if p:
            righe = [{"conto": p["fornitori"], "dare": d["importo"], "party_id": d["party_id"], "party_nome": d["fornitore"]} for d in disp] + [{"conto": conto, "avere": tot}]
            try:
                entry = await coge._insert(db, cid, p, body.data, "PG", f"Distinta pagamenti fornitori {dist['numero_display']} - {banca['nome']}", righe, "pagamenti", did,
                                           {"documento": dist["numero_display"], "data_documento": body.data}, by=by)
            except ValueError as e:
                raise HTTPException(400, f"Pagamento non registrato in prima nota: {e}")
        rif = f"prima nota n. {entry['numero']}/{entry['anno']}" if entry else None
        dist["coge_entry_id"], dist["coge_rif"] = (entry or {}).get("id"), rif
        await db.passive_payments.insert_many([{"id": str(uuid.uuid4()), "company_id": cid, "invoice_id": c["invoice_id"], "party_id": c["party_id"],
                                                "numero_display": c["numero_display"], "data": body.data, "importo": c["pagato"], "metodo": "bonifico",
                                                "note": f"Distinta pagamenti {dist['numero_display']} - {banca['nome']}", "nc_id": None, "nc_numero": None,
                                                "distinta_pag_id": did, "coge_entry_id": dist["coge_entry_id"], "coge_rif": rif,
                                                "created_by": t["user"]["user_id"], "created_by_name": by, "created_at": _now()} for c in sel])
        await db.pag_distinte.insert_one(dict(dist))
        return dist

    @r.get("/distinte/{did}/cbi")
    async def cbi(did: str, t: dict = Depends(tenant)):
        d = await _get(did, t["cid"])
        banca = _banca(t["company"], d["banca_iban"])
        if not banca.get("cuc"):
            raise HTTPException(400, f"Inserisci il codice CUC della banca {banca['nome']} in Dati azienda → Banche per generare il flusso CBI")
        xml = cbi_bonifici(t["company"], banca, d)
        return Response(xml.encode("utf-8"), media_type="application/xml",
                        headers={"Content-Disposition": f'attachment; filename="BONIFICI_{d["anno"]}_{d["numero"]:04d}.xml"'})

    @r.get("/distinte/{did}/pdf")
    async def pdf(did: str, t: dict = Depends(tenant)):
        d = await _get(did, t["cid"])
        banca = next((x for x in t["company"].get("banche") or [] if x.get("iban") == d["banca_iban"]), {"nome": d["banca_nome"], "iban": d["banca_iban"]})
        return Response(distinta_pdf(t["company"], banca, d), media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="Distinta_bonifici_{d["anno"]}_{d["numero"]:04d}.pdf"'})

    @r.delete("/distinte/{did}")
    async def annulla(did: str, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        d = await _get(did, cid)
        await coge.check_annullabile(db, cid, "pagamenti", did)
        q = {"company_id": cid, "$or": [{"distinta_pag_id": did}] + ([{"coge_entry_id": d["coge_entry_id"]}] if d.get("coge_entry_id") else [])}
        pays = await db.passive_payments.find(q, {"_id": 0, "id": 1}).to_list(5000)
        for x in pays:
            await check_tx(cid, x["id"])
        await db.passive_payments.delete_many(q)
        for x in pays:
            await unlink(cid, x["id"])
        await coge.annulla(db, cid, "pagamenti", did)
        await db.pag_distinte.delete_one({"id": did, "company_id": cid})
        return {"ok": True}

    return r

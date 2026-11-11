import uuid
from datetime import date, datetime, timezone
from io import BytesIO
from typing import List, Literal, Optional
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from pymongo.errors import DuplicateKeyError
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from estratto import eur, itd, _tbl
from magazzino import recompute_article, replay

CAUSALI = ["Vendita", "Conto visione", "Conto lavorazione", "Reso a fornitore", "Omaggio", "Sostituzione in garanzia", "Altro"]
MAG_CAUSALE = {"Vendita": "Vendita", "Reso a fornitore": "Reso a fornitore"}
DATE_RX = r"^\d{4}-\d{2}-\d{2}$"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DdtLine(BaseModel):
    article_id: Optional[str] = Field(default=None, max_length=40)
    codice: Optional[str] = Field(default="", max_length=40)
    descrizione: str = Field(min_length=1, max_length=1000)
    quantita: float = Field(gt=0)
    unita_misura: Optional[str] = Field(default="", max_length=10)
    prezzo_unitario: float = Field(default=0, ge=0)
    aliquota: float = 22
    natura: Optional[str] = None
    note: Optional[str] = Field(default="", max_length=500)


class Indirizzo(BaseModel):
    denominazione: Optional[str] = Field(default="", max_length=120)
    indirizzo: Optional[str] = Field(default="", max_length=120)
    cap: Optional[str] = Field(default="", max_length=10)
    comune: Optional[str] = Field(default="", max_length=80)
    provincia: Optional[str] = Field(default="", max_length=2)


class Vettore(BaseModel):
    denominazione: Optional[str] = Field(default="", max_length=120)
    partita_iva: Optional[str] = Field(default="", max_length=16)
    indirizzo: Optional[str] = Field(default="", max_length=160)


class DdtIn(BaseModel):
    data: str = Field(pattern=DATE_RX)
    party_id: str
    causale: Literal[tuple(CAUSALI)] = "Vendita"
    porto: Literal["franco", "assegnato"] = "franco"
    trasporto_a_cura: Literal["mittente", "destinatario", "vettore"] = "mittente"
    vettore: Optional[Vettore] = None
    destinazione: Optional[Indirizzo] = None
    colli: Optional[int] = Field(default=None, ge=0, le=100000)
    peso_kg: Optional[float] = Field(default=None, ge=0)
    aspetto_beni: Optional[str] = Field(default="", max_length=80)
    inizio_trasporto: Optional[str] = Field(default="", max_length=16)
    prezzi_in_stampa: bool = False
    note: Optional[str] = Field(default="", max_length=1000)
    lines: List[DdtLine] = Field(min_length=1, max_length=300)

    @field_validator("data")
    @classmethod
    def _d(cls, v):
        try:
            d = date.fromisoformat(v)
        except ValueError:
            raise ValueError("Data non valida")
        if d > date.today():
            raise ValueError("La data del DDT non può essere futura")
        return v


class ConfermaIn(BaseModel):
    forza: bool = False


class DifferitaIn(BaseModel):
    dal: str = Field(pattern=DATE_RX)
    al: str = Field(pattern=DATE_RX)
    data_fattura: str = Field(pattern=DATE_RX)
    party_ids: List[str] = Field(min_length=1, max_length=500)


def _line_tot(ln: dict) -> float:
    return round(ln["quantita"] * ln["prezzo_unitario"], 2)


def ddt_pdf(comp: dict, d: dict) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=12 * mm, title=f"DDT {d.get('numero_display') or 'bozza'}")
    ss = getSampleStyleSheet()
    sm = ParagraphStyle("sm", parent=ss["Normal"], fontSize=8.5, leading=11)
    e = lambda s: escape(str(s or ""))  # noqa: E731
    c = d["cliente"]
    dest = d.get("destinazione") or {}
    has_dest = any((dest.get(k) or "").strip() for k in ("denominazione", "indirizzo", "comune"))

    def addr(x):
        return f"<b>{e(x.get('denominazione'))}</b><br/>{e(x.get('indirizzo'))}<br/>{e(x.get('cap'))} {e(x.get('comune'))} {('(' + e(x.get('provincia')) + ')') if x.get('provincia') else ''}"
    mitt = f"{addr(comp)}<br/>P.IVA {e(comp.get('partita_iva'))}"
    dest_c = f"{addr(c)}<br/>P.IVA {e(c.get('partita_iva') or c.get('codice_fiscale'))}"
    head = Table([[Paragraph(mitt, sm), Paragraph("<b>DOCUMENTO DI TRASPORTO</b><br/>(D.P.R. 472/1996)<br/><br/>"
                                                  f"N. <b>{e(d.get('numero_display') or 'BOZZA')}</b> del <b>{itd(d['data'])}</b>", sm)],
                  [Paragraph(f"<font size=7 color='#64748b'>DESTINATARIO</font><br/>{dest_c}", sm),
                   Paragraph(f"<font size=7 color='#64748b'>LUOGO DI DESTINAZIONE</font><br/>{addr(dest) if has_dest else 'Come destinatario'}", sm)]],
                 colWidths=[91 * mm, 91 * mm])
    head.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")), ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                              ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    v = d.get("vettore") or {}
    info = Table([[Paragraph(f"<font size=7 color='#64748b'>CAUSALE DEL TRASPORTO</font><br/>{e(d['causale'])}", sm),
                   Paragraph(f"<font size=7 color='#64748b'>PORTO</font><br/>{e(d['porto'].capitalize())}", sm),
                   Paragraph(f"<font size=7 color='#64748b'>TRASPORTO A CURA DEL</font><br/>{e(d['trasporto_a_cura'].capitalize())}", sm),
                   Paragraph(f"<font size=7 color='#64748b'>INIZIO TRASPORTO</font><br/>{e(d.get('inizio_trasporto').replace('T', ' ') if d.get('inizio_trasporto') else '')}", sm)]],
                 colWidths=[50 * mm, 36 * mm, 48 * mm, 48 * mm])
    info.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")), ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    prezzi = d.get("prezzi_in_stampa")
    rows = [["Codice", "Descrizione", "U.M.", "Quantità"] + (["Prezzo", "Importo", "IVA"] if prezzi else [])]
    for ln in d["lines"]:
        desc = Paragraph(e(ln["descrizione"]) + (f"<br/><font size=7 color='#64748b'>{e(ln['note'])}</font>" if ln.get("note") else ""), sm)
        rows.append([ln.get("codice") or "", desc, ln.get("unita_misura") or "", f"{ln['quantita']:g}".replace(".", ",")] +
                    ([eur(ln["prezzo_unitario"]), eur(_line_tot(ln)), f"{ln['aliquota']:g}%"] if prezzi else []))
    widths = [24, 74, 14, 20, 18, 20, 12] if prezzi else [28, 116, 16, 22]
    story = [head, Spacer(1, 6), info, Spacer(1, 8), _tbl(rows, [w * mm for w in widths], right_cols=(3, 4, 5, 6) if prezzi else (3,))]
    if prezzi:
        story += [Spacer(1, 4), Paragraph(f"<para alignment='right'>Totale imponibile merce: <b>{eur(sum(_line_tot(ln) for ln in d['lines']))}</b></para>", sm)]
    if d.get("note"):
        story += [Spacer(1, 6), Paragraph(f"<b>Note:</b> {e(d['note'])}", sm)]
    foot = Table([[Paragraph(f"<font size=7 color='#64748b'>N. COLLI</font><br/>{e(d.get('colli') if d.get('colli') is not None else '')}", sm),
                   Paragraph(f"<font size=7 color='#64748b'>PESO KG</font><br/>{e(str(d['peso_kg']).replace('.', ',') if d.get('peso_kg') is not None else '')}", sm),
                   Paragraph(f"<font size=7 color='#64748b'>ASPETTO ESTERIORE DEI BENI</font><br/>{e(d.get('aspetto_beni'))}", sm)],
                  [Paragraph(f"<font size=7 color='#64748b'>VETTORE</font><br/>{e(v.get('denominazione'))} {('P.IVA ' + e(v.get('partita_iva'))) if v.get('partita_iva') else ''}<br/>{e(v.get('indirizzo'))}", sm), "", ""],
                  [Paragraph("<font size=7 color='#64748b'>FIRMA CONDUCENTE</font><br/><br/><br/>", sm), Paragraph("<font size=7 color='#64748b'>FIRMA VETTORE</font>", sm),
                   Paragraph("<font size=7 color='#64748b'>FIRMA DESTINATARIO</font>", sm)]], colWidths=[50 * mm, 50 * mm, 82 * mm])
    foot.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")), ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                              ("SPAN", (0, 1), (-1, 1)), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [Spacer(1, 10), foot]
    if d.get("status") == "annullato":
        story.insert(0, Paragraph("<font color='#dc2626'><b>DOCUMENTO ANNULLATO</b></font>", ss["Heading2"]))
    doc.build(story)
    return buf.getvalue()


def build(db, tenant, deps) -> APIRouter:
    r = APIRouter(prefix="/api/ddt")
    ferr = deps["ferr"]

    async def _get(cid, did):
        d = await db.ddts.find_one({"id": did, "company_id": cid}, {"_id": 0})
        if not d:
            raise HTTPException(404, "DDT non trovato")
        return d

    async def _prepare(body: DdtIn, t: dict) -> dict:
        cid = t["cid"]
        p = await db.parties.find_one({"id": body.party_id, "company_id": cid, "tipo": "cliente"}, {"_id": 0})
        if not p:
            raise ferr(400, "party_id", "Seleziona un cliente")
        lines = []
        for i, ln in enumerate(body.lines):
            if ln.aliquota not in deps["aliquote"]:
                raise ferr(422, f"lines.{i}.aliquota", "Aliquota IVA non valida")
            if ln.aliquota == 0 and ln.natura not in deps["nature"]:
                raise ferr(422, f"lines.{i}.natura", f"Indica la Natura IVA per la riga \"{ln.descrizione}\" con aliquota 0%")
            x = ln.model_dump()
            if ln.article_id:
                a = await db.articles.find_one({"id": ln.article_id, "company_id": cid}, {"_id": 0, "codice": 1, "gestione_magazzino": 1})
                if not a:
                    raise ferr(422, f"lines.{i}.descrizione", "Articolo non trovato")
                x |= {"codice": a["codice"], "gestione_magazzino": bool(a.get("gestione_magazzino"))}
            x["natura"] = x["natura"] if ln.aliquota == 0 else None
            lines.append(x)
        return {**body.model_dump(exclude={"lines"}), "lines": lines, "cliente": p, "imponibile": round(sum(_line_tot(x) for x in lines), 2)}

    @r.get("")
    async def elenco(stato: Optional[str] = None, dal: Optional[str] = None, al: Optional[str] = None, party_id: Optional[str] = None, t: dict = Depends(tenant)):
        q = {"company_id": t["cid"], **({"status": stato} if stato else {}), **({"party_id": party_id} if party_id else {})}
        if dal or al:
            q["data"] = {**({"$gte": dal} if dal else {}), **({"$lte": al} if al else {})}
        return await db.ddts.find(q, {"_id": 0, "lines": 0}).sort([("data", -1), ("numero", -1), ("created_at", -1)]).to_list(5000)

    @r.get("/fatturazione")
    async def da_fatturare(dal: str, al: str, t: dict = Depends(tenant)):
        docs = await db.ddts.find({"company_id": t["cid"], "status": "confermato", "causale": "Vendita", "data": {"$gte": dal, "$lte": al}},
                                  {"_id": 0, "id": 1, "numero_display": 1, "data": 1, "party_id": 1, "cliente.denominazione": 1, "imponibile": 1}).sort([("data", 1), ("numero", 1)]).to_list(10000)
        g = {}
        for d in docs:
            x = g.setdefault(d["party_id"], {"party_id": d["party_id"], "cliente": d["cliente"]["denominazione"], "ddt": [], "imponibile": 0})
            x["ddt"].append({k: d[k] for k in ("id", "numero_display", "data", "imponibile")})
            x["imponibile"] = round(x["imponibile"] + d["imponibile"], 2)
        return sorted(g.values(), key=lambda x: x["cliente"].lower())

    @r.post("/fatturazione")
    async def genera_differite(body: DifferitaIn, t: dict = Depends(tenant)):
        cid, out = t["cid"], {"fatture": [], "errori": []}
        for pid in dict.fromkeys(body.party_ids):
            docs = await db.ddts.find({"company_id": cid, "party_id": pid, "status": "confermato", "causale": "Vendita", "data": {"$gte": body.dal, "$lte": body.al}},
                                      {"_id": 0}).sort([("data", 1), ("numero", 1)]).to_list(1000)
            if not docs:
                continue
            nome = docs[-1]["cliente"]["denominazione"]
            if body.data_fattura < docs[-1]["data"]:
                out["errori"].append({"cliente": nome, "errore": f"La data della fattura non può precedere l'ultimo DDT ({itd(docs[-1]['data'])})"})
                continue
            lines, rif = [], []
            for d in docs:
                start = len(lines) + 1
                for k, ln in enumerate(d["lines"]):
                    nota = (f"Rif. DDT n. {d['numero_display']} del {itd(d['data'])}" if k == 0 else "") + (f" - {ln['note']}" if ln.get("note") else "")
                    lines.append(deps["LineIn"](descrizione=ln["descrizione"], quantita=ln["quantita"], unita_misura=ln.get("unita_misura") or "",
                                                prezzo_unitario=ln["prezzo_unitario"], aliquota=ln["aliquota"], natura=ln.get("natura"),
                                                note=nota.strip(" -")[:500], article_id=ln.get("article_id")))
                rif.append({"id": d["id"], "numero": d["numero_display"], "data": d["data"], "linee": list(range(start, len(lines) + 1))})
            mp = docs[-1]["cliente"].get("modalita_pagamento")
            try:
                inv_in = deps["InvoiceIn"](tipo_documento="TD24", data=body.data_fattura, party_id=pid, lines=lines,
                                           causale=f"Fattura riepilogativa DDT dal {itd(docs[0]['data'])} al {itd(docs[-1]['data'])}",
                                           **({"modalita_pagamento": mp} if mp in ("MP01", "MP02", "MP05", "MP08", "MP12") else {}))
                inv = await deps["create_invoice"](inv_in, t)
            except HTTPException as e:
                d = e.detail
                det = d if isinstance(d, str) else (d[0].get("msg") if isinstance(d, list) and d else (d.get("message") if isinstance(d, dict) else str(d)))
                out["errori"].append({"cliente": nome, "errore": det})
                continue
            except ValueError as e:
                out["errori"].append({"cliente": nome, "errore": str(e)})
                continue
            await db.invoices.update_one({"id": inv["id"]}, {"$set": {"ddt_rif": rif}})
            await db.ddts.update_many({"id": {"$in": [x["id"] for x in rif]}, "company_id": cid},
                                      {"$set": {"status": "fatturato", "invoice_id": inv["id"], "invoice_numero": inv["numero_display"], "updated_at": _now()}})
            out["fatture"].append({"id": inv["id"], "numero_display": inv["numero_display"], "cliente": nome, "totale": inv["totale"], "ddt": len(rif)})
        return out

    @r.get("/{did}")
    async def dettaglio(did: str, t: dict = Depends(tenant)):
        return await _get(t["cid"], did)

    @r.post("")
    async def crea(body: DdtIn, t: dict = Depends(tenant)):
        d = {"id": str(uuid.uuid4()), "company_id": t["cid"], **await _prepare(body, t), "status": "bozza", "numero": None, "anno": int(body.data[:4]),
             "numero_display": None, "stock_move_ids": [], "invoice_id": None, "created_at": _now(), "updated_at": _now(),
             "created_by": t["user"].get("name") or t["user"]["email"]}
        await db.ddts.insert_one(dict(d))
        return d

    @r.put("/{did}")
    async def modifica(did: str, body: DdtIn, t: dict = Depends(tenant)):
        d = await _get(t["cid"], did)
        if d["status"] != "bozza":
            raise HTTPException(400, "Il DDT è già confermato: annullalo per modificarlo")
        await db.ddts.update_one({"id": did}, {"$set": {**await _prepare(body, t), "anno": int(body.data[:4]), "updated_at": _now()}})
        return await _get(t["cid"], did)

    @r.delete("/{did}")
    async def elimina(did: str, t: dict = Depends(tenant)):
        d = await _get(t["cid"], did)
        if d["status"] != "bozza":
            raise HTTPException(400, "Puoi eliminare solo i DDT in bozza: un DDT confermato si annulla")
        await db.ddts.delete_one({"id": did})
        return {"ok": True}

    async def _carenze(cid: str, d: dict) -> list:
        need = {}
        for ln in d["lines"]:
            if ln.get("article_id") and ln.get("gestione_magazzino"):
                need[ln["article_id"]] = need.get(ln["article_id"], 0) + ln["quantita"]
        out = []
        for aid, q in need.items():
            a = await db.articles.find_one({"id": aid, "company_id": cid}, {"_id": 0, "codice": 1, "descrizione": 1, "unita_misura": 1})
            moves = await db.stock_moves.find({"company_id": cid, "article_id": aid}, {"_id": 0}).to_list(100000)
            sim = replay(moves + [{"tipo": "scarico", "quantita": q, "data": d["data"], "created_at": _now()}])
            if sim["minimo"]["giacenza"] < -0.0001:
                out.append({"article_id": aid, "codice": a["codice"], "descrizione": a["descrizione"], "richiesta": q,
                            "disponibile": round(q + sim["minimo"]["giacenza"], 4), "unita_misura": a.get("unita_misura") or ""})
        return out

    @r.post("/{did}/conferma")
    async def conferma(did: str, body: ConfermaIn, t: dict = Depends(tenant)):
        cid = t["cid"]
        d = await _get(cid, did)
        if d["status"] != "bozza":
            raise HTTPException(400, "Il DDT è già confermato")
        if d["data"] > date.today().isoformat():
            raise HTTPException(400, "La data del DDT non può essere futura")
        car = await _carenze(cid, d)
        if car:
            if t["company"].get("ddt_giacenza") == "blocca":
                raise HTTPException(400, {"message": "Giacenza insufficiente: il DDT non può essere confermato", "carenze": car})
            if not body.forza:
                raise HTTPException(409, {"message": "Giacenza insufficiente per alcuni articoli", "carenze": car})
        anno = int(d["data"][:4])
        for _ in range(5):
            last = await db.ddts.find_one({"company_id": cid, "anno": anno, "numero": {"$ne": None}}, {"_id": 0, "numero": 1, "data": 1}, sort=[("numero", -1)])
            if last and last["data"] > d["data"]:
                raise ferr(400, "data", f"Data non coerente: l'ultimo DDT confermato è del {itd(last['data'])}")
            numero = (last["numero"] if last else 0) + 1
            try:
                res = await db.ddts.update_one({"id": did, "status": "bozza"}, {"$set": {"numero": numero, "anno": anno, "numero_display": f"{numero}/{anno}", "status": "confermato",
                                                                                        "confermato_at": _now(), "updated_at": _now()}})
                break
            except DuplicateKeyError:
                continue
        else:
            raise HTTPException(409, "Numerazione occupata, riprova")
        if not res.modified_count:
            raise HTTPException(400, "Il DDT è già confermato")
        u, ids = t["user"], []
        for ln in d["lines"]:
            if not (ln.get("article_id") and ln.get("gestione_magazzino")):
                continue
            a = await db.articles.find_one({"id": ln["article_id"], "company_id": cid}, {"_id": 0, "codice": 1, "descrizione": 1, "unita_misura": 1})
            m = {"id": str(uuid.uuid4()), "company_id": cid, "article_id": ln["article_id"], "tipo": "scarico", "data": d["data"], "quantita": ln["quantita"],
                 "costo_unitario": None, "causale": MAG_CAUSALE.get(d["causale"], "Altro"), "documento": f"DDT {numero}/{anno}",
                 "note": f"{d['causale']} - {d['cliente']['denominazione']}"[:300], "codice": a["codice"], "descrizione": a["descrizione"],
                 "unita_misura": a.get("unita_misura") or "", "ddt_id": did, "created_at": _now(), "created_by": u.get("name") or u.get("email")}
            await db.stock_moves.insert_one(m)
            ids.append(m["id"])
        await db.ddts.update_one({"id": did}, {"$set": {"stock_move_ids": ids}})
        for aid in {ln["article_id"] for ln in d["lines"] if ln.get("article_id") and ln.get("gestione_magazzino")}:
            await recompute_article(db, cid, aid)
        return {**await _get(cid, did), "carenze": car}

    @r.post("/{did}/annulla")
    async def annulla(did: str, t: dict = Depends(tenant)):
        cid = t["cid"]
        d = await _get(cid, did)
        if d["status"] == "fatturato":
            raise HTTPException(400, f"Il DDT è già stato fatturato con la fattura {d.get('invoice_numero')}")
        if d["status"] != "confermato":
            raise HTTPException(400, "Puoi annullare solo un DDT confermato")
        await db.stock_moves.delete_many({"company_id": cid, "ddt_id": did})
        await db.ddts.update_one({"id": did}, {"$set": {"status": "annullato", "stock_move_ids": [], "annullato_at": _now(), "updated_at": _now()}})
        for aid in {ln["article_id"] for ln in d["lines"] if ln.get("article_id") and ln.get("gestione_magazzino")}:
            await recompute_article(db, cid, aid)
        return await _get(cid, did)

    @r.get("/{did}/pdf")
    async def pdf(did: str, t: dict = Depends(tenant)):
        d = await _get(t["cid"], did)
        name = f"DDT_{(d.get('numero_display') or 'bozza').replace('/', '-')}.pdf"
        return Response(ddt_pdf(t["company"], d), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}"'})

    return r


async def ensure_indexes(db):
    await db.ddts.create_index([("company_id", 1), ("anno", 1), ("numero", 1)], unique=True, partialFilterExpression={"numero": {"$type": "number"}})
    await db.ddts.create_index([("company_id", 1), ("status", 1), ("data", 1)])

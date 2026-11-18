import io
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import List, Literal, Optional

from bson import Binary
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

UE = {"AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GR", "EL", "HR", "HU", "IE", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK"}
SEED = [("VEN", "Registro IVA vendite", "vendite", True), ("ACQ", "Registro IVA acquisti", "acquisti", True),
        ("CEE", "Registro IVA acquisti intra UE", "acquisti", False), ("SPL", "Registro IVA vendite split payment PA", "vendite", False)]
CAUS_SEED = [("FC", "Fattura di acquisto intra UE", "acquisti", "CEE"), ("FS", "Fattura di vendita split payment PA", "vendite", "SPL")]
CAUS_DEF = {"FV": "VEN", "NV": "VEN", "FA": "ACQ", "NA": "ACQ"}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _r2(v):
    return round(float(v or 0) + 0.0, 2)


def _itd(s):
    return f"{s[8:10]}/{s[5:7]}/{s[:4]}" if s else ""


def _eur(v):
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class RegistroIn(BaseModel):
    codice: str = Field(min_length=1, max_length=6, pattern=r"^[A-Z0-9]+$")
    descrizione: str = Field(min_length=1, max_length=80)
    tipo: Literal["vendite", "acquisti"]
    causali: List[str] = Field(default_factory=list, max_length=50)


class AssegnaIn(BaseModel):
    kind: Literal["vendite", "acquisti"]
    id: str
    registro_id: str


class StampaIn(BaseModel):
    tipo: Literal["iva", "giornale"]
    registro_id: Optional[str] = None
    anno: int = Field(ge=2000, le=2100)
    dal: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    al: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    definitiva: bool = False


class BloccoIn(BaseModel):
    blocca: bool


async def lock_date(db, cid: str, key: str) -> Optional[str]:
    s = await db.stampe_fiscali.find_one({"company_id": cid, "key": key, "blocca": True}, {"_id": 0, "al": 1}, sort=[("al", -1)])
    return s["al"] if s else None


async def check_giornale(db, cid: str, data: str):
    lk = await lock_date(db, cid, "giornale")
    if lk and data <= lk:
        raise ValueError(f"Il libro giornale è stampato in definitiva fino al {_itd(lk)}: riapri i movimenti nei parametri azienda per modificare registrazioni fino a quella data")


async def ensure_registri(db, cid: str) -> list:
    regs = await db.iva_registri.find({"company_id": cid}, {"_id": 0}).to_list(100)
    if not regs:
        regs = [{"id": str(uuid.uuid4()), "company_id": cid, "codice": c, "descrizione": d, "tipo": t, "predefinito": p, "created_at": _now()} for c, d, t, p in SEED]
        await db.iva_registri.insert_many([dict(x) for x in regs])
        by = {r["codice"]: r["id"] for r in regs}
        if await db.coa_causali.count_documents({"company_id": cid}):
            for c, d, reg, rc in CAUS_SEED:
                await db.coa_causali.update_one({"company_id": cid, "codice": c}, {"$setOnInsert": {"id": str(uuid.uuid4()), "descrizione": d, "registro": reg,
                                                "conto_dare": "", "conto_avere": "", "registro_id": by[rc]}}, upsert=True)
            for c, rc in CAUS_DEF.items():
                await db.coa_causali.update_one({"company_id": cid, "codice": c, "registro_id": {"$in": [None, ""]}}, {"$set": {"registro_id": by[rc]}})
    return sorted(regs, key=lambda r: (r["tipo"], not r.get("predefinito"), r["codice"]))


def _proposta_causale(kind: str, row: dict) -> str:
    if kind == "vendite":
        return "NV" if row["tipo_documento"] == "TD04" else "FS" if row.get("split_payment") else "FV"
    if row.get("paese") in UE:
        return "FC"
    return "NA" if row["tipo_documento"] == "TD04" else "FA"


def assegna(kind: str, rows: list, regs: list, causali: dict) -> None:
    mine = [r for r in regs if r["tipo"] == kind]
    ids = {r["id"] for r in mine}
    by_cod = {r["codice"]: r["id"] for r in mine}
    pred = next((r["id"] for r in mine if r.get("predefinito")), mine[0]["id"] if mine else None)
    for x in rows:
        if x.get("registro_iva_id") in ids:
            x["registro_proposto"] = False
            continue
        c = _proposta_causale(kind, x)
        rid = causali.get(c)
        if rid not in ids:
            rid = by_cod.get({"FC": "CEE", "FS": "SPL"}.get(c, "")) or pred
        x["registro_iva_id"], x["registro_proposto"] = rid, True


def totali(rows: list) -> dict:
    tot = {}
    for x in rows:
        for r in x["riepilogo"]:
            k = f"{r['natura']} RC {r['aliquota']:g}%" if r.get("rc") else r["natura"] or f"{r['aliquota']:g}%"
            v = tot.setdefault(k, {"codice": k, "aliquota": r["aliquota"], "natura": r["natura"], "rc": bool(r.get("rc")), "imponibile": 0.0, "imposta": 0.0, "documenti": 0})
            v["imponibile"] += r["imponibile"]
            v["imposta"] += r["imposta"]
            v["documenti"] += 1
    t = sorted(({**v, "imponibile": _r2(v["imponibile"]), "imposta": _r2(v["imposta"])} for v in tot.values()), key=lambda v: (v["natura"] is not None, -v["aliquota"], v["codice"]))
    return {"totali": t, "imponibile": _r2(sum(v["imponibile"] for v in t)), "imposta": _r2(sum(v["imposta"] for v in t)),
            "totale": _r2(sum(x["totale"] for x in rows)), "imposta_indetraibile": _r2(sum(x.get("iva_indetraibile") or 0 for x in rows))}


def _pdf(comp: dict, titolo: str, sottotitolo: str, story_fn, anno: int, pagina_da: int, prova: bool) -> tuple:
    buf = io.BytesIO()
    pag = {"n": 0}

    def on_page(c, d):
        pag["n"] = d.page
        c.saveState()
        w, h = landscape(A4)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(12 * mm, h - 10 * mm, f"{comp.get('denominazione', '')} · P.IVA {comp.get('partita_iva', '')}")
        c.setFont("Helvetica", 8)
        c.drawString(12 * mm, h - 14 * mm, f"{titolo} · {sottotitolo}")
        c.drawRightString(w - 12 * mm, h - 10 * mm, f"Pag. {anno}/{pagina_da + d.page - 1}")
        if prova:
            c.setFont("Helvetica-Bold", 60)
            c.setFillColor(colors.Color(0.85, 0.1, 0.1, alpha=0.12))
            c.translate(w / 2, h / 2)
            c.rotate(30)
            c.drawCentredString(0, 0, "STAMPA DI PROVA")
        c.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=20 * mm, bottomMargin=12 * mm, title=titolo)
    doc.build(story_fn(), onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue(), pag["n"] or 1


def _table(data, widths, num_cols=(), bold_last=False):
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
    st = [("FONT", (0, 0), (-1, -1), "Helvetica", 7), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7), ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
          ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 2)]
    st += [("ALIGN", (c, 0), (c, -1), "RIGHT") for c in num_cols]
    if bold_last:
        st += [("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 7), ("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.black)]
    t.setStyle(TableStyle(st))
    return t


def pdf_iva(comp, reg, d, dal, al, anno, pagina_da, prova):
    sm = getSampleStyleSheet()["Normal"]
    sm.fontSize = 7
    sm.leading = 8.5
    ven = reg["tipo"] == "vendite"

    def story():
        head = ["N.", "Numero" if ven else "Prot.", "Data" if ven else "Data reg.", "Documento", "Cliente" if ven else "Fornitore", "P.IVA / C.F.", "Aliquota", "Imponibile", "Imposta", "Totale doc."]
        rows = [head]
        for i, x in enumerate(d["rows"], 1):
            for j, r in enumerate(x["riepilogo"]):
                al_ = f"{r['natura']} RC {r['aliquota']:g}%" if r.get("rc") else r["natura"] or f"{r['aliquota']:g}%"
                first = j == 0
                rows.append([str(i) if first else "", (x["numero"] if ven else str(x["protocollo"])) if first else "", _itd(x["data"] if ven else x["data_registrazione"]) if first else "",
                             (("NC " if x["tipo_documento"] == "TD04" else "FT ") + ("" if ven else f"{x['numero']} del {_itd(x['data'])}")) if first else "",
                             Paragraph(x["cliente" if ven else "fornitore"] or "", sm) if first else "", (x.get("partita_iva") or "") if first else "",
                             al_ + (" split" if x.get("split_payment") else ""), _eur(r["imponibile"]), _eur(r["imposta"]), _eur(x["totale"]) if first else ""])
        if len(rows) == 1:
            rows.append(["", "", "", "Nessun documento nel periodo", "", "", "", "", "", ""])
        out = [_table(rows, [10, 22, 18, 40, 70, 28, 22, 23, 21, 23], (7, 8, 9)), Spacer(1, 6 * mm),
               Paragraph("<b>Riepilogo per aliquota / natura</b>", sm), Spacer(1, 2 * mm)]
        tot = [["Aliquota / natura", "Documenti", "Imponibile", "Imposta"]] + [[v["codice"], str(v["documenti"]), _eur(v["imponibile"]), _eur(v["imposta"])] for v in d["totali"]]
        tot.append(["Totale", "", _eur(d["imponibile"]), _eur(d["imposta"])])
        out.append(_table(tot, [50, 22, 30, 30], (1, 2, 3), bold_last=True))
        if d.get("imposta_indetraibile"):
            out += [Spacer(1, 2 * mm), Paragraph(f"Di cui IVA indetraibile: {_eur(d['imposta_indetraibile'])}", sm)]
        return out

    return _pdf(comp, f"{reg['descrizione']} ({reg['codice']})", f"dal {_itd(dal)} al {_itd(al)}", story, anno, pagina_da, prova)


def pdf_giornale(comp, entries, dal, al, anno, pagina_da, prova, riporto):
    sm = getSampleStyleSheet()["Normal"]
    sm.fontSize = 7
    sm.leading = 8.5

    def story():
        rows = [["Riga", "Data", "N. reg.", "Causale", "Descrizione", "Conto", "Descrizione conto", "Dare", "Avere"]]
        n, td, ta = riporto["righe"], riporto["dare"], riporto["avere"]
        rows.append(["", "", "", "", "Riporto", "", "", _eur(td), _eur(ta)])
        for e in entries:
            for k, r in enumerate(e["righe"]):
                n += 1
                td += r["dare"]
                ta += r["avere"]
                rows.append([str(n), _itd(e["data"]) if not k else "", f"{e['numero']}" if not k else "", e["causale"] if not k else "",
                             Paragraph((e["descrizione"] or "") if not k else (r.get("party_nome") or ""), sm), r["conto"], Paragraph(r.get("conto_descrizione") or "", sm),
                             _eur(r["dare"]) if r["dare"] else "", _eur(r["avere"]) if r["avere"] else ""])
        rows.append(["", "", "", "", "Totali progressivi", "", "", _eur(td), _eur(ta)])
        riporto.update({"righe": n, "dare": _r2(td), "avere": _r2(ta)})
        return [_table(rows, [12, 17, 14, 13, 75, 18, 64, 22, 22], (7, 8), bold_last=True)]

    return _pdf(comp, "Libro giornale", f"dal {_itd(dal)} al {_itd(al)}", story, anno, pagina_da, prova)


def build(db, tenant, tenant_accounting, deps) -> APIRouter:
    r = APIRouter(prefix="/api/stampe-fiscali")
    fetch = deps["fetch"]

    def _admin(t):
        if t["user"].get("role") != "admin":
            raise HTTPException(403, "Operazione riservata agli amministratori")

    async def _causali(cid):
        return {c["codice"]: c.get("registro_id") async for c in db.coa_causali.find({"company_id": cid}, {"_id": 0, "codice": 1, "registro_id": 1})}

    async def _reg(cid, rid):
        reg = next((x for x in await ensure_registri(db, cid) if x["id"] == rid), None)
        if not reg:
            raise HTTPException(404, "Registro IVA non trovato")
        return reg

    async def _dati(t, reg, anno, dal, al):
        cid = t["cid"]
        regs = await ensure_registri(db, cid)
        d = await fetch(reg["tipo"], anno, dal, al, t)
        assegna(reg["tipo"], d["rows"], regs, await _causali(cid))
        rows = [x for x in d["rows"] if x["registro_iva_id"] == reg["id"]]
        return {"rows": rows, **totali(rows), "anni": d["anni"]}

    @r.get("/registri")
    async def registri(t: dict = Depends(tenant)):
        regs = await ensure_registri(db, t["cid"])
        caus = await db.coa_causali.find({"company_id": t["cid"], "registro": {"$in": ["vendite", "acquisti"]}}, {"_id": 0, "codice": 1, "descrizione": 1, "registro": 1, "registro_id": 1}).to_list(200)
        return {"registri": regs, "causali": caus}

    async def _save_causali(cid, reg, codici):
        await db.coa_causali.update_many({"company_id": cid, "registro_id": reg["id"], "codice": {"$nin": codici}}, {"$set": {"registro_id": None}})
        if codici:
            await db.coa_causali.update_many({"company_id": cid, "codice": {"$in": codici}, "registro": reg["tipo"]}, {"$set": {"registro_id": reg["id"]}})

    @r.post("/registri")
    async def crea_registro(body: RegistroIn, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        await ensure_registri(db, cid)
        if await db.iva_registri.find_one({"company_id": cid, "codice": body.codice}):
            raise HTTPException(400, f"Esiste già un registro con codice {body.codice}")
        reg = {"id": str(uuid.uuid4()), "company_id": cid, "codice": body.codice, "descrizione": body.descrizione, "tipo": body.tipo, "predefinito": False, "created_at": _now()}
        await db.iva_registri.insert_one(dict(reg))
        await _save_causali(cid, reg, body.causali)
        return reg

    @r.put("/registri/{rid}")
    async def mod_registro(rid: str, body: RegistroIn, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        reg = await _reg(cid, rid)
        if body.tipo != reg["tipo"] and await db.stampe_fiscali.find_one({"company_id": cid, "key": f"iva:{rid}"}):
            raise HTTPException(400, "Il registro ha stampe definitive: non puoi cambiarne il tipo")
        if await db.iva_registri.find_one({"company_id": cid, "codice": body.codice, "id": {"$ne": rid}}):
            raise HTTPException(400, f"Esiste già un registro con codice {body.codice}")
        await db.iva_registri.update_one({"id": rid}, {"$set": {"codice": body.codice, "descrizione": body.descrizione, "tipo": body.tipo}})
        await _save_causali(cid, {**reg, "tipo": body.tipo}, body.causali)
        return {**reg, "codice": body.codice, "descrizione": body.descrizione, "tipo": body.tipo}

    @r.delete("/registri/{rid}")
    async def del_registro(rid: str, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        reg = await _reg(cid, rid)
        if reg.get("predefinito"):
            raise HTTPException(400, "Il registro predefinito non si può eliminare")
        if await db.stampe_fiscali.find_one({"company_id": cid, "key": f"iva:{rid}"}):
            raise HTTPException(400, "Il registro ha stampe definitive: cancellale prima dai parametri azienda")
        for coll in (db.invoices, db.passive_invoices):
            await coll.update_many({"company_id": cid, "registro_iva_id": rid}, {"$unset": {"registro_iva_id": ""}})
        await db.coa_causali.update_many({"company_id": cid, "registro_id": rid}, {"$set": {"registro_id": None}})
        await db.iva_registri.delete_one({"id": rid})
        return {"ok": True}

    @r.get("/registro")
    async def registro(registro_id: str, anno: int = Query(ge=2000, le=2100), dal: Optional[str] = None, al: Optional[str] = None, t: dict = Depends(tenant)):
        reg = await _reg(t["cid"], registro_id)
        d = await _dati(t, reg, anno, dal, al)
        return {**d, "registro": reg, "bloccato_al": await lock_date(db, t["cid"], f"iva:{registro_id}"),
                "registri": [x for x in await ensure_registri(db, t["cid"]) if x["tipo"] == reg["tipo"]]}

    @r.get("/proposta")
    async def proposta(id: str, t: dict = Depends(tenant)):
        cid = t["cid"]
        d = await db.passive_invoices.find_one({"id": id, "company_id": cid}, {"_id": 0, "tipo_documento": 1, "fornitore": 1, "registro_iva_id": 1})
        if not d:
            raise HTTPException(404, "Documento non trovato")
        regs = await ensure_registri(db, cid)
        row = {"registro_iva_id": d.get("registro_iva_id"), "tipo_documento": d["tipo_documento"], "paese": (d["fornitore"] or {}).get("paese_iva") or (d["fornitore"] or {}).get("nazione")}
        assegna("acquisti", [row], regs, await _causali(cid))
        return {"registro_id": row["registro_iva_id"], "registri": [x for x in regs if x["tipo"] == "acquisti"]}

    @r.put("/documento")
    async def assegna_doc(body: AssegnaIn, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        reg = await _reg(cid, body.registro_id)
        if reg["tipo"] != body.kind:
            raise HTTPException(400, "Registro di tipo diverso dal documento")
        coll = db.invoices if body.kind == "vendite" else db.passive_invoices
        doc = await coll.find_one({"id": body.id, "company_id": cid}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Documento non trovato")
        regs = await ensure_registri(db, cid)
        row = {"registro_iva_id": doc.get("registro_iva_id"), "tipo_documento": doc["tipo_documento"], "split_payment": doc.get("split_payment"),
               "paese": ((doc.get("fornitore") or {}).get("paese_iva") or (doc.get("fornitore") or {}).get("nazione"))}
        assegna(body.kind, [row], regs, await _causali(cid))
        dd = doc["data"] if body.kind == "vendite" else (doc.get("data_registrazione") or doc["data"])
        for rid in {row["registro_iva_id"], body.registro_id}:
            lk = await lock_date(db, cid, f"iva:{rid}")
            if lk and dd <= lk:
                raise HTTPException(400, f"Il documento è in un periodo già stampato in definitiva (fino al {_itd(lk)}): riapri i movimenti nei parametri azienda")
        await coll.update_one({"id": body.id}, {"$set": {"registro_iva_id": body.registro_id}})
        return {"ok": True}

    async def _ultima(cid, key, anno):
        return await db.stampe_fiscali.find_one({"company_id": cid, "key": key, "anno": anno}, {"_id": 0, "pdf": 0}, sort=[("al", -1)])

    @r.post("/stampa")
    async def stampa(body: StampaIn, t: dict = Depends(tenant)):
        cid, comp = t["cid"], t["company"]
        if not (body.dal <= body.al and body.dal[:4] == body.al[:4] == str(body.anno)):
            raise HTTPException(400, "Periodo non valido: deve essere compreso nell'anno scelto")
        key = "giornale" if body.tipo == "giornale" else f"iva:{body.registro_id}"
        reg = await _reg(cid, body.registro_id) if body.tipo == "iva" else None
        last = await _ultima(cid, key, body.anno)
        pagina_da = (last["pagina_a"] + 1) if last else 1
        if body.definitiva:
            atteso = (date.fromisoformat(last["al"]) + timedelta(days=1)).isoformat() if last else f"{body.anno}-01-01"
            if body.dal != atteso:
                raise HTTPException(400, f"La stampa definitiva deve iniziare dal {_itd(atteso)} (giorno successivo all'ultima stampa definitiva)")
            if body.al > date.today().isoformat():
                raise HTTPException(400, "La stampa definitiva non può arrivare oltre la data di oggi")
        riporto = {"righe": 0, "dare": 0.0, "avere": 0.0}
        if body.tipo == "giornale":
            f = {"company_id": cid, "data": {"$gte": body.dal, "$lte": body.al}}
            if body.definitiva and await db.coa_entries.count_documents({**f, "provvisoria": True}):
                raise HTTPException(400, "Nel periodo ci sono registrazioni provvisorie (ratei in simulazione): rendile definitive o annullale prima della stampa definitiva")
            entries = await db.coa_entries.find({**f, "provvisoria": {"$ne": True}}, {"_id": 0}).sort([("data", 1), ("numero", 1)]).to_list(100000)
            if last:
                riporto = dict(last.get("riporto") or riporto)
            pdf, pagine = pdf_giornale(comp, entries, body.dal, body.al, body.anno, pagina_da, not body.definitiva, riporto)
            n = len(entries)
        else:
            d = await _dati(t, reg, body.anno, body.dal, body.al)
            pdf, pagine = pdf_iva(comp, reg, d, body.dal, body.al, body.anno, pagina_da, not body.definitiva)
            n = len(d["rows"])
            if body.definitiva:
                coll = db.invoices if reg["tipo"] == "vendite" else db.passive_invoices
                for x in d["rows"]:
                    if x.get("registro_proposto"):
                        await coll.update_one({"id": x["id"], "company_id": cid}, {"$set": {"registro_iva_id": reg["id"]}})
        name = f"{'Libro_giornale' if body.tipo == 'giornale' else 'Registro_IVA_' + reg['codice']}_{body.dal}_{body.al}{'' if body.definitiva else '_PROVA'}.pdf"
        if body.definitiva:
            await db.stampe_fiscali.insert_one({"id": str(uuid.uuid4()), "company_id": cid, "key": key, "tipo": body.tipo, "registro_id": body.registro_id if reg else None,
                                                "titolo": "Libro giornale" if body.tipo == "giornale" else f"{reg['descrizione']} ({reg['codice']})",
                                                "anno": body.anno, "dal": body.dal, "al": body.al, "pagina_da": pagina_da, "pagina_a": pagina_da + pagine - 1,
                                                "documenti": n, "riporto": riporto if body.tipo == "giornale" else None, "blocca": True, "file_name": name,
                                                "pdf": Binary(pdf), "created_at": _now(), "created_by": t["user"].get("name") or t["user"]["email"]})
        return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}"'})

    @r.get("/stampe")
    async def stampe(anno: Optional[int] = None, t: dict = Depends(tenant)):
        q = {"company_id": t["cid"], **({"anno": anno} if anno else {})}
        return await db.stampe_fiscali.find(q, {"_id": 0, "pdf": 0}).sort([("key", 1), ("al", -1)]).to_list(1000)

    @r.get("/stampe/{sid}/pdf")
    async def ristampa(sid: str, t: dict = Depends(tenant)):
        s = await db.stampe_fiscali.find_one({"id": sid, "company_id": t["cid"]}, {"_id": 0, "pdf": 1, "file_name": 1})
        if not s:
            raise HTTPException(404, "Stampa non trovata")
        return Response(bytes(s["pdf"]), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{s["file_name"]}"'})

    @r.delete("/stampe/{sid}")
    async def cancella_stampa(sid: str, t: dict = Depends(tenant)):
        _admin(t)
        r_ = await db.stampe_fiscali.delete_one({"id": sid, "company_id": t["cid"]})
        if not r_.deleted_count:
            raise HTTPException(404, "Stampa non trovata")
        return {"ok": True}

    @r.put("/stampe/{sid}/blocco")
    async def blocco(sid: str, body: BloccoIn, t: dict = Depends(tenant)):
        _admin(t)
        r_ = await db.stampe_fiscali.update_one({"id": sid, "company_id": t["cid"]}, {"$set": {"blocca": body.blocca, "blocco_by": t["user"].get("name") or t["user"]["email"], "blocco_at": _now()}})
        if not r_.matched_count:
            raise HTTPException(404, "Stampa non trovata")
        return {"ok": True}

    return r

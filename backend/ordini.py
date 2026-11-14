import asyncio
import base64
import re
import uuid
from datetime import date, datetime, timezone
from html import escape as hesc
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator

from ddt import DdtIn, ConfermaIn, Indirizzo
from estratto import itd
from fatturapa import line_total, norm_sconto
from magazzino import recompute_article, replay
from ordini_core import aggiorna_impegni, stato_righe, storna
import ordini_pdf

DATE_RX = r"^\d{4}-\d{2}-\d{2}$"
TIPO = Literal["cliente", "fornitore"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RigaOrd(BaseModel):
    id: Optional[str] = Field(default=None, max_length=40)
    article_id: Optional[str] = Field(default=None, max_length=40)
    descrizione: str = Field(min_length=1, max_length=1000)
    quantita: float = Field(gt=0, le=10_000_000)
    unita_misura: Optional[str] = Field(default="", max_length=10)
    prezzo_unitario: float = Field(default=0, ge=0, le=100_000_000)
    sconto: Optional[str] = Field(default="", max_length=30)
    aliquota: float = 22
    natura: Optional[str] = None
    note: Optional[str] = Field(default="", max_length=500)

    @field_validator("sconto")
    @classmethod
    def _sc(cls, v):
        return norm_sconto(v)


class OrdineIn(BaseModel):
    data: str = Field(pattern=DATE_RX)
    party_id: str = Field(min_length=1, max_length=40)
    data_consegna: Optional[str] = Field(default="", pattern=r"^(\d{4}-\d{2}-\d{2})?$")
    riferimento: Optional[str] = Field(default="", max_length=60)
    destinazione: Optional[Indirizzo] = None
    note: Optional[str] = Field(default="", max_length=1000)
    lines: List[RigaOrd] = Field(min_length=1, max_length=300)


class EvadiRiga(BaseModel):
    line_id: str = Field(max_length=40)
    quantita: float = Field(ge=0, le=10_000_000)


class EvadiIn(BaseModel):
    data: str = Field(pattern=DATE_RX)
    righe: List[EvadiRiga] = Field(default_factory=list, max_length=300)
    chiudi: bool = False
    forza: bool = False
    documento_fornitore: Optional[str] = Field(default="", max_length=40)


class EmailOrdIn(BaseModel):
    to: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=200)
    oggetto: str = Field(min_length=1, max_length=200)
    messaggio: str = Field(min_length=1, max_length=5000)
    conferma: bool = False


class LinkBemIn(BaseModel):
    bem_id: str = Field(max_length=40)


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def confronto(bems: list, inv: dict) -> dict:
    righe_f = [{**x, "_usata": False} for x in inv.get("lines") or []]
    out = []
    for b in bems:
        for ln in b["lines"]:
            cod, des = _norm(ln.get("codice")), _norm(ln["descrizione"])
            f = next((x for x in righe_f if not x["_usata"] and ((cod and cod in _norm(x["descrizione"])) or _norm(x["descrizione"]) == des)), None)
            pu = round(float(line_total({**ln, "quantita": 1})), 4)
            row = {"bem": b["numero_display"], "codice": ln.get("codice") or "", "descrizione": ln["descrizione"], "qta_bem": ln["quantita"], "prezzo_ordine": pu,
                   "qta_fattura": None, "prezzo_fattura": None, "esito": "mancante"}
            if f:
                f["_usata"] = True
                pf = round(f["prezzo_totale"] / f["quantita"], 4) if f.get("quantita") else f.get("prezzo_unitario") or 0
                dq, dp = round(f["quantita"] - ln["quantita"], 4), round(pf - pu, 4)
                row |= {"qta_fattura": f["quantita"], "prezzo_fattura": pf, "diff_qta": dq, "diff_prezzo": dp,
                        "esito": "ok" if abs(dq) < 0.0001 and abs(dp) < 0.01 else ("quantita" if abs(dq) >= 0.0001 else "prezzo")}
            out.append(row)
    extra = [{"descrizione": x["descrizione"], "qta_fattura": x["quantita"], "importo": x.get("prezzo_totale")} for x in righe_f if not x["_usata"]]
    imp_b = round(sum(b["imponibile"] for b in bems), 2)
    return {"righe": out, "extra_fattura": extra, "imponibile_bem": imp_b, "imponibile_fattura": inv.get("imponibile") or 0,
            "differenza": round((inv.get("imponibile") or 0) - imp_b, 2), "tutto_ok": bool(out) and all(r["esito"] == "ok" for r in out) and abs((inv.get("imponibile") or 0) - imp_b) < 0.01}


def _tot(lines: list) -> float:
    return round(float(sum(line_total(x) for x in lines)), 2)


def build(db, tenant, deps) -> APIRouter:
    r = APIRouter(prefix="/api")
    ferr, ddt_r, locks = deps["ferr"], deps["ddt"], {}

    async def _get(cid, tipo, oid):
        o = await db.orders.find_one({"id": oid, "company_id": cid, "tipo": tipo}, {"_id": 0})
        if not o:
            raise HTTPException(404, "Ordine non trovato")
        return o

    async def _prepare(cid: str, tipo: str, body: OrdineIn, old: Optional[dict] = None) -> dict:
        p = await db.parties.find_one({"id": body.party_id, "company_id": cid, "tipo": tipo}, {"_id": 0, "listino": 0})
        if not p:
            raise ferr(400, "party_id", f"Seleziona un {tipo}")
        prev = {x["id"]: x for x in (old or {}).get("lines") or []}
        lines = []
        for i, ln in enumerate(body.lines):
            if ln.aliquota not in deps["aliquote"]:
                raise ferr(422, f"lines.{i}.aliquota", "Aliquota IVA non valida")
            if ln.aliquota == 0 and ln.natura not in deps["nature"]:
                raise ferr(422, f"lines.{i}.natura", f"Indica la Natura IVA per la riga \"{ln.descrizione}\" con aliquota 0%")
            x = ln.model_dump() | {"natura": ln.natura if ln.aliquota == 0 else None, "codice": "", "gestione_magazzino": False}
            if ln.article_id:
                a = await db.articles.find_one({"id": ln.article_id, "company_id": cid}, {"_id": 0, "codice": 1, "gestione_magazzino": 1})
                if not a:
                    raise ferr(422, f"lines.{i}.descrizione", "Articolo non trovato")
                x |= {"codice": a["codice"], "gestione_magazzino": bool(a.get("gestione_magazzino"))}
            x["id"] = ln.id if ln.id in prev else str(uuid.uuid4())
            x["evasa"] = (prev.get(x["id"]) or {}).get("evasa") or 0
            if x["evasa"] > x["quantita"] + 1e-9:
                raise ferr(422, f"lines.{i}.quantita", f"Riga {i + 1}: quantità inferiore a quella già evasa ({x['evasa']:g})")
            lines.append(x)
        snap = {k: p.get(k) or "" for k in ("denominazione", "partita_iva", "codice_fiscale", "indirizzo", "cap", "comune", "provincia")}
        return {**body.model_dump(exclude={"lines"}), "party": snap, "lines": lines, "imponibile": _tot(lines)}

    @r.get("/ordini/{tipo}")
    async def elenco(tipo: TIPO, stato: Optional[str] = None, t: dict = Depends(tenant)):
        q = {"company_id": t["cid"], "tipo": tipo, **({"status": stato} if stato else {})}
        return await db.orders.find(q, {"_id": 0}).sort([("data", -1), ("numero", -1)]).to_list(5000)

    @r.get("/ordini/{tipo}/{oid}")
    async def dettaglio(tipo: TIPO, oid: str, t: dict = Depends(tenant)):
        return await _get(t["cid"], tipo, oid)

    @r.post("/ordini/{tipo}")
    async def crea(tipo: TIPO, body: OrdineIn, t: dict = Depends(tenant)):
        cid = t["cid"]
        async with locks.setdefault(cid, asyncio.Lock()):
            d = await _prepare(cid, tipo, body)
            anno = int(body.data[:4])
            last = await db.orders.find_one({"company_id": cid, "tipo": tipo, "anno": anno}, {"_id": 0, "numero": 1}, sort=[("numero", -1)])
            n = ((last or {}).get("numero") or 0) + 1
            o = {"id": str(uuid.uuid4()), "company_id": cid, "tipo": tipo, "anno": anno, "numero": n, "numero_display": f"{'OC' if tipo == 'cliente' else 'OF'} {n}/{anno}",
                 **d, "status": "aperto", "evasioni": [], "created_at": _now(), "created_by": t["user"].get("name") or t["user"]["email"]}
            await db.orders.insert_one(dict(o))
        await aggiorna_impegni(db, cid, [x["article_id"] for x in o["lines"]])
        return o

    @r.put("/ordini/{tipo}/{oid}")
    async def modifica(tipo: TIPO, oid: str, body: OrdineIn, t: dict = Depends(tenant)):
        cid = t["cid"]
        o = await _get(cid, tipo, oid)
        if o["status"] not in ("aperto", "parziale"):
            raise HTTPException(400, "Puoi modificare solo un ordine aperto o parzialmente evaso")
        d = await _prepare(cid, tipo, body, o)
        gone = {x["id"] for x in o["lines"]} - {x["id"] for x in d["lines"]}
        if any((x.get("evasa") or 0) > 0 for x in o["lines"] if x["id"] in gone):
            raise HTTPException(400, "Non puoi eliminare righe già evase (anche in parte)")
        await db.orders.update_one({"id": oid, "company_id": cid}, {"$set": {**d, "status": stato_righe(d["lines"]), "updated_at": _now()}})
        await aggiorna_impegni(db, cid, [x["article_id"] for x in o["lines"] + d["lines"]])
        return await _get(cid, tipo, oid)

    @r.delete("/ordini/{tipo}/{oid}")
    async def elimina(tipo: TIPO, oid: str, t: dict = Depends(tenant)):
        o = await _get(t["cid"], tipo, oid)
        if any(not e.get("annullata") for e in o.get("evasioni") or []):
            raise HTTPException(400, "L'ordine ha delle evasioni: chiudilo invece di eliminarlo")
        await db.orders.delete_one({"id": oid, "company_id": t["cid"]})
        await aggiorna_impegni(db, t["cid"], [x["article_id"] for x in o["lines"]])
        return {"ok": True}

    async def _set_stato(t, tipo, oid, chiudi: bool):
        o = await _get(t["cid"], tipo, oid)
        if chiudi and o["status"] not in ("aperto", "parziale"):
            raise HTTPException(400, "L'ordine è già evaso o chiuso")
        if not chiudi and o["status"] != "chiuso":
            raise HTTPException(400, "Puoi riaprire solo un ordine chiuso")
        st = "chiuso" if chiudi else stato_righe(o["lines"])
        await db.orders.update_one({"id": oid, "company_id": t["cid"]}, {"$set": {"status": st, "chiuso_at": _now() if chiudi else None}})
        await aggiorna_impegni(db, t["cid"], [x["article_id"] for x in o["lines"]])
        return await _get(t["cid"], tipo, oid)

    @r.post("/ordini/{tipo}/{oid}/chiudi")
    async def chiudi(tipo: TIPO, oid: str, t: dict = Depends(tenant)):
        return await _set_stato(t, tipo, oid, True)

    @r.post("/ordini/{tipo}/{oid}/riapri")
    async def riapri(tipo: TIPO, oid: str, t: dict = Depends(tenant)):
        return await _set_stato(t, tipo, oid, False)

    def _righe_evase(o: dict, body: EvadiIn) -> list:
        lines = {x["id"]: x for x in o["lines"]}
        out = []
        for i, rg in enumerate(body.righe):
            x = lines.get(rg.line_id)
            if not x:
                raise ferr(422, f"righe.{i}.line_id", "Riga dell'ordine non trovata")
            res = round(x["quantita"] - (x.get("evasa") or 0), 4)
            if rg.quantita > res + 1e-9:
                raise ferr(422, f"righe.{i}.quantita", f"\"{x['descrizione'][:40]}\": puoi evadere al massimo {res:g}")
            if rg.quantita > 0:
                out.append((x, round(rg.quantita, 4)))
        return out

    async def _ddt(t, o, sel, body) -> dict:
        nota = f"Rif. ordine {o['numero_display']} del {itd(o['data'])}" + (f" - vs. rif. {o['riferimento']}" if o.get("riferimento") else "")
        lines = [{"article_id": x.get("article_id"), "codice": x.get("codice") or "", "descrizione": x["descrizione"], "quantita": q, "unita_misura": x.get("unita_misura") or "",
                  "prezzo_unitario": x["prezzo_unitario"], "aliquota": x["aliquota"], "natura": x.get("natura"), "sconto": x.get("sconto") or "", "note": x.get("note") or ""} for x, q in sel]
        d = await ddt_r.crea(DdtIn(data=body.data, party_id=o["party_id"], destinazione=o.get("destinazione"), note=nota, lines=lines), t)
        try:
            d = await ddt_r.conferma(d["id"], ConfermaIn(forza=body.forza), t)
        except HTTPException:
            await db.ddts.delete_one({"id": d["id"], "company_id": t["cid"], "status": "bozza"})
            raise
        await db.ddts.update_one({"id": d["id"]}, {"$set": {"ordine_id": o["id"], "ordine_numero": o["numero_display"]}})
        return {"tipo": "ddt", "doc_id": d["id"], "numero": d["numero_display"]}

    async def _bem(t, o, sel, body) -> dict:
        cid = t["cid"]
        anno = int(body.data[:4])
        last = await db.bem.find_one({"company_id": cid, "anno": anno}, {"_id": 0, "numero": 1}, sort=[("numero", -1)])
        n = ((last or {}).get("numero") or 0) + 1
        bid, num = str(uuid.uuid4()), f"{n}/{anno}"
        lines, u = [], t["user"]
        for x, q in sel:
            ln = {k: x.get(k) for k in ("article_id", "codice", "descrizione", "unita_misura", "prezzo_unitario", "sconto", "aliquota", "natura", "gestione_magazzino")} | {"quantita": q, "line_id": x["id"]}
            lines.append(ln)
            if x.get("article_id") and x.get("gestione_magazzino"):
                costo = round(float(line_total({**ln, "quantita": 1})), 4)
                await db.stock_moves.insert_one({"id": str(uuid.uuid4()), "company_id": cid, "article_id": x["article_id"], "tipo": "carico", "data": body.data, "quantita": q,
                                                 "costo_unitario": costo, "causale": "Acquisto", "documento": f"BEM {num}", "note": f"Ordine {o['numero_display']} - {o['party']['denominazione']}"[:300],
                                                 "codice": x.get("codice"), "descrizione": x["descrizione"], "unita_misura": x.get("unita_misura") or "", "bem_id": bid,
                                                 "created_at": _now(), "created_by": u.get("name") or u.get("email")})
        b = {"id": bid, "company_id": cid, "anno": anno, "numero": n, "numero_display": num, "data": body.data, "party_id": o["party_id"], "fornitore": o["party"],
             "documento_fornitore": body.documento_fornitore or "", "ordine_id": o["id"], "ordine_numero": o["numero_display"], "lines": lines, "imponibile": _tot(lines),
             "status": "confermato", "created_at": _now(), "created_by": u.get("name") or u.get("email")}
        await db.bem.insert_one(dict(b))
        for aid in {x.get("article_id") for x, _ in sel if x.get("article_id") and x.get("gestione_magazzino")}:
            await recompute_article(db, cid, aid)
        return {"tipo": "bem", "doc_id": bid, "numero": num}

    @r.post("/ordini/{tipo}/{oid}/evadi")
    async def evadi(tipo: TIPO, oid: str, body: EvadiIn, t: dict = Depends(tenant)):
        cid = t["cid"]
        if body.data > date.today().isoformat():
            raise ferr(400, "data", "La data del documento non può essere futura")
        async with locks.setdefault(f"ev-{cid}", asyncio.Lock()):
            o = await _get(cid, tipo, oid)
            if o["status"] not in ("aperto", "parziale"):
                raise HTTPException(400, "L'ordine è già evaso o chiuso")
            if body.data < o["data"]:
                raise ferr(400, "data", "La data del documento non può precedere la data dell'ordine")
            sel = _righe_evase(o, body)
            if not sel and not body.chiudi:
                raise ferr(422, "righe", "Indica almeno una quantità da evadere")
            ev = (await (_ddt if tipo == "cliente" else _bem)(t, o, sel, body)) if sel else None
            q = {x["id"]: qq for x, qq in sel}
            lines = [{**x, "evasa": round((x.get("evasa") or 0) + q.get(x["id"], 0), 4)} for x in o["lines"]]
            st = stato_righe(lines)
            if body.chiudi and st != "evaso":
                st = "chiuso"
            evs = o.get("evasioni") or []
            if ev:
                evs = evs + [{**ev, "id": str(uuid.uuid4()), "data": body.data, "righe": [{"line_id": k, "quantita": v} for k, v in q.items()], "at": _now()}]
            await db.orders.update_one({"id": oid, "company_id": cid}, {"$set": {"lines": lines, "evasioni": evs, "status": st, "updated_at": _now()}})
        await aggiorna_impegni(db, cid, [x.get("article_id") for x in lines])
        return {**await _get(cid, tipo, oid), "documento": ev}

    @r.get("/ordini/{tipo}/{oid}/pdf")
    async def pdf(tipo: TIPO, oid: str, conferma: bool = False, t: dict = Depends(tenant)):
        o = await _get(t["cid"], tipo, oid)
        name = f"{'Conferma_ordine' if conferma and tipo == 'cliente' else 'Ordine'}_{o['numero_display'].replace('/', '-').replace(' ', '_')}.pdf"
        return Response(ordini_pdf.build(t["company"], o, conferma), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}"'})

    @r.get("/ordini/{tipo}/{oid}/email")
    async def email_preview(tipo: TIPO, oid: str, conferma: bool = False, t: dict = Depends(tenant)):
        o = await _get(t["cid"], tipo, oid)
        p = await db.parties.find_one({"id": o["party_id"], "company_id": t["cid"]}, {"_id": 0, "email": 1, "pec": 1}) or {}
        tit = ordini_pdf.titolo(o, conferma).capitalize()
        az = t["company"].get("denominazione") or ""
        msg = (f"Gentile {o['party']['denominazione']},\n\nin allegato {'la conferma del Vostro ordine' if conferma and tipo == 'cliente' else 'il nostro ordine' if tipo == 'fornitore' else 'il riepilogo del Vostro ordine'} "
               f"n. {o['numero_display']} del {itd(o['data'])}.\n" + ("Vi chiediamo cortesemente di confermarne ricezione, prezzi e data di consegna.\n" if tipo == "fornitore" else "") + f"\nCordiali saluti\n{az}")
        return {"to": p.get("email") or p.get("pec") or "", "oggetto": f"{tit} n. {o['numero_display']} - {az}", "messaggio": msg, "inviate": o.get("email_inviate") or []}

    @r.post("/ordini/{tipo}/{oid}/email")
    async def email_send(tipo: TIPO, oid: str, body: EmailOrdIn, t: dict = Depends(tenant)):
        o = await _get(t["cid"], tipo, oid)
        smtp = await deps["smtp"](t["cid"])
        pdf_b = ordini_pdf.build(t["company"], o, body.conferma)
        html = "<div style='font-family:Arial,sans-serif;font-size:14px'>" + hesc(body.messaggio).replace("\n", "<br/>") + "</div>"
        name = f"{'Conferma_ordine' if body.conferma and tipo == 'cliente' else 'Ordine'}_{o['numero_display'].replace('/', '-').replace(' ', '_')}.pdf"
        eid = await deps["send_email"](smtp=smtp, to=body.to, subject=body.oggetto, html=html, reply_to=smtp.get("reply_to") or t["company"].get("email") or None,
                                       attachments=[{"filename": name, "content": base64.b64encode(pdf_b).decode()}])
        rec = {"to": body.to, "conferma": body.conferma, "at": _now(), "by": t["user"].get("name") or t["user"]["email"], "email_id": eid}
        await db.orders.update_one({"id": oid, "company_id": t["cid"]}, {"$push": {"email_inviate": rec}})
        return rec

    async def _passiva(cid, pid):
        d = await db.passive_invoices.find_one({"id": pid, "company_id": cid}, {"_id": 0, "xml_b64": 0})
        if not d:
            raise HTTPException(404, "Fattura ricevuta non trovata")
        return d

    @r.get("/passive/{pid}/bem")
    async def bem_fattura(pid: str, t: dict = Depends(tenant)):
        cid = t["cid"]
        d = await _passiva(cid, pid)
        coll = await db.bem.find({"company_id": cid, "passive_id": pid, "status": "confermato"}, {"_id": 0}).sort("data", 1).to_list(100)
        cand = await db.bem.find({"company_id": cid, "party_id": d.get("party_id"), "status": "confermato", "passive_id": {"$in": [None, ""]}}, {"_id": 0}).sort("data", 1).to_list(100) if d.get("party_id") else []
        return {"collegate": coll, "candidate": cand, "confronto": confronto(coll, d) if coll else None}

    @r.post("/passive/{pid}/bem")
    async def bem_collega(pid: str, body: LinkBemIn, t: dict = Depends(tenant)):
        cid = t["cid"]
        d = await _passiva(cid, pid)
        res = await db.bem.update_one({"id": body.bem_id, "company_id": cid, "party_id": d.get("party_id"), "status": "confermato", "passive_id": {"$in": [None, ""]}},
                                      {"$set": {"passive_id": pid, "passive_numero": d.get("numero_display") or d.get("numero")}})
        if not res.modified_count:
            raise HTTPException(400, "Entrata merce non collegabile: è di un altro fornitore, annullata o già collegata a un'altra fattura")
        return await bem_fattura(pid, t)

    @r.delete("/passive/{pid}/bem/{bid}")
    async def bem_scollega(pid: str, bid: str, t: dict = Depends(tenant)):
        await db.bem.update_one({"id": bid, "company_id": t["cid"], "passive_id": pid}, {"$set": {"passive_id": None, "passive_numero": None}})
        return await bem_fattura(pid, t)

    @r.get("/bem")
    async def bem_elenco(t: dict = Depends(tenant)):
        return await db.bem.find({"company_id": t["cid"]}, {"_id": 0}).sort([("data", -1), ("numero", -1)]).to_list(5000)

    @r.post("/bem/{bid}/annulla")
    async def bem_annulla(bid: str, t: dict = Depends(tenant)):
        cid = t["cid"]
        b = await db.bem.find_one({"id": bid, "company_id": cid}, {"_id": 0})
        if not b:
            raise HTTPException(404, "Entrata merce non trovata")
        if b["status"] != "confermato":
            raise HTTPException(400, "Entrata merce già annullata")
        if b.get("passive_id"):
            raise HTTPException(400, f"L'entrata merce è collegata alla fattura {b.get('passive_numero')}: scollegala prima di annullarla")
        aids = {x["article_id"] for x in b["lines"] if x.get("article_id") and x.get("gestione_magazzino")}
        for aid in aids:
            rest = await db.stock_moves.find({"company_id": cid, "article_id": aid, "bem_id": {"$ne": bid}}, {"_id": 0}).to_list(100000)
            if rest and replay(rest)["minimo"]["giacenza"] < -0.0001:
                raise HTTPException(400, "Annullando l'entrata merce la giacenza andrebbe sotto zero: annulla prima gli scarichi successivi")
        await db.stock_moves.delete_many({"company_id": cid, "bem_id": bid})
        await db.bem.update_one({"id": bid}, {"$set": {"status": "annullato", "annullato_at": _now()}})
        for aid in aids:
            await recompute_article(db, cid, aid)
        await storna(db, cid, bid)
        return {"ok": True}

    return r

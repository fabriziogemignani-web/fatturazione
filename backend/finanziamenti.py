import base64
import calendar
import uuid
from datetime import date
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator

import contabilita as coge
from rateizzazioni import PagaIn, _now, _stato, leggi_pdf_ia, r2

DEF = {"conto_debito": "13.01.003", "conto_interessi": "40.02.002", "conto_canone": "30.08.002", "conto_iva": "05.02.002"}
TIPI = {"finanziamento": "Finanziamento", "leasing": "Leasing"}
SYS_PDF = ("Sei un contabile italiano. Ricevi il PDF di un piano di ammortamento di un finanziamento/mutuo o di un contratto di leasing con il piano dei canoni. "
           "Rispondi SOLO con JSON: {\"tipo\": \"finanziamento|leasing\", \"ente\": \"banca o societa di leasing\", \"numero\": \"numero contratto\", "
           "\"descrizione\": \"oggetto (max 200 caratteri)\", \"data\": \"AAAA-MM-GG data stipula o erogazione\", \"importo\": numero capitale finanziato o valore del bene, "
           "\"tasso\": numero tasso annuo %, \"aliquota_iva\": numero (solo leasing, di solito 22), "
           "\"rate\": [{\"scadenza\": \"AAAA-MM-GG\", \"capitale\": numero quota capitale, \"interessi\": numero quota interessi, \"descrizione\": \"es. Maxicanone, Canone, Riscatto, Rata\"}]}. "
           "Per il leasing capitale+interessi = canone imponibile senza IVA; se il piano riporta solo il canone mettilo in capitale e 0 in interessi. "
           "Importi in euro con il punto decimale. Non inventare rate assenti.")


def _mesi(d: date, m: int) -> date:
    y, mm = divmod(d.month - 1 + m, 12)
    y, mm = d.year + y, mm + 1
    return date(y, mm, min(d.day, calendar.monthrange(y, mm)[1]))


class CalcIn(BaseModel):
    tipo: Literal["finanziamento", "leasing"]
    importo: float = Field(gt=0)
    tasso: float = Field(default=0, ge=0, le=50)
    n_rate: int = Field(ge=1, le=480)
    periodicita: Literal[1, 2, 3, 6, 12] = 1
    prima_scadenza: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    maxicanone: float = Field(default=0, ge=0)
    riscatto: float = Field(default=0, ge=0)
    data: Optional[str] = None


def calcola_piano(c: CalcIn) -> list:
    i = c.tasso / 100 * c.periodicita / 12
    p = c.importo - (c.maxicanone if c.tipo == "leasing" else 0)
    fv = c.riscatto if c.tipo == "leasing" else 0
    if p <= 0:
        raise HTTPException(400, "Il maxicanone non può superare il valore del bene")
    n = c.n_rate
    rata = (p - fv) / n if i == 0 else (p - fv / (1 + i) ** n) * i / (1 - (1 + i) ** -n)
    out, res, d0 = [], p, date.fromisoformat(c.prima_scadenza)
    if c.tipo == "leasing" and c.maxicanone:
        out.append({"scadenza": c.data or c.prima_scadenza, "capitale": r2(c.maxicanone), "interessi": 0.0, "descrizione": "Maxicanone"})
    for k in range(n):
        inte = r2(res * i)
        cap = r2(rata - inte) if k < n - 1 else r2(res - fv)
        res = r2(res - cap)
        out.append({"scadenza": _mesi(d0, k * c.periodicita).isoformat(), "capitale": cap, "interessi": inte, "descrizione": "Canone" if c.tipo == "leasing" else "Rata"})
    if fv:
        out.append({"scadenza": _mesi(d0, n * c.periodicita).isoformat(), "capitale": r2(fv), "interessi": 0.0, "descrizione": "Riscatto"})
    return out


class RataFin(BaseModel):
    scadenza: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    capitale: float = Field(default=0, ge=0)
    interessi: float = Field(default=0, ge=0)
    descrizione: Optional[str] = Field(default="", max_length=40)


class FinIn(BaseModel):
    tipo: Literal["finanziamento", "leasing"]
    ente: str = Field(min_length=1, max_length=80)
    numero: Optional[str] = Field(default="", max_length=80)
    descrizione: Optional[str] = Field(default="", max_length=300)
    data: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    importo: float = Field(default=0, ge=0)
    tasso: float = Field(default=0, ge=0, le=50)
    aliquota_iva: float = Field(default=22, ge=0, le=30)
    party_id: Optional[str] = None
    conto_debito: Optional[str] = Field(default=DEF["conto_debito"], max_length=12)
    conto_interessi: Optional[str] = Field(default=DEF["conto_interessi"], max_length=12)
    conto_canone: Optional[str] = Field(default=DEF["conto_canone"], max_length=12)
    conto_iva: Optional[str] = Field(default=DEF["conto_iva"], max_length=12)
    pdf_id: Optional[str] = None
    rate: List[RataFin] = Field(min_length=1, max_length=480)

    @model_validator(mode="after")
    def _ok(self):
        if any(r.capitale + r.interessi <= 0 for r in self.rate):
            raise ValueError("Ogni rata deve avere un importo")
        self.rate.sort(key=lambda r: r.scadenza)
        return self


class CollegaIn(BaseModel):
    invoice_id: str


def _label(p: dict, n: int) -> str:
    return f"{TIPI[p['tipo']]} {p['ente']} {p.get('numero') or ''}".strip() + f" · rata {n}/{len(p['rate'])}"


async def rate_aperte(db, cid: str) -> list:
    rows = await db.finanziamenti.find({"company_id": cid, "annullata": {"$ne": True}}, {"_id": 0}).to_list(500)
    return [{**x, "piano_id": p["id"], "ente": p["ente"], "numero": p.get("numero") or "", "di": len(p["rate"]), "label": _label(p, x["n"]), "link": "/finanziamenti"}
            for p in rows for x in p["rate"] if not x.get("pagamento") and not x.get("fattura_id")]


def build(db, tenant, tenant_accounting, deps) -> APIRouter:
    r = APIRouter(prefix="/api")
    ferr = deps["ferr"]

    async def _get(pid: str, cid: str) -> dict:
        p = await db.finanziamenti.find_one({"id": pid, "company_id": cid, "annullata": {"$ne": True}}, {"_id": 0})
        if not p:
            raise HTTPException(404, "Finanziamento o leasing non trovato")
        return p

    async def _arricchisci(p: dict, residui: Optional[dict] = None) -> dict:
        today = date.today().isoformat()
        if residui is None:
            residui = {d["id"]: d["residuo"] for d in (await deps["ledger_passive"](p["company_id"]))[0]} if any(x.get("fattura_id") for x in p["rate"]) else {}
        rate = []
        for x in p["rate"]:
            st = _stato(x, today)
            if x.get("fattura_id"):
                st = "pagata" if residui.get(x["fattura_id"], 0) <= 0.005 else "fattura"
            rate.append({**x, "stato": st})
        aperte = [x for x in rate if x["stato"] != "pagata"]
        cap_pag = sum(x["capitale"] for x in rate if x["stato"] == "pagata")
        return {**p, "rate": rate, "totale": r2(sum(x["totale"] for x in rate)), "pagato": r2(sum(x["totale"] for x in rate if x["stato"] == "pagata")),
                "residuo": r2(sum(x["totale"] for x in aperte)), "debito_residuo": r2(sum(x["capitale"] for x in aperte)), "capitale_rimborsato": r2(cap_pag),
                "rate_pagate": len(rate) - len(aperte), "rate_scadute": sum(1 for x in aperte if x["stato"] == "scaduta"), "prossima": aperte[0] if aperte else None}

    async def _check(cid: str, body: FinIn):
        if body.party_id and not await db.parties.find_one({"id": body.party_id, "company_id": cid, "tipo": "fornitore"}, {"_id": 1}):
            raise ferr(400, "party_id", "Fornitore non trovato")
        if not coge.attiva(await coge._company(db, cid)):
            return
        await coge.ensure_seed(db, cid)
        campi = ("conto_debito", "conto_interessi") if body.tipo == "finanziamento" else ("conto_canone", "conto_iva")
        for f in campi:
            c = getattr(body, f)
            if not c or not await db.coa_accounts.find_one({"company_id": cid, "codice": c, "livello": 3}, {"_id": 1}):
                raise ferr(400, f, "Scegli un sottoconto esistente del piano dei conti")

    def _rate(body: FinIn, old: Optional[list] = None) -> list:
        iva = body.aliquota_iva / 100 if body.tipo == "leasing" else 0
        return [{"n": i, **x.model_dump(), "iva": r2((x.capitale + x.interessi) * iva), "totale": r2((x.capitale + x.interessi) * (1 + iva)), "pagamento": None, "fattura_id": None}
                for i, x in enumerate(body.rate, 1)]

    def _bloccato(p: dict) -> bool:
        return bool(p.get("erogazione")) or any(x.get("pagamento") or x.get("fattura_id") for x in p["rate"])

    async def _conto_banca(cid: str, conto: str, opts: dict) -> str:
        conto = conto or opts["default"].get("bonifico") or (opts["conti"][0]["conto"] if opts["conti"] else "")
        if conto not in {o["conto"] for o in opts["conti"]}:
            raise ferr(400, "conto", "Seleziona la banca o la cassa del movimento")
        return conto

    async def _registra(cid: str, by: str, data: str, desc: str, righe: list, ref: str) -> dict:
        try:
            e = await coge._insert(db, cid, coge.params_of(await coge._company(db, cid)), data, "GE", desc, righe, "finanziamento", ref_id=ref, by=by)
        except ValueError as ex:
            raise HTTPException(400, f"Movimento non registrato in prima nota: {ex}")
        return {"coge_entry_id": e["id"] if e else None, "coge_rif": f"prima nota n. {e['numero']}/{e['anno']}" if e else None}

    @r.post("/finanziamenti/calcola")
    async def calcola(body: CalcIn, t: dict = Depends(tenant)):
        return {"rate": calcola_piano(body)}

    @r.post("/finanziamenti/leggi-pdf")
    async def leggi_pdf(file: UploadFile = File(...), t: dict = Depends(tenant_accounting)):
        out, pdf_id = await leggi_pdf_ia(db, t, file, SYS_PDF, "Estrai il piano delle rate da questo PDF.", "finanziamento")
        rate = []
        for x in out.get("rate") or []:
            try:
                sc = date.fromisoformat(str(x.get("scadenza"))[:10]).isoformat()
            except ValueError:
                continue
            if r2(x.get("capitale")) + r2(x.get("interessi")) > 0:
                rate.append({"scadenza": sc, "capitale": r2(x.get("capitale")), "interessi": r2(x.get("interessi")), "descrizione": str(x.get("descrizione") or "")[:40]})
        try:
            dt = date.fromisoformat(str(out.get("data"))[:10]).isoformat()
        except ValueError:
            dt = rate[0]["scadenza"] if rate else date.today().isoformat()
        tipo = out.get("tipo") if out.get("tipo") in TIPI else "finanziamento"
        return {"pdf_id": pdf_id, "tipo": tipo, "ente": (out.get("ente") or "")[:80] or "Banca", "numero": (out.get("numero") or "")[:80],
                "descrizione": (out.get("descrizione") or "")[:300], "data": dt, "importo": r2(out.get("importo")), "tasso": min(r2(out.get("tasso")), 50),
                "aliquota_iva": r2(out.get("aliquota_iva")) if tipo == "leasing" and out.get("aliquota_iva") is not None else 22, "party_id": None,
                "rate": sorted(rate, key=lambda x: x["scadenza"]), **DEF}

    @r.get("/finanziamenti")
    async def elenco(t: dict = Depends(tenant)):
        rows = await db.finanziamenti.find({"company_id": t["cid"], "annullata": {"$ne": True}}, {"_id": 0}).sort("data", -1).to_list(500)
        residui = {d["id"]: d["residuo"] for d in (await deps["ledger_passive"](t["cid"]))[0]} if any(x.get("fattura_id") for p in rows for x in p["rate"]) else {}
        return {"piani": [await _arricchisci(p, residui) for p in rows], "conti_pagamento": await coge.conti_pagamento(db, t["cid"])}

    @r.post("/finanziamenti")
    async def crea(body: FinIn, t: dict = Depends(tenant_accounting)):
        await _check(t["cid"], body)
        doc = {"id": str(uuid.uuid4()), "company_id": t["cid"], **body.model_dump(exclude={"rate"}), "rate": _rate(body), "erogazione": None,
               "created_by": t["user"].get("name") or t["user"]["email"], "created_at": _now()}
        await db.finanziamenti.insert_one(doc)
        return await _arricchisci(await _get(doc["id"], t["cid"]))

    @r.put("/finanziamenti/{pid}")
    async def modifica(pid: str, body: FinIn, t: dict = Depends(tenant_accounting)):
        p = await _get(pid, t["cid"])
        if _bloccato(p):
            raise HTTPException(400, "Il piano ha movimenti (erogazione, rate pagate o fatture collegate): annullali prima di modificarlo")
        await _check(t["cid"], body)
        await db.finanziamenti.update_one({"id": pid, "company_id": t["cid"]}, {"$set": {**body.model_dump(exclude={"rate"}), "rate": _rate(body), "updated_at": _now()}})
        return await _arricchisci(await _get(pid, t["cid"]))

    @r.delete("/finanziamenti/{pid}")
    async def annulla(pid: str, t: dict = Depends(tenant_accounting)):
        p = await _get(pid, t["cid"])
        if _bloccato(p):
            raise HTTPException(400, "Il piano ha movimenti registrati: non può essere eliminato")
        await db.finanziamenti.update_one({"id": pid, "company_id": t["cid"]}, {"$set": {"annullata": True, "annullata_il": _now()}})
        return {"ok": True}

    @r.post("/finanziamenti/{pid}/erogazione")
    async def eroga(pid: str, body: PagaIn, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        p = await _get(pid, cid)
        if p["tipo"] != "finanziamento" or p["importo"] <= 0:
            raise HTTPException(400, "L'erogazione si registra solo sui finanziamenti con importo")
        by = t["user"].get("name") or t["user"]["email"]
        er = {"data": body.data, "importo": p["importo"], "conto": None, "coge_rif": None, "by": by, "at": _now()}
        if not (await db.finanziamenti.update_one({"id": pid, "company_id": cid, "erogazione": None}, {"$set": {"erogazione": er}})).modified_count:
            raise HTTPException(409, "Erogazione già registrata")
        try:
            opts = await coge.conti_pagamento(db, cid)
            if opts is not None:
                conto = await _conto_banca(cid, body.conto, opts)
                er |= {"conto": conto, **await _registra(cid, by, body.data, f"Erogazione finanziamento {p['ente']} {p.get('numero') or ''}".strip(),
                                                         [{"conto": conto, "dare": p["importo"]}, {"conto": p["conto_debito"], "avere": p["importo"]}], f"{pid}-E")}
        except Exception:
            await db.finanziamenti.update_one({"id": pid, "company_id": cid}, {"$set": {"erogazione": None}})
            raise
        await db.finanziamenti.update_one({"id": pid, "company_id": cid}, {"$set": {"erogazione": er}})
        return await _arricchisci(await _get(pid, cid))

    @r.delete("/finanziamenti/{pid}/erogazione")
    async def annulla_eroga(pid: str, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        p = await _get(pid, cid)
        if not p.get("erogazione"):
            raise HTTPException(400, "Erogazione non registrata")
        await coge.check_annullabile(db, cid, "finanziamento", f"{pid}-E")
        await coge.annulla(db, cid, "finanziamento", f"{pid}-E")
        await db.finanziamenti.update_one({"id": pid, "company_id": cid}, {"$set": {"erogazione": None}})
        return await _arricchisci(await _get(pid, cid))

    def _rata(p: dict, n: int) -> dict:
        x = next((x for x in p["rate"] if x["n"] == n), None)
        if not x:
            raise HTTPException(404, "Rata non trovata")
        return x

    @r.post("/finanziamenti/{pid}/rate/{n}/paga")
    async def paga(pid: str, n: int, body: PagaIn, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        p = await _get(pid, cid)
        x = _rata(p, n)
        if x.get("fattura_id"):
            raise HTTPException(400, "La rata è collegata a una fattura: pagala dalla fattura passiva")
        if body.data < p["data"]:
            raise ferr(400, "data", "La data del pagamento non può precedere la data del contratto")
        by = t["user"].get("name") or t["user"]["email"]
        pag = {"data": body.data, "conto": None, "coge_rif": None, "by": by, "at": _now()}
        q = {"id": pid, "company_id": cid, "rate": {"$elemMatch": {"n": n, "pagamento": None, "fattura_id": None}}}
        if not (await db.finanziamenti.update_one(q, {"$set": {"rate.$.pagamento": pag}})).modified_count:
            raise HTTPException(409, "Rata già pagata")
        try:
            opts = await coge.conti_pagamento(db, cid)
            if opts is not None:
                conto = await _conto_banca(cid, body.conto, opts)
                if p["tipo"] == "finanziamento":
                    righe = [{"conto": p["conto_debito"], "dare": x["capitale"]}, {"conto": p["conto_interessi"], "dare": x["interessi"]}]
                else:
                    righe = [{"conto": p["conto_canone"], "dare": r2(x["capitale"] + x["interessi"])}, {"conto": p["conto_iva"], "dare": x["iva"]}]
                pag |= {"conto": conto, **await _registra(cid, by, body.data, _label(p, n), righe + [{"conto": conto, "avere": x["totale"]}], f"{pid}-{n}")}
        except Exception:
            await db.finanziamenti.update_one({"id": pid, "company_id": cid, "rate.n": n}, {"$set": {"rate.$.pagamento": None}})
            raise
        await db.finanziamenti.update_one({"id": pid, "company_id": cid, "rate.n": n}, {"$set": {"rate.$.pagamento": pag}})
        return await _arricchisci(await _get(pid, cid))

    @r.delete("/finanziamenti/{pid}/rate/{n}/paga")
    async def annulla_paga(pid: str, n: int, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        p = await _get(pid, cid)
        if not _rata(p, n).get("pagamento"):
            raise HTTPException(400, "La rata non risulta pagata")
        await coge.check_annullabile(db, cid, "finanziamento", f"{pid}-{n}")
        await coge.annulla(db, cid, "finanziamento", f"{pid}-{n}")
        await db.finanziamenti.update_one({"id": pid, "company_id": cid, "rate.n": n}, {"$set": {"rate.$.pagamento": None}})
        return await _arricchisci(await _get(pid, cid))

    @r.get("/finanziamenti/{pid}/pdf")
    async def pdf(pid: str, t: dict = Depends(tenant)):
        p = await _get(pid, t["cid"])
        f = await db.rateizzazioni_pdf.find_one({"id": p.get("pdf_id"), "company_id": t["cid"]}, {"_id": 0}) if p.get("pdf_id") else None
        if not f:
            raise HTTPException(404, "PDF del piano non disponibile")
        return Response(base64.b64decode(f["pdf_b64"]), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="piano-{pid[:8]}.pdf"'})

    @r.get("/finanziamenti/{pid}/fatture")
    async def fatture(pid: str, t: dict = Depends(tenant)):
        p = await _get(pid, t["cid"])
        usate = {x["fattura_id"] for q in await db.finanziamenti.find({"company_id": t["cid"], "annullata": {"$ne": True}}, {"_id": 0, "rate.fattura_id": 1}).to_list(500)
                 for x in q["rate"] if x.get("fattura_id")}
        docs = (await deps["ledger_passive"](t["cid"], p.get("party_id")))[0]
        fatt = set(await db.passive_invoices.distinct("id", {"company_id": t["cid"], "id": {"$in": [d["id"] for d in docs]}}))
        return [{"id": d["id"], "numero_display": d["numero_display"], "data": d["data"], "fornitore": d["cliente"], "netto": d["netto"], "residuo": d["residuo"]}
                for d in sorted(docs, key=lambda d: d["data"], reverse=True) if d["id"] not in usate and d["id"] in fatt][:200]

    @r.post("/finanziamenti/{pid}/rate/{n}/collega")
    async def collega(pid: str, n: int, body: CollegaIn, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        p = await _get(pid, cid)
        if p["tipo"] != "leasing":
            raise HTTPException(400, "Le fatture si collegano solo alle rate di leasing")
        if _rata(p, n).get("pagamento"):
            raise HTTPException(400, "Rata già pagata dal modulo: annulla prima il pagamento")
        if not await db.passive_invoices.find_one({"id": body.invoice_id, "company_id": cid, **({"party_id": p["party_id"]} if p.get("party_id") else {})}, {"_id": 1}):
            raise HTTPException(404, "Fattura passiva non trovata")
        if await db.finanziamenti.find_one({"company_id": cid, "annullata": {"$ne": True}, "rate.fattura_id": body.invoice_id}, {"_id": 1}):
            raise HTTPException(400, "Fattura già collegata a un'altra rata")
        await db.finanziamenti.update_one({"id": pid, "company_id": cid, "rate.n": n}, {"$set": {"rate.$.fattura_id": body.invoice_id}})
        return await _arricchisci(await _get(pid, cid))

    @r.delete("/finanziamenti/{pid}/rate/{n}/collega")
    async def scollega(pid: str, n: int, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        await _get(pid, cid)
        await db.finanziamenti.update_one({"id": pid, "company_id": cid, "rate.n": n}, {"$set": {"rate.$.fattura_id": None}})
        return await _arricchisci(await _get(pid, cid))

    return r

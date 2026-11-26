import math
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from contabilita import _insert, _company, params_of, ensure_seed, r2, check_aperto


def pct(company: dict, anno: int) -> Optional[float]:
    pr = (company or {}).get("pro_rata") or {}
    v = (pr.get("percentuali") or {}).get(str(anno))
    return float(v) if pr.get("attivo") and v is not None else None


def _volumi(docs: list) -> tuple:
    detr = esenti = 0.0
    for d in docs:
        s = -1 if d.get("tipo_documento") == "TD04" else 1
        for r in d.get("riepilogo") or []:
            nat = r.get("natura") or ""
            imp = s * float(r.get("imponibile") or 0)
            if r.get("aliquota") or nat.startswith(("N3", "N6")):
                detr += imp
            elif nat.startswith("N4"):
                esenti += imp
    return r2(detr), r2(esenti)


class CfgIn(BaseModel):
    attivo: bool
    anno: int = Field(ge=2000, le=2100)
    percentuale: float = Field(ge=0, le=100)


class CongIn(BaseModel):
    anno: int = Field(ge=2000, le=2100)


def build(db, tenant, tenant_accounting, deps) -> APIRouter:
    r = APIRouter(prefix="/api/pro-rata")

    async def calcolo(cid: str, anno: int) -> dict:
        comp = await _company(db, cid)
        sales = await db.invoices.find({"company_id": cid, "status": {"$in": list(deps["iva_stati"])}, "anno": anno, "autofattura": {"$ne": True}}, {"_id": 0, "tipo_documento": 1, "riepilogo": 1}).to_list(50000)
        corr = await db.corrispettivi.find({"company_id": cid, "anno": anno}, {"_id": 0, "tipo_documento": 1, "riepilogo": 1}).to_list(50000)
        detr, esenti = _volumi(sales + corr)
        tot = detr + esenti
        definitivo = float(math.floor(detr / tot * 100 + 0.5)) if tot > 0 else 100.0
        liq = await deps["liq_calc"](cid, anno, "mensile", 0.0)
        detratta = r2(sum(p["iva_credito"] for p in liq["periodi"]))
        base = r2(detratta + sum(p.get("iva_pro_rata") or 0 for p in liq["periodi"]))
        spettante = r2(base * definitivo / 100)
        reg = await db.coa_entries.find_one({"company_id": cid, "origine": "prorata", "ref_id": f"PR-{anno}"}, {"_id": 0, "id": 1, "numero": 1, "data": 1})
        prv = pct(comp, anno)
        return {"anno": anno, "attivo": bool((comp.get("pro_rata") or {}).get("attivo")), "provvisorio": prv,
                "percentuali": (comp.get("pro_rata") or {}).get("percentuali") or {}, "operazioni_detraibili": detr, "operazioni_esenti": esenti,
                "definitivo": definitivo, "iva_base": base, "iva_detratta": detratta, "iva_spettante": spettante,
                "conguaglio": r2(spettante - detratta) if prv is not None else 0.0, "registrazione": reg,
                "concluso": anno < datetime.now(timezone.utc).year}

    @r.get("")
    async def get(anno: int, t: dict = Depends(tenant)):
        return await calcolo(t["cid"], anno)

    @r.put("")
    async def put(body: CfgIn, t: dict = Depends(tenant_accounting)):
        comp = await _company(db, t["cid"])
        pr = comp.get("pro_rata") or {}
        await db.companies.update_one({"id": t["cid"]}, {"$set": {"pro_rata": {"attivo": body.attivo, "percentuali": {**(pr.get("percentuali") or {}), str(body.anno): round(body.percentuale, 2)}}}})
        return await calcolo(t["cid"], body.anno)

    @r.post("/conguaglio")
    async def conguaglio(body: CongIn, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        await check_aperto(db, cid, body.anno)
        c = await calcolo(cid, body.anno)
        if c["registrazione"]:
            raise HTTPException(400, f"Conguaglio pro rata {body.anno} già registrato")
        if c["provvisorio"] is None or not c["conguaglio"]:
            raise HTTPException(400, "Nessun conguaglio da registrare")
        await ensure_seed(db, cid)
        p = params_of(await _company(db, cid))
        v = c["conguaglio"]
        ind = p.get("iva_indetraibile") or p["iva_acquisti"]
        righe = [{"conto": p["erario_iva"], "dare": v}, {"conto": ind, "avere": v}] if v > 0 else [{"conto": ind, "dare": -v}, {"conto": p["erario_iva"], "avere": -v}]
        descr = f"Conguaglio pro rata IVA {body.anno}: definitivo {c['definitivo']:g}% su provvisorio {c['provvisorio']:g}%"
        return await _insert(db, cid, p, f"{body.anno}-12-31", "GE", descr, righe, "prorata", f"PR-{body.anno}", {"documento": f"Pro rata {body.anno}"},
                             by=t["user"].get("name") or t["user"]["email"])

    @r.delete("/conguaglio/{anno}")
    async def annulla(anno: int, t: dict = Depends(tenant_accounting)):
        await check_aperto(db, t["cid"], anno)
        await db.coa_entries.delete_one({"company_id": t["cid"], "origine": "prorata", "ref_id": f"PR-{anno}"})
        return {"ok": True}

    return r

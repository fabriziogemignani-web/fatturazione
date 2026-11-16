import gzip
import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

MOVIMENTI = ["invoices", "passive_invoices", "payments", "passive_payments", "ddts", "bem", "orders", "ordini_produzione", "stock_moves", "coa_entries",
             "corrispettivi", "partite_aperte", "riba_distinte", "riba_effetti", "pag_distinte", "f24_versamenti", "ratei_risconti", "bank_tx", "solleciti",
             "arch_invoices", "import_batches", "export_log", "com_log"]
ANAGRAFICHE = ["parties", "intenti", "arch_anagrafiche"]
ESCLUSE = {"users", "user_sessions", "login_attempts", "password_reset_tokens", "companies", "counters"}


class CancellaIn(BaseModel):
    modo: Literal["totale", "parziale"]
    anagrafiche: bool = False
    conferma: str = Field(min_length=1, max_length=200)


def build(db, tenant, company_proj) -> APIRouter:
    r = APIRouter(prefix="/api/azienda")

    def _admin(t):
        if t["user"].get("role") != "admin":
            raise HTTPException(403, "Operazione riservata agli amministratori")

    async def _collezioni():
        return [c for c in await db.list_collection_names() if c not in ESCLUSE]

    @r.get("/backup")
    async def backup(t: dict = Depends(tenant)):
        _admin(t)
        cid = t["cid"]
        out = {"azienda": await db.companies.find_one({"id": cid}, company_proj), "creato_il": datetime.now(timezone.utc).isoformat(), "dati": {}}
        for c in await _collezioni():
            rows = await db[c].find({"company_id": cid}, {"_id": 0}).to_list(None)
            if rows:
                out["dati"][c] = rows
        body = gzip.compress(json.dumps(out, ensure_ascii=False, default=str).encode())
        name = f"backup_{(out['azienda'] or {}).get('partita_iva') or cid}_{datetime.now().strftime('%Y%m%d_%H%M')}.json.gz"
        return Response(body, media_type="application/gzip", headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @r.post("/cancella")
    async def cancella(body: CancellaIn, t: dict = Depends(tenant)):
        _admin(t)
        cid = t["cid"]
        comp = await db.companies.find_one({"id": cid}, {"_id": 0, "denominazione": 1})
        if not comp:
            raise HTTPException(404, "Azienda non trovata")
        if body.conferma.strip().lower() != (comp["denominazione"] or "").strip().lower():
            raise HTTPException(400, "Per confermare scrivi esattamente la ragione sociale dell'azienda")
        cancellati = {}
        if body.modo == "totale":
            for c in await _collezioni():
                n = (await db[c].delete_many({"company_id": cid})).deleted_count
                if n:
                    cancellati[c] = n
            await db.counters.delete_many({"key": f"progressivo_{cid}"})
            await db.companies.delete_one({"id": cid})
            await db.users.update_many({}, {"$pull": {"company_ids": cid}})
            await db.users.update_many({"active_company_id": cid}, {"$set": {"active_company_id": None}})
            return {"modo": "totale", "cancellati": cancellati}
        for c in MOVIMENTI + (ANAGRAFICHE if body.anagrafiche else []):
            n = (await db[c].delete_many({"company_id": cid})).deleted_count
            if n:
                cancellati[c] = n
        await db.articles.update_many({"company_id": cid}, {"$set": {"giacenza": 0, "impegnato": 0, "ordinato": 0, "disponibilita": 0}})
        await db.companies.update_one({"id": cid}, {"$unset": {"coge_chiusi": ""}})
        return {"modo": "parziale", "cancellati": cancellati}

    return r

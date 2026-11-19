import json
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request

SEGRETI = ("password", "token", "secret", "segreto", "api_key", "apikey", "chiave", "private", "xml_b64", "file_b64", "immagine", "image")
ESCLUSI = ("/api/auth/", "/api/stripe/webhook", "/api/ai/chat")
AZIONI = {"POST": "creazione / operazione", "PUT": "modifica", "PATCH": "modifica", "DELETE": "eliminazione"}


def _pulisci(v, depth=0):
    if depth > 6:
        return "…"
    if isinstance(v, dict):
        return {k: ("***" if any(s in k.lower() for s in SEGRETI) else _pulisci(x, depth + 1)) for k, x in list(v.items())[:80]}
    if isinstance(v, list):
        return [_pulisci(x, depth + 1) for x in v[:50]] + (["…"] if len(v) > 50 else [])
    if isinstance(v, str) and len(v) > 300:
        return v[:300] + "…"
    return v


async def leggi_corpo(request: Request) -> Optional[dict]:
    if "json" not in (request.headers.get("content-type") or "") or int(request.headers.get("content-length") or 0) > 200_000:
        return None
    try:
        return _pulisci(json.loads(await request.body() or b"null"))
    except ValueError:
        return None


def da_registrare(request: Request) -> bool:
    p = request.url.path
    return request.method in AZIONI and p.startswith("/api/") and not p.startswith(ESCLUSI)


async def scrivi(db, request: Request, status: int, corpo):
    au = getattr(request.state, "audit", None)
    if not au:
        return
    seg = request.url.path.removeprefix("/api/").split("/")
    await db.audit_log.insert_one({
        "id": str(uuid.uuid4()), "at": datetime.now(timezone.utc).isoformat(), "company_id": au.get("cid"), "user_id": au["user_id"],
        "utente": au["nome"], "email": au["email"], "method": request.method, "azione": AZIONI[request.method], "path": request.url.path,
        "area": seg[0], "riferimenti": [s for s in seg[1:] if len(s) >= 8], "esito": status,
        "ip": request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else ""), "dati": corpo})


def build_router(db, tenant_admin):
    r = APIRouter(prefix="/api/registro-attivita")

    @r.get("")
    async def elenco(dal: Optional[str] = None, al: Optional[str] = None, utente: Optional[str] = None, area: Optional[str] = None,
                     q: Optional[str] = None, pagina: int = 1, t: dict = Depends(tenant_admin)):
        f = {"company_id": t["cid"]}
        if dal or al:
            f["at"] = {**({"$gte": dal} if dal else {}), **({"$lte": f"{al}T23:59:59.999"} if al else {})}
        if utente:
            f["user_id"] = utente
        if area:
            f["area"] = area
        if q:
            rx = {"$regex": re.escape(q[:60]), "$options": "i"}
            f["$or"] = [{"path": rx}, {"riferimenti": q[:60]}, {"utente": rx}]
        pagina = max(pagina, 1)
        tot = await db.audit_log.count_documents(f)
        rows = await db.audit_log.find(f, {"_id": 0}).sort("at", -1).skip((pagina - 1) * 200).limit(200).to_list(200)
        utenti = await db.audit_log.aggregate([{"$match": {"company_id": t["cid"]}}, {"$group": {"_id": "$user_id", "nome": {"$last": "$utente"}}}]).to_list(500)
        aree = sorted(await db.audit_log.distinct("area", {"company_id": t["cid"]}))
        return {"righe": rows, "totale": tot, "pagina": pagina, "pagine": max(1, -(-tot // 200)),
                "utenti": sorted([{"id": u["_id"], "nome": u["nome"]} for u in utenti], key=lambda u: u["nome"] or ""), "aree": aree}

    return r


async def ensure_indexes(db):
    await db.audit_log.create_index([("company_id", 1), ("at", -1)])
    await db.audit_log.create_index([("company_id", 1), ("user_id", 1), ("at", -1)])

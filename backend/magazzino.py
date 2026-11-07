import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

CAUSALI = {"carico": ["Acquisto", "Reso da cliente", "Produzione", "Altro"],
           "scarico": ["Vendita", "Reso a fornitore", "Uso interno", "Scarto / rottura", "Altro"],
           "rettifica": ["Inventario", "Altro"]}


class MovIn(BaseModel):
    article_id: str
    tipo: Literal["carico", "scarico", "rettifica"]
    data: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    quantita: float
    costo_unitario: Optional[float] = Field(default=None, ge=0)
    causale: str = Field(min_length=1, max_length=60)
    documento: Optional[str] = Field(default="", max_length=80)
    note: Optional[str] = Field(default="", max_length=300)


def _now():
    return datetime.now(timezone.utc).isoformat()


def replay(moves: list) -> dict:
    qty, avg, low = 0.0, 0.0, None
    for m in sorted(moves, key=lambda x: (x["data"], x["created_at"])):
        q = m["quantita"]
        if m["tipo"] == "scarico":
            q = -abs(q)
        elif m["tipo"] == "carico":
            q = abs(q)
        if q > 0:
            c = m.get("costo_unitario")
            c = avg if c is None else c
            avg = (qty * avg + q * c) / (qty + q) if qty + q > 0 and qty >= 0 else c
        qty = round(qty + q, 4)
        m["giacenza_dopo"] = qty
        if low is None or qty < low["giacenza"]:
            low = {"giacenza": qty, "data": m["data"]}
    return {"giacenza": qty, "costo_medio": round(avg, 4), "valore": round(max(qty, 0) * avg, 2), "minimo": low}


def stato(a: dict) -> str:
    if not a.get("gestione_magazzino"):
        return "non_gestito"
    g, smin = a.get("giacenza") or 0, a.get("scorta_minima") or 0
    if g <= 0:
        return "esaurito" if smin > 0 or g < 0 else "zero"
    return "sottoscorta" if smin > 0 and g <= smin else "ok"


def da_ordinare(a: dict) -> float:
    g, smin, lotto = a.get("giacenza") or 0, a.get("scorta_minima") or 0, a.get("scorta_riordino") or 0
    return round(max(lotto, smin - g), 4)


def build_router(db, tenant, tenant_accounting) -> APIRouter:
    r = APIRouter(prefix="/api")

    async def recompute(cid: str, aid: str) -> dict:
        moves = await db.stock_moves.find({"company_id": cid, "article_id": aid}, {"_id": 0}).to_list(100000)
        res = replay(moves)
        upd = {"giacenza": res["giacenza"], "costo_medio": res["costo_medio"], "valore_magazzino": res["valore"],
               "ultimo_movimento": max((m["data"] for m in moves), default=None)}
        await db.articles.update_one({"id": aid, "company_id": cid}, {"$set": upd})
        return res

    def enrich(a: dict) -> dict:
        a["stato_scorta"] = stato(a)
        a["da_ordinare"] = da_ordinare(a) if a["stato_scorta"] in ("sottoscorta", "esaurito") else 0
        return a

    @r.get("/magazzino/articoli")
    async def giacenze(t: dict = Depends(tenant)):
        rows = await db.articles.find({"company_id": t["cid"], "gestione_magazzino": True}, {"_id": 0}).sort("codice", 1).to_list(5000)
        rows = [enrich(a) for a in rows]
        return {"articoli": rows, "valore_totale": round(sum(a.get("valore_magazzino") or 0 for a in rows), 2),
                "sottoscorta": sum(1 for a in rows if a["stato_scorta"] in ("sottoscorta", "esaurito")), "causali": CAUSALI}

    @r.get("/magazzino/sottoscorta")
    async def sottoscorta(t: dict = Depends(tenant)):
        rows = await db.articles.find({"company_id": t["cid"], "gestione_magazzino": True, "scorta_minima": {"$gt": 0}}, {"_id": 0}).sort("codice", 1).to_list(5000)
        rows = [enrich(a) for a in rows]
        return [a for a in rows if a["stato_scorta"] in ("sottoscorta", "esaurito")]

    @r.get("/magazzino/movimenti")
    async def movimenti(article_id: Optional[str] = None, tipo: Optional[str] = None, dal: Optional[str] = None, al: Optional[str] = None,
                        t: dict = Depends(tenant)):
        f = {"company_id": t["cid"], **({"article_id": article_id} if article_id else {}), **({"tipo": tipo} if tipo in CAUSALI else {})}
        if dal or al:
            f["data"] = {**({"$gte": dal} if dal else {}), **({"$lte": al} if al else {})}
        rows = await db.stock_moves.find(f, {"_id": 0}).sort([("data", -1), ("created_at", -1)]).to_list(2000)
        if article_id:
            allm = await db.stock_moves.find({"company_id": t["cid"], "article_id": article_id}, {"_id": 0}).to_list(100000)
            replay(allm)
            after = {m["id"]: m["giacenza_dopo"] for m in allm}
            for m in rows:
                m["giacenza_dopo"] = after.get(m["id"])
        return rows

    @r.post("/magazzino/movimenti")
    async def add_move(body: MovIn, t: dict = Depends(tenant)):
        a = await db.articles.find_one({"id": body.article_id, "company_id": t["cid"]}, {"_id": 0})
        if not a:
            raise HTTPException(404, "Articolo non trovato")
        if not a.get("gestione_magazzino"):
            raise HTTPException(400, "Attiva la gestione di magazzino nell'anagrafica dell'articolo")
        if body.tipo != "rettifica" and body.quantita <= 0:
            raise HTTPException(400, "La quantit\u00e0 deve essere maggiore di zero")
        if body.tipo == "rettifica" and body.quantita == 0:
            raise HTTPException(400, "Indica una quantit\u00e0 positiva o negativa")
        if body.tipo == "carico" and body.costo_unitario is None:
            raise HTTPException(400, "Indica il costo unitario del carico")
        if body.causale not in CAUSALI[body.tipo]:
            raise HTTPException(400, "Causale non valida")
        u = t["user"]
        m = {"id": str(uuid.uuid4()), "company_id": t["cid"], **body.model_dump(), "codice": a["codice"], "descrizione": a["descrizione"],
             "unita_misura": a.get("unita_misura") or "", "created_at": _now(), "created_by": u.get("name") or u.get("email")}
        if m["tipo"] != "carico":
            m["costo_unitario"] = None if m["tipo"] == "scarico" or m["quantita"] < 0 else m["costo_unitario"]
        moves = await db.stock_moves.find({"company_id": t["cid"], "article_id": a["id"]}, {"_id": 0}).to_list(100000)
        sim = replay(moves + [dict(m)])
        if sim["minimo"]["giacenza"] < -0.0001:
            raise HTTPException(400, f"Giacenza insufficiente: il {sim['minimo']['data'][8:10]}/{sim['minimo']['data'][5:7]}/{sim['minimo']['data'][:4]} "
                                     f"si andrebbe a {sim['minimo']['giacenza']:g} {a.get('unita_misura') or ''}".strip())
        await db.stock_moves.insert_one(dict(m))
        res = await recompute(t["cid"], a["id"])
        return {**m, "articolo": enrich({**a, **res, "valore_magazzino": res["valore"]})}

    @r.delete("/magazzino/movimenti/{mid}")
    async def del_move(mid: str, t: dict = Depends(tenant_accounting)):
        m = await db.stock_moves.find_one({"id": mid, "company_id": t["cid"]}, {"_id": 0})
        if not m:
            raise HTTPException(404, "Movimento non trovato")
        rest = await db.stock_moves.find({"company_id": t["cid"], "article_id": m["article_id"], "id": {"$ne": mid}}, {"_id": 0}).to_list(100000)
        if rest and replay(rest)["minimo"]["giacenza"] < -0.0001:
            raise HTTPException(400, "Eliminando questo carico la giacenza andrebbe sotto zero: elimina prima gli scarichi successivi")
        await db.stock_moves.delete_one({"id": mid})
        await recompute(t["cid"], m["article_id"])
        return {"ok": True}

    @r.get("/magazzino/riepilogo")
    async def riepilogo(t: dict = Depends(tenant)):
        d = await giacenze(t)
        sotto = [a for a in d["articoli"] if a["stato_scorta"] in ("sottoscorta", "esaurito")]
        return {"articoli": len(d["articoli"]), "valore_totale": d["valore_totale"], "sottoscorta": len(sotto),
                "esauriti": sum(1 for a in sotto if a["stato_scorta"] == "esaurito"),
                "elenco": [{k: a.get(k) for k in ("id", "codice", "descrizione", "giacenza", "scorta_minima", "da_ordinare", "unita_misura", "stato_scorta")} for a in sotto[:6]]}

    return r

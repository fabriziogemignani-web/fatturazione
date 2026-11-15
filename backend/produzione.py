import asyncio
import uuid
from datetime import date, datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from magazzino import recompute_article, replay
from ordini_core import OP_APERTI, aggiorna_impegni

DATE_RX = r"^\d{4}-\d{2}-\d{2}$"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CentroIn(BaseModel):
    codice: str = Field(min_length=1, max_length=20)
    descrizione: str = Field(min_length=1, max_length=120)
    costo_orario: float = Field(default=0, ge=0, le=100_000)


class CompIn(BaseModel):
    article_id: str = Field(max_length=40)
    quantita: float = Field(gt=0, le=1_000_000)
    note: Optional[str] = Field(default="", max_length=200)


class FaseIn(BaseModel):
    descrizione: str = Field(min_length=1, max_length=200)
    centro_id: str = Field(max_length=40)
    setup_min: float = Field(default=0, ge=0, le=100_000)
    minuti_pezzo: float = Field(default=0, ge=0, le=100_000)


class DistintaIn(BaseModel):
    article_id: str = Field(max_length=40)
    lotto: float = Field(default=1, gt=0, le=1_000_000)
    note: Optional[str] = Field(default="", max_length=1000)
    componenti: List[CompIn] = Field(min_length=1, max_length=200)
    fasi: List[FaseIn] = Field(default_factory=list, max_length=50)


class OpIn(BaseModel):
    article_id: str = Field(max_length=40)
    quantita: float = Field(gt=0, le=1_000_000)
    data: str = Field(pattern=DATE_RX)
    data_consegna: Optional[str] = Field(default="", pattern=r"^(\d{4}-\d{2}-\d{2})?$")
    note: Optional[str] = Field(default="", max_length=500)


class VersaIn(BaseModel):
    data: str = Field(pattern=DATE_RX)
    quantita: float = Field(gt=0, le=1_000_000)
    forza: bool = False
    chiudi: bool = False


class GeneraIn(BaseModel):
    righe: List[OpIn] = Field(min_length=1, max_length=200)


def build(db, tenant, deps) -> APIRouter:
    r = APIRouter(prefix="/api/produzione")
    ferr, locks = deps["ferr"], {}

    async def _art(cid, aid, field="article_id"):
        a = await db.articles.find_one({"id": aid, "company_id": cid}, {"_id": 0})
        if not a:
            raise ferr(422, field, "Articolo non trovato")
        return a

    # ---- centri di lavoro
    @r.get("/centri")
    async def centri(t: dict = Depends(tenant)):
        return await db.centri_lavoro.find({"company_id": t["cid"]}, {"_id": 0}).sort("codice", 1).to_list(1000)

    @r.post("/centri")
    async def centro_crea(body: CentroIn, t: dict = Depends(tenant)):
        if await db.centri_lavoro.find_one({"company_id": t["cid"], "codice": body.codice}):
            raise ferr(409, "codice", "Codice gi\u00e0 usato")
        c = {"id": str(uuid.uuid4()), "company_id": t["cid"], **body.model_dump()}
        await db.centri_lavoro.insert_one(dict(c))
        c.pop("_id", None)
        return c

    @r.put("/centri/{cid_}")
    async def centro_mod(cid_: str, body: CentroIn, t: dict = Depends(tenant)):
        if await db.centri_lavoro.find_one({"company_id": t["cid"], "codice": body.codice, "id": {"$ne": cid_}}):
            raise ferr(409, "codice", "Codice gi\u00e0 usato")
        res = await db.centri_lavoro.update_one({"id": cid_, "company_id": t["cid"]}, {"$set": body.model_dump()})
        if not res.matched_count:
            raise HTTPException(404, "Centro di lavoro non trovato")
        return {"ok": True}

    @r.delete("/centri/{cid_}")
    async def centro_del(cid_: str, t: dict = Depends(tenant)):
        if await db.distinte.find_one({"company_id": t["cid"], "fasi.centro_id": cid_}):
            raise HTTPException(400, "Centro usato nei cicli di lavoro: toglilo prima dalle distinte")
        await db.centri_lavoro.delete_one({"id": cid_, "company_id": t["cid"]})
        return {"ok": True}

    # ---- distinte base
    async def _costo(cid, aid, centri_map, seen=()) -> dict:
        a = await db.articles.find_one({"id": aid, "company_id": cid}, {"_id": 0, "costo_medio": 1, "codice": 1})
        d = await db.distinte.find_one({"company_id": cid, "article_id": aid}, {"_id": 0})
        if not d or aid in seen:
            return {"materiali": round(float((a or {}).get("costo_medio") or 0), 4), "lavorazioni": 0}
        mat = lav = 0.0
        for c in d["componenti"]:
            sub = await _costo(cid, c["article_id"], centri_map, seen + (aid,))
            mat += c["quantita"] * (sub["materiali"] + sub["lavorazioni"])
        for f in d["fasi"]:
            lav += (f["setup_min"] / d["lotto"] + f["minuti_pezzo"]) / 60 * (centri_map.get(f["centro_id"]) or 0)
        return {"materiali": round(mat, 4), "lavorazioni": round(lav, 4)}

    async def _centri_map(cid):
        return {c["id"]: c["costo_orario"] async for c in db.centri_lavoro.find({"company_id": cid}, {"_id": 0, "id": 1, "costo_orario": 1})}

    async def _usa(cid, aid, target, seen=()) -> bool:
        if aid == target:
            return True
        d = await db.distinte.find_one({"company_id": cid, "article_id": aid}, {"_id": 0, "componenti": 1})
        return bool(d) and aid not in seen and any([await _usa(cid, c["article_id"], target, seen + (aid,)) for c in d["componenti"]])

    @r.get("/distinte")
    async def distinte(t: dict = Depends(tenant)):
        cid = t["cid"]
        cm = await _centri_map(cid)
        out = await db.distinte.find({"company_id": cid}, {"_id": 0}).sort("codice", 1).to_list(5000)
        for d in out:
            d["costo"] = await _costo(cid, d["article_id"], cm)
        return out

    async def _prep_distinta(cid, body: DistintaIn, did=None) -> dict:
        p = await _art(cid, body.article_id)
        if not p.get("gestione_magazzino"):
            raise ferr(422, "article_id", "Attiva la gestione di magazzino sull'articolo prodotto per poterlo produrre")
        dup = await db.distinte.find_one({"company_id": cid, "article_id": body.article_id, "id": {"$ne": did}})
        if dup:
            raise ferr(409, "article_id", "Questo articolo ha gi\u00e0 una distinta base")
        comps = []
        for i, c in enumerate(body.componenti):
            a = await _art(cid, c.article_id, f"componenti.{i}.article_id")
            if await _usa(cid, c.article_id, body.article_id):
                raise ferr(422, f"componenti.{i}.article_id", f"{a['codice']}: il componente contiene gi\u00e0 il prodotto (ciclo nella distinta)")
            comps.append({**c.model_dump(), "codice": a["codice"], "descrizione": a["descrizione"], "unita_misura": a.get("unita_misura") or ""})
        centri_ids = {c["id"] async for c in db.centri_lavoro.find({"company_id": cid}, {"_id": 0, "id": 1})}
        for i, f in enumerate(body.fasi):
            if f.centro_id not in centri_ids:
                raise ferr(422, f"fasi.{i}.centro_id", "Scegli un centro di lavoro")
        return {**body.model_dump(), "componenti": comps, "fasi": [f.model_dump() for f in body.fasi], "codice": p["codice"], "descrizione": p["descrizione"],
                "unita_misura": p.get("unita_misura") or "", "updated_at": _now()}

    @r.post("/distinte")
    async def distinta_crea(body: DistintaIn, t: dict = Depends(tenant)):
        d = {"id": str(uuid.uuid4()), "company_id": t["cid"], **await _prep_distinta(t["cid"], body)}
        await db.distinte.insert_one(dict(d))
        return d

    @r.put("/distinte/{did}")
    async def distinta_mod(did: str, body: DistintaIn, t: dict = Depends(tenant)):
        d = await _prep_distinta(t["cid"], body, did)
        res = await db.distinte.update_one({"id": did, "company_id": t["cid"]}, {"$set": d})
        if not res.matched_count:
            raise HTTPException(404, "Distinta non trovata")
        return {"id": did, **d}

    @r.delete("/distinte/{did}")
    async def distinta_del(did: str, t: dict = Depends(tenant)):
        await db.distinte.delete_one({"id": did, "company_id": t["cid"]})
        return {"ok": True}

    # ---- ordini di produzione
    async def _crea_op(t, body: OpIn, origine="manuale", ordine=None) -> dict:
        cid = t["cid"]
        d = await db.distinte.find_one({"company_id": cid, "article_id": body.article_id}, {"_id": 0})
        if not d:
            raise ferr(422, "article_id", "L'articolo non ha una distinta base: creala prima")
        cm = await _centri_map(cid)
        centri = {c["id"]: c async for c in db.centri_lavoro.find({"company_id": cid}, {"_id": 0})}
        async with locks.setdefault(cid, asyncio.Lock()):
            anno = int(body.data[:4])
            last = await db.ordini_produzione.find_one({"company_id": cid, "anno": anno}, {"_id": 0, "numero": 1}, sort=[("numero", -1)])
            n = ((last or {}).get("numero") or 0) + 1
            fasi = [{**f, "centro": centri.get(f["centro_id"], {}).get("descrizione", ""), "costo_orario": cm.get(f["centro_id"]) or 0,
                     "minuti_previsti": round(f["setup_min"] + f["minuti_pezzo"] * body.quantita, 2)} for f in d["fasi"]]
            op = {"id": str(uuid.uuid4()), "company_id": cid, "anno": anno, "numero": n, "numero_display": f"OP {n}/{anno}", **body.model_dump(),
                  "codice": d["codice"], "descrizione": d["descrizione"], "unita_misura": d["unita_misura"], "lotto": d["lotto"],
                  "componenti": [{k: c[k] for k in ("article_id", "codice", "descrizione", "unita_misura", "quantita")} for c in d["componenti"]], "fasi": fasi,
                  "prodotta": 0, "status": "pianificato", "origine": origine, "ordine_cliente_id": (ordine or {}).get("id"), "ordine_cliente": (ordine or {}).get("numero_display"),
                  "cliente": ((ordine or {}).get("party") or {}).get("denominazione"), "versamenti": [], "costo_standard": await _costo(cid, body.article_id, cm),
                  "created_at": _now(), "created_by": t["user"].get("name") or t["user"]["email"]}
            await db.ordini_produzione.insert_one(dict(op))
        await aggiorna_impegni(db, cid, [op["article_id"]] + [c["article_id"] for c in op["componenti"]])
        op.pop("_id", None)
        return op

    async def _op(cid, oid):
        o = await db.ordini_produzione.find_one({"id": oid, "company_id": cid}, {"_id": 0})
        if not o:
            raise HTTPException(404, "Ordine di produzione non trovato")
        return o

    @r.get("/ordini")
    async def ops(t: dict = Depends(tenant)):
        return await db.ordini_produzione.find({"company_id": t["cid"]}, {"_id": 0}).sort([("data", -1), ("numero", -1)]).to_list(5000)

    @r.post("/ordini")
    async def op_crea(body: OpIn, t: dict = Depends(tenant)):
        return await _crea_op(t, body)

    @r.post("/ordini/genera")
    async def op_genera(body: GeneraIn, t: dict = Depends(tenant)):
        return [await _crea_op(t, x, "mrp") for x in body.righe]

    @r.post("/da-ordine/{oid}")
    async def da_ordine(oid: str, t: dict = Depends(tenant)):
        cid = t["cid"]
        o = await db.orders.find_one({"id": oid, "company_id": cid, "tipo": "cliente"}, {"_id": 0})
        if not o or o["status"] not in ("aperto", "parziale"):
            raise HTTPException(400, "Ordine cliente non trovato o gi\u00e0 evaso")
        creati = []
        for ln in o["lines"]:
            if not ln.get("article_id") or not await db.distinte.find_one({"company_id": cid, "article_id": ln["article_id"]}):
                continue
            a = await db.articles.find_one({"id": ln["article_id"], "company_id": cid}, {"_id": 0, "disponibilita": 1, "giacenza": 1})
            manca = round(min(max(-(a.get("disponibilita") if a.get("disponibilita") is not None else a.get("giacenza") or 0), 0), ln["quantita"] - (ln.get("evasa") or 0)), 4)
            if manca > 0:
                creati.append(await _crea_op(t, OpIn(article_id=ln["article_id"], quantita=manca, data=date.today().isoformat(), data_consegna=o.get("data_consegna") or "",
                                                     note=f"Per ordine {o['numero_display']}"), "ordine_cliente", o))
        if not creati:
            raise HTTPException(400, "Nessun prodotto da produrre: gli articoli con distinta base sono gi\u00e0 disponibili o in produzione")
        return creati

    @r.post("/ordini/{oid}/stato/{st}")
    async def op_stato(oid: str, st: str, t: dict = Depends(tenant)):
        o = await _op(t["cid"], oid)
        ok = {"lanciato": ("pianificato",), "pianificato": ("lanciato",), "chiuso": tuple(OP_APERTI)}
        if o["status"] not in ok.get(st, ()):
            raise HTTPException(400, "Cambio di stato non consentito")
        if st == "pianificato" and o["versamenti"]:
            raise HTTPException(400, "L'ordine ha gi\u00e0 dei versamenti")
        await db.ordini_produzione.update_one({"id": oid}, {"$set": {"status": st, f"{st}_at": _now()}})
        await aggiorna_impegni(db, t["cid"], [o["article_id"]] + [c["article_id"] for c in o["componenti"]])
        return await _op(t["cid"], oid)

    @r.delete("/ordini/{oid}")
    async def op_del(oid: str, t: dict = Depends(tenant)):
        o = await _op(t["cid"], oid)
        if any(not v.get("annullato") for v in o["versamenti"]):
            raise HTTPException(400, "L'ordine ha dei versamenti: chiudilo invece di eliminarlo")
        await db.ordini_produzione.delete_one({"id": oid})
        await aggiorna_impegni(db, t["cid"], [o["article_id"]] + [c["article_id"] for c in o["componenti"]])
        return {"ok": True}

    @r.post("/ordini/{oid}/versa")
    async def versa(oid: str, body: VersaIn, t: dict = Depends(tenant)):
        cid, u = t["cid"], t["user"]
        if body.data > date.today().isoformat():
            raise ferr(400, "data", "La data non pu\u00f2 essere futura")
        async with locks.setdefault(f"v-{cid}", asyncio.Lock()):
            o = await _op(cid, oid)
            if o["status"] not in ("lanciato", "in_corso"):
                raise HTTPException(400, "Lancia l'ordine prima di versare la produzione" if o["status"] == "pianificato" else "Ordine gi\u00e0 completato o chiuso")
            arts = {a["id"]: a async for a in db.articles.find({"company_id": cid, "id": {"$in": [c["article_id"] for c in o["componenti"]]}}, {"_id": 0})}
            carenze, mat = [], 0.0
            for c in o["componenti"]:
                a = arts.get(c["article_id"]) or {}
                need = round(c["quantita"] * body.quantita, 4)
                mat += need * float(a.get("costo_medio") or 0)
                if a.get("gestione_magazzino") and (a.get("giacenza") or 0) < need - 1e-9:
                    carenze.append({"codice": c["codice"], "richiesta": need, "disponibile": a.get("giacenza") or 0})
            if carenze and not body.forza:
                raise HTTPException(409, {"message": "Componenti insufficienti in magazzino", "carenze": carenze})
            primo = not any(not v.get("annullato") for v in o["versamenti"])
            lav = sum(((f["setup_min"] if primo else 0) + f["minuti_pezzo"] * body.quantita) / 60 * f["costo_orario"] for f in o["fasi"])
            vid, doc = str(uuid.uuid4()), f"{o['numero_display']}"
            base = {"company_id": cid, "data": body.data, "documento": doc, "versamento_id": vid, "op_id": oid, "created_at": _now(), "created_by": u.get("name") or u.get("email")}
            for c in o["componenti"]:
                a = arts.get(c["article_id"]) or {}
                if a.get("gestione_magazzino"):
                    await db.stock_moves.insert_one({**base, "id": str(uuid.uuid4()), "article_id": c["article_id"], "tipo": "scarico", "quantita": round(c["quantita"] * body.quantita, 4),
                                                     "causale": "Produzione", "note": f"Consumo per {o['codice']}", "codice": c["codice"], "descrizione": c["descrizione"], "unita_misura": c["unita_misura"]})
            cu = round((mat + lav) / body.quantita, 4)
            await db.stock_moves.insert_one({**base, "id": str(uuid.uuid4()), "article_id": o["article_id"], "tipo": "carico", "quantita": body.quantita, "costo_unitario": cu,
                                             "causale": "Produzione", "note": "Versamento prodotto finito", "codice": o["codice"], "descrizione": o["descrizione"], "unita_misura": o["unita_misura"]})
            prod = round(o["prodotta"] + body.quantita, 4)
            st = "completato" if prod >= o["quantita"] - 1e-9 else ("chiuso" if body.chiudi else "in_corso")
            v = {"id": vid, "data": body.data, "quantita": body.quantita, "costo_materiali": round(mat, 2), "costo_lavorazioni": round(lav, 2), "costo_unitario": cu, "at": _now(), "forzato": bool(carenze)}
            await db.ordini_produzione.update_one({"id": oid}, {"$set": {"prodotta": prod, "status": st}, "$push": {"versamenti": v}})
        for aid in [o["article_id"]] + [c["article_id"] for c in o["componenti"] if (arts.get(c["article_id"]) or {}).get("gestione_magazzino")]:
            await recompute_article(db, cid, aid)
        await aggiorna_impegni(db, cid, [o["article_id"]] + [c["article_id"] for c in o["componenti"]])
        return await _op(cid, oid)

    @r.post("/ordini/{oid}/versamenti/{vid}/annulla")
    async def versa_annulla(oid: str, vid: str, t: dict = Depends(tenant)):
        async with locks.setdefault(f"v-{t['cid']}", asyncio.Lock()):
            return await _versa_annulla(oid, vid, t)

    async def _versa_annulla(oid: str, vid: str, t: dict):
        cid = t["cid"]
        o = await _op(cid, oid)
        v = next((x for x in o["versamenti"] if x["id"] == vid and not x.get("annullato")), None)
        if not v:
            raise HTTPException(404, "Versamento non trovato")
        moves = await db.stock_moves.find({"company_id": cid, "versamento_id": vid}, {"_id": 0, "article_id": 1}).to_list(500)
        aids = {m["article_id"] for m in moves}
        for aid in aids:
            rest = await db.stock_moves.find({"company_id": cid, "article_id": aid, "versamento_id": {"$ne": vid}}, {"_id": 0}).to_list(100000)
            if rest and replay(rest)["minimo"]["giacenza"] < -0.0001:
                raise HTTPException(400, "Annullando il versamento la giacenza del prodotto andrebbe sotto zero")
        await db.stock_moves.delete_many({"company_id": cid, "versamento_id": vid})
        prod = round(o["prodotta"] - v["quantita"], 4)
        vs = [{**x, "annullato": True} if x["id"] == vid else x for x in o["versamenti"]]
        st = "chiuso" if o["status"] == "chiuso" else ("in_corso" if prod > 0 else "lanciato")
        await db.ordini_produzione.update_one({"id": oid}, {"$set": {"prodotta": prod, "versamenti": vs, "status": st}})
        for aid in aids:
            await recompute_article(db, cid, aid)
        await aggiorna_impegni(db, cid, [o["article_id"]] + [c["article_id"] for c in o["componenti"]])
        return await _op(cid, oid)

    # ---- MRP
    @r.get("/mrp")
    async def mrp(t: dict = Depends(tenant)):
        cid = t["cid"]
        arts = {a["id"]: a async for a in db.articles.find({"company_id": cid, "gestione_magazzino": True}, {"_id": 0})}
        bom = {d["article_id"]: d async for d in db.distinte.find({"company_id": cid}, {"_id": 0})}
        llc = {}

        def level(aid, depth=0, seen=()):
            if aid in seen:
                return
            llc[aid] = max(llc.get(aid, 0), depth)
            for c in (bom.get(aid) or {}).get("componenti", []):
                level(c["article_id"], depth + 1, seen + (aid,))
        for aid in list(arts) + list(bom):
            level(aid)
        disp = {aid: (a.get("giacenza") or 0) - (a.get("impegnato") or 0) + (a.get("ordinato") or 0) for aid, a in arts.items()}
        prod, acq = [], []
        for aid in sorted(arts, key=lambda x: llc.get(x, 0)):
            a = arts[aid]
            need = round((a.get("scorta_minima") or 0) - disp[aid], 4)
            if need <= 1e-9:
                continue
            if aid in bom:
                q = round(max(need, bom[aid]["lotto"]), 4)
                for c in bom[aid]["componenti"]:
                    if c["article_id"] in disp:
                        disp[c["article_id"]] -= c["quantita"] * q
                prod.append({"article_id": aid, "codice": a["codice"], "descrizione": a["descrizione"], "quantita": q, "disponibilita": round(disp[aid], 4),
                             "scorta_minima": a.get("scorta_minima") or 0, "livello": llc.get(aid, 0)})
            else:
                q = round(max(need, a.get("scorta_riordino") or 0), 4)
                acq.append({"article_id": aid, "codice": a["codice"], "descrizione": a["descrizione"], "quantita": q, "disponibilita": round(disp[aid], 4),
                            "fornitore_abituale": a.get("fornitore_abituale") or "", "unita_misura": a.get("unita_misura") or "", "aliquota": a.get("aliquota", 22),
                            "natura": a.get("natura") or "", "prezzo_unitario": round(float(a.get("costo_medio") or 0), 4)})
            disp[aid] += q
        return {"produrre": prod, "acquistare": acq}

    return r

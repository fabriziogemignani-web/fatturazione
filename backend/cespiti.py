import uuid
from datetime import date, datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import ai_agent
import contabilita as coge

# coefficienti fiscali DM 31/12/1988 (valori proposti, modificabili per ogni cespite)
CATEGORIE = [
    ("fabbricati", "Fabbricati strumentali", 3, "02.01.002", "02.09.001", "30.10.002"),
    ("costruzioni_leggere", "Costruzioni leggere (tettoie, baracche)", 10, "02.01.002", "02.09.001", "30.10.002"),
    ("terreni", "Terreni (non ammortizzabili)", 0, "02.01.001", "", ""),
    ("impianti_generici", "Impianti generici", 10, "02.02.001", "02.09.002", "30.10.002"),
    ("macchinari", "Macchinari, apparecchi e impianti specifici", 15, "02.02.002", "02.09.002", "30.10.002"),
    ("attrezzature", "Attrezzature industriali e commerciali", 15, "02.03.001", "02.09.003", "30.10.002"),
    ("mobili", "Mobili e arredi d'ufficio", 12, "02.04.001", "02.09.004", "30.10.002"),
    ("macchine_ufficio", "Macchine d'ufficio elettroniche e computer", 20, "02.04.002", "02.09.005", "30.10.002"),
    ("telefonia", "Telefoni cellulari e apparati di telefonia", 20, "02.04.002", "02.09.005", "30.10.002"),
    ("autovetture", "Autovetture e motocicli", 25, "02.04.003", "02.09.006", "30.10.002"),
    ("autocarri", "Autocarri e mezzi di trasporto", 20, "02.04.003", "02.09.006", "30.10.002"),
    ("beni_minori", "Beni di costo unitario fino a 516,46 euro", 100, "02.04.004", "02.09.003", "30.10.002"),
    ("software", "Software e licenze d'uso", 33.33, "01.02.001", "01.09.002", "30.10.001"),
    ("marchi", "Marchi (1/18)", 5.56, "01.03.001", "01.09.003", "30.10.001"),
    ("brevetti", "Brevetti e opere dell'ingegno", 50, "01.03.001", "01.09.003", "30.10.001"),
    ("avviamento", "Avviamento (1/18)", 5.56, "01.04.001", "01.09.004", "30.10.001"),
    ("impianto_ampliamento", "Costi di impianto e ampliamento", 20, "01.01.001", "01.09.001", "30.10.001"),
]
CAT = {c[0]: {"id": c[0], "nome": c[1], "aliquota": c[2], "conto_cespite": c[3], "conto_fondo": c[4], "conto_ammortamento": c[5]} for c in CATEGORIE}
PRIMO_ANNO = ("meta", "giorni", "piena")


def _now():
    return datetime.now(timezone.utc).isoformat()


def r2(v) -> float:
    return round(float(v or 0) + 0.0, 2)


def categoria_da_conto(conto: str) -> str:
    return next((c[0] for c in CATEGORIE if c[3] == conto and c[0] not in ("costruzioni_leggere", "telefonia", "autocarri", "brevetti")), "attrezzature")


def quota(c: dict, anno: int, regola: str) -> float:
    """Quota teorica di ammortamento dell'anno, nei limiti del residuo da ammortizzare."""
    if not c.get("aliquota") or not c.get("conto_fondo"):
        return 0.0
    d0 = date.fromisoformat(c.get("data_entrata_funzione") or c["data_acquisto"])
    y0 = max(d0.year, int(c.get("anno_inizio") or 0))
    if anno < y0 or (c.get("data_dismissione") and anno > int(c["data_dismissione"][:4])):
        return 0.0
    fondo = float(c.get("fondo_iniziale") or 0)
    for y in range(y0, anno):
        fondo += _piena(c, y, d0, regola)
    return r2(max(min(_piena(c, anno, d0, regola), float(c["costo"]) - fondo), 0))


def _piena(c: dict, y: int, d0: date, regola: str) -> float:
    q = float(c["costo"]) * float(c["aliquota"]) / 100
    if y == d0.year and c.get("categoria") != "beni_minori" and not c.get("fondo_iniziale"):
        if regola == "meta":
            q /= 2
        elif regola == "giorni":
            q *= ((date(y, 12, 31) - d0).days + 1) / (366 if y % 4 == 0 else 365)
    return q


def piano(c: dict, regola: str) -> list:
    d0 = date.fromisoformat(c.get("data_entrata_funzione") or c["data_acquisto"])
    out, fondo, y = [], float(c.get("fondo_iniziale") or 0), max(d0.year, int(c.get("anno_inizio") or 0))
    reg = {a["anno"]: a for a in c.get("ammortamenti") or []}
    while fondo < float(c["costo"]) - 0.005 and y < d0.year + 120 and c.get("aliquota") and c.get("conto_fondo"):
        q = quota(c, y, regola)
        if q <= 0:
            break
        fondo = r2(fondo + q)
        out.append({"anno": y, "quota": q, "fondo": fondo, "residuo": r2(float(c["costo"]) - fondo), "registrato": y in reg})
        y += 1
    return out


class CespiteIn(BaseModel):
    descrizione: str = Field(min_length=1, max_length=200)
    categoria: str
    data_acquisto: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    data_entrata_funzione: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    costo: float = Field(gt=0, le=100_000_000)
    aliquota: float = Field(ge=0, le=100)
    fondo_iniziale: float = Field(default=0, ge=0)
    conto_cespite: Optional[str] = Field(default="", max_length=12)
    conto_fondo: Optional[str] = Field(default="", max_length=12)
    conto_ammortamento: Optional[str] = Field(default="", max_length=12)
    fornitore: Optional[str] = Field(default="", max_length=200)
    passive_id: Optional[str] = None
    riga_n: Optional[int] = None


class ConfigIn(BaseModel):
    primo_anno: Literal["meta", "giorni", "piena"]


class DismettiIn(BaseModel):
    data: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


def build(db, tenant, tenant_accounting, deps) -> APIRouter:
    r = APIRouter(prefix="/api/cespiti")
    ferr = deps["ferr"]

    def _regola(comp: dict) -> str:
        return (comp.get("cespiti_config") or {}).get("primo_anno") or "meta"

    async def _get(cid: str, xid: str) -> dict:
        c = await db.cespiti.find_one({"id": xid, "company_id": cid, "annullato": {"$ne": True}}, {"_id": 0})
        if not c:
            raise HTTPException(404, "Cespite non trovato")
        return c

    def _out(c: dict, regola: str) -> dict:
        anno = date.today().year
        pp = piano(c, regola)
        fondo = r2(float(c.get("fondo_iniziale") or 0) + sum(x["quota"] for x in pp if x["anno"] < anno))
        return {**c, "piano": pp, "categoria_nome": CAT.get(c["categoria"], {}).get("nome", c["categoria"]), "quota_anno": quota(c, anno, regola),
                "fondo_inizio_anno": fondo, "residuo_inizio_anno": r2(float(c["costo"]) - fondo)}

    async def _check(cid: str, body: CespiteIn) -> dict:
        if body.categoria not in CAT:
            raise ferr(400, "categoria", "Categoria non valida")
        if body.fondo_iniziale > body.costo:
            raise ferr(400, "fondo_iniziale", "Il fondo non può superare il costo")
        base = CAT[body.categoria]
        v = body.model_dump()
        v["anno_inizio"] = date.today().year if body.fondo_iniziale > 0 else None
        for k in ("conto_cespite", "conto_fondo", "conto_ammortamento"):
            v[k] = v[k] or base[k]
        if coge.attiva(await coge._company(db, cid)) and body.aliquota > 0:
            await coge.ensure_seed(db, cid)
            for k in ("conto_cespite", "conto_fondo", "conto_ammortamento"):
                if not v[k] or not await db.coa_accounts.find_one({"company_id": cid, "codice": v[k], "livello": 3}, {"_id": 1}):
                    raise ferr(400, k, "Scegli un sottoconto esistente del piano dei conti")
        return v

    @r.get("/categorie")
    async def categorie(t: dict = Depends(tenant)):
        return list(CAT.values())

    @r.get("/config")
    async def get_config(t: dict = Depends(tenant)):
        return {"primo_anno": _regola(t["company"])}

    @r.put("/config")
    async def put_config(body: ConfigIn, t: dict = Depends(tenant_accounting)):
        if await db.cespiti.find_one({"company_id": t["cid"], "ammortamenti.0": {"$exists": True}}, {"_id": 1}) and body.primo_anno != _regola(t["company"]):
            raise HTTPException(400, "Ci sono ammortamenti già registrati: annullali prima di cambiare la regola del primo anno")
        await db.companies.update_one({"id": t["cid"]}, {"$set": {"cespiti_config.primo_anno": body.primo_anno}})
        return {"primo_anno": body.primo_anno}

    @r.get("")
    async def elenco(t: dict = Depends(tenant)):
        reg = _regola(t["company"])
        rows = await db.cespiti.find({"company_id": t["cid"], "annullato": {"$ne": True}}, {"_id": 0}).sort("data_acquisto", -1).to_list(5000)
        return [_out(c, reg) for c in rows]

    @r.post("")
    async def crea(body: CespiteIn, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        v = await _check(cid, body)
        if body.passive_id and await db.cespiti.find_one({"company_id": cid, "passive_id": body.passive_id, "riga_n": body.riga_n, "annullato": {"$ne": True}}, {"_id": 1}):
            raise HTTPException(400, "Per questa riga della fattura il cespite esiste già")
        doc = {"id": str(uuid.uuid4()), "company_id": cid, **v, "ammortamenti": [], "created_by": t["user"].get("name") or t["user"]["email"], "created_at": _now()}
        await db.cespiti.insert_one(doc)
        return _out(await _get(cid, doc["id"]), _regola(t["company"]))

    @r.put("/{xid}")
    async def modifica(xid: str, body: CespiteIn, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        c = await _get(cid, xid)
        if c.get("ammortamenti"):
            raise HTTPException(400, "Il cespite ha ammortamenti registrati: annullali prima di modificarlo")
        v = await _check(cid, body)
        v.pop("passive_id", None), v.pop("riga_n", None)
        await db.cespiti.update_one({"id": xid, "company_id": cid}, {"$set": {**v, "updated_at": _now()}})
        return _out(await _get(cid, xid), _regola(t["company"]))

    @r.delete("/{xid}")
    async def elimina(xid: str, t: dict = Depends(tenant_accounting)):
        c = await _get(t["cid"], xid)
        if c.get("ammortamenti"):
            raise HTTPException(400, "Il cespite ha ammortamenti registrati: non può essere eliminato")
        await db.cespiti.update_one({"id": xid, "company_id": t["cid"]}, {"$set": {"annullato": True, "annullato_il": _now()}})
        return {"ok": True}

    @r.post("/{xid}/dismetti")
    async def dismetti(xid: str, body: DismettiIn, t: dict = Depends(tenant_accounting)):
        c = await _get(t["cid"], xid)
        if body.data < c["data_acquisto"]:
            raise ferr(400, "data", "La dismissione non può precedere l'acquisto")
        await db.cespiti.update_one({"id": xid, "company_id": t["cid"]}, {"$set": {"data_dismissione": body.data}})
        return _out(await _get(t["cid"], xid), _regola(t["company"]))

    @r.delete("/{xid}/dismetti")
    async def riattiva(xid: str, t: dict = Depends(tenant_accounting)):
        await _get(t["cid"], xid)
        await db.cespiti.update_one({"id": xid, "company_id": t["cid"]}, {"$unset": {"data_dismissione": ""}})
        return _out(await _get(t["cid"], xid), _regola(t["company"]))

    async def _proposte(cid: str, pid: Optional[str] = None) -> list:
        q = {"company_id": cid, "stato_reg": "registrata", "cespiti_ignorati": {"$ne": True}}
        if pid:
            q["id"] = pid
        docs = await db.passive_invoices.find(q, {"_id": 0, "xml_b64": 0}).sort("data", -1).to_list(2000 if not pid else 1)
        fatti = {(c.get("passive_id"), c.get("riga_n")) for c in await db.cespiti.find({"company_id": cid, "passive_id": {"$ne": None}, "annullato": {"$ne": True}}, {"_id": 0, "passive_id": 1, "riga_n": 1}).to_list(10000)}
        out = []
        for d in docs:
            fin = ai_agent.conti_finali(d, _rc_aliquote(d))
            for x in d.get("lines") or []:
                conto = fin.get(x.get("n"))
                if not conto or conto[:3] not in ("01.", "02.") or (d["id"], x.get("n")) in fatti or (x.get("prezzo_totale") or 0) <= 0:
                    continue
                cat = CAT[categoria_da_conto(conto)]
                out.append({"passive_id": d["id"], "riga_n": x.get("n"), "numero_display": d.get("numero_display") or d.get("numero"), "fornitore": (d.get("fornitore") or {}).get("denominazione") or "",
                            "descrizione": (x.get("descrizione") or "")[:200], "costo": r2(x["prezzo_totale"]), "data_acquisto": d["data"], "conto": conto,
                            "categoria": cat["id"], "aliquota": 100 if x["prezzo_totale"] <= 516.46 and conto == "02.04.004" else cat["aliquota"]})
        return out

    def _rc_aliquote(d: dict) -> list:
        rc = d.get("righe_costo") or []
        rie = d.get("riepilogo") or []
        if rc and all("aliquota" in x for x in rc):
            return rc
        if len(rc) == len(rie):
            return [{**rr, "conto": x.get("conto")} for rr, x in zip(rie, rc)]
        if len({x.get("conto") for x in rc if x.get("conto")}) == 1:
            return [{**rr, "conto": rc[0]["conto"]} for rr in rie]
        return [{**rr, "conto": d.get("ai_conto")} for rr in rie] if d.get("ai_conto") else []

    @r.get("/proposte")
    async def proposte(passive_id: Optional[str] = None, t: dict = Depends(tenant)):
        return await _proposte(t["cid"], passive_id)

    @r.post("/proposte/{pid}/ignora")
    async def ignora(pid: str, t: dict = Depends(tenant_accounting)):
        await db.passive_invoices.update_one({"id": pid, "company_id": t["cid"]}, {"$set": {"cespiti_ignorati": True}})
        return {"ok": True}

    async def _anteprima(cid: str, anno: int, regola: str) -> dict:
        rows = await db.cespiti.find({"company_id": cid, "annullato": {"$ne": True}}, {"_id": 0}).to_list(5000)
        voci = []
        for c in rows:
            q = quota(c, anno, regola)
            if q > 0:
                voci.append({"id": c["id"], "descrizione": c["descrizione"], "categoria": CAT.get(c["categoria"], {}).get("nome", ""), "costo": c["costo"], "aliquota": c["aliquota"], "quota": q,
                             "conto_ammortamento": c["conto_ammortamento"], "conto_fondo": c["conto_fondo"], "registrato": any(a["anno"] == anno for a in c.get("ammortamenti") or [])})
        righe = {}
        for v in voci:
            righe.setdefault((v["conto_ammortamento"], "dare"), 0)
            righe.setdefault((v["conto_fondo"], "avere"), 0)
            righe[(v["conto_ammortamento"], "dare")] += v["quota"]
            righe[(v["conto_fondo"], "avere")] += v["quota"]
        reg = await db.coa_entries.find_one({"company_id": cid, "origine": "ammortamento", "ref_id": f"amm-{anno}"}, {"_id": 0, "numero": 1, "anno": 1, "id": 1})
        return {"anno": anno, "regola": regola, "voci": voci, "totale": r2(sum(v["quota"] for v in voci)), "registrato": bool(reg) or any(v["registrato"] for v in voci),
                "coge_rif": f"prima nota n. {reg['numero']}/{reg['anno']}" if reg else None,
                "righe": [{"conto": k[0], k[1]: r2(v)} for k, v in sorted(righe.items(), key=lambda kv: (kv[0][1] != "dare", kv[0][0]))]}

    @r.get("/ammortamenti/{anno}")
    async def anteprima(anno: int, t: dict = Depends(tenant)):
        return await _anteprima(t["cid"], anno, _regola(t["company"]))

    @r.post("/ammortamenti/{anno}")
    async def registra(anno: int, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        a = await _anteprima(cid, anno, _regola(t["company"]))
        if a["registrato"]:
            raise HTTPException(400, f"Gli ammortamenti {anno} sono già registrati")
        if not a["voci"]:
            raise HTTPException(400, f"Nessuna quota di ammortamento per il {anno}")
        by = t["user"].get("name") or t["user"]["email"]
        rif = None
        if coge.attiva(await coge._company(db, cid)):
            await coge.check_aperto(db, cid, anno)
            try:
                e = await coge._insert(db, cid, coge.params_of(await coge._company(db, cid)), f"{anno}-12-31", "GE", f"Ammortamenti esercizio {anno}", a["righe"], "ammortamento", ref_id=f"amm-{anno}", by=by)
            except ValueError as ex:
                raise HTTPException(400, f"Ammortamenti non registrati: {ex}")
            rif = f"prima nota n. {e['numero']}/{e['anno']}" if e else None
        for v in a["voci"]:
            await db.cespiti.update_one({"id": v["id"], "company_id": cid}, {"$push": {"ammortamenti": {"anno": anno, "quota": v["quota"], "at": _now(), "by": by}}})
        return {**await _anteprima(cid, anno, _regola(t["company"])), "coge_rif": rif}

    @r.delete("/ammortamenti/{anno}")
    async def annulla(anno: int, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        if await db.cespiti.find_one({"company_id": cid, "ammortamenti.anno": anno + 1}, {"_id": 1}):
            raise HTTPException(400, f"Annulla prima gli ammortamenti {anno + 1}")
        await coge.check_annullabile(db, cid, "ammortamento", f"amm-{anno}")
        await coge.annulla(db, cid, "ammortamento", f"amm-{anno}")
        await db.cespiti.update_many({"company_id": cid}, {"$pull": {"ammortamenti": {"anno": anno}}})
        return await _anteprima(cid, anno, _regola(t["company"]))

    return r

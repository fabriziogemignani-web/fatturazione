import base64
import uuid
from datetime import date, datetime, timezone, timedelta
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field, field_validator


def _d(v: str) -> date:
    try:
        return date.fromisoformat(v)
    except (TypeError, ValueError):
        raise HTTPException(422, "Data non valida (formato AAAA-MM-GG)")


class _Date(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v


class ConfigIn(BaseModel):
    alta_da: str = Field(pattern=r"^\d{2}-\d{2}$")
    alta_a: str = Field(pattern=r"^\d{2}-\d{2}$")
    aliquota: float = Field(ge=0, le=22)
    natura: Optional[str] = None


class PontileIn(_Date):
    nome: str = Field(min_length=1, max_length=40)
    ordine: int = 0


class PostoIn(_Date):
    pontile_id: str
    codice: str = Field(min_length=1, max_length=20)
    lunghezza_max: float = Field(gt=0, le=200)
    larghezza_max: float = Field(default=0, ge=0, le=60)
    tipo: Literal["mare", "terra"] = "mare"
    fuori_servizio: bool = False
    note: str = Field(default="", max_length=200)


class SerieIn(BaseModel):
    pontile_id: str
    prefisso: str = Field(default="", max_length=10)
    da: int = Field(ge=1, le=9999)
    a: int = Field(ge=1, le=9999)
    lunghezza_max: float = Field(gt=0, le=200)
    larghezza_max: float = Field(default=0, ge=0, le=60)


class FasciaIn(BaseModel):
    da_m: float = Field(ge=0, le=200)
    a_m: float = Field(gt=0, le=200)
    giorno_alta: float = Field(ge=0)
    giorno_bassa: float = Field(ge=0)
    mese_alta: float = Field(ge=0)
    mese_bassa: float = Field(ge=0)
    annuale: float = Field(ge=0)


class ListinoIn(BaseModel):
    fasce: List[FasciaIn] = Field(max_length=50)


class BarcaIn(_Date):
    nome: str = Field(min_length=1, max_length=60)
    party_id: str
    matricola: str = Field(default="", max_length=40)
    tipo: Literal["motore", "vela", "gommone", "altro"] = "motore"
    lunghezza: float = Field(gt=0, le=200)
    larghezza: float = Field(default=0, ge=0, le=60)
    pescaggio: float = Field(default=0, ge=0, le=20)
    bandiera: str = Field(default="IT", max_length=30)
    note: str = Field(default="", max_length=300)


class ContrattoIn(BaseModel):
    barca_id: str
    posto_id: str
    tipo: Literal["annuale", "stagionale", "mensile"] = "annuale"
    data_inizio: str
    data_fine: str
    n_rate: Literal[1, 2, 3, 4, 6, 12] = 1
    importo: Optional[float] = Field(default=None, ge=0)
    note: str = Field(default="", max_length=300)


class TransitoIn(BaseModel):
    barca_id: str
    posto_id: str
    arrivo: str
    partenza_prevista: str
    note: str = Field(default="", max_length=300)


class PartenzaIn(BaseModel):
    partenza: str
    importo: Optional[float] = Field(default=None, ge=0)


class FatturaRateIn(BaseModel):
    fino_al: str
    contratto_ids: List[str] = Field(default_factory=list, max_length=2000)


class PosIn(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class DisponiIn(BaseModel):
    posto_ids: List[str] = Field(min_length=1, max_length=300)
    x1: float = Field(ge=0, le=1)
    y1: float = Field(ge=0, le=1)
    x2: float = Field(ge=0, le=1)
    y2: float = Field(ge=0, le=1)


IMG_MAX = 5 * 1024 * 1024


def _alta(cfg: dict, d: date) -> bool:
    md = d.strftime("%m-%d")
    a, b = cfg.get("alta_da", "06-01"), cfg.get("alta_a", "09-30")
    return a <= md <= b if a <= b else (md >= a or md <= b)


def _fascia(listino: list, lun: float) -> dict:
    fs = sorted(listino, key=lambda x: x["da_m"])
    f = next((x for x in fs if lun <= x["a_m"]), None) if fs and lun >= fs[0]["da_m"] else None
    if not f:
        raise HTTPException(400, f"Nessuna fascia di listino per una barca di {lun:g} m: completa il listino in Configurazione porto")
    return f


def prezzo_transito(cfg, listino, lun, da: date, a: date) -> float:
    f = _fascia(listino, lun)
    notti = max((a - da).days, 1)
    return round(sum(f["giorno_alta"] if _alta(cfg, da + timedelta(days=i)) else f["giorno_bassa"] for i in range(notti)), 2)


def prezzo_contratto(cfg, listino, lun, tipo, da: date, a: date) -> float:
    f = _fascia(listino, lun)
    giorni = (a - da).days + 1
    if tipo == "annuale":
        return round(f["annuale"] * min(giorni, 366) / 365 if giorni < 360 else f["annuale"] * round(giorni / 365), 2)
    mesi = max(round(giorni / 30.4), 1)
    return round(sum(f["mese_alta"] if _alta(cfg, da + timedelta(days=int(i * 30.4 + 15))) else f["mese_bassa"] for i in range(mesi)), 2)


def _rate(importo: float, n: int, da: date, a: date) -> list:
    step = ((a - da).days + 1) / n
    q = round(importo / n, 2)
    out = [{"n": i + 1, "scadenza": (da + timedelta(days=int(step * i))).isoformat(), "importo": q, "fattura_id": None, "fattura_numero": None} for i in range(n)]
    out[-1]["importo"] = round(importo - q * (n - 1), 2)
    return out


def build(db, tenant, deps) -> APIRouter:
    r = APIRouter(prefix="/api/porto")
    ferr, now_iso = deps["ferr"], deps["now_iso"]

    async def _cfg(cid):
        return await db.porto_config.find_one({"company_id": cid}, {"_id": 0}) or {"alta_da": "06-01", "alta_a": "09-30", "aliquota": 22.0, "natura": None, "listino": []}

    async def _one(coll, cid, i, msg):
        x = await db[coll].find_one({"id": i, "company_id": cid}, {"_id": 0})
        if not x:
            raise HTTPException(404, msg)
        return x

    async def _sovrapposti(cid, filtro: dict, da: str, a_excl: str, skip=None):
        out = []
        base = {"company_id": cid, **filtro, "occ_da": {"$lt": a_excl}, **({"id": {"$ne": skip}} if skip else {})}
        for coll, tipo, st in (("porto_contratti", "contratto", {"stato": "attivo"}), ("porto_transiti", "transito", {})):
            async for x in db[coll].find({**base, **st, "$or": [{"occ_a": {"$gt": da}}, {"stato": {"$in": ["presente", "in_fatturazione"]}}]}, {"_id": 0}):
                if tipo == "transito" and x["stato"] in ("presente", "in_fatturazione"):
                    x["occ_a"] = max(x["occ_a"], (date.today() + timedelta(days=1)).isoformat())
                if x["occ_a"] > da:
                    out.append((tipo, x))
        return out

    async def _conflitto(cid, posto_id, da: date, a_excl: date, skip=None, barca_id=None):
        for filtro, cosa in (({"posto_id": posto_id}, "Posto occupato"), ({"barca.id": barca_id}, "La barca ha già un ormeggio")):
            if filtro.get("barca.id", True) is None:
                continue
            hit = await _sovrapposti(cid, filtro, da.isoformat(), a_excl.isoformat(), skip)
            if hit:
                tipo, x = hit[0]
                raise HTTPException(409, f"{cosa} nel periodo: {tipo} {x['barca']['nome']} posto {x['posto']['codice']} ({x['occ_da']} - {x['occ_a']})")

    async def _barca_posto(cid, barca_id, posto_id):
        b = await _one("porto_barche", cid, barca_id, "Barca non trovata")
        p = await _one("porto_posti", cid, posto_id, "Posto barca non trovato")
        if p.get("fuori_servizio"):
            raise HTTPException(400, f"Il posto {p['codice']} è fuori servizio")
        if b["lunghezza"] > p["lunghezza_max"] or (p.get("larghezza_max") and b.get("larghezza") and b["larghezza"] > p["larghezza_max"]):
            raise HTTPException(400, f"La barca {b['nome']} ({b['lunghezza']:g} m) non entra nel posto {p['codice']} (max {p['lunghezza_max']:g} m)")
        pa = await db.parties.find_one({"id": b["party_id"], "company_id": cid}, {"_id": 0, "denominazione": 1, "modalita_pagamento": 1})
        if not pa:
            raise HTTPException(400, "L'armatore della barca non è più in anagrafica")
        return b, p, pa

    def _snap(b, p, pa):
        return {"barca": {"id": b["id"], "nome": b["nome"], "lunghezza": b["lunghezza"], "matricola": b.get("matricola", "")},
                "posto": {"id": p["id"], "codice": p["codice"]}, "party_id": b["party_id"], "cliente": pa["denominazione"]}

    async def _fattura(t, party_id, descr, imponibile, scadenza, causale):
        cfg = await _cfg(t["cid"])
        pa = await db.parties.find_one({"id": party_id, "company_id": t["cid"]}, {"_id": 0, "modalita_pagamento": 1})
        mp = (pa or {}).get("modalita_pagamento")
        line = deps["LineIn"](descrizione=descr, quantita=1, prezzo_unitario=imponibile, aliquota=cfg.get("aliquota", 22.0),
                              natura=cfg.get("natura") if not cfg.get("aliquota") else None)
        oggi = date.today().isoformat()
        try:
            inv = deps["InvoiceIn"](data=oggi, party_id=party_id, lines=[line], causale=causale, scadenza=max(scadenza, oggi),
                                    **({"modalita_pagamento": mp} if mp in ("MP01", "MP02", "MP05", "MP08", "MP12") else {}))
            return await deps["create_invoice"](inv, t)
        except HTTPException as e:
            d = e.detail
            raise HTTPException(400, f"Fattura non creata: {d if isinstance(d, str) else d}")
        except ValueError as e:
            raise HTTPException(400, f"Fattura non creata: {e}")

    # --- configurazione ---
    @r.get("/config")
    async def get_config(t: dict = Depends(tenant)):
        return await _cfg(t["cid"])

    @r.put("/config")
    async def put_config(body: ConfigIn, t: dict = Depends(tenant)):
        if body.aliquota == 0 and not body.natura:
            raise ferr(422, "natura", "Con aliquota 0% indica la natura IVA")
        await db.porto_config.update_one({"company_id": t["cid"]}, {"$set": {**body.model_dump(), "company_id": t["cid"]}}, upsert=True)
        return await _cfg(t["cid"])

    @r.put("/listino")
    async def put_listino(body: ListinoIn, t: dict = Depends(tenant)):
        f = sorted([x.model_dump() for x in body.fasce], key=lambda x: x["da_m"])
        for i, x in enumerate(f):
            if x["da_m"] > x["a_m"]:
                raise HTTPException(422, f"Fascia {i + 1}: 'da' maggiore di 'a'")
            if i and x["da_m"] <= f[i - 1]["a_m"]:
                raise HTTPException(422, f"Le fasce {f[i - 1]['da_m']:g}-{f[i - 1]['a_m']:g} m e {x['da_m']:g}-{x['a_m']:g} m si sovrappongono")
        await db.porto_config.update_one({"company_id": t["cid"]}, {"$set": {"listino": f, "company_id": t["cid"]}, "$setOnInsert": {"alta_da": "06-01", "alta_a": "09-30", "aliquota": 22.0}}, upsert=True)
        return f

    @r.get("/pontili")
    async def pontili(t: dict = Depends(tenant)):
        return await db.porto_pontili.find({"company_id": t["cid"]}, {"_id": 0}).sort([("ordine", 1), ("nome", 1)]).to_list(500)

    @r.post("/pontili")
    async def add_pontile(body: PontileIn, t: dict = Depends(tenant)):
        doc = {"id": str(uuid.uuid4()), "company_id": t["cid"], **body.model_dump()}
        await db.porto_pontili.insert_one(dict(doc))
        doc.pop("_id", None)
        return doc

    @r.put("/pontili/{pid}")
    async def upd_pontile(pid: str, body: PontileIn, t: dict = Depends(tenant)):
        await _one("porto_pontili", t["cid"], pid, "Pontile non trovato")
        await db.porto_pontili.update_one({"id": pid, "company_id": t["cid"]}, {"$set": body.model_dump()})
        return await _one("porto_pontili", t["cid"], pid, "")

    @r.delete("/pontili/{pid}")
    async def del_pontile(pid: str, t: dict = Depends(tenant)):
        await _one("porto_pontili", t["cid"], pid, "Pontile non trovato")
        if await db.porto_posti.count_documents({"company_id": t["cid"], "pontile_id": pid}):
            raise HTTPException(400, "Il pontile ha ancora posti barca: eliminali o spostali prima")
        await db.porto_pontili.delete_one({"id": pid, "company_id": t["cid"]})
        return {"ok": True}

    @r.get("/posti")
    async def posti(t: dict = Depends(tenant)):
        ps = await db.porto_posti.find({"company_id": t["cid"]}, {"_id": 0}).to_list(5000)
        return sorted(ps, key=lambda p: (len(p["codice"]), p["codice"]))

    async def _check_posto(cid, body, pid=None):
        await _one("porto_pontili", cid, body.pontile_id, "Pontile non trovato")
        if await db.porto_posti.find_one({"company_id": cid, "codice": body.codice, **({"id": {"$ne": pid}} if pid else {})}, {"_id": 1}):
            raise ferr(409, "codice", f"Il codice posto {body.codice} esiste già")

    @r.post("/posti")
    async def add_posto(body: PostoIn, t: dict = Depends(tenant)):
        await _check_posto(t["cid"], body)
        doc = {"id": str(uuid.uuid4()), "company_id": t["cid"], **body.model_dump()}
        await db.porto_posti.insert_one(dict(doc))
        doc.pop("_id", None)
        return doc

    @r.post("/posti/serie")
    async def add_serie(body: SerieIn, t: dict = Depends(tenant)):
        cid = t["cid"]
        if body.a < body.da or body.a - body.da >= 300:
            raise HTTPException(422, "Intervallo non valido (massimo 300 posti alla volta)")
        await _one("porto_pontili", cid, body.pontile_id, "Pontile non trovato")
        codici = [f"{body.prefisso}{n}" for n in range(body.da, body.a + 1)]
        esist = {x["codice"] for x in await db.porto_posti.find({"company_id": cid, "codice": {"$in": codici}}, {"_id": 0, "codice": 1}).to_list(400)}
        nuovi = [{"id": str(uuid.uuid4()), "company_id": cid, "pontile_id": body.pontile_id, "codice": c, "lunghezza_max": body.lunghezza_max,
                  "larghezza_max": body.larghezza_max, "tipo": "mare", "fuori_servizio": False, "note": ""} for c in codici if c not in esist]
        if nuovi:
            await db.porto_posti.insert_many(nuovi)
        return {"creati": len(nuovi), "saltati": len(esist)}

    @r.put("/posti/{pid}")
    async def upd_posto(pid: str, body: PostoIn, t: dict = Depends(tenant)):
        await _one("porto_posti", t["cid"], pid, "Posto barca non trovato")
        await _check_posto(t["cid"], body, pid)
        await db.porto_posti.update_one({"id": pid, "company_id": t["cid"]}, {"$set": body.model_dump()})
        return await _one("porto_posti", t["cid"], pid, "")

    @r.delete("/posti/{pid}")
    async def del_posto(pid: str, t: dict = Depends(tenant)):
        q = {"company_id": t["cid"], "posto_id": pid}
        if await db.porto_contratti.count_documents(q) or await db.porto_transiti.count_documents(q):
            raise HTTPException(400, "Il posto ha contratti o transiti: mettilo fuori servizio invece di eliminarlo")
        await db.porto_posti.delete_one({"id": pid, "company_id": t["cid"]})
        return {"ok": True}

    # --- barche ---
    @r.get("/barche")
    async def barche(t: dict = Depends(tenant)):
        bs = await db.porto_barche.find({"company_id": t["cid"]}, {"_id": 0}).sort("nome", 1).to_list(10000)
        ids = list({b["party_id"] for b in bs})
        nomi = {p["id"]: p["denominazione"] for p in await db.parties.find({"company_id": t["cid"], "id": {"$in": ids}}, {"_id": 0, "id": 1, "denominazione": 1}).to_list(10000)}
        return [{**b, "armatore": nomi.get(b["party_id"], "")} for b in bs]

    async def _check_barca(cid, body):
        if not await db.parties.find_one({"id": body.party_id, "company_id": cid, "tipo": "cliente"}, {"_id": 1}):
            raise ferr(400, "party_id", "Seleziona l'armatore tra i clienti")

    @r.post("/barche")
    async def add_barca(body: BarcaIn, t: dict = Depends(tenant)):
        await _check_barca(t["cid"], body)
        doc = {"id": str(uuid.uuid4()), "company_id": t["cid"], **body.model_dump(), "created_at": now_iso()}
        await db.porto_barche.insert_one(dict(doc))
        doc.pop("_id", None)
        return doc

    @r.put("/barche/{bid}")
    async def upd_barca(bid: str, body: BarcaIn, t: dict = Depends(tenant)):
        await _one("porto_barche", t["cid"], bid, "Barca non trovata")
        await _check_barca(t["cid"], body)
        await db.porto_barche.update_one({"id": bid, "company_id": t["cid"]}, {"$set": body.model_dump()})
        return await _one("porto_barche", t["cid"], bid, "")

    @r.delete("/barche/{bid}")
    async def del_barca(bid: str, t: dict = Depends(tenant)):
        q = {"company_id": t["cid"], "barca.id": bid}
        if await db.porto_contratti.count_documents(q) or await db.porto_transiti.count_documents(q):
            raise HTTPException(400, "La barca ha contratti o transiti registrati e non può essere eliminata")
        await db.porto_barche.delete_one({"id": bid, "company_id": t["cid"]})
        return {"ok": True}

    # --- prezzi ---
    @r.get("/prezzo")
    async def prezzo(barca_id: str, da: str, a: str, tipo: Literal["transito", "annuale", "stagionale", "mensile"] = "transito", t: dict = Depends(tenant)):
        cfg = await _cfg(t["cid"])
        b = await _one("porto_barche", t["cid"], barca_id, "Barca non trovata")
        d1, d2 = _d(da), _d(a)
        if d2 < d1:
            raise HTTPException(422, "La data finale è prima di quella iniziale")
        imp = prezzo_transito(cfg, cfg.get("listino", []), b["lunghezza"], d1, d2) if tipo == "transito" else prezzo_contratto(cfg, cfg.get("listino", []), b["lunghezza"], tipo, d1, d2)
        return {"imponibile": imp, "aliquota": cfg.get("aliquota", 22.0), "totale": round(imp * (1 + cfg.get("aliquota", 22.0) / 100), 2)}

    # --- contratti ---
    @r.get("/contratti")
    async def contratti(stato: Optional[str] = None, t: dict = Depends(tenant)):
        return await db.porto_contratti.find({"company_id": t["cid"], **({"stato": stato} if stato else {})}, {"_id": 0}).sort([("anno", -1), ("numero", -1)]).to_list(5000)

    async def _prep_contratto(t, body: ContrattoIn, skip=None):
        cid = t["cid"]
        d1, d2 = _d(body.data_inizio), _d(body.data_fine)
        if d2 < d1:
            raise ferr(422, "data_fine", "La fine del contratto è prima dell'inizio")
        if (d2 - d1).days > 366 * 5:
            raise ferr(422, "data_fine", "Durata massima 5 anni")
        b, p, pa = await _barca_posto(cid, body.barca_id, body.posto_id)
        await _conflitto(cid, p["id"], d1, d2 + timedelta(days=1), skip, b["id"])
        cfg = await _cfg(cid)
        imp = body.importo if body.importo is not None else prezzo_contratto(cfg, cfg.get("listino", []), b["lunghezza"], body.tipo, d1, d2)
        if imp <= 0:
            raise ferr(422, "importo", "Importo del contratto non valido")
        return {**body.model_dump(exclude={"importo", "barca_id", "posto_id"}), **_snap(b, p, pa), "posto_id": p["id"], "importo": round(imp, 2),
                "occ_da": d1.isoformat(), "occ_a": (d2 + timedelta(days=1)).isoformat(), "rate": _rate(round(imp, 2), body.n_rate, d1, d2)}

    @r.post("/contratti")
    async def add_contratto(body: ContrattoIn, t: dict = Depends(tenant)):
        doc = await _prep_contratto(t, body)
        anno = int(body.data_inizio[:4])
        last = await db.porto_contratti.find_one({"company_id": t["cid"], "anno": anno}, {"_id": 0, "numero": 1}, sort=[("numero", -1)])
        doc |= {"id": str(uuid.uuid4()), "company_id": t["cid"], "anno": anno, "numero": (last["numero"] if last else 0) + 1, "stato": "attivo", "created_at": now_iso()}
        await db.porto_contratti.insert_one(dict(doc))
        doc.pop("_id", None)
        return doc

    @r.put("/contratti/{kid}")
    async def upd_contratto(kid: str, body: ContrattoIn, t: dict = Depends(tenant)):
        old = await _one("porto_contratti", t["cid"], kid, "Contratto non trovato")
        if any(x.get("fattura_id") for x in old["rate"]):
            raise HTTPException(400, "Contratto già fatturato in parte: non modificabile (puoi chiuderlo e farne uno nuovo)")
        doc = await _prep_contratto(t, body, kid)
        await db.porto_contratti.update_one({"id": kid, "company_id": t["cid"]}, {"$set": doc})
        return await _one("porto_contratti", t["cid"], kid, "")

    @r.post("/contratti/{kid}/chiudi")
    async def chiudi(kid: str, t: dict = Depends(tenant)):
        await _one("porto_contratti", t["cid"], kid, "Contratto non trovato")
        await db.porto_contratti.update_one({"id": kid, "company_id": t["cid"]}, {"$set": {"stato": "chiuso"}})
        return {"ok": True}

    @r.delete("/contratti/{kid}")
    async def del_contratto(kid: str, t: dict = Depends(tenant)):
        old = await _one("porto_contratti", t["cid"], kid, "Contratto non trovato")
        if any(x.get("fattura_id") for x in old["rate"]):
            raise HTTPException(400, "Contratto con rate già fatturate: puoi solo chiuderlo")
        await db.porto_contratti.delete_one({"id": kid, "company_id": t["cid"]})
        return {"ok": True}

    @r.get("/rate")
    async def rate_da_fatturare(fino_al: str, t: dict = Depends(tenant)):
        _d(fino_al)
        out = []
        async for k in db.porto_contratti.find({"company_id": t["cid"], "stato": "attivo", "rate": {"$elemMatch": {"fattura_id": None, "scadenza": {"$lte": fino_al}}}}, {"_id": 0}):
            for x in k["rate"]:
                if not x.get("fattura_id") and x["scadenza"] <= fino_al:
                    out.append({"contratto_id": k["id"], "contratto": f"{k['numero']}/{k['anno']}", "cliente": k["cliente"], "barca": k["barca"]["nome"],
                                "posto": k["posto"]["codice"], "rata": f"{x['n']}/{len(k['rate'])}", "n": x["n"], "scadenza": x["scadenza"], "importo": x["importo"]})
        return sorted(out, key=lambda x: (x["scadenza"], x["cliente"]))

    @r.post("/rate/fattura")
    async def fattura_rate(body: FatturaRateIn, t: dict = Depends(tenant)):
        _d(body.fino_al)
        q = {"company_id": t["cid"], "stato": "attivo", **({"id": {"$in": body.contratto_ids}} if body.contratto_ids else {})}
        res = {"create": [], "errori": []}
        async for k in db.porto_contratti.find(q, {"_id": 0}):
            for x in k["rate"]:
                if x.get("fattura_id") or x["scadenza"] > body.fino_al:
                    continue
                lock = await db.porto_contratti.update_one({"id": k["id"], "company_id": t["cid"], "rate": {"$elemMatch": {"n": x["n"], "fattura_id": None}}},
                                                          {"$set": {"rate.$.fattura_id": "in_corso"}})
                if not lock.modified_count:
                    continue
                descr = (f"Ormeggio {k['tipo']} posto {k['posto']['codice']} - {k['barca']['nome']} ({k['barca']['lunghezza']:g} m) - "
                         f"contratto {k['numero']}/{k['anno']} dal {k['data_inizio']} al {k['data_fine']} - rata {x['n']}/{len(k['rate'])}")
                try:
                    inv = await _fattura(t, k["party_id"], descr, x["importo"], x["scadenza"], f"Contratto di ormeggio {k['numero']}/{k['anno']}")
                except HTTPException as e:
                    await db.porto_contratti.update_one({"id": k["id"], "rate.n": x["n"]}, {"$set": {"rate.$.fattura_id": None}})
                    res["errori"].append(f"{k['cliente']} rata {x['n']}: {e.detail}")
                    continue
                await db.porto_contratti.update_one({"id": k["id"], "rate.n": x["n"]}, {"$set": {"rate.$.fattura_id": inv["id"], "rate.$.fattura_numero": inv.get("numero_display")}})
                res["create"].append({"fattura_id": inv["id"], "numero": inv.get("numero_display"), "cliente": k["cliente"], "totale": inv.get("totale")})
        return res

    # --- transiti ---
    @r.get("/transiti")
    async def transiti(stato: Optional[str] = None, t: dict = Depends(tenant)):
        return await db.porto_transiti.find({"company_id": t["cid"], **({"stato": stato} if stato else {})}, {"_id": 0}).sort("arrivo", -1).to_list(5000)

    async def _prep_transito(t, body: TransitoIn, skip=None):
        d1, d2 = _d(body.arrivo), _d(body.partenza_prevista)
        if d2 <= d1:
            raise ferr(422, "partenza_prevista", "La partenza deve essere dopo l'arrivo")
        b, p, pa = await _barca_posto(t["cid"], body.barca_id, body.posto_id)
        await _conflitto(t["cid"], p["id"], d1, d2, skip, b["id"])
        return {**body.model_dump(exclude={"barca_id", "posto_id"}), **_snap(b, p, pa), "posto_id": p["id"], "occ_da": d1.isoformat(), "occ_a": d2.isoformat()}

    @r.post("/transiti")
    async def add_transito(body: TransitoIn, t: dict = Depends(tenant)):
        doc = await _prep_transito(t, body)
        doc |= {"id": str(uuid.uuid4()), "company_id": t["cid"], "stato": "presente", "partenza": None, "importo": None, "fattura_id": None, "created_at": now_iso()}
        await db.porto_transiti.insert_one(dict(doc))
        doc.pop("_id", None)
        return doc

    @r.put("/transiti/{tid}")
    async def upd_transito(tid: str, body: TransitoIn, t: dict = Depends(tenant)):
        old = await _one("porto_transiti", t["cid"], tid, "Transito non trovato")
        if old["stato"] != "presente":
            raise HTTPException(400, "Transito già chiuso: non modificabile")
        doc = await _prep_transito(t, body, tid)
        await db.porto_transiti.update_one({"id": tid, "company_id": t["cid"]}, {"$set": doc})
        return await _one("porto_transiti", t["cid"], tid, "")

    @r.delete("/transiti/{tid}")
    async def del_transito(tid: str, t: dict = Depends(tenant)):
        old = await _one("porto_transiti", t["cid"], tid, "Transito non trovato")
        if old.get("fattura_id"):
            raise HTTPException(400, "Transito già fatturato: non eliminabile")
        await db.porto_transiti.delete_one({"id": tid, "company_id": t["cid"]})
        return {"ok": True}

    @r.post("/transiti/{tid}/partenza")
    async def partenza(tid: str, body: PartenzaIn, t: dict = Depends(tenant)):
        cid = t["cid"]
        tr = await _one("porto_transiti", cid, tid, "Transito non trovato")
        if tr["stato"] != "presente":
            raise HTTPException(400, "Partenza già registrata")
        d1, d2 = _d(tr["arrivo"]), _d(body.partenza)
        if d2 < d1:
            raise ferr(422, "partenza", "La partenza è prima dell'arrivo")
        if d2 > date.today():
            raise ferr(422, "partenza", "La partenza non può essere futura")
        if d2 > _d(tr["occ_a"]):
            await _conflitto(cid, tr["posto_id"], _d(tr["occ_a"]), d2, tid, tr["barca"]["id"])
        cfg = await _cfg(cid)
        imp = body.importo if body.importo is not None else prezzo_transito(cfg, cfg.get("listino", []), tr["barca"]["lunghezza"], d1, d2)
        lock = await db.porto_transiti.update_one({"id": tid, "company_id": cid, "stato": "presente"}, {"$set": {"stato": "in_fatturazione"}})
        if not lock.modified_count:
            raise HTTPException(409, "Partenza già in registrazione")
        notti = max((d2 - d1).days, 1)
        try:
            inv = await _fattura(t, tr["party_id"], f"Transito posto {tr['posto']['codice']} - {tr['barca']['nome']} ({tr['barca']['lunghezza']:g} m) - dal {tr['arrivo']} al {body.partenza} ({notti} notti)",
                                 round(imp, 2), body.partenza, "Ormeggio in transito") if imp > 0 else None
        except HTTPException:
            await db.porto_transiti.update_one({"id": tid}, {"$set": {"stato": "presente"}})
            raise
        upd = {"stato": "partito", "partenza": body.partenza, "occ_a": d2.isoformat(), "importo": round(imp, 2),
               "fattura_id": inv["id"] if inv else None, "fattura_numero": inv.get("numero_display") if inv else None}
        await db.porto_transiti.update_one({"id": tid}, {"$set": upd})
        return {**tr, **upd}

    # --- viste ---
    async def _occupazioni(cid, da: str, a_excl: str):
        return [{"id": x["id"], "tipo": tipo, "posto_id": x["posto_id"], "da": x["occ_da"], "a": x["occ_a"], "barca": x["barca"]["nome"],
                 "lunghezza": x["barca"]["lunghezza"], "cliente": x["cliente"], "stato": x["stato"]} for tipo, x in await _sovrapposti(cid, {}, da, a_excl)]

    @r.get("/mappa")
    async def mappa(data: Optional[str] = None, t: dict = Depends(tenant)):
        cid = t["cid"]
        d = _d(data) if data else date.today()
        occ = await _occupazioni(cid, d.isoformat(), (d + timedelta(days=1)).isoformat())
        by = {}
        for o in sorted(occ, key=lambda o: o["tipo"] != "transito"):
            by.setdefault(o["posto_id"], o)
        pont = await db.porto_pontili.find({"company_id": cid}, {"_id": 0}).sort([("ordine", 1), ("nome", 1)]).to_list(500)
        posti = await db.porto_posti.find({"company_id": cid}, {"_id": 0}).to_list(5000)
        posti.sort(key=lambda p: (len(p["codice"]), p["codice"]))
        for p in posti:
            o = by.get(p["id"])
            p["stato"] = "fuori_servizio" if p.get("fuori_servizio") else (o["tipo"] if o else "libero")
            p["occupazione"] = o
        cont = {s: sum(1 for p in posti if p["stato"] == s) for s in ("libero", "contratto", "transito", "fuori_servizio")}
        return {"data": d.isoformat(), "conteggi": cont, "pontili": [{**x, "posti": [p for p in posti if p["pontile_id"] == x["id"]]} for x in pont]}

    @r.get("/planning")
    async def planning(da: str, giorni: int = 31, t: dict = Depends(tenant)):
        d = _d(da)
        giorni = max(7, min(giorni, 92))
        posti = await db.porto_posti.find({"company_id": t["cid"]}, {"_id": 0, "id": 1, "codice": 1, "pontile_id": 1, "lunghezza_max": 1, "fuori_servizio": 1}).to_list(5000)
        pont = {x["id"]: x for x in await db.porto_pontili.find({"company_id": t["cid"]}, {"_id": 0}).to_list(500)}
        posti.sort(key=lambda p: (pont.get(p["pontile_id"], {}).get("ordine", 0), pont.get(p["pontile_id"], {}).get("nome", ""), len(p["codice"]), p["codice"]))
        for p in posti:
            p["pontile"] = pont.get(p["pontile_id"], {}).get("nome", "")
        occ = await _occupazioni(t["cid"], d.isoformat(), (d + timedelta(days=giorni)).isoformat())
        return {"da": d.isoformat(), "giorni": giorni, "posti": posti, "occupazioni": occ}

    # --- piantina interattiva ---
    @r.get("/piantina/info")
    async def piantina_info(t: dict = Depends(tenant)):
        x = await db.porto_piantina.find_one({"company_id": t["cid"]}, {"_id": 0, "data": 0, "company_id": 0})
        return x or {"presente": False}

    @r.get("/piantina/immagine")
    async def piantina_img(t: dict = Depends(tenant)):
        x = await db.porto_piantina.find_one({"company_id": t["cid"]}, {"_id": 0})
        if not x:
            raise HTTPException(404, "Nessuna piantina caricata")
        return Response(base64.b64decode(x["data"]), media_type=x["mime"])

    @r.post("/piantina")
    async def piantina_upload(file: UploadFile = File(...), t: dict = Depends(tenant)):
        raw = await file.read(IMG_MAX + 1)
        if len(raw) > IMG_MAX:
            raise HTTPException(413, "Immagine troppo grande (massimo 5 MB)")
        sig = {b"\x89PNG": "image/png", b"\xff\xd8\xff": "image/jpeg"}
        mime = next((m for k, m in sig.items() if raw.startswith(k)), "image/webp" if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP" else None)
        if not mime:
            raise HTTPException(415, "Formato non supportato: usa PNG, JPG o WEBP")
        doc = {"company_id": t["cid"], "mime": mime, "data": base64.b64encode(raw).decode(), "nome": (file.filename or "piantina")[:120],
               "dimensione": len(raw), "presente": True, "updated_at": datetime.now(timezone.utc).isoformat()}
        await db.porto_piantina.update_one({"company_id": t["cid"]}, {"$set": doc}, upsert=True)
        return {k: v for k, v in doc.items() if k not in ("data", "company_id")}

    @r.delete("/piantina")
    async def piantina_del(t: dict = Depends(tenant)):
        await db.porto_piantina.delete_one({"company_id": t["cid"]})
        await db.porto_posti.update_many({"company_id": t["cid"]}, {"$unset": {"pos": ""}})
        return {"ok": True}

    @r.post("/piantina/disponi")
    async def disponi(body: DisponiIn, t: dict = Depends(tenant)):
        cid = t["cid"]
        ids = list(dict.fromkeys(body.posto_ids))
        if await db.porto_posti.count_documents({"company_id": cid, "id": {"$in": ids}}) != len(ids):
            raise HTTPException(404, "Alcuni posti non esistono")
        k = len(ids)
        for i, pid in enumerate(ids):
            f = 0.5 if k == 1 else i / (k - 1)
            await db.porto_posti.update_one({"id": pid, "company_id": cid}, {"$set": {"pos": {"x": round(body.x1 + (body.x2 - body.x1) * f, 5), "y": round(body.y1 + (body.y2 - body.y1) * f, 5)}}})
        return {"posizionati": k}

    @r.put("/posti/{pid}/pos")
    async def set_pos(pid: str, body: PosIn, t: dict = Depends(tenant)):
        res = await db.porto_posti.update_one({"id": pid, "company_id": t["cid"]}, {"$set": {"pos": body.model_dump()}})
        if not res.matched_count:
            raise HTTPException(404, "Posto barca non trovato")
        return body.model_dump()

    @r.delete("/posti/{pid}/pos")
    async def del_pos(pid: str, t: dict = Depends(tenant)):
        res = await db.porto_posti.update_one({"id": pid, "company_id": t["cid"]}, {"$unset": {"pos": ""}})
        if not res.matched_count:
            raise HTTPException(404, "Posto barca non trovato")
        return {"ok": True}

    return r

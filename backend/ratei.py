import uuid
from datetime import date, datetime, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import contabilita as coge
from contabilita_dati import tipo_conto

DATE_RX = r"^\d{4}-\d{2}-\d{2}$"
NOMI = {("acquisto", "risconto"): "Risconto attivo", ("acquisto", "rateo"): "Rateo passivo",
        ("vendita", "risconto"): "Risconto passivo", ("vendita", "rateo"): "Rateo attivo"}
RUOLO = {("acquisto", "risconto"): "risconti_attivi", ("acquisto", "rateo"): "ratei_passivi",
         ("vendita", "risconto"): "risconti_passivi", ("vendita", "rateo"): "ratei_attivi"}


def _now():
    return datetime.now(timezone.utc).isoformat()


class RateoIn(BaseModel):
    competenza_dal: str = Field(pattern=DATE_RX)
    competenza_al: str = Field(pattern=DATE_RX)
    tipo: Literal["rateo", "risconto"]
    note: Optional[str] = Field(default="", max_length=300)


class RigaRR(BaseModel):
    conto: str = Field(min_length=1, max_length=20)
    importo: float = Field(ge=-100_000_000, le=100_000_000)


class ManualeIn(RateoIn):
    origine: Literal["acquisto", "vendita"]
    party_id: str = Field(min_length=1, max_length=40)
    documento: str = Field(min_length=1, max_length=40)
    data_documento: str = Field(pattern=DATE_RX)
    data_registrazione: str = Field(pattern=DATE_RX)
    righe: List[RigaRR] = Field(min_length=1, max_length=20)


class ContabIn(BaseModel):
    anno: int = Field(ge=2000, le=2100)
    definitiva: bool = False
    ids: Optional[List[str]] = None


class AnnullaIn(BaseModel):
    anno: int = Field(ge=2000, le=2100)
    ids: Optional[List[str]] = None


def proponi(data_reg: str, dal: str, al: str) -> Optional[str]:
    y = data_reg[:4]
    if al > f"{y}-12-31":
        return "risconto"
    if dal < f"{y}-01-01":
        return "rateo"
    return None


def valida(x: RateoIn, ferr, data_reg: Optional[str] = None):
    try:
        d1, d2 = date.fromisoformat(x.competenza_dal), date.fromisoformat(x.competenza_al)
    except ValueError:
        raise ferr(422, "competenza_dal", "Data di competenza non valida")
    if d2 < d1:
        raise ferr(422, "competenza_al", "La fine competenza non può precedere l'inizio")
    if (d2 - d1).days > 366 * 10:
        raise ferr(422, "competenza_al", "Periodo di competenza troppo lungo (massimo 10 anni)")
    if data_reg and not anni({"data_registrazione": data_reg, **x.model_dump()}):
        p = proponi(data_reg, x.competenza_dal, x.competenza_al)
        raise ferr(422, "tipo", f"Con queste date serve un {p}" if p else "La competenza è tutta nell'esercizio di registrazione: non serve rateo né risconto")


def anni(rr: dict) -> list:
    r, y1, y2 = int(rr["data_registrazione"][:4]), int(rr["competenza_dal"][:4]), int(rr["competenza_al"][:4])
    return list(range(r, y2)) if rr["tipo"] == "risconto" else list(range(y1, r))


def quota(rr: dict, anno: int) -> dict:
    d1, d2 = date.fromisoformat(rr["competenza_dal"]), date.fromisoformat(rr["competenza_al"])
    tot = (d2 - d1).days + 1
    if anno not in anni(rr):
        return {"giorni": 0, "giorni_totali": tot, "righe": [], "importo": 0.0}
    if rr["tipo"] == "risconto":
        a, b = max(d1, date(anno + 1, 1, 1)), d2
    else:
        a, b = d1, min(d2, date(anno, 12, 31))
    g = max((b - a).days + 1, 0)
    righe = [{"conto": x["conto"], "importo": coge.r2(x["importo"] * g / tot)} for x in rr["righe"]]
    return {"giorni": g, "giorni_totali": tot, "righe": righe, "importo": coge.r2(sum(x["importo"] for x in righe))}


async def da_registrazione(db, cid: str, origine: str, doc: dict, body: RateoIn, by: str):
    e = await db.coa_entries.find_one({"company_id": cid, "origine": origine, "ref_id": doc["id"]}, {"_id": 0})
    if not e:
        return None
    k = "costo" if origine == "acquisto" else "ricavo"
    righe = {}
    for x in e["righe"]:
        if tipo_conto(x["conto"]) == k:
            v = x["dare"] - x["avere"] if k == "costo" else x["avere"] - x["dare"]
            righe[x["conto"]] = righe.get(x["conto"], 0) + v
    righe = [{"conto": c, "importo": coge.r2(v)} for c, v in righe.items() if coge.r2(v)]
    if not righe:
        return None
    party = doc.get("fornitore" if origine == "acquisto" else "cliente") or {}
    cur = await db.ratei_risconti.find_one({"company_id": cid, "doc_id": doc["id"]}, {"_id": 0})
    if cur and any(c["stato"] == "definitiva" for c in (cur.get("contabilizzazioni") or {}).values()):
        raise HTTPException(400, "Il rateo/risconto del documento è già contabilizzato in definitiva: annullalo prima da Ratei e risconti")
    if cur:
        await _togli(db, cid, cur, None)
    rr = {"id": (cur or {}).get("id") or str(uuid.uuid4()), "company_id": cid, "origine": origine, "doc_id": doc["id"], "party_id": doc.get("party_id"),
          "party_nome": party.get("denominazione") or "", "documento": doc.get("numero_display") or doc.get("numero") or "", "data_documento": doc["data"],
          "data_registrazione": e["data"], **body.model_dump(), "righe": righe, "contabilizzazioni": {}, "created_by": by, "created_at": _now()}
    await db.ratei_risconti.replace_one({"company_id": cid, "id": rr["id"]}, rr, upsert=True)
    return rr


async def _togli(db, cid: str, rr: dict, anno: Optional[int]):
    cont = rr.get("contabilizzazioni") or {}
    keys = [str(anno)] if anno is not None else list(cont)
    for k in keys:
        c = cont.get(k)
        if not c:
            continue
        await db.coa_entries.delete_many({"company_id": cid, "id": {"$in": c.get("entry_ids") or []}})
        cont.pop(k, None)
    await db.ratei_risconti.update_one({"company_id": cid, "id": rr["id"]}, {"$set": {"contabilizzazioni": cont}})


async def check_elimina_doc(db, cid: str, doc_id: str):
    rr = await db.ratei_risconti.find_one({"company_id": cid, "doc_id": doc_id}, {"_id": 0})
    if rr and any(c["stato"] == "definitiva" for c in (rr.get("contabilizzazioni") or {}).values()):
        raise HTTPException(400, "Il documento ha un rateo/risconto contabilizzato in definitiva: annullalo prima da Ratei e risconti")
    return rr


async def elimina_doc(db, cid: str, doc_id: str):
    rr = await check_elimina_doc(db, cid, doc_id)
    if rr:
        await _togli(db, cid, rr, None)
        await db.ratei_risconti.delete_one({"company_id": cid, "id": rr["id"]})


def build(db, tenant, tenant_accounting, deps) -> APIRouter:
    r = APIRouter(prefix="/api/contabilita/ratei")
    ferr = deps["ferr"]

    def _view(rr: dict, anno: int) -> dict:
        q = quota(rr, anno)
        c = (rr.get("contabilizzazioni") or {}).get(str(anno))
        return {**rr, "nome_tipo": NOMI[(rr["origine"], rr["tipo"])], "importo": coge.r2(sum(x["importo"] for x in rr["righe"])), "anni": anni(rr),
                "quota": q, "stato": (c or {}).get("stato") or ("da_contabilizzare" if q["giorni"] else "non_dovuto"),
                "definitive": sorted(int(k) for k, v in (rr.get("contabilizzazioni") or {}).items() if v["stato"] == "definitiva")}

    async def _get(cid, rid):
        rr = await db.ratei_risconti.find_one({"company_id": cid, "id": rid}, {"_id": 0})
        if not rr:
            raise HTTPException(404, "Rateo/risconto non trovato")
        return rr

    def _no_def(rr):
        d = [k for k, v in (rr.get("contabilizzazioni") or {}).items() if v["stato"] == "definitiva"]
        if d:
            raise HTTPException(400, f"Contabilizzato in definitiva per il {', '.join(sorted(d))}: annulla prima la contabilizzazione")

    @r.get("")
    async def lista(anno: int, t: dict = Depends(tenant)):
        rows = await db.ratei_risconti.find({"company_id": t["cid"]}, {"_id": 0}).sort([("data_registrazione", -1)]).to_list(5000)
        return [_view(x, anno) for x in rows]

    @r.get("/proposta")
    async def proposta(data_registrazione: str, competenza_dal: str, competenza_al: str, t: dict = Depends(tenant)):
        return {"tipo": proponi(data_registrazione, competenza_dal, competenza_al)}

    @r.post("")
    async def crea(body: ManualeIn, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        valida(body, ferr, body.data_registrazione)
        if any(not coge.r2(x.importo) for x in body.righe):
            raise ferr(422, "righe", "Indica un importo diverso da zero su ogni conto")
        ruolo = "fornitore" if body.origine == "acquisto" else "cliente"
        p = await db.parties.find_one({"company_id": cid, "id": body.party_id, "tipo": ruolo}, {"_id": 0, "denominazione": 1})
        if not p:
            raise ferr(422, "party_id", f"Seleziona un {ruolo}")
        k = "costo" if body.origine == "acquisto" else "ricavo"
        accs = {a["codice"] for a in await db.coa_accounts.find({"company_id": cid, "livello": 3, "codice": {"$in": [x.conto for x in body.righe]}}, {"_id": 0, "codice": 1}).to_list(50)}
        for i, x in enumerate(body.righe):
            if x.conto not in accs or tipo_conto(x.conto) != k:
                raise ferr(422, f"righe.{i}.conto", f"Riga {i + 1}: scegli un sottoconto di {k}")
        rr = {"id": str(uuid.uuid4()), "company_id": cid, "doc_id": None, **body.model_dump(), "party_nome": p["denominazione"],
              "righe": [x.model_dump() for x in body.righe], "contabilizzazioni": {}, "created_by": t["user"].get("name") or t["user"]["email"], "created_at": _now()}
        await db.ratei_risconti.insert_one(dict(rr))
        return _view(rr, int(body.data_registrazione[:4]))

    @r.put("/{rid}")
    async def modifica(rid: str, body: RateoIn, anno: int, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        rr = await _get(cid, rid)
        valida(body, ferr, rr["data_registrazione"])
        _no_def(rr)
        await _togli(db, cid, rr, None)
        await db.ratei_risconti.update_one({"company_id": cid, "id": rid}, {"$set": {**body.model_dump(), "updated_at": _now()}})
        return _view(await _get(cid, rid), anno)

    @r.delete("/{rid}")
    async def elimina(rid: str, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        rr = await _get(cid, rid)
        _no_def(rr)
        await _togli(db, cid, rr, None)
        await db.ratei_risconti.delete_one({"company_id": cid, "id": rid})
        return {"ok": True}

    @r.post("/contabilizza")
    async def contabilizza(body: ContabIn, t: dict = Depends(tenant_accounting)):
        cid, y = t["cid"], body.anno
        await coge.check_aperto(db, cid, y)
        await coge.check_aperto(db, cid, y + 1)
        p = coge.params_of(await coge._company(db, cid))
        f = {"company_id": cid, **({"id": {"$in": body.ids}} if body.ids is not None else {})}
        fatte, errori, by = 0, [], t["user"].get("name") or t["user"]["email"]
        async for rr in db.ratei_risconti.find(f, {"_id": 0}):
            q = quota(rr, y)
            c = (rr.get("contabilizzazioni") or {}).get(str(y))
            if not q["giorni"] or (c and c["stato"] == "definitiva"):
                continue
            await _togli(db, cid, rr, y)
            rr = await _get(cid, rr["id"])
            conto = p.get(RUOLO[(rr["origine"], rr["tipo"])])
            sg = 1 if (rr["origine"] == "acquisto") == (rr["tipo"] == "risconto") else -1
            chi = [{"conto": conto, "dare": sg * q["importo"], "party_id": None}] + [{"conto": x["conto"], "avere": sg * x["importo"]} for x in q["righe"]]
            sto = [{"conto": x["conto"], "dare": sg * x["importo"]} for x in q["righe"]] + [{"conto": conto, "avere": sg * q["importo"]}]
            nome = NOMI[(rr["origine"], rr["tipo"])]
            descr = f"{nome} {rr['documento']} {rr['party_nome']} ({q['giorni']}/{q['giorni_totali']} gg)"
            extra = {"documento": rr["documento"], "data_documento": rr["data_documento"], "party_id": rr.get("party_id"), "provvisoria": not body.definitiva}
            ids = []
            try:
                e1 = await coge._insert(db, cid, p, f"{y}-12-31", "RR", descr, chi, "ratei", f"{rr['id']}:{y}:c", extra, by=by)
                ids.append(e1["id"])
                e2 = await coge._insert(db, cid, p, f"{y + 1}-01-01", "RR", f"Storno {descr}", sto, "ratei", f"{rr['id']}:{y}:s", extra, by=by)
                ids.append(e2["id"])
            except (ValueError, TypeError) as ex:
                await db.coa_entries.delete_many({"company_id": cid, "id": {"$in": ids}})
                errori.append(f"{rr['documento']}: {ex}")
                continue
            await db.ratei_risconti.update_one({"company_id": cid, "id": rr["id"]}, {"$set": {f"contabilizzazioni.{y}": {
                "stato": "definitiva" if body.definitiva else "simulata", "importo": q["importo"], "giorni": q["giorni"], "entry_ids": ids, "at": _now(), "by": by}}})
            fatte += 1
        return {"contabilizzati": fatte, "errori": errori[:20]}

    @r.post("/annulla")
    async def annulla(body: AnnullaIn, t: dict = Depends(tenant_accounting)):
        cid, y = t["cid"], body.anno
        f = {"company_id": cid, f"contabilizzazioni.{y}": {"$exists": True}, **({"id": {"$in": body.ids}} if body.ids is not None else {})}
        rows = await db.ratei_risconti.find(f, {"_id": 0}).to_list(5000)
        if any(x["contabilizzazioni"][str(y)]["stato"] == "definitiva" for x in rows):
            await coge.check_aperto(db, cid, y)
            await coge.check_aperto(db, cid, y + 1)
        for rr in rows:
            await _togli(db, cid, rr, y)
        return {"annullati": len(rows)}

    return r

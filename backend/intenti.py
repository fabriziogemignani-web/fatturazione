import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

DATE_RX = r"^\d{4}-\d{2}-\d{2}$"
SOGLIA_AVVISO = 0.10


def _now():
    return datetime.now(timezone.utc).isoformat()


def _eur(v):
    return f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def imponibile_n35(riepilogo: list) -> float:
    return round(sum(r.get("imponibile") or 0 for r in riepilogo or [] if r.get("natura") == "N3.5"), 2)


class IntentoIn(BaseModel):
    party_id: str = Field(min_length=1, max_length=40)
    protocollo: str = Field(pattern=r"^\d{17}-\d{6}$")
    data: str = Field(pattern=DATE_RX)
    anno: int = Field(ge=2020, le=2100)
    importo: float = Field(gt=0, le=1_000_000_000)
    verificata: bool = False
    revocata: bool = False
    note: Optional[str] = Field(default="", max_length=300)

    @field_validator("protocollo", mode="before")
    @classmethod
    def _p(cls, v):
        return (v or "").strip().replace("/", "-")

    @field_validator("data")
    @classmethod
    def _d(cls, v):
        date.fromisoformat(v)
        return v


def build(db, tenant, ferr):
    r = APIRouter(prefix="/api/intenti")

    async def usato(cid: str, ids: list, exclude_iid: Optional[str] = None) -> dict:
        out = {i: 0.0 for i in ids}
        q = {"company_id": cid, "intento.id": {"$in": ids}, "status": {"$ne": "scartata"}, **({"id": {"$ne": exclude_iid}} if exclude_iid else {})}
        for inv in await db.invoices.find(q, {"_id": 0, "intento.id": 1, "riepilogo": 1, "tipo_documento": 1}).to_list(50000):
            s = -1 if inv.get("tipo_documento") == "TD04" else 1
            out[inv["intento"]["id"]] = round(out[inv["intento"]["id"]] + s * imponibile_n35(inv.get("riepilogo")), 2)
        return out

    async def _list(cid: str, q: dict) -> list:
        rows = await db.intenti.find({"company_id": cid, **q}, {"_id": 0}).sort([("anno", -1), ("data", 1)]).to_list(5000)
        u = await usato(cid, [x["id"] for x in rows])
        for x in rows:
            x["utilizzato"] = u[x["id"]]
            x["residuo"] = round(x["importo"] - x["utilizzato"], 2)
            x["percentuale_residua"] = round(x["residuo"] / x["importo"] * 100, 1) if x["importo"] else 0
        return rows

    async def scegli(cid: str, party: dict, data: str, imponibile: float, exclude_iid: Optional[str] = None, nc: bool = False) -> Optional[dict]:
        decl = [x for x in await _list(cid, {"party_id": party["id"], "revocata": False, "anno": int(data[:4]), "data": {"$lte": data}})]
        if not decl:
            if party.get("intento_protocollo") and not await db.intenti.find_one({"company_id": cid, "party_id": party["id"]}, {"_id": 1}):
                return {"id": None, "protocollo": party["intento_protocollo"], "data": party["intento_data"]}
            raise ferr(422, "party_id", f"Natura N3.5: registra nell'anagrafica del cliente una dichiarazione d'intento valida per il {data[:4]} con data non successiva alla fattura")
        if exclude_iid:
            u = await usato(cid, [x["id"] for x in decl], exclude_iid)
            for x in decl:
                x["residuo"] = round(x["importo"] - u[x["id"]], 2)
        ok = decl[0] if nc else next((x for x in decl if x["residuo"] + 0.005 >= imponibile), None)
        if not ok:
            best = max(decl, key=lambda x: x["residuo"])
            raise ferr(422, "lines", f"Plafond superato: la dichiarazione d'intento prot. {best['protocollo']} ha un residuo di {_eur(max(best['residuo'], 0))}, "
                                     f"la fattura ne usa {_eur(imponibile)}. Riduci l'importo non imponibile o applica l'IVA sull'eccedenza")
        return {"id": ok["id"], "protocollo": ok["protocollo"], "data": ok["data"]}

    async def _check_party(cid, pid):
        if not await db.parties.find_one({"id": pid, "company_id": cid, "tipo": "cliente"}, {"_id": 1}):
            raise ferr(400, "party_id", "Cliente non trovato")

    @r.get("")
    async def lista(party_id: Optional[str] = None, t: dict = Depends(tenant)):
        return await _list(t["cid"], {"party_id": party_id} if party_id else {})

    @r.get("/avvisi")
    async def avvisi(t: dict = Depends(tenant)):
        anno = datetime.now(timezone.utc).year
        rows = [x for x in await _list(t["cid"], {"revocata": False, "anno": {"$gte": anno}}) if x["residuo"] <= x["importo"] * SOGLIA_AVVISO]
        names = {p["id"]: p["denominazione"] for p in await db.parties.find({"company_id": t["cid"], "id": {"$in": [x["party_id"] for x in rows]}}, {"_id": 0, "id": 1, "denominazione": 1}).to_list(5000)}
        return [x | {"cliente": names.get(x["party_id"], "")} for x in sorted(rows, key=lambda x: x["percentuale_residua"])]

    @r.post("")
    async def crea(body: IntentoIn, t: dict = Depends(tenant)):
        await _check_party(t["cid"], body.party_id)
        if await db.intenti.find_one({"company_id": t["cid"], "protocollo": body.protocollo}, {"_id": 1}):
            raise ferr(400, "protocollo", "Dichiarazione con questo protocollo già registrata")
        doc = {"id": str(uuid.uuid4()), "company_id": t["cid"], **body.model_dump(), "created_at": _now()}
        await db.intenti.insert_one(doc)
        return (await _list(t["cid"], {"id": doc["id"]}))[0]

    @r.put("/{iid}")
    async def modifica(iid: str, body: IntentoIn, t: dict = Depends(tenant)):
        cur = (await _list(t["cid"], {"id": iid}) or [None])[0]
        if not cur:
            raise HTTPException(404, "Dichiarazione non trovata")
        if cur["utilizzato"] and (body.protocollo != cur["protocollo"] or body.party_id != cur["party_id"]):
            raise ferr(400, "protocollo", "Dichiarazione già usata in fattura: protocollo e cliente non sono modificabili")
        if body.importo + 0.005 < cur["utilizzato"]:
            raise ferr(400, "importo", f"Il plafond non può essere inferiore a quanto già fatturato ({_eur(cur['utilizzato'])})")
        if await db.intenti.find_one({"company_id": t["cid"], "protocollo": body.protocollo, "id": {"$ne": iid}}, {"_id": 1}):
            raise ferr(400, "protocollo", "Dichiarazione con questo protocollo già registrata")
        await db.intenti.update_one({"id": iid, "company_id": t["cid"]}, {"$set": body.model_dump() | {"updated_at": _now()}})
        return (await _list(t["cid"], {"id": iid}))[0]

    @r.delete("/{iid}")
    async def elimina(iid: str, t: dict = Depends(tenant)):
        if await db.invoices.find_one({"company_id": t["cid"], "intento.id": iid}, {"_id": 1}):
            raise HTTPException(400, "Dichiarazione usata in una o più fatture: puoi solo segnarla come revocata")
        await db.intenti.delete_one({"id": iid, "company_id": t["cid"]})
        return {"ok": True}

    return r, scegli

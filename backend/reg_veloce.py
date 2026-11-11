import asyncio
import uuid
from datetime import date, datetime, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

import contabilita as coge
from intenti import imponibile_n35

DATE_RX = r"^\d{4}-\d{2}-\d{2}$"
TIPI = {"vendita": ("cliente", "TD01"), "nc_vendita": ("cliente", "TD04"), "acquisto": ("fornitore", "TD01"), "nc_acquisto": ("fornitore", "TD04")}


def _now():
    return datetime.now(timezone.utc).isoformat()


def scorporo(righe: list) -> list:
    out = []
    for x in righe:
        imp = round(x["totale"] / (1 + x["aliquota"] / 100), 2)
        out.append({"aliquota": x["aliquota"], "natura": x.get("natura") or None, "imponibile": imp, "imposta": round(x["totale"] - imp, 2)})
    return out


class RigaIn(BaseModel):
    aliquota: float
    natura: Optional[str] = None
    totale: float = Field(gt=0, le=100_000_000)


class RegIn(BaseModel):
    tipo: Literal["vendita", "nc_vendita", "acquisto", "nc_acquisto"]
    party_id: str = Field(min_length=1, max_length=40)
    numero: str = Field(min_length=1, max_length=20)
    data_documento: str = Field(pattern=DATE_RX)
    data_registrazione: str = Field(pattern=DATE_RX)
    scadenza: Optional[str] = Field(default="", pattern=r"^(\d{4}-\d{2}-\d{2})?$")
    righe: List[RigaIn] = Field(min_length=1, max_length=10)

    @field_validator("numero")
    @classmethod
    def _num(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Inserisci il numero del documento")
        return v


def build(db, tenant_accounting, deps) -> APIRouter:
    r = APIRouter(prefix="/api/reg-veloce")
    ferr, aliquote, nature = deps["ferr"], deps["aliquote"], deps["nature"]

    def _valida(body: RegIn):
        for i, x in enumerate(body.righe):
            if x.aliquota not in aliquote:
                raise ferr(422, f"righe.{i}.aliquota", "Aliquota IVA non valida")
            if x.aliquota == 0 and x.natura not in nature:
                raise ferr(422, f"righe.{i}.natura", "Indica la Natura IVA per l'aliquota 0%")
            if x.aliquota:
                x.natura = None
        try:
            dd, dr = date.fromisoformat(body.data_documento), date.fromisoformat(body.data_registrazione)
            sc = date.fromisoformat(body.scadenza) if body.scadenza else dd
        except ValueError:
            raise ferr(422, "data_documento", "Data non valida")
        if dr < dd:
            raise ferr(422, "data_registrazione", "La data di registrazione non può precedere la data del documento")
        if sc < dd:
            raise ferr(422, "scadenza", "La scadenza non può precedere la data del documento")
        return sc.isoformat()

    @r.post("/anteprima")
    async def anteprima(body: RegIn, t: dict = Depends(tenant_accounting)):
        _valida(body)
        rie = scorporo([x.model_dump() for x in body.righe])
        return {"riepilogo": rie, "imponibile": round(sum(x["imponibile"] for x in rie), 2), "iva": round(sum(x["imposta"] for x in rie), 2),
                "totale": round(sum(x.totale for x in body.righe), 2)}

    @r.post("")
    async def registra(body: RegIn, t: dict = Depends(tenant_accounting)):
        async with deps["lock"].setdefault(t["cid"], asyncio.Lock()):
            return await _registra(body, t)

    async def _registra(body: RegIn, t: dict):
        cid = t["cid"]
        scad = _valida(body)
        await coge.check_aperto(db, cid, int(body.data_registrazione[:4]))
        ruolo, td = TIPI[body.tipo]
        p = await db.parties.find_one({"id": body.party_id, "company_id": cid, "tipo": ruolo}, {"_id": 0, "listino": 0})
        if not p:
            raise ferr(400, "party_id", f"Seleziona un {ruolo}")
        rie = scorporo([x.model_dump() for x in body.righe])
        imp, iva = round(sum(x["imponibile"] for x in rie), 2), round(sum(x["imposta"] for x in rie), 2)
        tot = round(imp + iva, 2)
        snap = {k: p.get(k) or "" for k in ("denominazione", "partita_iva", "codice_fiscale", "indirizzo", "cap", "comune", "provincia", "nazione")}
        base = {"id": str(uuid.uuid4()), "company_id": cid, "party_id": p["id"], "tipo_documento": td, "numero_display": body.numero, "data": body.data_documento,
                "riepilogo": rie, "imponibile": imp, "iva": iva, "totale": tot, "netto": tot, "scadenza": scad, "rate": [{"scadenza": scad, "importo": tot}],
                "manuale": True, "created_by": t["user"]["user_id"], "created_by_name": t["user"].get("name") or t["user"]["email"], "created_at": _now()}
        anno = int(body.data_documento[:4])
        if ruolo == "cliente":
            if await db.invoices.find_one({"company_id": cid, "manuale": True, "party_id": p["id"], "anno": anno, "numero_display": body.numero, "tipo_documento": td}, {"_id": 1}):
                raise ferr(400, "numero", "Documento già registrato per questo cliente")
            sez = "MANNC" if td == "TD04" else "MAN"
            last = await db.invoices.find_one({"company_id": cid, "anno": anno, "sezionale": sez}, {"_id": 0, "numero": 1}, sort=[("numero", -1)])
            imp35 = imponibile_n35(rie)
            intento = await deps["intento"](cid, p, body.data_documento, imp35, None, nc=td == "TD04") if imp35 else None
            if intento:
                snap |= {"intento_protocollo": intento["protocollo"], "intento_data": intento["data"]}
            doc = base | {"anno": anno, "sezionale": sez, "numero": (last["numero"] if last else 0) + 1, "cliente": snap, "status": "manuale", "modalita_pagamento": "MP05", "intento": intento,
                          "lines": [{"descrizione": f"Imponibile {x['aliquota']:g}%" + (f" {x['natura']}" if x["natura"] else ""), "quantita": 1, "prezzo_unitario": x["imponibile"],
                                     "prezzo_totale": x["imponibile"], "aliquota": x["aliquota"], "natura": x["natura"]} for x in rie],
                          "sdi_history": [{"status": "manuale", "at": _now(), "message": f"Registrazione veloce di {base['created_by_name']}"}]}
            await db.invoices.insert_one(dict(doc))
            reg = await coge.safe(coge.registra_vendita(db, {**doc, "status": "consegnata", "data": body.data_registrazione}))
        else:
            ar = int(body.data_registrazione[:4])
            if await db.passive_invoices.find_one({"company_id": cid, "party_id": p["id"], "numero": body.numero, "data": body.data_documento, "tipo_documento": td}, {"_id": 1}):
                raise ferr(400, "numero", "Documento già registrato per questo fornitore")
            last = await db.passive_invoices.find_one({"company_id": cid, "anno_registrazione": ar}, {"_id": 0, "protocollo": 1}, sort=[("protocollo", -1)])
            doc = base | {"hash": f"manuale:{base['id']}", "numero": body.numero, "fornitore": snap, "stato_reg": "registrata", "data_registrazione": body.data_registrazione,
                          "anno_registrazione": ar, "protocollo": ((last or {}).get("protocollo") or 0) + 1, "ricevuta_at": body.data_registrazione,
                          "detraibilita_iva": float(p.get("detraibilita_iva") if p.get("detraibilita_iva") is not None else 100), "origine": "manuale", "lines": []}
            await db.passive_invoices.insert_one(dict(doc))
            reg = await coge.safe(coge.registra_acquisto(db, doc))
        return {"id": doc["id"], "tipo": body.tipo, "numero": body.numero, "totale": tot, "imponibile": imp, "iva": iva, "riepilogo": rie,
                "registrazione": (reg or {}).get("numero") if isinstance(reg, dict) else None}

    @r.get("")
    async def lista(t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        proj = {"_id": 0, "id": 1, "numero_display": 1, "data": 1, "tipo_documento": 1, "totale": 1, "imponibile": 1, "iva": 1, "created_at": 1, "created_by_name": 1}
        v = await db.invoices.find({"company_id": cid, "manuale": True}, {**proj, "cliente.denominazione": 1}).sort("created_at", -1).to_list(200)
        a = await db.passive_invoices.find({"company_id": cid, "manuale": True}, {**proj, "fornitore.denominazione": 1, "protocollo": 1}).sort("created_at", -1).to_list(200)
        rows = [x | {"kind": "vendita", "anagrafica": x.pop("cliente")["denominazione"]} for x in v] + [x | {"kind": "acquisto", "anagrafica": x.pop("fornitore")["denominazione"]} for x in a]
        return sorted(rows, key=lambda x: x["created_at"], reverse=True)[:200]

    @r.delete("/{kind}/{did}")
    async def elimina(kind: Literal["vendita", "acquisto"], did: str, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        coll, pay, orig = (db.invoices, db.payments, "vendita") if kind == "vendita" else (db.passive_invoices, db.passive_payments, "acquisto")
        doc = await coll.find_one({"id": did, "company_id": cid, "manuale": True}, {"_id": 0, "id": 1})
        if not doc:
            raise HTTPException(404, "Registrazione non trovata")
        if await pay.find_one({"company_id": cid, "invoice_id": did}, {"_id": 1}):
            raise HTTPException(400, "Il documento ha incassi o pagamenti registrati: eliminali prima")
        await coge.check_annullabile(db, cid, orig, did)
        await coge.annulla(db, cid, orig, did)
        await coll.delete_one({"id": did, "company_id": cid})
        return {"ok": True}

    return r

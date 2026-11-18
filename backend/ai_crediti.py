import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import List

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
TOKEN_PER_CREDITO = 1000
OMAGGIO = 100.0
PACCHETTI_DEFAULT = [
    {"id": "base", "nome": "Base", "crediti": 500, "prezzo": 10.0},
    {"id": "pro", "nome": "Pro", "crediti": 2000, "prezzo": 35.0},
    {"id": "studio", "nome": "Studio", "crediti": 10000, "prezzo": 150.0},
]


def _now():
    return datetime.now(timezone.utc).isoformat()


class Pacchetto(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_]{1,20}$")
    nome: str = Field(min_length=1, max_length=40)
    crediti: int = Field(ge=1, le=10_000_000)
    prezzo: float = Field(ge=1, le=100000)


class PadreIn(BaseModel):
    pacchetti: List[Pacchetto] = Field(min_length=1, max_length=6)


class AttivaIn(BaseModel):
    attiva: bool


class CheckoutIn(BaseModel):
    pacchetto_id: str
    origin_url: str = Field(pattern=r"^https?://")


def stato(comp: dict) -> dict:
    return {"attiva": comp.get("ai_attiva", True), "crediti": round(float(comp.get("ai_crediti", OMAGGIO)), 2)}


def controlla(comp: dict):
    s = stato(comp)
    if not s["attiva"]:
        raise HTTPException(400, "L'intelligenza artificiale \u00e8 disattivata per questa azienda (Dati azienda)")
    if s["crediti"] <= 0:
        raise HTTPException(402, "Crediti IA esauriti: acquistane altri dalla dashboard")


async def addebita(db, cid: str, tokens: int, tipo: str):
    cr = round(max(tokens, 1) / TOKEN_PER_CREDITO, 3)
    await db.companies.update_one({"id": cid}, {"$inc": {"ai_crediti": -cr}})
    await db.ai_consumi.insert_one({"company_id": cid, "tipo": tipo, "token": tokens, "crediti": cr, "at": _now()})


async def _padre(db):
    return await db.companies.find_one({"societa_padre": True}, {"_id": 0, "id": 1, "denominazione": 1, "ai_pacchetti": 1})


def _price(pk: dict, venditore: str) -> str:
    lk = f"ai_crediti_{pk['id']}"
    cents = int(round(pk["prezzo"] * 100))
    ex = stripe.Price.list(lookup_keys=[lk], active=True, limit=1).data
    if ex and ex[0].unit_amount == cents and ex[0].currency == "eur":
        return ex[0].id
    if ex:
        stripe.Price.modify(ex[0].id, active=False)
    prod = next((p for p in stripe.Product.list(active=True).auto_paging_iter() if p.to_dict().get("metadata", {}).get("emergent_product_id") == "crediti_ia"), None)
    if not prod:
        prod = stripe.Product.create(name="Crediti IA Invoix", tax_code="txcd_10103001", metadata={"managed_by": "emergent", "emergent_product_id": "crediti_ia"})
    return stripe.Price.create(product=prod.id, unit_amount=cents, currency="eur", lookup_key=lk, transfer_lookup_key=True,
                               nickname=f"{pk['nome']} - {pk['crediti']} crediti ({venditore})").id


def _session(price_id: str, req: CheckoutIn, meta: dict):
    kw = dict(line_items=[{"price": price_id, "quantity": 1}], mode="payment", metadata=meta,
              success_url=f"{req.origin_url}/payment/success?session_id={{CHECKOUT_SESSION_ID}}", cancel_url=f"{req.origin_url}/payment/cancel")
    try:
        return stripe.checkout.Session.create(**kw, managed_payments={"enabled": True})
    except stripe.error.InvalidRequestError as e:
        msg = (e.user_message or str(e)).lower()
        if "managed payments" in msg or "ineligible" in msg or "managed_payments" in msg:
            return stripe.checkout.Session.create(**kw, automatic_tax={"enabled": True}, billing_address_collection="required")
        raise


def build(db, tenant, tenant_admin, admin_user) -> APIRouter:
    r = APIRouter(prefix="/api")

    async def accredita(session_id: str):
        tx = await db.payment_transactions.find_one_and_update({"session_id": session_id, "payment_status": "paid", "accreditato": {"$ne": True}}, {"$set": {"accreditato": True, "updated_at": _now()}})
        if tx:
            await db.companies.update_one({"id": tx["company_id"]}, {"$inc": {"ai_crediti": float(tx["crediti"])}})

    async def segna_pagato(session_id: str, pi=None):
        await db.payment_transactions.update_one({"session_id": session_id, "payment_status": {"$ne": "paid"}},
                                                 {"$set": {"status": "completed", "payment_status": "paid", "stripe_payment_intent_id": pi, "updated_at": _now()}})
        await accredita(session_id)

    @r.get("/ai/crediti")
    async def get_crediti(t: dict = Depends(tenant)):
        p = await _padre(db)
        movimenti = await db.payment_transactions.find({"company_id": t["cid"], "payment_status": "paid"}, {"_id": 0, "crediti": 1, "amount": 1, "pacchetto": 1, "created_at": 1}).sort("created_at", -1).to_list(10)
        return {**stato(t["company"]), "token_per_credito": TOKEN_PER_CREDITO, "venditore": p["denominazione"] if p else None,
                "pacchetti": (p.get("ai_pacchetti") or PACCHETTI_DEFAULT) if p else [], "acquisti": movimenti}

    @r.put("/ai/attiva")
    async def put_attiva(body: AttivaIn, t: dict = Depends(tenant_admin)):
        await db.companies.update_one({"id": t["cid"]}, {"$set": {"ai_attiva": body.attiva}})
        return {"attiva": body.attiva}

    @r.get("/ai/padre")
    async def get_padre(_: dict = Depends(admin_user)):
        p = await _padre(db)
        return {"id": p["id"] if p else None, "denominazione": p["denominazione"] if p else None, "pacchetti": (p or {}).get("ai_pacchetti") or PACCHETTI_DEFAULT}

    @r.put("/companies/{cid}/padre")
    async def put_padre(cid: str, body: PadreIn, _: dict = Depends(admin_user)):
        if len({x.id for x in body.pacchetti}) != len(body.pacchetti):
            raise HTTPException(422, "Ogni pacchetto deve avere un codice diverso")
        if not await db.companies.find_one({"id": cid}, {"_id": 1}):
            raise HTTPException(404, "Azienda non trovata")
        await db.companies.update_many({"id": {"$ne": cid}, "societa_padre": True}, {"$set": {"societa_padre": False}})
        await db.companies.update_one({"id": cid}, {"$set": {"societa_padre": True, "ai_pacchetti": [x.model_dump() for x in body.pacchetti]}})
        return {"ok": True}

    @r.delete("/companies/{cid}/padre")
    async def del_padre(cid: str, _: dict = Depends(admin_user)):
        r_ = await db.companies.update_one({"id": cid}, {"$set": {"societa_padre": False}})
        if not r_.matched_count:
            raise HTTPException(404, "Azienda non trovata")
        return {"ok": True}

    @r.post("/ai/crediti/checkout")
    async def checkout(body: CheckoutIn, t: dict = Depends(tenant_admin)):
        p = await _padre(db)
        if not p:
            raise HTTPException(400, "Nessuna societ\u00e0 padre configurata: impostala in Anagrafica aziende")
        pk = next((x for x in (p.get("ai_pacchetti") or PACCHETTI_DEFAULT) if x["id"] == body.pacchetto_id), None)
        if not pk:
            raise HTTPException(404, "Pacchetto non trovato")
        meta = {"company_id": t["cid"], "pacchetto": pk["id"], "crediti": str(pk["crediti"]), "venditore_id": p["id"]}
        try:
            price_id = await asyncio.to_thread(_price, pk, p["denominazione"])
            s = await asyncio.to_thread(_session, price_id, body, meta)
        except stripe.error.StripeError as e:
            raise HTTPException(502, f"Pagamento non disponibile: {e.user_message or str(e)[:150]}")
        await db.payment_transactions.insert_one({"id": str(uuid.uuid4()), "session_id": s.id, "company_id": t["cid"], "user_id": t["user"]["user_id"], "venditore_id": p["id"],
                                                  "pacchetto": pk["id"], "crediti": pk["crediti"], "amount": float(pk["prezzo"]), "currency": "eur",
                                                  "status": "initiated", "payment_status": "pending", "created_at": _now(), "updated_at": _now()})
        return {"checkout_url": s.url, "session_id": s.id}

    @r.get("/payments/status/{session_id}")
    async def pay_status(session_id: str):
        rec = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
        if not rec:
            raise HTTPException(404, "Pagamento non trovato")
        if rec.get("payment_status") != "paid":
            try:
                s = await asyncio.to_thread(stripe.checkout.Session.retrieve, session_id)
                if s.payment_status == "paid":
                    await segna_pagato(session_id, s.payment_intent)
                elif s.status == "expired":
                    await db.payment_transactions.update_one({"session_id": session_id}, {"$set": {"status": "expired", "payment_status": "expired"}})
            except stripe.error.StripeError:
                pass
            rec = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
        else:
            await accredita(session_id)
        return {"session_id": rec["session_id"], "status": rec["status"], "payment_status": rec["payment_status"]}

    @r.post("/stripe/webhook")
    async def webhook(request: Request):
        secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
        try:
            ev = stripe.Webhook.construct_event(await request.body(), request.headers.get("stripe-signature", ""), secret)
        except (stripe.error.SignatureVerificationError, ValueError):
            raise HTTPException(400, "Firma non valida")
        obj, tp = ev["data"]["object"], ev["type"]
        if tp in ("checkout.session.completed", "checkout.session.async_payment_succeeded") and obj.get("payment_status") == "paid":
            await segna_pagato(obj["id"], obj.get("payment_intent"))
        elif tp == "checkout.session.async_payment_failed":
            await db.payment_transactions.update_one({"session_id": obj["id"]}, {"$set": {"status": "failed", "payment_status": "failed"}})
        elif tp == "checkout.session.expired":
            await db.payment_transactions.update_one({"session_id": obj["id"], "payment_status": {"$ne": "paid"}}, {"$set": {"status": "expired", "payment_status": "expired"}})
        return {"status": "ok"}

    return r

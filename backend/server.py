from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends
from fastapi.responses import Response as RawResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError
import os
import re
import logging
import uuid
import httpx
from pathlib import Path
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal
from datetime import datetime, timezone, timedelta, date

from fatturapa import compute_totals, build_xml, file_name

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

client = AsyncIOMotorClient(os.environ['MONGO_URL'])
db = client[os.environ['DB_NAME']]
ADMIN_EMAIL = os.environ['ADMIN_EMAIL'].strip().lower()

app = FastAPI()
api = APIRouter(prefix="/api")

STATUSES = ["bozza", "inviata", "consegnata", "scartata"]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------- Auth ----------
async def get_user(request: Request) -> dict:
    token = request.cookies.get("session_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(401, "Non autenticato")
    sess = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not sess:
        raise HTTPException(401, "Sessione non valida")
    exp = sess["expires_at"]
    if isinstance(exp, str):
        exp = datetime.fromisoformat(exp)
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        raise HTTPException(401, "Sessione scaduta")
    user = await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(401, "Utente non trovato")
    return user


async def approved_user(user: dict = Depends(get_user)) -> dict:
    if user.get("status") != "approved":
        raise HTTPException(403, "Account in attesa di approvazione")
    return user


async def accounting_user(user: dict = Depends(approved_user)) -> dict:
    if user.get("role") not in ("admin", "contabile"):
        raise HTTPException(403, "Operazione riservata ad Admin o Contabile")
    return user


async def admin_user(user: dict = Depends(approved_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(403, "Operazione riservata agli amministratori")
    return user


class SessionIn(BaseModel):
    session_id: str


@api.post("/auth/session")
async def create_session(body: SessionIn, response: Response):
    async with httpx.AsyncClient(timeout=15) as hc:
        r = await hc.get("https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                         headers={"X-Session-ID": body.session_id})
    if r.status_code != 200:
        raise HTTPException(401, "Sessione Google non valida")
    data = r.json()
    email = data["email"].lower()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if user:
        await db.users.update_one({"email": email}, {"$set": {"name": data.get("name"), "picture": data.get("picture")}})
        if email == ADMIN_EMAIL and (user.get("role") != "admin" or user.get("status") != "approved"):
            await db.users.update_one({"email": email}, {"$set": {"role": "admin", "status": "approved"}})
        user_id = user["user_id"]
    else:
        is_admin = email == ADMIN_EMAIL
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": user_id, "email": email, "name": data.get("name"), "picture": data.get("picture"),
            "role": "admin" if is_admin else "operatore",
            "status": "approved" if is_admin else "pending",
            "created_at": now_iso(),
        })
    token = data["session_token"]
    await db.user_sessions.insert_one({
        "user_id": user_id, "session_token": token,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7), "created_at": now_iso(),
    })
    response.set_cookie("session_token", token, httponly=True, secure=True, samesite="none",
                        path="/", max_age=7 * 24 * 3600)
    return await db.users.find_one({"user_id": user_id}, {"_id": 0})


@api.get("/auth/me")
async def me(user: dict = Depends(get_user)):
    return user


@api.post("/auth/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        await db.user_sessions.delete_many({"session_token": token})
    response.delete_cookie("session_token", path="/", secure=True, samesite="none")
    return {"ok": True}


# ---------- Users ----------
class UserPatch(BaseModel):
    role: Optional[Literal["admin", "contabile", "operatore"]] = None
    status: Optional[Literal["approved", "pending", "rejected"]] = None


@api.get("/users")
async def list_users(_: dict = Depends(admin_user)):
    return await db.users.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)


@api.patch("/users/{user_id}")
async def patch_user(user_id: str, body: UserPatch, admin: dict = Depends(admin_user)):
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(404, "Utente non trovato")
    if target["user_id"] == admin["user_id"]:
        raise HTTPException(400, "Non puoi modificare il tuo stesso account")
    if target["email"] == ADMIN_EMAIL:
        raise HTTPException(400, "Non puoi modificare l'amministratore principale")
    upd = body.model_dump(exclude_none=True)
    if upd:
        await db.users.update_one({"user_id": user_id}, {"$set": upd})
        if upd.get("status") in ("rejected", "pending"):
            await db.user_sessions.delete_many({"user_id": user_id})
    return await db.users.find_one({"user_id": user_id}, {"_id": 0})


# ---------- Company ----------
def _clean(v):
    return v.strip() if isinstance(v, str) else v


class Company(BaseModel):
    denominazione: str = Field(min_length=1)
    partita_iva: str
    codice_fiscale: Optional[str] = ""
    regime_fiscale: str = "RF01"
    indirizzo: str = Field(min_length=1)
    cap: str
    comune: str = Field(min_length=1)
    provincia: Optional[str] = ""
    nazione: str = "IT"
    iban: Optional[str] = ""
    email: Optional[str] = ""
    pec: Optional[str] = ""
    telefono: Optional[str] = ""

    @field_validator("partita_iva")
    @classmethod
    def _piva(cls, v):
        v = _clean(v)
        if not re.fullmatch(r"\d{11}", v):
            raise ValueError("La Partita IVA deve avere 11 cifre")
        return v

    @field_validator("cap")
    @classmethod
    def _cap(cls, v):
        v = _clean(v)
        if not re.fullmatch(r"\d{5}", v):
            raise ValueError("Il CAP deve avere 5 cifre")
        return v


@api.get("/company")
async def get_company(_: dict = Depends(approved_user)):
    return await db.company.find_one({"key": "main"}, {"_id": 0, "key": 0}) or {}


@api.put("/company")
async def put_company(body: Company, _: dict = Depends(admin_user)):
    await db.company.update_one({"key": "main"}, {"$set": body.model_dump()}, upsert=True)
    return await db.company.find_one({"key": "main"}, {"_id": 0, "key": 0})


# ---------- Parties ----------
class PartyIn(BaseModel):
    tipo: Literal["cliente", "fornitore"]
    denominazione: str = Field(min_length=1)
    partita_iva: Optional[str] = ""
    codice_fiscale: Optional[str] = ""
    codice_destinatario: Optional[str] = "0000000"
    pec: Optional[str] = ""
    email: Optional[str] = ""
    telefono: Optional[str] = ""
    indirizzo: str = Field(min_length=1)
    cap: str
    comune: str = Field(min_length=1)
    provincia: Optional[str] = ""
    nazione: str = "IT"

    @field_validator("partita_iva")
    @classmethod
    def _piva(cls, v):
        v = _clean(v or "")
        if v and not re.fullmatch(r"\d{11}", v):
            raise ValueError("La Partita IVA deve avere 11 cifre")
        return v

    @field_validator("codice_destinatario")
    @classmethod
    def _cd(cls, v):
        v = (_clean(v) or "0000000").upper()
        if not re.fullmatch(r"[A-Z0-9]{7}", v):
            raise ValueError("Il Codice Destinatario deve avere 7 caratteri")
        return v


@api.get("/parties")
async def list_parties(tipo: Optional[str] = None, _: dict = Depends(approved_user)):
    q = {"tipo": tipo} if tipo else {}
    return await db.parties.find(q, {"_id": 0}).sort("denominazione", 1).to_list(2000)


@api.post("/parties")
async def create_party(body: PartyIn, _: dict = Depends(approved_user)):
    doc = {"id": str(uuid.uuid4()), **body.model_dump(), "created_at": now_iso()}
    await db.parties.insert_one(doc)
    return await db.parties.find_one({"id": doc["id"]}, {"_id": 0})


@api.put("/parties/{pid}")
async def update_party(pid: str, body: PartyIn, _: dict = Depends(approved_user)):
    res = await db.parties.update_one({"id": pid}, {"$set": body.model_dump()})
    if not res.matched_count:
        raise HTTPException(404, "Anagrafica non trovata")
    return await db.parties.find_one({"id": pid}, {"_id": 0})


@api.delete("/parties/{pid}")
async def delete_party(pid: str, _: dict = Depends(approved_user)):
    if await db.invoices.find_one({"party_id": pid}):
        raise HTTPException(400, "Anagrafica usata in una o più fatture: non eliminabile")
    await db.parties.delete_one({"id": pid})
    return {"ok": True}


# ---------- Invoices ----------
NATURE = ["N1", "N2.1", "N2.2", "N3.1", "N3.2", "N3.5", "N4", "N5", "N6.1", "N6.9", "N7"]


class LineIn(BaseModel):
    descrizione: str = Field(min_length=1)
    quantita: float = Field(gt=0)
    unita_misura: Optional[str] = ""
    prezzo_unitario: float
    aliquota: float
    natura: Optional[str] = None

    @field_validator("aliquota")
    @classmethod
    def _al(cls, v):
        if v not in (0, 4, 5, 10, 22):
            raise ValueError("Aliquota IVA non valida")
        return v


class InvoiceIn(BaseModel):
    tipo_documento: Literal["TD01", "TD04", "TD05", "TD06"] = "TD01"
    data: str
    party_id: str
    lines: List[LineIn] = Field(min_length=1)
    causale: Optional[str] = ""
    modalita_pagamento: Literal["MP01", "MP02", "MP05", "MP08", "MP12"] = "MP05"
    scadenza: Optional[str] = ""
    note: Optional[str] = ""

    @field_validator("data", "scadenza")
    @classmethod
    def _date(cls, v, info):
        if not v and info.field_name == "scadenza":
            return ""
        try:
            return date.fromisoformat(v).isoformat()
        except (TypeError, ValueError):
            raise ValueError("Data non valida (formato AAAA-MM-GG)")


def _check_lines(lines: List[LineIn]):
    for ln in lines:
        if ln.aliquota == 0 and ln.natura not in NATURE:
            raise HTTPException(422, f"Indica la Natura IVA per la riga \"{ln.descrizione}\" con aliquota 0%")


async def _party_snapshot(pid: str) -> dict:
    p = await db.parties.find_one({"id": pid, "tipo": "cliente"}, {"_id": 0})
    if not p:
        raise HTTPException(400, "Cliente non trovato")
    return p


async def _get_invoice(iid: str) -> dict:
    inv = await db.invoices.find_one({"id": iid}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Fattura non trovata")
    return inv


async def _next_progressivo() -> str:
    seq = await db.counters.find_one_and_update({"key": "progressivo"}, {"$inc": {"v": 1}}, upsert=True, return_document=True)
    return _to_base36(seq["v"])


def _to_base36(n: int) -> str:
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    s = ""
    while n:
        n, r = divmod(n, 36)
        s = chars[r] + s
    return (s or "0").rjust(5, "0")


@api.get("/invoices")
async def list_invoices(status: Optional[str] = None, _: dict = Depends(approved_user)):
    q = {"status": status} if status else {}
    return await db.invoices.find(q, {"_id": 0, "sdi_history": 0}).sort([("anno", -1), ("numero", -1)]).to_list(5000)


@api.get("/invoices/{iid}")
async def get_invoice(iid: str, _: dict = Depends(approved_user)):
    return await _get_invoice(iid)


@api.post("/invoices")
async def create_invoice(body: InvoiceIn, user: dict = Depends(approved_user)):
    _check_lines(body.lines)
    cliente = await _party_snapshot(body.party_id)
    anno = int(body.data[:4])
    totals = compute_totals([ln.model_dump() for ln in body.lines])
    for _ in range(5):
        last = await db.invoices.find_one({"anno": anno}, {"_id": 0, "numero": 1, "data": 1}, sort=[("numero", -1)])
        if last and body.data < last["data"]:
            raise HTTPException(400, f"La data non può essere precedente all'ultima fattura dell'anno ({last['data']})")
        numero = (last["numero"] if last else 0) + 1
        doc = {
            "id": str(uuid.uuid4()), **body.model_dump(), **totals,
            "numero": numero, "anno": anno, "numero_display": f"{numero}/{anno}",
            "progressivo_invio": await _next_progressivo(), "cliente": cliente,
            "status": "bozza", "sdi_id": None, "sdi_message": None,
            "sdi_history": [{"status": "bozza", "at": now_iso(), "message": f"Creata da {user.get('name') or user['email']}"}],
            "created_by": user["user_id"], "created_at": now_iso(), "updated_at": now_iso(),
        }
        try:
            await db.invoices.insert_one(doc)
            return await _get_invoice(doc["id"])
        except DuplicateKeyError:
            continue
    raise HTTPException(409, "Numerazione occupata, riprova")


@api.put("/invoices/{iid}")
async def update_invoice(iid: str, body: InvoiceIn, _: dict = Depends(approved_user)):
    inv = await _get_invoice(iid)
    if inv["status"] not in ("bozza", "scartata"):
        raise HTTPException(400, "La fattura è già stata inviata allo SDI e non è modificabile")
    _check_lines(body.lines)
    if int(body.data[:4]) != inv["anno"]:
        raise HTTPException(400, "Non puoi cambiare l'anno della fattura")
    cliente = await _party_snapshot(body.party_id)
    totals = compute_totals([ln.model_dump() for ln in body.lines])
    await db.invoices.update_one({"id": iid}, {"$set": {**body.model_dump(), **totals, "cliente": cliente, "updated_at": now_iso()}})
    return await _get_invoice(iid)


@api.delete("/invoices/{iid}")
async def delete_invoice(iid: str, _: dict = Depends(approved_user)):
    inv = await _get_invoice(iid)
    if inv["status"] != "bozza":
        raise HTTPException(400, "Solo le bozze possono essere eliminate")
    last = await db.invoices.find_one({"anno": inv["anno"]}, {"_id": 0, "numero": 1}, sort=[("numero", -1)])
    if last["numero"] != inv["numero"]:
        raise HTTPException(400, "Puoi eliminare solo l'ultima fattura numerata dell'anno (per non lasciare buchi nella numerazione)")
    await db.invoices.delete_one({"id": iid})
    return {"ok": True}


async def _company_required() -> dict:
    c = await db.company.find_one({"key": "main"}, {"_id": 0, "key": 0})
    if not c or not c.get("partita_iva"):
        raise HTTPException(400, "Completa prima i dati azienda in Impostazioni")
    return c


@api.get("/invoices/{iid}/xml")
async def invoice_xml(iid: str, _: dict = Depends(approved_user)):
    inv = await _get_invoice(iid)
    company = await _company_required()
    xml = build_xml(company, inv)
    fname = file_name(company, inv)
    return RawResponse(content=xml, media_type="application/xml",
                       headers={"Content-Disposition": f'attachment; filename="{fname}"', "X-Filename": fname,
                                "Access-Control-Expose-Headers": "X-Filename"})


# ---------- SDI (SIMULATED intermediary) ----------
def _sdi_checks(inv: dict) -> Optional[str]:
    c = inv["cliente"]
    if not c.get("partita_iva") and not c.get("codice_fiscale"):
        return "Errore 00417: il cessionario/committente deve avere Partita IVA o Codice Fiscale"
    if (c.get("codice_destinatario") or "0000000") == "0000000" and not c.get("pec") and c.get("partita_iva"):
        return "Errore 00426: Codice Destinatario 0000000 senza PEC destinatario (cliente con P.IVA)"
    if inv["totale"] <= 0 and inv.get("tipo_documento") == "TD01":
        return "Errore 00433: importo totale documento non valido"
    return None


async def _push_status(iid: str, status: str, message: str, extra: dict = None):
    await db.invoices.update_one({"id": iid}, {
        "$set": {"status": status, "sdi_message": message, "updated_at": now_iso(), **(extra or {})},
        "$push": {"sdi_history": {"status": status, "at": now_iso(), "message": message}},
    })


@api.post("/invoices/{iid}/send")
async def send_sdi(iid: str, _: dict = Depends(accounting_user)):
    inv = await _get_invoice(iid)
    if inv["status"] not in ("bozza", "scartata"):
        raise HTTPException(400, "Fattura già inviata")
    company = await _company_required()
    if inv["status"] == "scartata":
        inv["progressivo_invio"] = await _next_progressivo()
        await db.invoices.update_one({"id": iid}, {"$set": {"progressivo_invio": inv["progressivo_invio"]}})
    fname = file_name(company, inv)
    sdi_id = str(uuid.uuid4().int)[:10]
    await _push_status(iid, "inviata", f"File {fname} trasmesso all'intermediario (SIMULATO). Id SDI {sdi_id}",
                       {"sdi_id": sdi_id, "sent_at": now_iso()})
    return await _get_invoice(iid)


@api.post("/invoices/{iid}/refresh")
async def refresh_sdi(iid: str, _: dict = Depends(approved_user)):
    inv = await _get_invoice(iid)
    if inv["status"] != "inviata":
        raise HTTPException(400, "Nessun esito da aggiornare")
    err = _sdi_checks(inv)
    if err:
        await _push_status(iid, "scartata", f"Notifica di scarto (NS): {err}")
    else:
        await _push_status(iid, "consegnata", "Ricevuta di consegna (RC): fattura recapitata al destinatario")
    return await _get_invoice(iid)


# ---------- Dashboard ----------
@api.get("/dashboard")
async def dashboard(_: dict = Depends(approved_user)):
    invs = await db.invoices.find({}, {"_id": 0, "sdi_history": 0, "lines": 0, "riepilogo": 0}).to_list(10000)
    year = datetime.now(timezone.utc).year
    counts = {s: 0 for s in STATUSES}
    fatt = imp = iva = 0.0
    months = [{"mese": m, "totale": 0.0} for m in range(1, 13)]
    for i in invs:
        counts[i["status"]] = counts.get(i["status"], 0) + 1
        if i["status"] in ("inviata", "consegnata"):
            sign = -1 if i.get("tipo_documento") == "TD04" else 1
            fatt += sign * i["totale"]
            imp += sign * i["imponibile"]
            iva += sign * i["iva"]
            if i["anno"] == year:
                months[int(i["data"][5:7]) - 1]["totale"] += sign * i["totale"]
    recent = sorted(invs, key=lambda x: x["created_at"], reverse=True)[:6]
    return {"counts": counts, "fatturato": round(fatt, 2), "imponibile": round(imp, 2), "iva": round(iva, 2),
            "anno": year, "mesi": months, "recenti": recent, "totale_fatture": len(invs)}


@app.on_event("startup")
async def init_indexes():
    await db.invoices.create_index([("anno", 1), ("numero", 1)], unique=True)


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

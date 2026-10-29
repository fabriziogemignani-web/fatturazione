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
import bcrypt
import secrets
import hashlib
from html import escape
from urllib.parse import urlparse
from pathlib import Path
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Literal
from datetime import datetime, timezone, timedelta, date

from fatturapa import compute_totals, build_xml, file_name

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from emailer import send_email, EMAIL_FROM_NAME  # noqa: E402

client = AsyncIOMotorClient(os.environ['MONGO_URL'])
db = client[os.environ['DB_NAME']]
ADMIN_EMAIL = os.environ['ADMIN_EMAIL'].strip().lower()
APP_URL = os.environ['APP_URL'].rstrip("/")
USER_PROJ = {"_id": 0, "password_hash": 0}

app = FastAPI()
api = APIRouter(prefix="/api")

STATUSES = ["bozza", "inviata", "consegnata", "mancata_consegna", "scartata"]
SENT = ("inviata", "consegnata", "mancata_consegna")
NATURE = ["N1", "N2.1", "N2.2", "N3.1", "N3.2", "N3.5", "N4", "N5", "N6.1", "N6.9", "N7"]
ALIQUOTE = (0, 4, 5, 10, 22)


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
    user = await db.users.find_one({"user_id": sess["user_id"]}, USER_PROJ)
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


COMPANY_PROJ = {"_id": 0}


async def tenant(request: Request, user: dict = Depends(approved_user)) -> dict:
    cid = request.headers.get("X-Company-Id")
    if not cid:
        raise HTTPException(400, "Seleziona un'azienda")
    if user.get("role") != "admin" and cid not in (user.get("company_ids") or []):
        raise HTTPException(404, "Azienda non trovata")
    comp = await db.companies.find_one({"id": cid}, COMPANY_PROJ)
    if not comp:
        raise HTTPException(404, "Azienda non trovata")
    return {"user": user, "cid": cid, "company": comp}


async def tenant_accounting(t: dict = Depends(tenant)) -> dict:
    if t["user"].get("role") not in ("admin", "contabile"):
        raise HTTPException(403, "Operazione riservata ad Admin o Contabile")
    return t


async def tenant_admin(t: dict = Depends(tenant)) -> dict:
    if t["user"].get("role") != "admin":
        raise HTTPException(403, "Operazione riservata agli amministratori")
    return t


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
        if user.get("password_hash") and not user.get("email_verified"):
            await db.users.update_one({"email": email}, {"$unset": {"password_hash": ""}})
            await db.user_sessions.delete_many({"user_id": user["user_id"]})
        await db.users.update_one({"email": email}, {"$set": {"name": data.get("name"), "picture": data.get("picture"), "email_verified": True}})
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
    await _start_session(response, user_id, token)
    return await db.users.find_one({"user_id": user_id}, USER_PROJ)


async def _start_session(response: Response, user_id: str, token: str = None):
    token = token or secrets.token_urlsafe(32)
    await db.user_sessions.insert_one({
        "user_id": user_id, "session_token": token,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7), "created_at": now_iso(),
    })
    response.set_cookie("session_token", token, httponly=True, secure=True, samesite="none",
                        path="/", max_age=7 * 24 * 3600)


def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def verify_password(p: str, h: str) -> bool:
    return bcrypt.checkpw(p.encode(), h.encode())


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _em(cls, v):
        v = v.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", v):
            raise ValueError("Email non valida")
        return v


class LoginIn(BaseModel):
    email: str
    password: str


class ForgotIn(BaseModel):
    email: str


class ResetIn(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)


@api.post("/auth/register")
async def register(body: RegisterIn, response: Response):
    existing = await db.users.find_one({"email": body.email}, {"_id": 0})
    if existing:
        raise HTTPException(400, "Email già registrata: accedi o usa 'Password dimenticata'")
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    await db.users.insert_one({
        "user_id": user_id, "email": body.email, "name": body.name.strip(), "picture": None,
        "password_hash": hash_password(body.password), "email_verified": False,
        "role": "operatore", "status": "pending", "created_at": now_iso(),
    })
    await _start_session(response, user_id)
    return await db.users.find_one({"user_id": user_id}, USER_PROJ)


@api.post("/auth/login")
async def login(body: LoginIn, request: Request, response: Response):
    email = body.email.strip().lower()
    ident = email
    att = await db.login_attempts.find_one({"identifier": ident}, {"_id": 0})
    if att and att.get("count", 0) >= 5:
        until = datetime.fromisoformat(att["last"]) + timedelta(minutes=15)
        if until > datetime.now(timezone.utc):
            raise HTTPException(429, "Troppi tentativi falliti. Riprova tra 15 minuti")
        await db.login_attempts.delete_one({"identifier": ident})
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user or not user.get("password_hash") or not verify_password(body.password, user["password_hash"]):
        await db.login_attempts.update_one({"identifier": ident}, {"$inc": {"count": 1}, "$set": {"last": now_iso()}}, upsert=True)
        raise HTTPException(401, "Email o password non corretti")
    await db.login_attempts.delete_one({"identifier": ident})
    await _start_session(response, user["user_id"])
    return await db.users.find_one({"user_id": user["user_id"]}, USER_PROJ)


def _reset_base(request: Request) -> str:
    origin = (request.headers.get("origin") or "").rstrip("/")
    host = urlparse(origin).hostname or ""
    if origin.startswith("https://") and (origin == APP_URL or host.endswith(".emergentagent.com") or host.endswith(".emergent.host")):
        return origin
    return APP_URL


async def _send_password_link(user: dict, request: Request, invite: bool = False):
    token = secrets.token_urlsafe(32)
    hours = 72 if invite else 1
    await db.password_reset_tokens.insert_one({
        "token_hash": hashlib.sha256(token.encode()).hexdigest(), "user_id": user["user_id"],
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=hours), "used": False, "created_at": now_iso(),
    })
    link = f"{_reset_base(request)}/reset-password?token={token}"
    intro = (f"sei stato invitato ad accedere a {escape(EMAIL_FROM_NAME)}. Imposta la tua password per entrare (puoi anche accedere con Google usando questo indirizzo)."
             if invite else f"abbiamo ricevuto una richiesta di reimpostazione della password per il tuo account {escape(EMAIL_FROM_NAME)}.")
    durata = "72 ore" if invite else "1 ora"
    html = (
        '<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif;color:#0f172a">'
        f'<p>Ciao {escape(user.get("name") or "")},</p>'
        f'<p>{intro}</p>'
        f'<p><a href="{escape(link)}" style="display:inline-block;background:#0f172a;color:#ffffff;padding:12px 20px;border-radius:6px;text-decoration:none">{"Imposta password" if invite else "Reimposta password"}</a></p>'
        f'<p>Il link scade tra {durata} e può essere usato una sola volta. Se non ti aspettavi questa email, ignorala.</p>'
        f'<p style="font-size:12px;color:#888">Inviato da {escape(EMAIL_FROM_NAME)}. Non ti chiederemo mai la password via email.</p>'
        '</td></tr></table>'
    )
    subject = f"Invito ad accedere - {EMAIL_FROM_NAME}" if invite else f"Reimposta la password - {EMAIL_FROM_NAME}"
    await send_email(to=user["email"], subject=subject, html=html)


@api.post("/auth/forgot-password")
async def forgot_password(body: ForgotIn, request: Request):
    email = body.email.strip().lower()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if user and user.get("status") != "rejected":
        recent = await db.password_reset_tokens.count_documents({"user_id": user["user_id"], "created_at": {"$gt": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()}})
        if recent < 3:
            await _send_password_link(user, request)
    return {"ok": True, "message": "Se l'email è registrata, riceverai un link per reimpostare la password"}


@api.post("/auth/reset-password")
async def reset_password(body: ResetIn):
    th = hashlib.sha256(body.token.encode()).hexdigest()
    rec = await db.password_reset_tokens.find_one_and_update({"token_hash": th, "used": False}, {"$set": {"used": True}})
    if not rec:
        raise HTTPException(400, "Link non valido o già utilizzato")
    exp = rec["expires_at"]
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        raise HTTPException(400, "Link scaduto: richiedine uno nuovo")
    upd = {"password_hash": hash_password(body.password), "email_verified": True}
    target = await db.users.find_one({"user_id": rec["user_id"]}, {"_id": 0, "email": 1})
    if target and target["email"] == ADMIN_EMAIL:
        upd.update({"role": "admin", "status": "approved"})
    await db.users.update_one({"user_id": rec["user_id"]}, {"$set": upd})
    await db.user_sessions.delete_many({"user_id": rec["user_id"]})
    return {"ok": True}


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
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    company_ids: Optional[List[str]] = None


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str
    role: Literal["admin", "contabile", "operatore"] = "operatore"
    send_invite: bool = True
    company_ids: List[str] = []

    @field_validator("email")
    @classmethod
    def _em(cls, v):
        v = v.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", v):
            raise ValueError("Email non valida")
        return v


@api.get("/users")
async def list_users(_: dict = Depends(admin_user)):
    users = await db.users.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    for u in users:
        u["has_password"] = bool(u.pop("password_hash", None))
        u["is_owner"] = u["email"] == ADMIN_EMAIL
    return users


async def _valid_company_ids(ids: List[str]) -> List[str]:
    ids = list(dict.fromkeys(ids))
    found = await db.companies.count_documents({"id": {"$in": ids}})
    if found != len(ids):
        raise HTTPException(400, "Una o più aziende non esistono")
    return ids


@api.post("/users")
async def create_user(body: UserCreate, request: Request, admin: dict = Depends(admin_user)):
    if await db.users.find_one({"email": body.email}):
        raise HTTPException(400, "Esiste già un utente con questa email")
    user = {
        "user_id": f"user_{uuid.uuid4().hex[:12]}", "email": body.email, "name": body.name.strip(), "picture": None,
        "email_verified": False, "role": body.role, "status": "approved", "created_at": now_iso(),
        "created_by": admin["user_id"], "company_ids": await _valid_company_ids(body.company_ids),
    }
    try:
        await db.users.insert_one(user)
    except DuplicateKeyError:
        raise HTTPException(400, "Esiste già un utente con questa email")
    if body.send_invite:
        try:
            await _send_password_link(user, request, invite=True)
        except HTTPException:
            await db.users.delete_one({"user_id": user["user_id"]})
            await db.password_reset_tokens.delete_many({"user_id": user["user_id"]})
            raise
    return await db.users.find_one({"user_id": user["user_id"]}, USER_PROJ)


async def _editable_target(user_id: str, admin: dict) -> dict:
    target = await db.users.find_one({"user_id": user_id}, USER_PROJ)
    if not target:
        raise HTTPException(404, "Utente non trovato")
    if target["user_id"] == admin["user_id"]:
        raise HTTPException(400, "Non puoi modificare il tuo stesso account")
    if target["email"] == ADMIN_EMAIL:
        raise HTTPException(400, "Non puoi modificare l'amministratore principale")
    return target


@api.delete("/users/{user_id}")
async def delete_user(user_id: str, admin: dict = Depends(admin_user)):
    await _editable_target(user_id, admin)
    await db.users.delete_one({"user_id": user_id})
    await db.user_sessions.delete_many({"user_id": user_id})
    await db.password_reset_tokens.delete_many({"user_id": user_id})
    return {"ok": True}


@api.post("/users/{user_id}/send-reset")
async def send_user_reset(user_id: str, request: Request, admin: dict = Depends(admin_user)):
    target = await _editable_target(user_id, admin)
    if target.get("status") == "rejected":
        raise HTTPException(400, "Utente rifiutato: riattivalo prima")
    await _send_password_link(target, request, invite=not target.get("email_verified"))
    return {"ok": True}


@api.patch("/users/{user_id}")
async def patch_user(user_id: str, body: UserPatch, admin: dict = Depends(admin_user)):
    await _editable_target(user_id, admin)
    upd = body.model_dump(exclude_none=True)
    if "company_ids" in upd:
        upd["company_ids"] = await _valid_company_ids(upd["company_ids"])
    if upd:
        await db.users.update_one({"user_id": user_id}, {"$set": upd})
        if upd.get("status") in ("rejected", "pending"):
            await db.user_sessions.delete_many({"user_id": user_id})
    return await db.users.find_one({"user_id": user_id}, USER_PROJ)


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
    cassa_tipo: Optional[str] = ""
    cassa_aliquota: Optional[float] = 4
    cassa_aliquota_iva: Optional[float] = 22
    cassa_ritenuta: bool = False
    ritenuta_tipo: Optional[str] = ""
    ritenuta_aliquota: Optional[float] = 20
    ritenuta_causale: Optional[str] = "A"

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


@api.get("/companies")
async def list_companies(user: dict = Depends(approved_user)):
    q = {} if user.get("role") == "admin" else {"id": {"$in": user.get("company_ids") or []}}
    return await db.companies.find(q, {"_id": 0, "id": 1, "denominazione": 1, "partita_iva": 1, "comune": 1}).sort("denominazione", 1).to_list(1000)


@api.post("/companies")
async def create_company(body: Company, _: dict = Depends(admin_user)):
    if await db.companies.find_one({"partita_iva": body.partita_iva}):
        raise HTTPException(400, "Esiste già un'azienda con questa Partita IVA")
    doc = {"id": str(uuid.uuid4()), **body.model_dump(), "created_at": now_iso()}
    await db.companies.insert_one(doc)
    return await db.companies.find_one({"id": doc["id"]}, COMPANY_PROJ)


@api.delete("/companies/{cid}")
async def delete_company(cid: str, _: dict = Depends(admin_user)):
    if not await db.companies.find_one({"id": cid}):
        raise HTTPException(404, "Azienda non trovata")
    if await db.invoices.find_one({"company_id": cid}):
        raise HTTPException(400, "L'azienda ha delle fatture: non può essere eliminata")
    await db.parties.delete_many({"company_id": cid})
    await db.articles.delete_many({"company_id": cid})
    await db.counters.delete_many({"key": f"progressivo_{cid}"})
    await db.users.update_many({}, {"$pull": {"company_ids": cid}})
    await db.companies.delete_one({"id": cid})
    return {"ok": True}


@api.get("/company")
async def get_company(t: dict = Depends(tenant)):
    return t["company"]


@api.put("/company")
async def put_company(body: Company, t: dict = Depends(tenant_admin)):
    if await db.companies.find_one({"partita_iva": body.partita_iva, "id": {"$ne": t["cid"]}}):
        raise HTTPException(400, "Esiste già un'altra azienda con questa Partita IVA")
    await db.companies.update_one({"id": t["cid"]}, {"$set": body.model_dump()})
    return await db.companies.find_one({"id": t["cid"]}, COMPANY_PROJ)


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
    natura_default: Optional[str] = ""
    riferimento_normativo: Optional[str] = ""
    intento_protocollo: Optional[str] = ""
    intento_data: Optional[str] = ""

    @model_validator(mode="after")
    def _esenzione(self):
        n = self.natura_default or ""
        if n and n not in NATURE:
            raise ValueError("Natura IVA di esenzione non valida")
        if n == "N3.5":
            prot = (self.intento_protocollo or "").strip()
            if not re.fullmatch(r"\d{17}-\d{6}", prot):
                raise ValueError("Dichiarazione d'intento: protocollo obbligatorio nel formato 17 cifre-6 cifre")
            try:
                self.intento_data = date.fromisoformat(self.intento_data or "").isoformat()
            except ValueError:
                raise ValueError("Dichiarazione d'intento: data di protocollo obbligatoria")
            self.intento_protocollo = prot
        else:
            self.intento_protocollo, self.intento_data = "", ""
        return self

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
async def list_parties(tipo: Optional[str] = None, t: dict = Depends(tenant)):
    q = {"company_id": t["cid"], **({"tipo": tipo} if tipo else {})}
    return await db.parties.find(q, {"_id": 0}).sort("denominazione", 1).to_list(2000)


@api.post("/parties")
async def create_party(body: PartyIn, t: dict = Depends(tenant)):
    doc = {"id": str(uuid.uuid4()), **body.model_dump(), "company_id": t["cid"], "created_at": now_iso()}
    await db.parties.insert_one(doc)
    return await db.parties.find_one({"id": doc["id"]}, {"_id": 0})


@api.put("/parties/{pid}")
async def update_party(pid: str, body: PartyIn, t: dict = Depends(tenant)):
    res = await db.parties.update_one({"id": pid, "company_id": t["cid"]}, {"$set": body.model_dump()})
    if not res.matched_count:
        raise HTTPException(404, "Anagrafica non trovata")
    return await db.parties.find_one({"id": pid}, {"_id": 0})


@api.delete("/parties/{pid}")
async def delete_party(pid: str, t: dict = Depends(tenant)):
    if await db.invoices.find_one({"party_id": pid, "company_id": t["cid"]}):
        raise HTTPException(400, "Anagrafica usata in una o più fatture: non eliminabile")
    await db.parties.delete_one({"id": pid, "company_id": t["cid"]})
    return {"ok": True}


# ---------- Articles ----------
class ArticleIn(BaseModel):
    codice: str = Field(min_length=1, max_length=35)
    descrizione: str = Field(min_length=1, max_length=1000)
    unita_misura: Optional[str] = ""
    prezzo: float = 0
    aliquota: float = 22
    natura: Optional[str] = None

    @model_validator(mode="after")
    def _iva(self):
        if self.aliquota not in ALIQUOTE:
            raise ValueError("Aliquota IVA non valida")
        if self.aliquota == 0 and self.natura not in NATURE:
            raise ValueError("Indica la Natura IVA per l'aliquota 0%")
        if self.aliquota != 0:
            self.natura = None
        return self


@api.get("/articles")
async def list_articles(t: dict = Depends(tenant)):
    return await db.articles.find({"company_id": t["cid"]}, {"_id": 0}).sort("codice", 1).to_list(5000)


@api.post("/articles")
async def create_article(body: ArticleIn, t: dict = Depends(tenant)):
    if await db.articles.find_one({"codice": body.codice, "company_id": t["cid"]}):
        raise HTTPException(400, "Codice articolo già esistente")
    doc = {"id": str(uuid.uuid4()), **body.model_dump(), "company_id": t["cid"], "created_at": now_iso()}
    await db.articles.insert_one(doc)
    return await db.articles.find_one({"id": doc["id"]}, {"_id": 0})


@api.put("/articles/{aid}")
async def update_article(aid: str, body: ArticleIn, t: dict = Depends(tenant)):
    if await db.articles.find_one({"codice": body.codice, "company_id": t["cid"], "id": {"$ne": aid}}):
        raise HTTPException(400, "Codice articolo già esistente")
    res = await db.articles.update_one({"id": aid, "company_id": t["cid"]}, {"$set": body.model_dump()})
    if not res.matched_count:
        raise HTTPException(404, "Articolo non trovato")
    return await db.articles.find_one({"id": aid}, {"_id": 0})


@api.delete("/articles/{aid}")
async def delete_article(aid: str, t: dict = Depends(tenant)):
    await db.articles.delete_one({"id": aid, "company_id": t["cid"]})
    return {"ok": True}


# ---------- Invoices ----------
TIPI_CASSA = [f"TC{i:02d}" for i in range(1, 23)]


class CassaIn(BaseModel):
    tipo: str
    aliquota: float = Field(gt=0, le=100)
    aliquota_iva: float = 22
    natura: Optional[str] = None
    ritenuta: bool = False

    @model_validator(mode="after")
    def _v(self):
        if self.tipo not in TIPI_CASSA:
            raise ValueError("Tipo cassa previdenziale non valido")
        if self.aliquota_iva not in ALIQUOTE:
            raise ValueError("Aliquota IVA della cassa non valida")
        if self.aliquota_iva == 0 and self.natura not in NATURE:
            raise ValueError("Indica la Natura IVA della cassa con aliquota 0%")
        if self.aliquota_iva != 0:
            self.natura = None
        return self


class RitenutaIn(BaseModel):
    tipo: Literal["RT01", "RT02", "RT03", "RT04", "RT05", "RT06"]
    aliquota: float = Field(gt=0, le=100)
    causale: str = Field(default="A", pattern=r"^[A-Z]{1,2}\d?$")


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
        if v not in ALIQUOTE:
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
    cassa: Optional[CassaIn] = None
    ritenuta: Optional[RitenutaIn] = None
    fattura_collegata_id: Optional[str] = None

    @field_validator("data", "scadenza")
    @classmethod
    def _date(cls, v, info):
        if not v and info.field_name == "scadenza":
            return ""
        try:
            d = date.fromisoformat(v)
        except (TypeError, ValueError):
            raise ValueError("Data non valida (formato AAAA-MM-GG)")
        if info.field_name == "data" and d > datetime.now(timezone.utc).date() + timedelta(days=1):
            raise ValueError("La data della fattura non può essere futura")
        return d.isoformat()


def _totals(body: InvoiceIn) -> dict:
    return compute_totals([ln.model_dump() for ln in body.lines],
                          body.cassa.model_dump() if body.cassa else None,
                          body.ritenuta.model_dump() if body.ritenuta else None)


def _check_lines(lines: List[LineIn]):
    for ln in lines:
        if ln.aliquota == 0 and ln.natura not in NATURE:
            raise HTTPException(422, f"Indica la Natura IVA per la riga \"{ln.descrizione}\" con aliquota 0%")


async def _party_snapshot(pid: str, cid: str, lines: List[LineIn] = (), cassa: Optional[CassaIn] = None) -> dict:
    p = await db.parties.find_one({"id": pid, "tipo": "cliente", "company_id": cid}, {"_id": 0})
    if not p:
        raise HTTPException(400, "Cliente non trovato")
    if any(ln.aliquota == 0 and ln.natura == "N3.5" for ln in lines) or (cassa is not None and cassa.natura == "N3.5"):
        if not p.get("intento_protocollo"):
            raise HTTPException(422, "Natura N3.5: inserisci nell'anagrafica del cliente protocollo e data della dichiarazione d'intento")
    return p


async def _get_invoice(iid: str, cid: str) -> dict:
    inv = await db.invoices.find_one({"id": iid, "company_id": cid}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Fattura non trovata")
    return inv


async def _next_progressivo(cid: str) -> str:
    seq = await db.counters.find_one_and_update({"key": f"progressivo_{cid}"}, {"$inc": {"v": 1}}, upsert=True, return_document=True)
    return _to_base36(seq["v"])


def _to_base36(n: int) -> str:
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    s = ""
    while n:
        n, r = divmod(n, 36)
        s = chars[r] + s
    return (s or "0").rjust(5, "0")


def _sezionale(tipo: str) -> str:
    return "NC" if tipo == "TD04" else ""


def _display(numero: int, sez: str, anno: int) -> str:
    return f"{numero}/{sez}/{anno}" if sez else f"{numero}/{anno}"


async def _linked_invoice(body: InvoiceIn, cid: str, totale: float, current_id: str = None) -> Optional[dict]:
    if body.tipo_documento != "TD04" or not body.fattura_collegata_id:
        return None
    orig = await db.invoices.find_one({"id": body.fattura_collegata_id, "company_id": cid}, {"_id": 0, "sdi_history": 0})
    if not orig or orig.get("tipo_documento") == "TD04":
        raise HTTPException(400, "Fattura collegata non trovata")
    if orig["party_id"] != body.party_id:
        raise HTTPException(400, "La nota di credito deve essere intestata allo stesso cliente della fattura collegata")
    if orig["status"] not in SENT:
        raise HTTPException(400, "Puoi stornare solo fatture già inviate allo SDI")
    others = await db.invoices.find({"company_id": cid, "fattura_collegata_id": orig["id"], "id": {"$ne": current_id},
                                     "status": {"$ne": "scartata"}}, {"_id": 0, "totale": 1}).to_list(500)
    residuo = round(orig["totale"] - sum(o["totale"] for o in others), 2)
    if totale > residuo + 0.005:
        raise HTTPException(400, f"Importo superiore al residuo stornabile della fattura {orig['numero_display']} ({residuo:.2f} €)")
    return {"id": orig["id"], "numero_display": orig["numero_display"], "data": orig["data"], "totale": orig["totale"]}


@api.get("/invoices")
async def list_invoices(status: Optional[str] = None, t: dict = Depends(tenant)):
    q = {"company_id": t["cid"], **({"status": status} if status else {})}
    return await db.invoices.find(q, {"_id": 0, "sdi_history": 0}).sort([("anno", -1), ("numero", -1)]).to_list(5000)


@api.get("/invoices/{iid}")
async def get_invoice(iid: str, t: dict = Depends(tenant)):
    inv = await _get_invoice(iid, t["cid"])
    inv["note_credito"] = await db.invoices.find(
        {"company_id": t["cid"], "fattura_collegata_id": iid},
        {"_id": 0, "id": 1, "numero_display": 1, "data": 1, "totale": 1, "status": 1}).sort("numero", 1).to_list(100)
    inv["residuo_stornabile"] = round(inv["totale"] - sum(n["totale"] for n in inv["note_credito"] if n["status"] != "scartata"), 2)
    return inv


@api.post("/invoices")
async def create_invoice(body: InvoiceIn, t: dict = Depends(tenant)):
    user, cid = t["user"], t["cid"]
    _check_lines(body.lines)
    cliente = await _party_snapshot(body.party_id, cid, body.lines, body.cassa)
    anno = int(body.data[:4])
    totals = _totals(body)
    sez = _sezionale(body.tipo_documento)
    collegata = await _linked_invoice(body, cid, totals["totale"])
    for _ in range(5):
        last = await db.invoices.find_one({"anno": anno, "company_id": cid, "sezionale": sez}, {"_id": 0, "numero": 1, "data": 1}, sort=[("numero", -1)])
        if last and body.data < last["data"]:
            raise HTTPException(400, f"La data non può essere precedente all'ultimo documento dello stesso registro ({last['data']})")
        numero = (last["numero"] if last else 0) + 1
        doc = {
            "id": str(uuid.uuid4()), **body.model_dump(), **totals, "company_id": cid,
            "numero": numero, "anno": anno, "sezionale": sez, "numero_display": _display(numero, sez, anno),
            "fattura_collegata_id": collegata["id"] if collegata else None, "fattura_collegata": collegata,
            "progressivo_invio": await _next_progressivo(cid), "cliente": cliente,
            "status": "bozza", "sdi_id": None, "sdi_message": None,
            "sdi_history": [{"status": "bozza", "at": now_iso(), "message": f"Creata da {user.get('name') or user['email']}"}],
            "created_by": user["user_id"], "created_at": now_iso(), "updated_at": now_iso(),
        }
        try:
            await db.invoices.insert_one(doc)
            return await _get_invoice(doc["id"], cid)
        except DuplicateKeyError:
            continue
    raise HTTPException(409, "Numerazione occupata, riprova")


@api.put("/invoices/{iid}")
async def update_invoice(iid: str, body: InvoiceIn, t: dict = Depends(tenant)):
    cid = t["cid"]
    inv = await _get_invoice(iid, cid)
    if inv["status"] not in ("bozza", "scartata"):
        raise HTTPException(400, "La fattura è già stata inviata allo SDI e non è modificabile")
    _check_lines(body.lines)
    if int(body.data[:4]) != inv["anno"]:
        raise HTTPException(400, "Non puoi cambiare l'anno della fattura")
    if _sezionale(body.tipo_documento) != inv.get("sezionale", ""):
        raise HTTPException(400, "Non puoi trasformare una fattura in nota di credito (o viceversa): crea un nuovo documento")
    cliente = await _party_snapshot(body.party_id, cid, body.lines, body.cassa)
    totals = _totals(body)
    collegata = await _linked_invoice(body, cid, totals["totale"], iid)
    await db.invoices.update_one({"id": iid, "company_id": cid}, {"$set": {**body.model_dump(), **totals, "cliente": cliente, "updated_at": now_iso(),
                                                                         "fattura_collegata_id": collegata["id"] if collegata else None, "fattura_collegata": collegata}})
    return await _get_invoice(iid, cid)


@api.delete("/invoices/{iid}")
async def delete_invoice(iid: str, t: dict = Depends(tenant)):
    cid = t["cid"]
    inv = await _get_invoice(iid, cid)
    if inv["status"] != "bozza":
        raise HTTPException(400, "Solo le bozze possono essere eliminate")
    last = await db.invoices.find_one({"anno": inv["anno"], "company_id": cid, "sezionale": inv.get("sezionale", "")}, {"_id": 0, "numero": 1}, sort=[("numero", -1)])
    if last["numero"] != inv["numero"]:
        raise HTTPException(400, "Puoi eliminare solo l'ultima fattura numerata dell'anno (per non lasciare buchi nella numerazione)")
    if await db.invoices.find_one({"company_id": cid, "fattura_collegata_id": iid}):
        raise HTTPException(400, "Esistono note di credito collegate a questa fattura")
    await db.invoices.delete_one({"id": iid, "company_id": cid})
    return {"ok": True}


def _company_required(t: dict) -> dict:
    c = t["company"]
    if not c.get("partita_iva"):
        raise HTTPException(400, "Completa prima i dati azienda in Impostazioni")
    return c


@api.get("/invoices/{iid}/xml")
async def invoice_xml(iid: str, t: dict = Depends(tenant)):
    inv = await _get_invoice(iid, t["cid"])
    company = _company_required(t)
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


async def _push_status(iid: str, status: str, message: str, extra: dict = None, notifica: str = None):
    await db.invoices.update_one({"id": iid}, {
        "$set": {"status": status, "sdi_message": message, "sdi_notifica": notifica, "updated_at": now_iso(), **(extra or {})},
        "$push": {"sdi_history": {"status": status, "notifica": notifica, "at": now_iso(), "message": message}},
    })


@api.post("/invoices/{iid}/send")
async def send_sdi(iid: str, t: dict = Depends(tenant_accounting)):
    cid = t["cid"]
    inv = await _get_invoice(iid, cid)
    if inv["status"] not in ("bozza", "scartata"):
        raise HTTPException(400, "Fattura già inviata")
    company = _company_required(t)
    if inv.get("tipo_documento") == "TD04" and inv.get("fattura_collegata_id"):
        others = await db.invoices.find({"company_id": cid, "fattura_collegata_id": inv["fattura_collegata_id"], "id": {"$ne": iid},
                                         "status": {"$ne": "scartata"}}, {"_id": 0, "totale": 1}).to_list(500)
        residuo = round(inv["fattura_collegata"]["totale"] - sum(o["totale"] for o in others), 2)
        if inv["totale"] > residuo + 0.005:
            raise HTTPException(400, f"Importo superiore al residuo stornabile della fattura collegata ({residuo:.2f} €)")
    if inv["status"] == "scartata":
        inv["progressivo_invio"] = await _next_progressivo(cid)
        await db.invoices.update_one({"id": iid}, {"$set": {"progressivo_invio": inv["progressivo_invio"]}})
    fname = file_name(company, inv)
    sdi_id = str(uuid.uuid4().int)[:10]
    await _push_status(iid, "inviata", f"File {fname} trasmesso all'intermediario (SIMULATO). Id SDI {sdi_id}",
                       {"sdi_id": sdi_id, "sent_at": now_iso()}, notifica="IN")
    return await _get_invoice(iid, cid)


@api.post("/invoices/{iid}/refresh")
async def refresh_sdi(iid: str, t: dict = Depends(tenant)):
    inv = await _get_invoice(iid, t["cid"])
    if inv["status"] != "inviata":
        raise HTTPException(400, "Nessun esito da aggiornare")
    err = _sdi_checks(inv)
    c = inv["cliente"]
    if err:
        await _push_status(iid, "scartata", f"Notifica di scarto (NS): {err}", notifica="NS")
    elif (c.get("codice_destinatario") or "0000000") == "0000000" and not c.get("pec"):
        await _push_status(iid, "mancata_consegna", "Notifica di mancata consegna (MC): fattura a disposizione del cliente nell'area riservata Fatture e Corrispettivi", notifica="MC")
    else:
        await _push_status(iid, "consegnata", "Ricevuta di consegna (RC): fattura recapitata al destinatario", notifica="RC")
    return await _get_invoice(iid, t["cid"])


class StornoIn(BaseModel):
    invia: bool = False


@api.post("/invoices/{iid}/storno-totale")
async def storno_totale(iid: str, body: StornoIn, t: dict = Depends(tenant)):
    cid = t["cid"]
    if body.invia and t["user"].get("role") not in ("admin", "contabile"):
        raise HTTPException(403, "L'invio allo SDI è riservato ad Admin e Contabile")
    orig = await _get_invoice(iid, cid)
    if orig.get("tipo_documento") == "TD04":
        raise HTTPException(400, "Non puoi stornare una nota di credito")
    if orig["status"] not in SENT:
        raise HTTPException(400, "Puoi stornare solo fatture già inviate allo SDI")
    if await db.invoices.find_one({"company_id": cid, "fattura_collegata_id": iid, "status": {"$ne": "scartata"}}):
        raise HTTPException(400, "La fattura ha già note di credito collegate: usa lo storno parziale per il residuo")
    d = orig["data"].split("-")
    nc_in = InvoiceIn(
        tipo_documento="TD04", data=datetime.now(timezone.utc).date().isoformat(), party_id=orig["party_id"],
        lines=[LineIn(**{k: ln.get(k) for k in ("descrizione", "quantita", "unita_misura", "prezzo_unitario", "aliquota", "natura")}) for ln in orig["lines"]],
        causale=f"Storno totale fattura n. {orig['numero_display']} del {d[2]}/{d[1]}/{d[0]}",
        modalita_pagamento=orig.get("modalita_pagamento") or "MP05",
        cassa=CassaIn(**orig["cassa"]) if orig.get("cassa") else None,
        ritenuta=RitenutaIn(**orig["ritenuta"]) if orig.get("ritenuta") else None,
        fattura_collegata_id=iid,
    )
    nc = await create_invoice(nc_in, t)
    if body.invia:
        nc = await send_sdi(nc["id"], t)
    return nc


# ---------- Dashboard ----------
@api.get("/dashboard")
async def dashboard(t: dict = Depends(tenant)):
    invs = await db.invoices.find({"company_id": t["cid"]}, {"_id": 0, "sdi_history": 0, "lines": 0, "riepilogo": 0}).to_list(10000)
    year = datetime.now(timezone.utc).year
    counts = {s: 0 for s in STATUSES}
    fatt = imp = iva = nc_tot = 0.0
    nc_count = 0
    months = [{"mese": m, "totale": 0.0} for m in range(1, 13)]
    notif_status = {"attesa": "inviata", "RC": "consegnata", "MC": "mancata_consegna", "NS": "scartata"}
    notifiche = {k: {"count": 0, "totale": 0.0, "status": s} for k, s in notif_status.items()}
    by_status = {s: k for k, s in notif_status.items()}
    for i in invs:
        counts[i["status"]] = counts.get(i["status"], 0) + 1
        if i["status"] in by_status:
            n = notifiche[by_status[i["status"]]]
            n["count"] += 1
            n["totale"] = round(n["totale"] + (-i["totale"] if i.get("tipo_documento") == "TD04" else i["totale"]), 2)
        if i["status"] in SENT:
            sign = -1 if i.get("tipo_documento") == "TD04" else 1
            if sign < 0:
                nc_tot += i["totale"]
                nc_count += 1
            fatt += sign * i["totale"]
            imp += sign * i["imponibile"]
            iva += sign * i["iva"]
            if i["anno"] == year:
                months[int(i["data"][5:7]) - 1]["totale"] += sign * i["totale"]
    recent = sorted(invs, key=lambda x: x["created_at"], reverse=True)[:6]
    sent_total = sum(n["count"] for n in notifiche.values())
    last = await db.invoices.find({"company_id": t["cid"], "status": {"$ne": "bozza"}}, {"_id": 0, "id": 1, "numero_display": 1, "cliente.denominazione": 1, "totale": 1, "status": 1, "sdi_notifica": 1, "sdi_message": 1, "updated_at": 1}).sort("updated_at", -1).to_list(8)
    return {"counts": counts, "fatturato": round(fatt, 2), "imponibile": round(imp, 2), "iva": round(iva, 2),
            "anno": year, "mesi": months, "recenti": recent, "totale_fatture": len(invs),
            "notifiche": notifiche, "inviate_totale": sent_total, "ultime_notifiche": last,
            "note_credito": {"count": nc_count, "totale": round(nc_tot, 2)}}


async def _migrate_single_company():
    if await db.companies.count_documents({}) == 0:
        old = await db.company.find_one({"key": "main"}, {"_id": 0, "key": 0})
        if old:
            cid = str(uuid.uuid4())
            await db.companies.insert_one({"id": cid, **old, "created_at": now_iso()})
            for coll in (db.parties, db.articles, db.invoices):
                await coll.update_many({"company_id": {"$exists": False}}, {"$set": {"company_id": cid}})
            await db.users.update_many({}, {"$addToSet": {"company_ids": cid}})
            seq = await db.counters.find_one({"key": "progressivo"})
            if seq:
                await db.counters.insert_one({"key": f"progressivo_{cid}", "v": seq["v"]})
            await db.company.delete_many({})
    for coll, name in ((db.invoices, "anno_1_numero_1"), (db.articles, "codice_unique"), (db.invoices, "company_anno_numero")):
        try:
            await coll.drop_index(name)
        except Exception:
            pass


@app.on_event("startup")
async def init_indexes():
    await _migrate_single_company()
    await db.invoices.update_many({"sezionale": {"$exists": False}}, {"$set": {"sezionale": ""}})
    await db.invoices.create_index([("company_id", 1), ("sezionale", 1), ("anno", 1), ("numero", 1)], unique=True, name="company_sez_anno_numero")
    await db.invoices.create_index("fattura_collegata_id")
    await db.users.create_index("email", unique=True)
    await db.password_reset_tokens.create_index("expires_at", expireAfterSeconds=0)
    await db.login_attempts.create_index("identifier")
    await db.articles.create_index([("company_id", 1), ("codice", 1)], unique=True, name="company_codice")
    await db.parties.create_index("company_id")
    await db.companies.create_index("id", unique=True)


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

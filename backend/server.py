from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, UploadFile, File
from fastapi.responses import Response as RawResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError
import os
import re
import logging
import uuid
import base64
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
from scadenzario import build_ledger, per_cliente  # noqa: E402
from estratto import build_pdf, eur as _eur_pdf, itd  # noqa: E402
from passive import extract_xml, parse_fattura, sha, demo_xmls  # noqa: E402
import random  # noqa: E402

client = AsyncIOMotorClient(os.environ['MONGO_URL'])
db = client[os.environ['DB_NAME']]
ADMIN_EMAIL = os.environ['ADMIN_EMAIL'].strip().lower()
APP_URL = os.environ['APP_URL'].rstrip("/")
USER_PROJ = {"_id": 0, "password_hash": 0}

app = FastAPI()
api = APIRouter(prefix="/api")


class FieldError(ValueError):
    def __init__(self, field: str, msg: str):
        super().__init__(msg)
        self.field = field


def ferr(status: int, field: str, msg: str) -> HTTPException:
    return HTTPException(status, [{"loc": ["body", *field.split(".")], "msg": msg, "type": "value_error"}])


def _it_msg(e: dict) -> str:
    t, c = e["type"], {k: (f"{v:g}" if isinstance(v, float) else v) for k, v in (e.get("ctx") or {}).items()}
    m = {"missing": "Campo obbligatorio", "string_too_short": "Campo obbligatorio" if c.get("min_length") == 1 else f"Minimo {c.get('min_length')} caratteri",
         "string_too_long": f"Massimo {c.get('max_length')} caratteri", "greater_than": f"Deve essere maggiore di {c.get('gt')}",
         "greater_than_equal": f"Deve essere almeno {c.get('ge')}", "less_than_equal": f"Deve essere al massimo {c.get('le')}",
         "float_parsing": "Inserisci un numero valido", "float_type": "Inserisci un numero valido", "int_parsing": "Inserisci un numero intero",
         "int_type": "Inserisci un numero intero", "bool_type": "Valore non valido", "string_type": "Campo obbligatorio", "literal_error": "Valore non valido",
         "too_short": "Inserisci almeno una riga", "string_pattern_mismatch": "Formato non valido"}
    return m.get(t) or e["msg"].replace("Value error, ", "")


@app.exception_handler(RequestValidationError)
async def _validation_handler(request: Request, exc: RequestValidationError):
    out = []
    for e in exc.errors():
        err = (e.get("ctx") or {}).get("error")
        loc = list(e["loc"]) + ([err.field] if isinstance(err, FieldError) else [])
        out.append({"loc": loc, "msg": _it_msg(e), "type": e["type"]})
    return JSONResponse(status_code=422, content={"detail": out})

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
        raise ferr(400, "email", "Email già registrata: accedi o usa 'Password dimenticata'")
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
        raise ferr(400, "email", "Esiste già un utente con questa email")
    user = {
        "user_id": f"user_{uuid.uuid4().hex[:12]}", "email": body.email, "name": body.name.strip(), "picture": None,
        "email_verified": False, "role": body.role, "status": "approved", "created_at": now_iso(),
        "created_by": admin["user_id"], "company_ids": await _valid_company_ids(body.company_ids),
    }
    try:
        await db.users.insert_one(user)
    except DuplicateKeyError:
        raise ferr(400, "email", "Esiste già un utente con questa email")
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
        raise ferr(400, "partita_iva", "Esiste già un'azienda con questa Partita IVA")
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
        raise ferr(400, "partita_iva", "Esiste già un'altra azienda con questa Partita IVA")
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
    pubblica_amministrazione: bool = False
    split_payment: bool = False

    @model_validator(mode="after")
    def _esenzione(self):
        cd = self.codice_destinatario or ""
        if self.pubblica_amministrazione:
            if not re.fullmatch(r"[A-Z0-9]{6}", cd):
                raise FieldError("codice_destinatario", "Pubblica Amministrazione: il Codice Univoco Ufficio (IPA) deve avere 6 caratteri")
        else:
            self.split_payment = False
            cd = cd or "0000000"
            if not re.fullmatch(r"[A-Z0-9]{7}", cd):
                raise FieldError("codice_destinatario", "Il Codice Destinatario deve avere 7 caratteri")
            self.codice_destinatario = cd
        n = self.natura_default or ""
        if n and n not in NATURE:
            raise FieldError("natura_default", "Natura IVA di esenzione non valida")
        if n == "N3.5":
            prot = (self.intento_protocollo or "").strip()
            if not re.fullmatch(r"\d{17}-\d{6}", prot):
                raise FieldError("intento_protocollo", "Dichiarazione d'intento: protocollo obbligatorio nel formato 17 cifre-6 cifre")
            try:
                self.intento_data = date.fromisoformat(self.intento_data or "").isoformat()
            except ValueError:
                raise FieldError("intento_data", "Dichiarazione d'intento: data di protocollo obbligatoria")
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
        return _clean(v or "").upper()


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
            raise FieldError("aliquota", "Aliquota IVA non valida")
        if self.aliquota == 0 and self.natura not in NATURE:
            raise FieldError("natura", "Indica la Natura IVA per l'aliquota 0%")
        if self.aliquota != 0:
            self.natura = None
        return self


@api.get("/articles")
async def list_articles(t: dict = Depends(tenant)):
    return await db.articles.find({"company_id": t["cid"]}, {"_id": 0}).sort("codice", 1).to_list(5000)


@api.post("/articles")
async def create_article(body: ArticleIn, t: dict = Depends(tenant)):
    if await db.articles.find_one({"codice": body.codice, "company_id": t["cid"]}):
        raise ferr(400, "codice", "Codice articolo già esistente")
    doc = {"id": str(uuid.uuid4()), **body.model_dump(), "company_id": t["cid"], "created_at": now_iso()}
    await db.articles.insert_one(doc)
    return await db.articles.find_one({"id": doc["id"]}, {"_id": 0})


@api.put("/articles/{aid}")
async def update_article(aid: str, body: ArticleIn, t: dict = Depends(tenant)):
    if await db.articles.find_one({"codice": body.codice, "company_id": t["cid"], "id": {"$ne": aid}}):
        raise ferr(400, "codice", "Codice articolo già esistente")
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
            raise FieldError("tipo", "Tipo cassa previdenziale non valido")
        if self.aliquota_iva not in ALIQUOTE:
            raise FieldError("aliquota_iva", "Aliquota IVA della cassa non valida")
        if self.aliquota_iva == 0 and self.natura not in NATURE:
            raise FieldError("natura", "Indica la Natura IVA della cassa con aliquota 0%")
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
    note: Optional[str] = Field(default="", max_length=500)

    @field_validator("aliquota")
    @classmethod
    def _al(cls, v):
        if v not in ALIQUOTE:
            raise ValueError("Aliquota IVA non valida")
        return v


class RataIn(BaseModel):
    scadenza: str
    importo: float = Field(gt=0, le=10_000_000)

    @field_validator("scadenza")
    @classmethod
    def _d(cls, v):
        try:
            return date.fromisoformat(v).isoformat()
        except (TypeError, ValueError):
            raise ValueError("Data di scadenza non valida")


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
    numero: Optional[int] = Field(default=None, ge=1, le=999999)
    rif_tipo: Literal["ordine", "contratto", "convenzione"] = "ordine"
    rif_documento: Optional[str] = Field(default="", max_length=20)
    rif_data: Optional[str] = ""
    cig: Optional[str] = ""
    cup: Optional[str] = ""
    rate: List[RataIn] = Field(default_factory=list, max_length=36)

    @field_validator("cig", "cup")
    @classmethod
    def _cigcup(cls, v, info):
        v = _clean(v or "").upper()
        n = 10 if info.field_name == "cig" else 15
        if v and not re.fullmatch(rf"[A-Z0-9]{{{n}}}", v):
            raise ValueError(f"Il codice {info.field_name.upper()} deve avere {n} caratteri alfanumerici")
        return v

    @field_validator("rif_data")
    @classmethod
    def _rifdata(cls, v):
        if not v:
            return ""
        try:
            return date.fromisoformat(v).isoformat()
        except ValueError:
            raise ValueError("Data del documento di riferimento non valida")

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


def _totals(body: InvoiceIn, cliente: dict) -> dict:
    return compute_totals([ln.model_dump() for ln in body.lines],
                          body.cassa.model_dump() if body.cassa else None,
                          body.ritenuta.model_dump() if body.ritenuta else None,
                          bool(cliente.get("pubblica_amministrazione") and cliente.get("split_payment")))


def _check_rate(body: InvoiceIn, totals: dict):
    if body.tipo_documento == "TD04":
        body.rate = []
    if not body.rate:
        return
    for i, r in enumerate(body.rate):
        if r.scadenza < body.data:
            raise ferr(422, f"rate.{i}.scadenza", f"Rata {i + 1}: la scadenza non può precedere la data della fattura")
    s = round(sum(r.importo for r in body.rate), 2)
    if abs(s - totals["netto"]) > 0.01:
        raise ferr(422, "rate", f"La somma delle rate ({_eur(s)}) deve essere uguale al netto a pagare ({_eur(totals['netto'])})")
    body.rate = sorted(body.rate, key=lambda r: r.scadenza)
    body.scadenza = body.rate[-1].scadenza


def _check_pa(body: InvoiceIn, cliente: dict):
    if not cliente.get("pubblica_amministrazione"):
        body.cig, body.cup, body.rif_documento, body.rif_data = "", "", "", ""
    elif (body.cig or body.cup) and not (body.rif_documento or "").strip():
        raise ferr(422, "rif_documento", "Per indicare CIG/CUP inserisci il numero del documento di riferimento (ordine, contratto o convenzione)")


def _check_lines(lines: List[LineIn]):
    for i, ln in enumerate(lines):
        if ln.aliquota == 0 and ln.natura not in NATURE:
            raise ferr(422, f"lines.{i}.natura", f"Indica la Natura IVA per la riga \"{ln.descrizione}\" con aliquota 0%")


async def _party_snapshot(pid: str, cid: str, lines: List[LineIn] = (), cassa: Optional[CassaIn] = None) -> dict:
    p = await db.parties.find_one({"id": pid, "tipo": "cliente", "company_id": cid}, {"_id": 0})
    if not p:
        raise ferr(400, "party_id", "Seleziona un cliente")
    if any(ln.aliquota == 0 and ln.natura == "N3.5" for ln in lines) or (cassa is not None and cassa.natura == "N3.5"):
        if not p.get("intento_protocollo"):
            raise ferr(422, "party_id", "Natura N3.5: inserisci nell'anagrafica del cliente protocollo e data della dichiarazione d'intento")
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


def _eur(v: float) -> str:
    return f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _it_date(d: str) -> str:
    return "/".join(reversed(d.split("-")))


async def _check_sequence(cid: str, sez: str, anno: int, numero: int, data: str, exclude: Optional[str] = None):
    base = {"company_id": cid, "sezionale": sez, "anno": anno, "id": {"$ne": exclude}}
    if await db.invoices.find_one({**base, "numero": numero}, {"_id": 1}):
        raise ferr(400, "numero", f"Il numero {_display(numero, sez, anno)} è già usato da un altro documento")
    last = await db.invoices.find_one(base, {"_id": 0, "numero": 1}, sort=[("numero", -1)])
    if last and numero > last["numero"] + 1:
        raise ferr(400, "numero", f"Numerazione non progressiva: il prossimo numero disponibile è {_display(last['numero'] + 1, sez, anno)}")
    prev = await db.invoices.find_one({**base, "numero": {"$lt": numero}}, {"_id": 0, "numero_display": 1, "data": 1}, sort=[("numero", -1)])
    if prev and data < prev["data"]:
        raise ferr(400, "data", f"Data non coerente: il documento precedente N. {prev['numero_display']} è del {_it_date(prev['data'])}")
    nxt = await db.invoices.find_one({**base, "numero": {"$gt": numero}}, {"_id": 0, "numero_display": 1, "data": 1}, sort=[("numero", 1)])
    if nxt and data > nxt["data"]:
        raise ferr(400, "data", f"Data non coerente: il documento successivo N. {nxt['numero_display']} è del {_it_date(nxt['data'])}")


async def _linked_invoice(body: InvoiceIn, cid: str, totale: float, current_id: str = None) -> Optional[dict]:
    if body.tipo_documento != "TD04" or not body.fattura_collegata_id:
        return None
    orig = await db.invoices.find_one({"id": body.fattura_collegata_id, "company_id": cid}, {"_id": 0, "sdi_history": 0})
    if not orig or orig.get("tipo_documento") == "TD04":
        raise ferr(400, "fattura_collegata_id", "Fattura collegata non trovata")
    if orig["party_id"] != body.party_id:
        raise ferr(400, "party_id", "La nota di credito deve essere intestata allo stesso cliente della fattura collegata")
    if orig["status"] not in SENT:
        raise HTTPException(400, "Puoi stornare solo fatture già inviate allo SDI")
    others = await db.invoices.find({"company_id": cid, "fattura_collegata_id": orig["id"], "id": {"$ne": current_id},
                                     "status": {"$ne": "scartata"}}, {"_id": 0, "totale": 1}).to_list(500)
    residuo = round(orig["totale"] - sum(o["totale"] for o in others), 2)
    if totale > residuo + 0.005:
        raise ferr(400, "fattura_collegata_id", f"Importo superiore al residuo stornabile della fattura {orig['numero_display']} ({_eur(residuo)})")
    return {"id": orig["id"], "numero_display": orig["numero_display"], "data": orig["data"], "totale": orig["totale"]}


@api.get("/invoices")
async def list_invoices(status: Optional[str] = None, t: dict = Depends(tenant)):
    q = {"company_id": t["cid"], **({"status": status} if status else {})}
    items = await db.invoices.find(q, {"_id": 0, "sdi_history": 0}).sort([("anno", -1), ("numero", -1)]).to_list(5000)
    stornate = set(await db.invoices.distinct("fattura_collegata_id", {"company_id": t["cid"], "status": {"$ne": "scartata"}, "fattura_collegata_id": {"$ne": None}}))
    for i in items:
        i["has_nc"] = i["id"] in stornate
    return items


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
    _check_pa(body, cliente)
    anno = int(body.data[:4])
    totals = _totals(body, cliente)
    _check_rate(body, totals)
    sez = _sezionale(body.tipo_documento)
    collegata = await _linked_invoice(body, cid, totals["totale"])
    for _ in range(1 if body.numero else 5):
        if body.numero:
            numero = body.numero
        else:
            last = await db.invoices.find_one({"anno": anno, "company_id": cid, "sezionale": sez}, {"_id": 0, "numero": 1}, sort=[("numero", -1)])
            numero = (last["numero"] if last else 0) + 1
        await _check_sequence(cid, sez, anno, numero, body.data)
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
    raise HTTPException(409, "Numero già usato da un altro documento" if body.numero else "Numerazione occupata, riprova")


@api.put("/invoices/{iid}")
async def update_invoice(iid: str, body: InvoiceIn, t: dict = Depends(tenant)):
    cid = t["cid"]
    inv = await _get_invoice(iid, cid)
    if inv["status"] not in ("bozza", "scartata"):
        raise HTTPException(400, "Il documento è già stato inviato allo SDI e non è più modificabile")
    if inv["status"] == "scartata" and body.numero and body.numero != inv["numero"]:
        raise ferr(400, "numero", "Una fattura scartata va reinviata con lo stesso numero")
    _check_lines(body.lines)
    if int(body.data[:4]) != inv["anno"]:
        raise ferr(400, "data", "Non puoi cambiare l'anno della fattura")
    if _sezionale(body.tipo_documento) != inv.get("sezionale", ""):
        raise HTTPException(400, "Non puoi trasformare una fattura in nota di credito (o viceversa): crea un nuovo documento")
    cliente = await _party_snapshot(body.party_id, cid, body.lines, body.cassa)
    _check_pa(body, cliente)
    totals = _totals(body, cliente)
    _check_rate(body, totals)
    collegata = await _linked_invoice(body, cid, totals["totale"], iid)
    numero = body.numero or inv["numero"]
    await _check_sequence(cid, inv.get("sezionale", ""), inv["anno"], numero, body.data, iid)
    try:
        await db.invoices.update_one({"id": iid, "company_id": cid}, {"$set": {**body.model_dump(exclude={"numero"}), **totals, "cliente": cliente, "updated_at": now_iso(),
                                                                         "numero": numero, "numero_display": _display(numero, inv.get("sezionale", ""), inv["anno"]),
                                                                         "fattura_collegata_id": collegata["id"] if collegata else None, "fattura_collegata": collegata}})
    except DuplicateKeyError:
        raise HTTPException(409, "Numero già usato da un altro documento")
    if inv["status"] == "scartata":
        await db.invoices.update_one({"id": iid}, {"$push": {"sdi_history": {"status": "scartata", "at": now_iso(),
                                      "message": f"Corretta dopo lo scarto da {t['user'].get('name') or t['user']['email']}, pronta per il reinvio"}}})
    return await _get_invoice(iid, cid)


@api.delete("/invoices/{iid}")
async def delete_invoice(iid: str, t: dict = Depends(tenant)):
    cid = t["cid"]
    inv = await _get_invoice(iid, cid)
    if inv["status"] != "bozza":
        raise HTTPException(400, "Il documento è già stato inviato allo SDI e non può essere eliminato")
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
            raise HTTPException(400, f"Importo superiore al residuo stornabile della fattura collegata ({_eur(residuo)})")
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
        lines=[LineIn(**{k: ln.get(k) for k in ("descrizione", "quantita", "unita_misura", "prezzo_unitario", "aliquota", "natura", "note")}) for ln in orig["lines"]],
        causale=f"Storno totale fattura n. {orig['numero_display']} del {d[2]}/{d[1]}/{d[0]}",
        modalita_pagamento=orig.get("modalita_pagamento") or "MP05",
        cassa=CassaIn(**orig["cassa"]) if orig.get("cassa") else None,
        ritenuta=RitenutaIn(**orig["ritenuta"]) if orig.get("ritenuta") else None,
        fattura_collegata_id=iid,
        **{k: orig.get(k) or "" for k in ("rif_documento", "rif_data", "cig", "cup")}, rif_tipo=orig.get("rif_tipo") or "ordine",
    )
    nc = await create_invoice(nc_in, t)
    if body.invia:
        nc = await send_sdi(nc["id"], t)
    return nc


# ---------- Ricerca Indice PA ----------
IPA_SEARCH = "https://indicepa.gov.it/ipa-dati/api/3/action/datastore_search"
IPA_RESOURCE = "57bd2be0-4d3d-41cd-bdb8-2f0a60d6f490"


@api.get("/ipa/search")
async def ipa_search(q: str, user: dict = Depends(approved_user)):
    q = q.strip()
    if len(q) < 3:
        raise HTTPException(400, "Scrivi almeno 3 caratteri")
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(IPA_SEARCH, params={"resource_id": IPA_RESOURCE, "q": q[:100], "limit": 20})
            r.raise_for_status()
            recs = r.json()["result"]["records"]
    except (httpx.HTTPError, KeyError, ValueError):
        raise HTTPException(502, "Indice PA non raggiungibile, riprova tra poco")
    return [{"codice_uo": x.get("Codice_uni_uo") or "", "descrizione_uo": x.get("Descrizione_uo") or "",
             "ente": x.get("Denominazione_ente") or "", "codice_fiscale": x.get("Codice_fiscale_sfe") or x.get("Codice_fiscale_ente") or "",
             "indirizzo": x.get("Indirizzo") or "", "cap": x.get("CAP") or "",
             "pec": x.get("Mail1") if x.get("Tipo_Mail1") == "Pec" else "", "categoria": x.get("Nome_Categoria") or ""}
            for x in recs if x.get("Codice_uni_uo")]


# ---------- Scadenzario ----------
METODI = Literal["bonifico", "contanti", "assegno", "carta", "riba", "rid", "altro", "compensazione"]


class PagamentoIn(BaseModel):
    data: str
    importo: float = Field(gt=0, le=10_000_000)
    metodo: METODI = "bonifico"
    note: Optional[str] = Field(default="", max_length=200)
    nc_id: Optional[str] = None

    @field_validator("data")
    @classmethod
    def _d(cls, v):
        try:
            d = date.fromisoformat(v)
        except (TypeError, ValueError):
            raise ValueError("Data non valida")
        if d > datetime.now(timezone.utc).date() + timedelta(days=1):
            raise ValueError("La data del pagamento non può essere futura")
        return d.isoformat()


LEDGER_PROJ = {"_id": 0, "id": 1, "numero": 1, "numero_display": 1, "data": 1, "party_id": 1, "cliente.denominazione": 1, "totale": 1,
               "netto": 1, "rate": 1, "scadenza": 1, "tipo_documento": 1, "fattura_collegata_id": 1}


async def _ledger(cid: str, party_id: Optional[str] = None):
    q = {"company_id": cid, "status": {"$in": list(SENT)}}
    if party_id:
        q["party_id"] = party_id
    invs = await db.invoices.find(q, LEDGER_PROJ).to_list(20000)
    pq = {"company_id": cid, **({"party_id": party_id} if party_id else {})}
    pays = await db.payments.find(pq, {"_id": 0}).to_list(50000)
    today = datetime.now(timezone.utc).date().isoformat()
    docs, crediti = build_ledger(invs, pays, today)
    return docs, crediti, pays, today


@api.get("/scadenzario")
async def scadenzario(party_id: Optional[str] = None, t: dict = Depends(tenant)):
    docs, crediti, _, today = await _ledger(t["cid"], party_id)
    return _scad_response(docs, crediti, today)


def _scad_response(docs, crediti, today):
    clienti = per_cliente(docs, crediti, today)
    rate = [{**r, "invoice_id": d["id"], "numero_display": d["numero_display"], "data": d["data"], "party_id": d["party_id"],
             "cliente": d["cliente"], "residuo_documento": d["residuo"]} for d in docs for r in d["rate"]]
    rate.sort(key=lambda r: (r["scadenza"], r["numero_display"]))
    tot = {k: round(sum(c[k] for c in clienti), 2) for k in ("aperto", "scaduto", "entro_30", "oltre_30", "crediti")}
    return {"oggi": today, "rate": rate, "clienti": clienti, "crediti": crediti, "totali": tot}


@api.get("/invoices/{iid}/pagamenti")
async def invoice_payments(iid: str, t: dict = Depends(tenant)):
    inv = await _get_invoice(iid, t["cid"])
    docs, crediti, pays, _ = await _ledger(t["cid"], inv["party_id"])
    doc = next((d for d in docs if d["id"] == iid), None)
    return {"scadenzario": doc, "pagamenti": sorted([p for p in pays if p["invoice_id"] == iid], key=lambda p: p["data"]), "crediti": crediti}


@api.post("/invoices/{iid}/pagamenti")
async def add_payment(iid: str, body: PagamentoIn, t: dict = Depends(tenant_accounting)):
    cid = t["cid"]
    inv = await _get_invoice(iid, cid)
    if inv.get("tipo_documento") == "TD04" or inv["status"] not in SENT:
        raise HTTPException(400, "Gli incassi si registrano solo su fatture inviate allo SDI")
    docs, crediti, _, _ = await _ledger(cid, inv["party_id"])
    doc = next(d for d in docs if d["id"] == iid)
    if body.importo > doc["residuo"] + 0.005:
        raise ferr(400, "importo", f"Importo superiore al residuo da incassare ({_eur(doc['residuo'])})")
    if body.data < inv["data"]:
        raise ferr(400, "data", f"La data dell'incasso non può precedere la data della fattura ({_it_date(inv['data'])})")
    nc = None
    if body.metodo == "compensazione" or body.nc_id:
        nc = next((c for c in crediti if c["id"] == body.nc_id), None)
        if not nc:
            raise ferr(400, "nc_id", "Seleziona una nota di credito dello stesso cliente con credito disponibile")
        if body.importo > nc["residuo"] + 0.005:
            raise ferr(400, "importo", f"Importo superiore al credito disponibile della nota {nc['numero_display']} ({_eur(nc['residuo'])})")
        body.metodo = "compensazione"
    p = {"id": str(uuid.uuid4()), **body.model_dump(), "importo": round(body.importo, 2), "company_id": cid, "invoice_id": iid,
         "party_id": inv["party_id"], "numero_display": inv["numero_display"], "nc_numero": nc["numero_display"] if nc else None,
         "created_by": t["user"]["user_id"], "created_by_name": t["user"].get("name") or t["user"]["email"], "created_at": now_iso()}
    await db.payments.insert_one(p)
    p.pop("_id", None)
    return p


@api.delete("/pagamenti/{pid}")
async def delete_payment(pid: str, t: dict = Depends(tenant_accounting)):
    r = await db.payments.delete_one({"id": pid, "company_id": t["cid"]})
    if not r.deleted_count:
        raise HTTPException(404, "Incasso non trovato")
    return {"ok": True}


# ---------- Fatture passive ----------
PASSIVE_LIST = {"_id": 0, "xml_b64": 0, "lines": 0, "riepilogo": 0}


async def _supplier(cid: str, f: dict) -> str:
    q = [{"partita_iva": f["partita_iva"]}] if f.get("partita_iva") else []
    q += [{"codice_fiscale": f["codice_fiscale"]}] if f.get("codice_fiscale") else []
    if q:
        p = await db.parties.find_one({"company_id": cid, "tipo": "fornitore", "$or": q}, {"_id": 0, "id": 1})
        if p:
            return p["id"]
    doc = {"id": str(uuid.uuid4()), "company_id": cid, "tipo": "fornitore", "denominazione": f["denominazione"] or "Fornitore senza nome",
           "partita_iva": f.get("partita_iva", ""), "codice_fiscale": f.get("codice_fiscale", ""), "codice_destinatario": "0000000", "pec": "",
           "email": f.get("email", ""), "telefono": "", "indirizzo": f.get("indirizzo", ""), "cap": f.get("cap", ""), "comune": f.get("comune", ""),
           "provincia": f.get("provincia", ""), "nazione": f.get("nazione") or "IT", "natura_default": "", "riferimento_normativo": "",
           "intento_protocollo": "", "intento_data": "", "pubblica_amministrazione": False, "split_payment": False,
           "origine": "fattura_passiva", "created_at": now_iso()}
    await db.parties.insert_one(doc)
    return doc["id"]


async def _import_passive(t: dict, raw: bytes, file_name: str, origine: str) -> list:
    cid, comp = t["cid"], t["company"]
    xml = extract_xml(raw)
    parsed = parse_fattura(xml)
    ces = parsed["cessionario"]
    ids = {x for x in (comp.get("partita_iva"), comp.get("codice_fiscale")) if x}
    if ids and not ({ces.get("partita_iva"), ces.get("codice_fiscale")} & ids):
        raise ValueError(f"Fattura intestata a un altro soggetto ({ces.get('denominazione') or ces.get('partita_iva')}), non a {comp['denominazione']}")
    h = sha(xml)
    if await db.passive_invoices.find_one({"company_id": cid, "hash": h}, {"_id": 1}):
        raise ValueError("File già importato")
    f = parsed["fornitore"]
    pid = await _supplier(cid, f)
    for d in parsed["docs"]:
        if await db.passive_invoices.find_one({"company_id": cid, "party_id": pid, "numero": d["numero"], "data": d["data"], "tipo_documento": d["tipo_documento"]}, {"_id": 1}):
            raise ValueError(f"Documento {d['numero']} del {_it_date(d['data'])} di {f['denominazione']} già presente")
    out = []
    for i, d in enumerate(parsed["docs"]):
        coll = None
        if d["tipo_documento"] == "TD04" and d["collegate"]:
            coll = await db.passive_invoices.find_one({"company_id": cid, "party_id": pid, "numero": {"$in": d["collegate"]}, "tipo_documento": {"$ne": "TD04"}}, {"_id": 0, "id": 1})
        doc = {"id": str(uuid.uuid4()), "company_id": cid, "origine": origine, "file_name": file_name, "hash": h if i == 0 else f"{h}:{i}",
               "xml_b64": base64.b64encode(xml).decode(), "sdi_progressivo": parsed["progressivo"], "fornitore": f, "party_id": pid,
               **d, "numero_display": d["numero"], "scadenza": d["rate"][-1]["scadenza"] if d["rate"] else d["data"],
               "fattura_collegata_id": coll["id"] if coll else None, "stato_reg": "da_registrare", "note": "",
               "ricevuta_at": now_iso(), "created_by_name": t["user"].get("name") or t["user"]["email"]}
        await db.passive_invoices.insert_one(doc)
        if d["tipo_documento"] != "TD04":
            await db.passive_invoices.update_many({"company_id": cid, "party_id": pid, "tipo_documento": "TD04", "fattura_collegata_id": None, "collegate": d["numero"]},
                                                  {"$set": {"fattura_collegata_id": doc["id"]}})
        out.append({"id": doc["id"], "numero": d["numero"], "fornitore": f["denominazione"], "totale": d["totale"]})
    return out


@api.post("/passive/upload")
async def passive_upload(files: List[UploadFile] = File(...), t: dict = Depends(tenant_accounting)):
    if len(files) > 20:
        raise HTTPException(400, "Puoi caricare al massimo 20 file alla volta")
    res = []
    for fl in files:
        raw = await fl.read(5 * 1024 * 1024 + 1)
        name = (fl.filename or "file")[:120]
        if len(raw) > 5 * 1024 * 1024:
            res.append({"file": name, "ok": False, "error": "File troppo grande (max 5 MB)"})
            continue
        try:
            res.append({"file": name, "ok": True, "documenti": await _import_passive(t, raw, name, "upload")})
        except ValueError as e:
            res.append({"file": name, "ok": False, "error": str(e)})
    return res


@api.post("/passive/sdi-sync")
async def passive_sdi_sync(t: dict = Depends(tenant_accounting)):
    if not t["company"].get("partita_iva"):
        raise HTTPException(400, "Inserisci la Partita IVA nei dati azienda")
    docs = []
    for k, x in enumerate(demo_xmls(t["company"], random.randint(1, 3))):
        try:
            docs += await _import_passive(t, x, f"SDI_simulato_{k + 1}.xml", "sdi_simulato")
        except ValueError:
            continue
    return {"ricevute": docs}


@api.get("/passive")
async def list_passive(stato: Optional[str] = None, party_id: Optional[str] = None, t: dict = Depends(tenant)):
    q = {"company_id": t["cid"]}
    if stato in ("da_registrare", "registrata", "contestata"):
        q["stato_reg"] = stato
    if party_id:
        q["party_id"] = party_id
    return await db.passive_invoices.find(q, PASSIVE_LIST).sort([("data", -1), ("ricevuta_at", -1)]).to_list(5000)


async def _get_passive(pid: str, cid: str, proj=None) -> dict:
    d = await db.passive_invoices.find_one({"id": pid, "company_id": cid}, proj or {"_id": 0, "xml_b64": 0})
    if not d:
        raise HTTPException(404, "Fattura passiva non trovata")
    return d


@api.get("/passive/{pid}")
async def get_passive(pid: str, t: dict = Depends(tenant)):
    return await _get_passive(pid, t["cid"])


@api.get("/passive/{pid}/xml")
async def passive_xml(pid: str, t: dict = Depends(tenant)):
    d = await _get_passive(pid, t["cid"], {"_id": 0, "xml_b64": 1, "file_name": 1})
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", d["file_name"]).rsplit(".p7m", 1)[0]
    return RawResponse(base64.b64decode(d["xml_b64"]), media_type="application/xml", headers={"Content-Disposition": f'attachment; filename="{name if name.endswith(".xml") else name + ".xml"}"'})


class PassivePatch(BaseModel):
    stato_reg: Optional[Literal["da_registrare", "registrata", "contestata"]] = None
    note: Optional[str] = Field(default=None, max_length=1000)
    rate: Optional[List[RataIn]] = None
    data_registrazione: Optional[str] = None
    aliquota_rc: Optional[float] = None


RC_ALIQUOTE = (4.0, 5.0, 10.0, 22.0)


@api.patch("/passive/{pid}")
async def patch_passive(pid: str, body: PassivePatch, t: dict = Depends(tenant_accounting)):
    d = await _get_passive(pid, t["cid"])
    upd = {k: v for k, v in body.model_dump(exclude={"rate", "data_registrazione", "aliquota_rc"}).items() if v is not None}
    if body.stato_reg == "contestata" and d["stato_reg"] != "contestata" and await db.passive_payments.find_one(
            {"company_id": t["cid"], "$or": [{"invoice_id": pid}, {"nc_id": pid}]}, {"_id": 1}):
        raise HTTPException(400, "Elimina prima i pagamenti o le compensazioni registrati su questo documento")
    if body.rate is not None:
        if d["tipo_documento"] == "TD04":
            raise HTTPException(400, "Le note di credito non hanno scadenze")
        rate = sorted(body.rate, key=lambda r: r.scadenza)
        if not rate:
            rate = [RataIn(scadenza=d["data"], importo=d["netto"])]
        s = round(sum(r.importo for r in rate), 2)
        if abs(s - d["netto"]) > 0.01:
            raise ferr(422, "rate", f"La somma delle rate ({_eur(s)}) deve essere uguale al netto da pagare ({_eur(d['netto'])})")
        extra = {k: (d["rate"][0].get(k) if d["rate"] else "") or "" for k in ("modalita", "iban")}
        upd |= {"rate": [{**r.model_dump(), **extra} for r in rate], "scadenza": rate[-1].scadenza}
    if body.stato_reg == "registrata" and d["stato_reg"] != "registrata":
        dr = body.data_registrazione or datetime.now(timezone.utc).date().isoformat()
        try:
            date.fromisoformat(dr)
        except ValueError:
            raise ferr(422, "data_registrazione", "Data di registrazione non valida")
        if dr < d["data"] or dr > datetime.now(timezone.utc).date().isoformat():
            raise ferr(422, "data_registrazione", f"La data di registrazione deve essere tra il {_it_date(d['data'])} e oggi")
        last = await db.passive_invoices.find_one({"company_id": t["cid"], "anno_registrazione": int(dr[:4])}, {"_id": 0, "protocollo": 1}, sort=[("protocollo", -1)])
        rc_rows = [r for r in d.get("riepilogo") or [] if (r.get("natura") or "").startswith("N6")]
        aliq = 22.0 if body.aliquota_rc is None else body.aliquota_rc
        if rc_rows and aliq not in RC_ALIQUOTE:
            raise ferr(422, "aliquota_rc", "Aliquota IVA per il reverse charge non valida (4, 5, 10 o 22%)")
        rc = [{"natura": r["natura"], "imponibile": r["imponibile"], "aliquota": aliq, "imposta": round(r["imponibile"] * aliq / 100, 2)} for r in rc_rows]
        upd |= {"data_registrazione": dr, "anno_registrazione": int(dr[:4]), "protocollo": (last["protocollo"] if last else 0) + 1, "reverse_charge": rc or None}
    elif body.stato_reg and body.stato_reg != "registrata" and d["stato_reg"] == "registrata":
        upd |= {"data_registrazione": None, "anno_registrazione": None, "protocollo": None, "reverse_charge": None}
    if upd:
        await db.passive_invoices.update_one({"id": pid, "company_id": t["cid"]}, {"$set": {**upd, "updated_at": now_iso()}})
    return await _get_passive(pid, t["cid"])


@api.get("/registro-iva-acquisti")
async def registro_iva_acquisti(anno: Optional[int] = None, dal: Optional[str] = None, al: Optional[str] = None, t: dict = Depends(tenant)):
    cid = t["cid"]
    anni = sorted(set(await db.passive_invoices.distinct("anno_registrazione", {"company_id": cid, "stato_reg": "registrata"})) - {None}
                  | {datetime.now(timezone.utc).year}, reverse=True)
    anno = anno or anni[0]
    q = {"company_id": cid, "stato_reg": "registrata", "anno_registrazione": anno}
    rng = {k: v for k, v in (("$gte", dal), ("$lte", al)) if v and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v)}
    if rng:
        q["data_registrazione"] = rng
    docs = await db.passive_invoices.find(q, {"_id": 0, "id": 1, "protocollo": 1, "data_registrazione": 1, "data": 1, "numero": 1, "tipo_documento": 1,
                                             "fornitore": 1, "riepilogo": 1, "totale": 1, "split_payment": 1, "reverse_charge": 1}).sort("protocollo", 1).to_list(20000)
    rows, out = _iva_register(docs, lambda d: {**{k: d.get(k) for k in ("id", "protocollo", "data_registrazione", "data", "numero", "tipo_documento", "split_payment")},
                                               "fornitore": d["fornitore"]["denominazione"], "partita_iva": d["fornitore"].get("partita_iva") or d["fornitore"].get("codice_fiscale")})
    return {"anno": anno, "anni": anni, "rows": rows, **out, "azienda": {k: t["company"].get(k) for k in ("denominazione", "partita_iva")}}


def _iva_register(docs: list, base) -> tuple:
    tot, rows = {}, []
    for d in docs:
        sgn = -1 if d["tipo_documento"] == "TD04" else 1
        rcm = {r["natura"]: r for r in d.get("reverse_charge") or []}
        rie = [{"aliquota": rc["aliquota"], "natura": r["natura"], "imponibile": round(sgn * r["imponibile"], 2), "imposta": round(sgn * rc["imposta"], 2), "rc": True}
               if (rc := rcm.get(r.get("natura"))) else
               {"aliquota": r["aliquota"], "natura": r.get("natura"), "imponibile": round(sgn * r["imponibile"], 2), "imposta": round(sgn * r["imposta"], 2)} for r in d.get("riepilogo") or []]
        for r in rie:
            k = f"{r['natura']} RC {r['aliquota']:g}%" if r.get("rc") else r["natura"] or f"{r['aliquota']:g}%"
            x = tot.setdefault(k, {"codice": k, "aliquota": r["aliquota"], "natura": r["natura"], "rc": bool(r.get("rc")), "imponibile": 0.0, "imposta": 0.0, "documenti": 0})
            x["imponibile"] += r["imponibile"]
            x["imposta"] += r["imposta"]
            x["documenti"] += 1
        rows.append({**base(d), "riepilogo": rie, "totale": round(sgn * d["totale"], 2)})
    totali = sorted(({**v, "imponibile": round(v["imponibile"], 2), "imposta": round(v["imposta"], 2)} for v in tot.values()), key=lambda v: (v["natura"] is not None, -v["aliquota"], v["codice"]))
    split = round(sum(sum(r["imposta"] for r in x["riepilogo"]) for x in rows if x.get("split_payment")), 2)
    rc = round(sum(sum(r["imposta"] for r in x["riepilogo"] if r.get("rc")) for x in rows), 2)
    return rows, {"totali": totali, "imposta_rc": rc, "imponibile": round(sum(v["imponibile"] for v in totali), 2), "imposta": round(sum(v["imposta"] for v in totali), 2),
                  "imposta_split": split, "totale": round(sum(r["totale"] for r in rows), 2)}


SALES_PROJ = {"_id": 0, "id": 1, "numero": 1, "sezionale": 1, "numero_display": 1, "data": 1, "tipo_documento": 1, "cliente": 1, "riepilogo": 1, "totale": 1, "split_payment": 1}


def _sales_row(d: dict) -> dict:
    c = d.get("cliente") or {}
    return {"id": d["id"], "numero": d["numero_display"], "data": d["data"], "tipo_documento": d["tipo_documento"], "split_payment": d.get("split_payment", False),
            "cliente": c.get("denominazione", ""), "partita_iva": c.get("partita_iva") or c.get("codice_fiscale")}


@api.get("/registro-iva-vendite")
async def registro_iva_vendite(anno: Optional[int] = None, dal: Optional[str] = None, al: Optional[str] = None, t: dict = Depends(tenant)):
    cid = t["cid"]
    anni = sorted(set(await db.invoices.distinct("anno", {"company_id": cid, "status": {"$in": list(SENT)}})) | {datetime.now(timezone.utc).year}, reverse=True)
    anno = anno or anni[0]
    q = {"company_id": cid, "status": {"$in": list(SENT)}, "anno": anno}
    rng = {k: v for k, v in (("$gte", dal), ("$lte", al)) if v and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v)}
    if rng:
        q["data"] = rng
    docs = await db.invoices.find(q, SALES_PROJ).sort([("sezionale", 1), ("numero", 1)]).to_list(20000)
    rows, out = _iva_register(docs, _sales_row)
    return {"anno": anno, "anni": anni, "rows": rows, **out, "azienda": {k: t["company"].get(k) for k in ("denominazione", "partita_iva")}}


@api.get("/liquidazione-iva")
async def liquidazione_iva(anno: Optional[int] = None, periodicita: Literal["mensile", "trimestrale"] = "mensile", t: dict = Depends(tenant)):
    anno = anno or datetime.now(timezone.utc).year
    prev = await _liq_calc(t["cid"], anno - 1, periodicita, 0.0)
    out = await _liq_calc(t["cid"], anno, periodicita, prev["credito_finale"])
    return {**out, "credito_anno_precedente": prev["credito_finale"], "azienda": {k: t["company"].get(k) for k in ("denominazione", "partita_iva")}}


MIN_VERSAMENTO = 25.82


async def _liq_calc(cid: str, anno: int, periodicita: str, credito: float) -> dict:
    sales = await db.invoices.find({"company_id": cid, "status": {"$in": list(SENT)}, "anno": anno}, SALES_PROJ).to_list(50000)
    purch = await db.passive_invoices.find({"company_id": cid, "stato_reg": "registrata", "anno_registrazione": anno},
                                           {"_id": 0, "data_registrazione": 1, "tipo_documento": 1, "riepilogo": 1, "totale": 1, "split_payment": 1, "reverse_charge": 1}).to_list(50000)
    n = 12 if periodicita == "mensile" else 4
    per = (lambda m: m) if n == 12 else (lambda m: (m - 1) // 3 + 1)
    buckets = {k: {"vendite": [], "acquisti": []} for k in range(1, n + 1)}
    for d in sales:
        buckets[per(int(d["data"][5:7]))]["vendite"].append(d)
    for d in purch:
        buckets[per(int(d["data_registrazione"][5:7]))]["acquisti"].append(d)
    mesi = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
    periodi, debito_prec = [], 0.0
    for k in range(1, n + 1):
        _, v = _iva_register(buckets[k]["vendite"], lambda d: {"split_payment": d.get("split_payment", False)})
        _, a = _iva_register(buckets[k]["acquisti"], lambda d: {})
        debito = round(v["imposta"] - v["imposta_split"] + a["imposta_rc"], 2)
        saldo = round(debito - a["imposta"] - credito, 2)
        interessi = round(saldo * 0.01, 2) if n == 4 and k < 4 and saldo > 0 else 0.0
        dovuto = round(saldo + interessi + debito_prec, 2) if saldo > 0 else round(debito_prec + min(saldo, 0), 2)
        sotto_soglia = 0 < dovuto <= MIN_VERSAMENTO and k < n
        periodi.append({"periodo": k, "label": mesi[k - 1] if n == 12 else f"{k}° trimestre", "vendite": v, "acquisti": a,
                        "iva_debito": debito, "iva_split": v["imposta_split"], "iva_rc": a["imposta_rc"], "iva_credito": a["imposta"], "credito_precedente": credito,
                        "debito_precedente": debito_prec, "saldo": saldo, "interessi": interessi,
                        "da_versare": dovuto if dovuto > 0 and not sotto_soglia else 0.0, "sotto_soglia": sotto_soglia,
                        "credito_riporto": round(-dovuto, 2) if dovuto < 0 else 0.0,
                        "documenti_vendite": len(buckets[k]["vendite"]), "documenti_acquisti": len(buckets[k]["acquisti"])})
        credito = round(-dovuto, 2) if dovuto < 0 else 0.0
        debito_prec = dovuto if sotto_soglia else 0.0
    return {"anno": anno, "periodicita": periodicita, "periodi": periodi,
            "totale_versare": round(sum(p["da_versare"] for p in periodi), 2), "credito_finale": credito}


@api.delete("/passive/{pid}")
async def delete_passive(pid: str, t: dict = Depends(tenant_accounting)):
    await _get_passive(pid, t["cid"])
    if await db.passive_payments.find_one({"company_id": t["cid"], "$or": [{"invoice_id": pid}, {"nc_id": pid}]}, {"_id": 1}):
        raise HTTPException(400, "Elimina prima i pagamenti registrati su questo documento")
    await db.passive_invoices.delete_one({"id": pid, "company_id": t["cid"]})
    return {"ok": True}


async def _ledger_passive(cid: str, party_id: Optional[str] = None):
    q = {"company_id": cid, "stato_reg": {"$ne": "contestata"}, **({"party_id": party_id} if party_id else {})}
    rows = await db.passive_invoices.find(q, {"_id": 0, "id": 1, "numero_display": 1, "data": 1, "party_id": 1, "fornitore.denominazione": 1, "totale": 1,
                                               "netto": 1, "rate": 1, "scadenza": 1, "tipo_documento": 1, "fattura_collegata_id": 1}).to_list(20000)
    invs = [{**r, "numero": 0, "cliente": {"denominazione": r["fornitore"]["denominazione"]}} for r in rows]
    pays = await db.passive_payments.find({"company_id": cid, **({"party_id": party_id} if party_id else {})}, {"_id": 0}).to_list(50000)
    today = datetime.now(timezone.utc).date().isoformat()
    docs, crediti = build_ledger(invs, pays, today)
    return docs, crediti, pays, today


@api.get("/scadenzario-passivo")
async def scadenzario_passivo(party_id: Optional[str] = None, t: dict = Depends(tenant)):
    docs, crediti, _, today = await _ledger_passive(t["cid"], party_id)
    return _scad_response(docs, crediti, today)


@api.get("/passive/{pid}/pagamenti")
async def passive_payments(pid: str, t: dict = Depends(tenant)):
    d = await _get_passive(pid, t["cid"])
    docs, crediti, pays, _ = await _ledger_passive(t["cid"], d["party_id"])
    return {"scadenzario": next((x for x in docs if x["id"] == pid), None),
            "pagamenti": sorted([p for p in pays if p["invoice_id"] == pid], key=lambda p: p["data"]), "crediti": crediti}


@api.post("/passive/{pid}/pagamenti")
async def add_passive_payment(pid: str, body: PagamentoIn, t: dict = Depends(tenant_accounting)):
    cid = t["cid"]
    d = await _get_passive(pid, cid)
    if d["tipo_documento"] == "TD04" or d["stato_reg"] == "contestata":
        raise HTTPException(400, "Pagamenti non registrabili su note di credito o fatture contestate")
    docs, crediti, _, _ = await _ledger_passive(cid, d["party_id"])
    doc = next(x for x in docs if x["id"] == pid)
    if body.importo > doc["residuo"] + 0.005:
        raise ferr(400, "importo", f"Importo superiore al residuo da pagare ({_eur(doc['residuo'])})")
    if body.data < d["data"]:
        raise ferr(400, "data", f"La data del pagamento non può precedere la data della fattura ({_it_date(d['data'])})")
    nc = None
    if body.metodo == "compensazione" or body.nc_id:
        nc = next((c for c in crediti if c["id"] == body.nc_id), None)
        if not nc:
            raise ferr(400, "nc_id", "Seleziona una nota di credito dello stesso fornitore con credito disponibile")
        if body.importo > nc["residuo"] + 0.005:
            raise ferr(400, "importo", f"Importo superiore al credito disponibile della nota {nc['numero_display']} ({_eur(nc['residuo'])})")
        body.metodo = "compensazione"
    p = {"id": str(uuid.uuid4()), **body.model_dump(), "importo": round(body.importo, 2), "company_id": cid, "invoice_id": pid,
         "party_id": d["party_id"], "numero_display": d["numero_display"], "nc_numero": nc["numero_display"] if nc else None,
         "created_by_name": t["user"].get("name") or t["user"]["email"], "created_at": now_iso()}
    await db.passive_payments.insert_one(p)
    p.pop("_id", None)
    return p


@api.delete("/passive-pagamenti/{pid}")
async def delete_passive_payment(pid: str, t: dict = Depends(tenant_accounting)):
    r = await db.passive_payments.delete_one({"id": pid, "company_id": t["cid"]})
    if not r.deleted_count:
        raise HTTPException(404, "Pagamento non trovato")
    return {"ok": True}


# ---------- Estratto conto e solleciti ----------
async def _party_ledger(t: dict, pid: str):
    party = await db.parties.find_one({"id": pid, "company_id": t["cid"], "tipo": {"$ne": "fornitore"}}, {"_id": 0})
    if not party:
        raise HTTPException(404, "Cliente non trovato")
    docs, crediti, pays, today = await _ledger(t["cid"], pid)
    invs = await db.invoices.find({"company_id": t["cid"], "party_id": pid, "status": {"$in": list(SENT)}}, LEDGER_PROJ).to_list(20000)
    return party, docs, crediti, pays, invs, today


def _statement_pdf(t, party, docs, crediti, pays, invs, today) -> bytes:
    return build_pdf(t["company"], party, invs, pays, docs, crediti, today)


@api.get("/clienti/{pid}/estratto-conto.pdf")
async def estratto_conto(pid: str, t: dict = Depends(tenant)):
    party, docs, crediti, pays, invs, today = await _party_ledger(t, pid)
    pdf = _statement_pdf(t, party, docs, crediti, pays, invs, today)
    name = re.sub(r"[^A-Za-z0-9]+", "_", party["denominazione"])[:40]
    return RawResponse(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="Estratto_conto_{name}_{today}.pdf"'})


def _rata_lbl(r: dict) -> str:
    return f" rata {r['n']}/{r['di']}" if r["di"] > 1 else ""


def _sollecito_mail(t: dict, party: dict, docs: list, today: str):
    comp = t["company"]
    scadute = sorted(((d, r) for d in docs for r in d["rate"] if r["scaduta"]), key=lambda x: x[1]["scadenza"])
    tot = round(sum(r["residuo"] for _, r in scadute), 2)
    td = 'style="padding:6px 8px;border-bottom:1px solid #e2e8f0;font-size:13px"'
    rows = "".join(f"<tr><td {td}>{escape(d['numero_display'])}{_rata_lbl(r)}</td><td {td}>{itd(r['scadenza'])}</td>"
                   f"<td {td}>{r['giorni_ritardo']} gg</td><td {td} align=\"right\"><b>{_eur_pdf(r['residuo'])}</b></td></tr>" for d, r in scadute)
    iban = f"<p>Potete effettuare il pagamento con bonifico sull'IBAN <b>{escape(comp['iban'])}</b> intestato a {escape(comp['denominazione'])}.</p>" if comp.get("iban") else ""
    html = (f'<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif;color:#0f172a">'
            f"<p>Spett.le <b>{escape(party['denominazione'])}</b>,</p>"
            f"<p>dalle nostre verifiche al {itd(today)} risultano non ancora saldate le seguenti scadenze:</p>"
            f'<table role="presentation" cellspacing="0" style="border-collapse:collapse;width:100%;max-width:560px">'
            f'<tr style="background:#0f172a;color:#ffffff"><th align="left" style="padding:6px 8px;font-size:12px">Documento</th><th align="left" style="padding:6px 8px;font-size:12px">Scadenza</th>'
            f'<th align="left" style="padding:6px 8px;font-size:12px">Ritardo</th><th align="right" style="padding:6px 8px;font-size:12px">Importo dovuto</th></tr>{rows}'
            f'<tr><td colspan="3" style="padding:8px;font-size:14px"><b>Totale scaduto</b></td><td align="right" style="padding:8px;font-size:14px;color:#be123c"><b>{_eur_pdf(tot)}</b></td></tr></table>'
            f"<p>Vi preghiamo di provvedere al pagamento quanto prima. In allegato trovate l'estratto conto aggiornato.</p>{iban}"
            f"<p>Se il pagamento è già stato effettuato, vi preghiamo di non considerare questo messaggio.</p>"
            f"<p>Cordiali saluti,<br/><b>{escape(comp['denominazione'])}</b></p>"
            f'<p style="font-size:12px;color:#888">Inviato da {escape(EMAIL_FROM_NAME)} per conto di {escape(comp["denominazione"])}.</p></td></tr></table>')
    subject = f"Sollecito di pagamento - {comp['denominazione']}"
    return subject, html, tot, len(scadute)


def _recipient(party: dict) -> str:
    return (party.get("email") or party.get("pec") or "").strip()


@api.get("/clienti/{pid}/sollecito")
async def sollecito_preview(pid: str, t: dict = Depends(tenant)):
    party, docs, *_rest, today = await _party_ledger(t, pid)
    subject, html, tot, n = _sollecito_mail(t, party, docs, today)
    storico = await db.solleciti.find({"company_id": t["cid"], "party_id": pid}, {"_id": 0}).sort("created_at", -1).to_list(10)
    return {"to": _recipient(party), "subject": subject, "html": html, "scaduto": tot, "rate": n, "storico": storico}


@api.post("/clienti/{pid}/sollecito")
async def sollecito_send(pid: str, t: dict = Depends(tenant_accounting)):
    party, docs, crediti, pays, invs, today = await _party_ledger(t, pid)
    to = _recipient(party)
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", to):
        raise HTTPException(400, "Il cliente non ha un indirizzo email o PEC valido in anagrafica")
    subject, html, tot, n = _sollecito_mail(t, party, docs, today)
    if not n:
        raise HTTPException(400, "Il cliente non ha rate scadute da sollecitare")
    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    if await db.solleciti.count_documents({"company_id": t["cid"], "party_id": pid, "created_at": {"$gte": since}}) >= 3:
        raise HTTPException(429, "Hai già inviato 3 solleciti a questo cliente nelle ultime 24 ore")
    pdf = _statement_pdf(t, party, docs, crediti, pays, invs, today)
    name = re.sub(r"[^A-Za-z0-9]+", "_", party["denominazione"])[:40]
    email_id = await send_email(to=to, subject=subject, html=html, reply_to=t["company"].get("email") or None,
                                attachments=[{"filename": f"Estratto_conto_{name}_{today}.pdf", "content": base64.b64encode(pdf).decode()}])
    rec = {"id": str(uuid.uuid4()), "company_id": t["cid"], "party_id": pid, "to": to, "importo_scaduto": tot, "rate": n, "email_id": email_id,
           "created_by_name": t["user"].get("name") or t["user"]["email"], "created_at": now_iso()}
    await db.solleciti.insert_one(rec)
    rec.pop("_id", None)
    return rec


# ---------- Registro numerazione ----------
@api.get("/registro")
async def registro(anno: Optional[int] = None, sezionale: Literal["", "NC"] = "", t: dict = Depends(tenant)):
    cid = t["cid"]
    anni = sorted(set(await db.invoices.distinct("anno", {"company_id": cid})) | {datetime.now(timezone.utc).year}, reverse=True)
    anno = anno or anni[0]
    docs = await db.invoices.find({"company_id": cid, "anno": anno, "sezionale": sezionale},
                                  {"_id": 0, "id": 1, "numero": 1, "numero_display": 1, "data": 1, "totale": 1, "status": 1,
                                   "tipo_documento": 1, "cliente.denominazione": 1}).sort("numero", 1).to_list(10000)
    rows = []
    for i, d in enumerate(docs):
        if i:
            prev = docs[i - 1]
            for n in range(prev["numero"] + 1, d["numero"]):
                rows.append({"libero": True, "numero": n, "numero_display": _display(n, sezionale, anno), "data_min": prev["data"], "data_max": d["data"]})
        rows.append({"libero": False, **d})
    last = docs[-1] if docs else None
    nxt = (last["numero"] + 1) if last else 1
    return {"anno": anno, "sezionale": sezionale, "anni": anni, "rows": rows, "documenti": len(docs),
            "liberi": sum(1 for r in rows if r["libero"]), "primo": docs[0]["numero"] if docs else None,
            "prossimo": {"numero": nxt, "numero_display": _display(nxt, sezionale, anno), "data_min": last["data"] if last else None}}


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
    await db.payments.create_index([("company_id", 1), ("invoice_id", 1)])
    await db.passive_invoices.create_index([("company_id", 1), ("hash", 1)], unique=True)
    await db.passive_payments.create_index([("company_id", 1), ("invoice_id", 1)])
    await db.passive_invoices.create_index([("company_id", 1), ("anno_registrazione", 1), ("protocollo", 1)])
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

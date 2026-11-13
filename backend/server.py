from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, UploadFile, File, Query
from fastapi.responses import Response as RawResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError, BulkWriteError
import os
import re
import asyncio
import functools
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
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from types import SimpleNamespace
from typing import List, Optional, Literal
from datetime import datetime, timezone, timedelta, date

from fatturapa import compute_totals, build_xml, file_name, norm_sconto, line_total

ROOT_DIR = Path(__file__).parent


REQUIRED_ENV = ("MONGO_URL", "DB_NAME", "APP_URL", "COOKIE_SECURE", "ADMIN_EMAIL", "ADMIN_PASSWORD", "EMAIL_FROM_NAME", "SMTP_ENCRYPTION_KEY")


def _load_env():
    src = None
    for name in (".env", ".env.txt"):
        p = ROOT_DIR / name
        if p.is_file():
            raw = p.read_bytes()
            if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
                enc = "utf-16"
            else:
                try:
                    raw.decode("utf-8-sig")
                    enc = "utf-8-sig"
                except UnicodeDecodeError:
                    enc = "cp1252"
            load_dotenv(p, encoding=enc)
            src = p
            break
    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        where = src or ROOT_DIR / ".env"
        raise SystemExit(f"Configurazione incompleta in {where}: mancano {', '.join(missing)}. "
                         "Copiate deploy/windows/backend.env.example in backend/.env e compilatelo (vedi guida, punto 5)")


_load_env()

from emailer import send_email, send_system_email  # noqa: E402
from archivio import build_router as build_archivio_router, ensure_indexes as archivio_indexes  # noqa: E402
from cryptography.fernet import Fernet, InvalidToken  # noqa: E402
from scadenzario import build_ledger, per_cliente  # noqa: E402
from estratto import build_pdf, eur as _eur_pdf, itd  # noqa: E402
from passive import extract_xml, parse_fattura, sha, demo_xmls  # noqa: E402
import random  # noqa: E402
import sdi_providers as sdip  # noqa: E402
import sdi_schedule as sdis  # noqa: E402
import export_comm  # noqa: E402
import banca as bk  # noqa: E402
import html as _html  # noqa: E402
from updater import build_router as build_updater_router  # noqa: E402
from magazzino import build_router as build_magazzino_router  # noqa: E402
import contabilita as coge  # noqa: E402
import sistema  # noqa: E402
import ftp_backup as ftpb  # noqa: E402
from menu_voci import MENU, MENU_IDS, MENU_LABEL, menu_for, menu_off  # noqa: E402
import f24  # noqa: E402
from contabilita_chiusure import build_router as build_chiusure_router  # noqa: E402
from comunicazioni import build as build_comunicazioni  # noqa: E402
import conservazione as cons  # noqa: E402
import ddt as ddt_mod  # noqa: E402
import importazione  # noqa: E402
from export_comm import courtesy_pdf  # noqa: E402
import riba as riba_mod  # noqa: E402
import pagamenti_fornitori as pagforn  # noqa: E402
import codici_tributo  # noqa: E402
import intenti as intenti_mod  # noqa: E402
import reg_veloce  # noqa: E402
import registra_passiva  # noqa: E402

client = AsyncIOMotorClient(os.environ['MONGO_URL'])
db = client[os.environ['DB_NAME']]
ADMIN_EMAIL = os.environ['ADMIN_EMAIL'].strip().lower()
APP_URL = os.environ['APP_URL'].rstrip("/")
logger = logging.getLogger(__name__)
ADMIN_PASSWORD = os.environ['ADMIN_PASSWORD']
EMAIL_FROM_NAME = os.environ['EMAIL_FROM_NAME']
COOKIE_SECURE = os.environ['COOKIE_SECURE'].strip().lower() == "true"
COOKIE_SAMESITE = "none" if COOKIE_SECURE else "lax"
FERNET = Fernet(os.environ['SMTP_ENCRYPTION_KEY'].encode())
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
IVA_STATI = (*SENT, "manuale")
NATURE = ["N1", "N2.1", "N2.2", "N3.1", "N3.2", "N3.3", "N3.4", "N3.5", "N3.6", "N4", "N5", "N6.1", "N6.2", "N6.3", "N6.4", "N6.5", "N6.6", "N6.7", "N6.8", "N6.9", "N7"]
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


COMPANY_PROJ = {"_id": 0, "smtp.password_enc": 0, "sdi.token_enc": 0, "sdi.password_enc": 0, "banca.password_enc": 0}


MODULI = ("fatturazione", "archivio", "fatture_attive", "fatture_passive", "corrispettivi", "contabilita")
MODULE_SEGMENTS = {
    "archivio": ("archivio",),
    "corrispettivi": ("fatturazione", "corrispettivi"),
    "contabilita": ("fatturazione", "contabilita"),
    "comunicazioni": ("fatturazione", "fatture_attive"),
    "ddt": ("fatturazione", "fatture_attive"),
    "riba": ("fatturazione", "fatture_attive"),
    "intenti": ("fatturazione", "fatture_attive"),
    "reg-veloce": ("fatturazione", "contabilita"),
    "scadenze": ("fatturazione",),
    **{s: ("fatturazione", "fatture_passive") for s in ("passive", "passive-pagamenti", "scadenzario-passivo", "pagamenti-fornitori", "registro-iva-acquisti", "ritenute")},
    **{s: ("fatturazione", "fatture_attive") for s in ("invio-sdi", "bolli", "invoices", "pagamenti", "scadenzario", "registro-iva-vendite", "registro", "clienti")},
    **{s: ("fatturazione",) for s in ("liquidazione-iva", "f24-storico", "codici-tributo", "dashboard", "parties", "articles", "ipa", "export", "banca", "magazzino", "scadenze-fiscali", "conservazione")},
}
MODULE_LABEL = {"fatturazione": "Fatturazione", "archivio": "Archivio fatture", "fatture_attive": "Fatture attive", "fatture_passive": "Fatture passive", "corrispettivi": "Corrispettivi", "contabilita": "Contabilità generale"}


def company_moduli(comp: dict, user: Optional[dict] = None) -> dict:
    m = comp.get("moduli") or {}
    u = (user or {}).get("moduli") or {} if (user or {}).get("role") != "admin" else {}
    return {k: m.get(k, True) is not False and u.get(k, True) is not False for k in MODULI}


DIRITTI = ("dati_azienda", "banche", "tabelle_contabili", "articoli_magazzino", "testi_comunicazioni")
DIRITTO_LABEL = {"dati_azienda": "modificare i dati azienda", "banche": "modificare le banche aziendali", "tabelle_contabili": "modificare piano dei conti, causali, codici IVA e parametri",
                 "articoli_magazzino": "modificare articoli e magazzino", "testi_comunicazioni": "modificare i testi delle comunicazioni"}


def diritti(user: dict) -> dict:
    if user.get("role") == "admin":
        return {k: True for k in DIRITTI}
    acc = user.get("role") == "contabile"
    base = {"dati_azienda": False, "banche": False, "tabelle_contabili": acc, "articoli_magazzino": True, "testi_comunicazioni": acc}
    return {**base, **{k: bool(v) for k, v in (user.get("diritti") or {}).items() if k in DIRITTI}}


def diritto_for(method: str, path: str):
    if method == "GET":
        return None
    s0 = path.removeprefix("/api/").split("/", 1)[0]
    if s0 in ("articles", "magazzino"):
        return "articoli_magazzino"
    if s0 == "contabilita" and menu_for(method, path) == "piano-conti":
        return "tabelle_contabili"
    return None


async def tenant(request: Request, user: dict = Depends(approved_user)) -> dict:
    cid = request.headers.get("X-Company-Id")
    if not cid:
        raise HTTPException(400, "Seleziona un'azienda")
    if user.get("role") != "admin" and cid not in (user.get("company_ids") or []):
        raise HTTPException(404, "Azienda non trovata")
    comp = await db.companies.find_one({"id": cid}, COMPANY_PROJ)
    if not comp:
        raise HTTPException(404, "Azienda non trovata")
    seg = request.url.path.removeprefix("/api/").split("/", 1)[0]
    mods = company_moduli(comp, user)
    off = [MODULE_LABEL[k] for k in MODULE_SEGMENTS.get(seg, ()) if not mods[k]]
    if off:
        raise HTTPException(403, f"Modulo non attivo per questa azienda o per il tuo utente: {', '.join(off)}")
    mid = menu_for(request.method, request.url.path)
    if mid and mid in menu_off(comp, user):
        raise HTTPException(403, f"Voce di menu non attiva per questa azienda o per il tuo utente: {MENU_LABEL[mid]}")
    need = diritto_for(request.method, request.url.path)
    if need and not diritti(user)[need]:
        raise HTTPException(403, f"Non hai il diritto di {DIRITTO_LABEL[need]}")
    return {"user": user, "cid": cid, "company": comp}


async def tenant_accounting(t: dict = Depends(tenant)) -> dict:
    if t["user"].get("role") not in ("admin", "contabile"):
        raise HTTPException(403, "Operazione riservata ad Admin o Contabile")
    return t


async def tenant_admin(t: dict = Depends(tenant)) -> dict:
    if t["user"].get("role") != "admin":
        raise HTTPException(403, "Operazione riservata agli amministratori")
    return t


async def _start_session(response: Response, user_id: str):
    token = secrets.token_urlsafe(32)
    await db.user_sessions.insert_one({
        "user_id": user_id, "session_token": token,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7), "created_at": now_iso(),
    })
    response.set_cookie("session_token", token, httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE,
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
    ts = now_iso()
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"last_login_at": ts}})
    await db.users.update_one({"user_id": user["user_id"], "first_login_at": None}, {"$set": {"first_login_at": ts}})
    await _start_session(response, user["user_id"])
    return await db.users.find_one({"user_id": user["user_id"]}, USER_PROJ)


def _reset_base(request: Request) -> str:
    origin = (request.headers.get("origin") or "").rstrip("/")
    host = urlparse(origin).hostname or ""
    if origin == APP_URL or (origin.startswith("https://") and (host.endswith(".emergentagent.com") or host.endswith(".emergent.host"))):
        return origin
    return APP_URL


def _smtp_config(comp: dict) -> Optional[dict]:
    s = comp.get("smtp") or {}
    if not s.get("host"):
        return None
    try:
        pwd = FERNET.decrypt(s["password_enc"].encode()).decode() if s.get("password_enc") else ""
    except InvalidToken:
        pwd = ""
    return {**{k: v for k, v in s.items() if k != "password_enc"}, "password": pwd, "from_name": s.get("from_name") or comp.get("denominazione")}


async def _company_smtp(cid: str) -> dict:
    comp = await db.companies.find_one({"id": cid}, {"_id": 0})
    cfg = _smtp_config(comp or {})
    if not cfg:
        raise HTTPException(400, "Configura il server email (SMTP) dell'azienda in Dati azienda → Email in uscita")
    return cfg


async def _smtp_for_user(user: dict) -> dict:
    ids = user.get("company_ids") or []
    comps = await db.companies.find({"id": {"$in": ids}, "smtp.host": {"$nin": [None, ""]}}, {"_id": 0}).to_list(50)
    comps = comps or await db.companies.find({"smtp.host": {"$nin": [None, ""]}}, {"_id": 0}).sort("denominazione", 1).to_list(1)
    if not comps:
        raise HTTPException(400, "Nessuna azienda ha un server email (SMTP) configurato: impostalo in Dati azienda → Email in uscita")
    return _smtp_config(comps[0])


async def _email_event(user_id: str, tipo: str, via: Optional[str], errore: Optional[str] = None, azienda: Optional[str] = None):
    ev = {"tipo": tipo, "at": now_iso(), "via": via, "ok": not errore, "errore": errore, "azienda": azienda}
    await db.users.update_one({"user_id": user_id}, {"$set": {"last_email": ev}, "$push": {"email_log": {"$each": [ev], "$slice": -20}}})


async def _deliver_system_first(to: str, subject: str, html: str, smtp_getter) -> str:
    try:
        await send_system_email(to=to, subject=subject, html=html, from_name=EMAIL_FROM_NAME)
        return "sistema"
    except Exception as e:
        logger.warning(f"System email failed for {to}, falling back to company SMTP: {e}")
    await send_email(smtp=await smtp_getter(), to=to, subject=subject, html=html)
    return "smtp"


async def _send_welcome(user: dict, cids: list, request: Request):
    for comp in await db.companies.find({"id": {"$in": cids}}, {"_id": 0}).to_list(50):
        nome = comp.get("denominazione") or ""
        mods = company_moduli(comp, user)
        attivi = [MODULE_LABEL[k] for k in MODULI if mods[k] and (k == "fatturazione" or k == "archivio" or mods["fatturazione"])]
        html = (
            '<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif;color:#0f172a">'
            f'<p>Ciao {escape(user.get("name") or "")},</p>'
            f'<p>benvenuto in <b>{escape(nome)}</b> su {escape(EMAIL_FROM_NAME)}: il tuo account è stato collegato a questa azienda.</p>'
            f'<p>Moduli attivi per te: <b>{escape(", ".join(attivi) or "nessuno")}</b>.</p>'
            f'<p><a href="{escape(_reset_base(request))}/login" style="display:inline-block;background:#0f172a;color:#ffffff;padding:12px 20px;border-radius:6px;text-decoration:none">Accedi al programma</a></p>'
            '<p>Se non hai ancora una password, usa il link dell\'email di invito.</p>'
            f'<p style="font-size:12px;color:#888">Inviato da {escape(EMAIL_FROM_NAME)}. Non ti chiederemo mai la password via email.</p>'
            '</td></tr></table>'
        )
        try:
            via = await _deliver_system_first(user["email"], f"Benvenuto in {nome} - {EMAIL_FROM_NAME}", html,
                                              lambda c=comp: _company_smtp(c["id"]))
            await _email_event(user["user_id"], "benvenuto", via, azienda=nome)
        except HTTPException as e:
            await _email_event(user["user_id"], "benvenuto", None, str(e.detail), azienda=nome)


async def _send_password_link(user: dict, request: Request, invite: bool = False):
    token = secrets.token_urlsafe(32)
    hours = 72 if invite else 1
    await db.password_reset_tokens.insert_one({
        "token_hash": hashlib.sha256(token.encode()).hexdigest(), "user_id": user["user_id"],
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=hours), "used": False, "created_at": now_iso(),
    })
    link = f"{_reset_base(request)}/reset-password?token={token}"
    intro = (f"sei stato invitato ad accedere a {escape(EMAIL_FROM_NAME)}. Imposta la tua password per entrare."
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
    tipo = "invito" if invite else "reset"
    try:
        via = await _deliver_system_first(user["email"], subject, html, lambda: _smtp_for_user(user))
    except HTTPException as e:
        await _email_event(user["user_id"], tipo, None, str(e.detail))
        raise
    await _email_event(user["user_id"], tipo, via)
    return via


async def _reset_bg(user: dict, request: Request):
    try:
        await _send_password_link(user, request)
    except HTTPException as e:
        logger.warning(f"Password reset email not sent to {user['email']}: {e.detail}")


@api.post("/auth/forgot-password")
async def forgot_password(body: ForgotIn, request: Request):
    email = body.email.strip().lower()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if user and user.get("status") != "rejected":
        recent = await db.password_reset_tokens.count_documents({"user_id": user["user_id"], "created_at": {"$gt": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()}})
        if recent < 3:
            asyncio.create_task(_reset_bg(user, request))
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
    return {**user, "diritti": diritti(user)}


class RiquadriPref(BaseModel):
    ordine: List[str] = Field(default_factory=list, max_length=30)
    nascosti: List[str] = Field(default_factory=list, max_length=30)


@api.get("/me/riquadri")
async def get_riquadri_pref(user: dict = Depends(get_user)):
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "riquadri_pref": 1}) or {}
    return u.get("riquadri_pref") or {"ordine": [], "nascosti": []}


@api.put("/me/riquadri")
async def put_riquadri_pref(body: RiquadriPref, user: dict = Depends(get_user)):
    pref = {k: [x[:40] for x in dict.fromkeys(v)] for k, v in body.model_dump().items()}
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"riquadri_pref": pref}})
    return pref


class ChangePwIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


@api.post("/auth/change-password")
async def change_password(body: ChangePwIn, request: Request, user: dict = Depends(get_user)):
    ident = f"chg:{user['user_id']}"
    att = await db.login_attempts.find_one({"identifier": ident}, {"_id": 0})
    if att and att.get("count", 0) >= 5 and datetime.fromisoformat(att["last"]) + timedelta(minutes=15) > datetime.now(timezone.utc):
        raise HTTPException(429, "Troppi tentativi falliti. Riprova tra 15 minuti")
    full = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "password_hash": 1})
    if not full or not full.get("password_hash") or not verify_password(body.current_password, full["password_hash"]):
        await db.login_attempts.update_one({"identifier": ident}, {"$inc": {"count": 1}, "$set": {"last": now_iso()}}, upsert=True)
        raise ferr(400, "current_password", "La password attuale non è corretta")
    if body.current_password == body.new_password:
        raise ferr(400, "new_password", "La nuova password deve essere diversa da quella attuale")
    await db.login_attempts.delete_one({"identifier": ident})
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"password_hash": hash_password(body.new_password), "password_changed_at": now_iso()}})
    keep = request.cookies.get("session_token") or request.headers.get("Authorization", "").removeprefix("Bearer ")
    await db.user_sessions.delete_many({"user_id": user["user_id"], "session_token": {"$ne": keep}})
    return {"ok": True}


@api.post("/auth/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        await db.user_sessions.delete_many({"session_token": token})
    response.delete_cookie("session_token", path="/", secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE)
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
        u["diritti"] = diritti(u)
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
    if user["company_ids"]:
        await _send_welcome(user, user["company_ids"], request)
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
async def patch_user(user_id: str, body: UserPatch, request: Request, admin: dict = Depends(admin_user)):
    target = await _editable_target(user_id, admin)
    upd = body.model_dump(exclude_none=True)
    if "company_ids" in upd:
        upd["company_ids"] = await _valid_company_ids(upd["company_ids"])
    if upd:
        await db.users.update_one({"user_id": user_id}, {"$set": upd})
        if upd.get("status") in ("rejected", "pending"):
            await db.user_sessions.delete_many({"user_id": user_id})
    nuove = [c for c in upd.get("company_ids") or [] if c not in (target.get("company_ids") or [])]
    if nuove and target.get("status") != "rejected":
        await _send_welcome({**target, **upd}, nuove, request)
    return await db.users.find_one({"user_id": user_id}, USER_PROJ)


# ---------- Company ----------
def _clean(v):
    return v.strip() if isinstance(v, str) else v


def _iban_check(v: str) -> str:
    s = re.sub(r"\s+", "", v or "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", s):
        raise ValueError("IBAN non valido (es. IT60X0542811101000000123456)")
    if s.startswith("IT") and len(s) != 27:
        raise ValueError("Un IBAN italiano deve avere 27 caratteri")
    n = int("".join(str(int(c, 36)) for c in s[4:] + s[:4]))
    if n % 97 != 1:
        raise ValueError("IBAN non valido: controlla le cifre (codice di controllo errato)")
    return s


class Banca(BaseModel):
    id: Optional[str] = None
    nome: str = Field(min_length=1, max_length=80)
    iban: str
    abi: Optional[str] = ""
    cab: Optional[str] = ""
    bic: Optional[str] = ""
    sia: Optional[str] = ""
    conto_sbf: Optional[str] = Field(default="", pattern=r"^(13\.01\.\d{3})?$")
    conto_coge: Optional[str] = Field(default="", pattern=r"^(06\.01\.\d{3})?$")
    cuc: Optional[str] = ""
    predefinita: bool = False

    @field_validator("cuc")
    @classmethod
    def _cuc(cls, v):
        v = _clean(v or "").upper()
        if v and not re.fullmatch(r"[A-Z0-9]{8}", v):
            raise ValueError("Il codice CUC deve avere 8 caratteri")
        return v

    @field_validator("sia")
    @classmethod
    def _sia(cls, v):
        v = _clean(v or "").upper()
        if v and not re.fullmatch(r"[A-Z0-9]{5}", v):
            raise ValueError("Il codice SIA deve avere 5 caratteri")
        return v

    @field_validator("nome")
    @classmethod
    def _nome(cls, v):
        v = _clean(v)
        if not v:
            raise ValueError("Inserisci il nome della banca")
        return v

    @field_validator("iban")
    @classmethod
    def _iban(cls, v):
        return _iban_check(v)

    @field_validator("abi", "cab")
    @classmethod
    def _abicab(cls, v, info):
        v = _clean(v or "")
        if v and not re.fullmatch(r"\d{5}", v):
            raise ValueError(f"Il codice {info.field_name.upper()} deve avere 5 cifre")
        return v

    @field_validator("bic")
    @classmethod
    def _bic(cls, v):
        v = _clean(v or "").upper()
        if v and not re.fullmatch(r"[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?", v):
            raise ValueError("Il BIC/SWIFT deve avere 8 o 11 caratteri")
        return v

    @model_validator(mode="after")
    def _it(self):
        if self.iban.startswith("IT"):
            self.abi, self.cab = self.abi or self.iban[5:10], self.cab or self.iban[10:15]
        self.id = self.id or str(uuid.uuid4())
        return self


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
    banche: List[Banca] = Field(default_factory=list, max_length=20)
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
    periodicita_iva: Literal["mensile", "trimestrale"] = "mensile"
    ddt_giacenza: Literal["avviso", "blocca"] = "avviso"

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

    @model_validator(mode="after")
    def _banche(self):
        if not self.banche and (self.iban or "").strip():
            try:
                self.banche = [Banca(nome="Banca", iban=self.iban, predefinita=True)]
            except ValueError:
                raise ferr(422, "iban", "IBAN non valido")
        ibans = [b.iban for b in self.banche]
        for i, b in enumerate(self.banche):
            if ibans.index(b.iban) != i:
                raise ferr(422, f"banche.{i}.iban", "Questo IBAN è già presente in un'altra banca")
            if b.iban.startswith("IT"):
                for k, v in (("abi", b.iban[5:10]), ("cab", b.iban[10:15])):
                    if getattr(b, k) != v:
                        raise ferr(422, f"banche.{i}.{k}", f"Il codice {k.upper()} non corrisponde all'IBAN (dovrebbe essere {v})")
        if self.banche and sum(b.predefinita for b in self.banche) != 1:
            first = next((b for b in self.banche if b.predefinita), self.banche[0])
            for b in self.banche:
                b.predefinita = b is first
        self.iban = next((b.iban for b in self.banche if b.predefinita), "")
        return self


def _bank_for_invoice(company: dict, body) -> Optional[dict]:
    if body.modalita_pagamento not in ("MP05", "MP12"):
        return None
    banche = company.get("banche") or []
    if body.banca_id:
        b = next((x for x in banche if x["id"] == body.banca_id), None)
        if not b:
            raise ferr(400, "banca_id", "Banca non trovata tra le banche aziendali")
    else:
        b = next((x for x in banche if x.get("predefinita")), banche[0] if banche else None)
    if b:
        return {k: b.get(k) or "" for k in ("id", "nome", "iban", "abi", "cab", "bic")}
    return {"id": "", "nome": "", "iban": company["iban"], "abi": "", "cab": "", "bic": ""} if company.get("iban") else None


@api.get("/companies")
async def list_companies(user: dict = Depends(approved_user)):
    q = {} if user.get("role") == "admin" else {"id": {"$in": user.get("company_ids") or []}}
    rows = await db.companies.find(q, {"_id": 0, "id": 1, "denominazione": 1, "partita_iva": 1, "comune": 1, "indirizzo": 1, "cap": 1, "moduli": 1, "periodicita_iva": 1, "menu_off": 1}).sort("denominazione", 1).to_list(1000)
    for c in rows:
        c["menu_off"] = sorted(menu_off(c, user))
    if user.get("role") != "admin":
        for c in rows:
            c["moduli"] = company_moduli(c, user)
    return rows


class ModuliIn(BaseModel):
    fatturazione: bool = True
    archivio: bool = True
    fatture_attive: bool = True
    fatture_passive: bool = True
    corrispettivi: bool = True
    contabilita: bool = True

    @model_validator(mode="after")
    def _check(self):
        if not self.fatturazione and not self.archivio:
            raise ValueError("Attiva almeno un'area: Fatturazione o Archivio fatture")
        if self.fatturazione and not (self.fatture_attive or self.fatture_passive or self.corrispettivi):
            raise ValueError("Con la Fatturazione attiva scegli almeno una funzione: fatture attive, passive o corrispettivi")
        return self


@api.put("/companies/{cid}/moduli")
async def put_moduli(cid: str, body: ModuliIn, _: dict = Depends(admin_user)):
    r = await db.companies.update_one({"id": cid}, {"$set": {"moduli": body.model_dump()}})
    if not r.matched_count:
        raise HTTPException(404, "Azienda non trovata")
    return body.model_dump()


@api.put("/users/{user_id}/moduli")
async def put_user_moduli(user_id: str, body: ModuliIn, admin: dict = Depends(admin_user)):
    await _editable_target(user_id, admin)
    await db.users.update_one({"user_id": user_id}, {"$set": {"moduli": body.model_dump()}})
    return body.model_dump()


class DirittiIn(BaseModel):
    dati_azienda: bool = False
    banche: bool = False
    tabelle_contabili: bool = False
    articoli_magazzino: bool = False
    testi_comunicazioni: bool = False


@api.put("/users/{user_id}/diritti")
async def put_user_diritti(user_id: str, body: DirittiIn, admin: dict = Depends(admin_user)):
    await _editable_target(user_id, admin)
    await db.users.update_one({"user_id": user_id}, {"$set": {"diritti": body.model_dump()}})
    return body.model_dump()


class MenuIn(BaseModel):
    off: List[str] = Field(default_factory=list, max_length=60)

    @field_validator("off")
    @classmethod
    def _ids(cls, v):
        bad = [x for x in v if x not in MENU_IDS]
        if bad:
            raise ValueError(f"Voci di menu sconosciute: {', '.join(bad)}")
        return sorted(set(v))


@api.get("/menu-voci")
async def menu_voci(_: dict = Depends(admin_user)):
    return [{"id": i, "gruppo": g, "label": lab} for i, g, lab in MENU]


@api.put("/companies/{cid}/menu")
async def put_company_menu(cid: str, body: MenuIn, _: dict = Depends(admin_user)):
    r = await db.companies.update_one({"id": cid}, {"$set": {"menu_off": body.off}})
    if not r.matched_count:
        raise HTTPException(404, "Azienda non trovata")
    return {"off": body.off}


@api.put("/users/{user_id}/menu")
async def put_user_menu(user_id: str, body: MenuIn, admin: dict = Depends(admin_user)):
    await _editable_target(user_id, admin)
    await db.users.update_one({"user_id": user_id}, {"$set": {"menu_off": body.off}})
    return {"off": body.off}


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
    if await db.cons_docs.find_one({"company_id": cid, "conserva_fino": {"$gte": date.today().isoformat()}}, {"_id": 1}):
        raise HTTPException(400, "L'azienda ha documenti in conservazione decennale: non può essere eliminata")
    await db.articles.delete_many({"company_id": cid})
    await db.cons_docs.delete_many({"company_id": cid})
    await db.ddts.delete_many({"company_id": cid})
    await db.partite_aperte.delete_many({"company_id": cid})
    await db.import_batches.delete_many({"company_id": cid})
    await db.counters.delete_many({"key": f"progressivo_{cid}"})
    await db.users.update_many({}, {"$pull": {"company_ids": cid}})
    await db.companies.delete_one({"id": cid})
    return {"ok": True}


@api.get("/company")
async def get_company(t: dict = Depends(tenant)):
    return {k: v for k, v in t["company"].items() if k != "smtp"}


class SmtpIn(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    security: Literal["ssl", "starttls", "none"] = "starttls"
    username: Optional[str] = Field(default="", max_length=255)
    password: Optional[str] = Field(default=None, max_length=255)
    from_email: str
    from_name: Optional[str] = Field(default="", max_length=120)
    reply_to: Optional[str] = ""

    @field_validator("host")
    @classmethod
    def _h(cls, v):
        v = v.strip()
        if not re.fullmatch(r"[A-Za-z0-9.-]+", v):
            raise ValueError("Server SMTP non valido (es. smtp.miodominio.it)")
        return v

    @field_validator("from_email", "reply_to")
    @classmethod
    def _em(cls, v):
        v = (v or "").strip().lower()
        if v and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", v):
            raise ValueError("Email non valida")
        return v


class SmtpTestIn(BaseModel):
    to: str

    @field_validator("to")
    @classmethod
    def _em(cls, v):
        v = v.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", v):
            raise ValueError("Email non valida")
        return v


def _smtp_public(comp: dict) -> dict:
    s = comp.get("smtp") or {}
    return {k: s.get(k) for k in ("host", "port", "security", "username", "from_email", "from_name", "reply_to", "updated_at")} | {"configured": bool(s.get("host")), "has_password": bool(s.get("password_enc"))}


@api.get("/company/smtp")
async def get_smtp(t: dict = Depends(tenant_admin)):
    return _smtp_public(await db.companies.find_one({"id": t["cid"]}, {"_id": 0, "smtp": 1}) or {})


@api.put("/company/smtp")
async def put_smtp(body: SmtpIn, t: dict = Depends(tenant_admin)):
    old = (await db.companies.find_one({"id": t["cid"]}, {"_id": 0, "smtp": 1}) or {}).get("smtp") or {}
    new = body.model_dump(exclude={"password"}) | {"updated_at": now_iso()}
    if body.password:
        new["password_enc"] = FERNET.encrypt(body.password.encode()).decode()
    elif body.password is None and old.get("password_enc"):
        new["password_enc"] = old["password_enc"]
    await db.companies.update_one({"id": t["cid"]}, {"$set": {"smtp": new}})
    return _smtp_public({"smtp": new})


@api.delete("/company/smtp")
async def delete_smtp(t: dict = Depends(tenant_admin)):
    await db.companies.update_one({"id": t["cid"]}, {"$unset": {"smtp": ""}})
    return {"ok": True}


@api.post("/company/smtp/test")
async def test_smtp(body: SmtpTestIn, t: dict = Depends(tenant_admin)):
    smtp = await _company_smtp(t["cid"])
    name = escape(t["company"]["denominazione"])
    html = (f'<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif;color:#0f172a">'
            f"<p>Questa è un'email di prova inviata da <b>{name}</b> tramite il server {escape(smtp['host'])}.</p>"
            f"<p>Se la ricevi, la configurazione dell'email in uscita funziona correttamente.</p></td></tr></table>")
    await send_email(smtp=smtp, to=body.to, subject=f"Email di prova - {t['company']['denominazione']}", html=html)
    return {"ok": True}


# ---------- Backup FTP per azienda ----------
class FtpIn(BaseModel):
    attivo: bool = False
    host: str = Field(default="", max_length=200)
    porta: int = Field(default=21, ge=1, le=65535)
    utente: str = Field(default="", max_length=200)
    password: Optional[str] = Field(default=None, max_length=300)
    cartella: str = Field(default="", max_length=300)
    tls: bool = True
    ora: str = Field(default="02:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")

    @field_validator("host")
    @classmethod
    def _h(cls, v):
        v = v.strip()
        if v.lower().startswith(("ftp://", "ftps://")):
            v = v.split("://", 1)[1].split("/", 1)[0]
        if v and not re.fullmatch(r"[A-Za-z0-9.\-]+", v):
            raise ValueError("Indirizzo server non valido (es. ftp.miodominio.it)")
        return v


def _ftp_public(comp: dict) -> dict:
    f = comp.get("ftp_backup") or {}
    return {k: f.get(k) for k in ("attivo", "host", "porta", "utente", "cartella", "tls", "ora", "ultimo", "updated_at")} | {"has_password": bool(f.get("password_enc"))}


def _ftp_password(f: dict) -> str:
    try:
        return FERNET.decrypt(f["password_enc"].encode()).decode() if f.get("password_enc") else ""
    except InvalidToken:
        return ""


async def _ftp_run(comp: dict) -> dict:
    f = comp.get("ftp_backup") or {}
    if not f.get("host"):
        raise HTTPException(400, "Server FTP non configurato")
    data, name, cnt = await ftpb.build_archive(db, comp)
    err = await ftpb.upload(f, _ftp_password(f), name, data)
    esito = {"data": now_iso(), "ok": not err, "errore": err, "file": name, "dimensione": len(data), "documenti": sum(cnt.values())}
    await db.companies.update_one({"id": comp["id"]}, {"$set": {"ftp_backup.ultimo": esito}})
    return esito


async def _ftp_tick():
    now = datetime.now(ftpb.ROME)
    today = now.date().isoformat()
    for comp in await db.companies.find({"ftp_backup.attivo": True}, {"_id": 0}).to_list(500):
        if not ftpb.due(comp["ftp_backup"], now):
            continue
        claimed = await db.companies.update_one({"id": comp["id"], "ftp_backup.ultimo_giorno": {"$ne": today}}, {"$set": {"ftp_backup.ultimo_giorno": today}})
        if claimed.modified_count:
            try:
                await _ftp_run(comp)
            except Exception:  # noqa: BLE001
                logging.exception("FTP backup failed for %s", comp["id"])


@api.get("/company/ftp-backup")
async def get_ftp(t: dict = Depends(tenant_admin)):
    return _ftp_public(await db.companies.find_one({"id": t["cid"]}, {"_id": 0, "ftp_backup": 1}) or {})


@api.put("/company/ftp-backup")
async def put_ftp(body: FtpIn, t: dict = Depends(tenant_admin)):
    if body.attivo and not body.host:
        raise HTTPException(400, "Per attivare l'invio indicate il server FTP")
    old = (await db.companies.find_one({"id": t["cid"]}, {"_id": 0, "ftp_backup": 1}) or {}).get("ftp_backup") or {}
    new = body.model_dump(exclude={"password"}) | {"updated_at": now_iso(), "ultimo": old.get("ultimo"), "ultimo_giorno": old.get("ultimo_giorno")}
    if body.password:
        new["password_enc"] = FERNET.encrypt(body.password.encode()).decode()
    elif body.password is None and old.get("password_enc"):
        new["password_enc"] = old["password_enc"]
    if new["ora"] != old.get("ora") and datetime.now(ftpb.ROME).strftime("%H:%M") < new["ora"]:
        new["ultimo_giorno"] = None
    await db.companies.update_one({"id": t["cid"]}, {"$set": {"ftp_backup": new}})
    return _ftp_public({"ftp_backup": new})


@api.post("/company/ftp-backup/test")
async def test_ftp(t: dict = Depends(tenant_admin)):
    f = (await db.companies.find_one({"id": t["cid"]}, {"_id": 0, "ftp_backup": 1}) or {}).get("ftp_backup") or {}
    if not f.get("host"):
        raise HTTPException(400, "Salvate prima la configurazione FTP")
    pwd, err = await ftpb.test(f, _ftp_password(f))
    if err:
        raise HTTPException(400, err)
    return {"ok": True, "cartella": pwd}


@api.post("/company/ftp-backup/run")
async def run_ftp(t: dict = Depends(tenant_admin)):
    comp = await db.companies.find_one({"id": t["cid"]}, {"_id": 0})
    esito = await _ftp_run(comp)
    if not esito["ok"]:
        raise HTTPException(400, esito["errore"])
    return esito


class SdiIn(BaseModel):
    provider: Literal["simulato", "openapi", "acube"]
    ambiente: Literal["sandbox", "production"] = "sandbox"
    token: Optional[str] = Field(default=None, max_length=4000)
    email: Optional[str] = Field(default="", max_length=255)
    password: Optional[str] = Field(default=None, max_length=255)


def _sdi_public(comp: dict) -> dict:
    s = comp.get("sdi") or {}
    return {"provider": s.get("provider") or "simulato", "ambiente": s.get("ambiente") or "sandbox", "email": s.get("email") or "",
            "has_token": bool(s.get("token_enc")), "has_password": bool(s.get("password_enc")),
            "label": sdip.LABEL.get(s.get("provider"), "Simulato"), "updated_at": s.get("updated_at"),
            "last_sync_at": s.get("last_sync_at"), "last_sync_error": s.get("last_sync_error")}


async def _sdi_cfg(cid: str) -> Optional[dict]:
    s = ((await db.companies.find_one({"id": cid}, {"_id": 0, "sdi": 1})) or {}).get("sdi") or {}
    if s.get("provider") not in sdip.LABEL:
        return None
    try:
        return {"provider": s["provider"], "ambiente": s.get("ambiente") or "sandbox", "email": s.get("email") or "",
                "token": FERNET.decrypt(s["token_enc"].encode()).decode() if s.get("token_enc") else "",
                "password": FERNET.decrypt(s["password_enc"].encode()).decode() if s.get("password_enc") else ""}
    except InvalidToken:
        raise HTTPException(400, "Credenziali SDI non leggibili: inseriscile di nuovo in Dati azienda")


@api.get("/company/sdi")
async def get_sdi(t: dict = Depends(tenant)):
    return _sdi_public(await db.companies.find_one({"id": t["cid"]}, {"_id": 0, "sdi": 1}) or {})


@api.put("/company/sdi")
async def put_sdi(body: SdiIn, t: dict = Depends(tenant_admin)):
    old = ((await db.companies.find_one({"id": t["cid"]}, {"_id": 0, "sdi": 1})) or {}).get("sdi") or {}
    new = {"provider": body.provider, "ambiente": body.ambiente, "email": (body.email or "").strip().lower(), "updated_at": now_iso()}
    same = old.get("provider") == body.provider
    for f in ("token", "password"):
        v = getattr(body, f)
        if v:
            new[f"{f}_enc"] = FERNET.encrypt(v.strip().encode()).decode()
        elif same and old.get(f"{f}_enc"):
            new[f"{f}_enc"] = old[f"{f}_enc"]
    if body.provider == "openapi" and not new.get("token_enc"):
        raise ferr(400, "token", "Inserisci il token Openapi")
    if body.provider == "acube" and not (new["email"] and new.get("password_enc")):
        raise ferr(400, "email" if not new["email"] else "password", "Inserisci email e password dell'account A-Cube")
    await db.companies.update_one({"id": t["cid"]}, {"$set": {"sdi": new}})
    return _sdi_public({"sdi": new})


@api.post("/company/sdi/test")
async def test_sdi(t: dict = Depends(tenant_admin)):
    cfg = await _sdi_cfg(t["cid"])
    if not cfg:
        raise HTTPException(400, "Nessun intermediario configurato: l'invio è simulato")
    try:
        await sdip.check(cfg)
    except sdip.SdiError as e:
        raise HTTPException(400, f"Collegamento a {sdip.LABEL[cfg['provider']]} non riuscito: {e}")
    return {"ok": True, "message": f"Collegamento a {sdip.LABEL[cfg['provider']]} ({'prova' if cfg['ambiente'] == 'sandbox' else 'reale'}) riuscito"}


CAMPI_LAYOUT = ("cliente_codice_fiscale", "cliente_codice_destinatario", "cliente_pec", "cliente_email", "cliente_telefono",
                "causale", "note_righe", "riepilogo_iva", "scadenza", "coordinate_bancarie")


class LayoutIn(BaseModel):
    logo: Optional[str] = Field(default=None, max_length=600_000)
    colore: str = Field(default="#0f172a", pattern=r"^#[0-9a-fA-F]{6}$")
    telefono: Optional[str] = Field(default="", max_length=40)
    email: Optional[str] = Field(default="", max_length=120)
    pec: Optional[str] = Field(default="", max_length=120)
    sito: Optional[str] = Field(default="", max_length=120)
    rea: Optional[str] = Field(default="", max_length=40)
    capitale_sociale: Optional[str] = Field(default="", max_length=60)
    piede_fattura: Optional[str] = Field(default="", max_length=2000)
    piede_nc: Optional[str] = Field(default="", max_length=2000)
    piede_ddt: Optional[str] = Field(default="", max_length=2000)
    campi: dict = Field(default_factory=dict, validate_default=True)

    @field_validator("logo")
    @classmethod
    def _logo(cls, v):
        if v and not re.match(r"^data:image/(png|jpeg);base64,[A-Za-z0-9+/=]+$", v):
            raise ValueError("Logo non valido: usa un'immagine PNG o JPG fino a 400 KB")
        return v

    @field_validator("campi")
    @classmethod
    def _campi(cls, v):
        return {k: bool(v.get(k, True)) for k in CAMPI_LAYOUT}


@api.get("/company/layout")
async def get_layout(t: dict = Depends(tenant)):
    return LayoutIn(**(t["company"].get("layout") or {})).model_dump()


@api.put("/company/layout")
async def put_layout(body: LayoutIn, t: dict = Depends(tenant_admin)):
    await db.companies.update_one({"id": t["cid"]}, {"$set": {"layout": body.model_dump()}})
    return body.model_dump()


@api.put("/company")
async def put_company(body: Company, t: dict = Depends(tenant)):
    d, cur, data = diritti(t["user"]), t["company"], body.model_dump()
    if not (d["dati_azienda"] or d["banche"]):
        raise HTTPException(403, "Non hai il diritto di modificare i dati azienda o le banche")
    if not d["dati_azienda"]:
        dflt = Company.model_fields
        data = {**{k: cur[k] if cur.get(k) is not None else dflt[k].get_default(call_default_factory=True) for k in data if k not in ("banche", "iban")},
                "banche": data["banche"], "iban": data["iban"]}
    if not d["banche"]:
        data |= {"banche": cur.get("banche") or [], "iban": cur.get("iban") or ""}
    if await db.companies.find_one({"partita_iva": data["partita_iva"], "id": {"$ne": t["cid"]}}):
        raise ferr(400, "partita_iva", "Esiste già un'altra azienda con questa Partita IVA")
    await db.companies.update_one({"id": t["cid"]}, {"$set": data})
    return await db.companies.find_one({"id": t["cid"]}, COMPANY_PROJ)


# ---------- Parties ----------
class ListinoRiga(BaseModel):
    article_id: str = Field(min_length=1, max_length=40)
    prezzo: float = Field(ge=0)
    sconto: Optional[str] = Field(default="", max_length=30)

    @field_validator("sconto")
    @classmethod
    def _sc(cls, v):
        return norm_sconto(v)


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
    bollo_addebito: bool = False
    conto_costo: Optional[str] = Field(default="", max_length=12)
    detraibilita_iva: float = Field(default=100, ge=0, le=100)
    soggetto_ritenuta: bool = False
    ritenuta_tipo: Optional[str] = Field(default="RT01", pattern=r"^(RT0[1-6])?$")
    ritenuta_aliquota: float = Field(default=20, ge=0, le=100)
    ritenuta_base: float = Field(default=100, ge=0, le=100)
    ritenuta_causale: Optional[str] = Field(default="A", max_length=2)
    cassa_tipo: Optional[str] = Field(default="", pattern=r"^(TC(0[1-9]|1\d|2[0-2]))?$")
    cassa_aliquota: float = Field(default=4, ge=0, le=100)
    cassa_ritenuta: bool = False
    listino: List[ListinoRiga] = Field(default_factory=list, max_length=2000)
    appoggio_banca: Optional[str] = Field(default="", max_length=80)
    appoggio_abi: Optional[str] = ""
    appoggio_cab: Optional[str] = ""
    iban: Optional[str] = ""
    persona: Literal["giuridica", "fisica"] = "giuridica"
    nome: Optional[str] = Field(default="", max_length=60)
    cognome: Optional[str] = Field(default="", max_length=60)
    data_nascita: Optional[str] = Field(default="", pattern=r"^(\d{4}-\d{2}-\d{2})?$")
    comune_nascita: Optional[str] = Field(default="", max_length=60)
    provincia_nascita: Optional[str] = Field(default="", max_length=2)
    ritenuta_codice_tributo: Optional[str] = Field(default="1040", pattern=r"^([0-9A-Z]{4})?$")
    pagamento_modalita: Optional[str] = Field(default="", pattern=r"^(MP0[1258]|MP12)?$")
    pagamento_rate: int = Field(default=1, ge=1, le=12)
    pagamento_giorni: int = Field(default=30, ge=0, le=365)
    pagamento_fine_mese: bool = False

    @field_validator("iban")
    @classmethod
    def _iban_party(cls, v):
        return _iban_check(v) if (v or "").strip() else ""

    @field_validator("appoggio_abi", "appoggio_cab")
    @classmethod
    def _appoggio(cls, v, info):
        v = (v or "").strip()
        if v and not re.fullmatch(r"\d{5}", v):
            raise ValueError(f"Il codice {info.field_name[9:].upper()} deve avere 5 cifre")
        return v

    @model_validator(mode="after")
    def _esenzione(self):
        if self.persona == "fisica":
            if not (self.nome or "").strip():
                raise FieldError("nome", "Inserisci il nome della persona fisica")
            if not (self.cognome or "").strip():
                raise FieldError("cognome", "Inserisci il cognome della persona fisica")
            self.denominazione = f"{self.cognome.strip()} {self.nome.strip()}"
            self.provincia_nascita = (self.provincia_nascita or "").strip().upper()
        else:
            self.nome = self.cognome = self.data_nascita = self.comune_nascita = self.provincia_nascita = ""
        if (self.nazione or "IT").strip().upper() == "IT" and not (self.codice_fiscale or "").strip():
            raise FieldError("codice_fiscale", "Il codice fiscale è obbligatorio per clienti e fornitori italiani")
        if (self.nazione or "IT").strip().upper() == "IT" and self.partita_iva and not re.fullmatch(r"\d{11}", self.partita_iva):
            raise FieldError("partita_iva", "La Partita IVA deve avere 11 cifre")
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
        if n == "N3.5" and (self.intento_protocollo or "").strip():
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
        return _clean(v or "")

    @field_validator("codice_destinatario")
    @classmethod
    def _cd(cls, v):
        return _clean(v or "").upper()


@api.get("/parties")
async def list_parties(tipo: Optional[str] = None, t: dict = Depends(tenant)):
    q = {"company_id": t["cid"], **({"tipo": tipo} if tipo else {})}
    return await db.parties.find(q, {"_id": 0}).sort("denominazione", 1).to_list(2000)


async def _check_conto(cid: str, codice: Optional[str], field: str):
    if codice:
        await coge.ensure_seed(db, cid)
    if codice and not await db.coa_accounts.find_one({"company_id": cid, "codice": codice, "livello": 3}, {"_id": 1}):
        raise ferr(400, field, "Scegli un sottoconto esistente del piano dei conti")


@api.post("/parties")
async def create_party(body: PartyIn, t: dict = Depends(tenant)):
    await _check_conto(t["cid"], body.conto_costo, "conto_costo")
    doc = {"id": str(uuid.uuid4()), **body.model_dump(), "company_id": t["cid"], "created_at": now_iso()}
    await db.parties.insert_one(doc)
    return await db.parties.find_one({"id": doc["id"]}, {"_id": 0})


@api.get("/parties/{pid}/prezzo")
async def prezzo_abituale(pid: str, article_id: str, t: dict = Depends(tenant)):
    cid = t["cid"]
    p = await db.parties.find_one({"id": pid, "company_id": cid}, {"_id": 0, "listino": 1})
    if not p:
        raise HTTPException(404, "Anagrafica non trovata")
    li = next((x for x in p.get("listino") or [] if x["article_id"] == article_id), None)
    if li:
        return {"prezzo": li["prezzo"], "sconto": li.get("sconto") or "", "fonte": "listino"}
    found = []
    for nome, coll, q in (("Fattura", db.invoices, {"tipo_documento": {"$ne": "TD04"}}), ("DDT", db.ddts, {"status": {"$in": ["confermato", "fatturato"]}})):
        doc = await coll.find_one({"company_id": cid, "party_id": pid, "lines.article_id": article_id, **q}, {"_id": 0, "data": 1, "created_at": 1, "lines": 1, "numero_display": 1},
                                  sort=[("data", -1), ("created_at", -1)])
        if doc:
            ln = next(x for x in reversed(doc["lines"]) if x.get("article_id") == article_id)
            found.append((doc["data"], doc.get("created_at") or "", {"prezzo": ln["prezzo_unitario"], "sconto": ln.get("sconto") or "", "fonte": "ultima_vendita",
                                                                     "riferimento": f"{nome} {doc.get('numero_display') or 'bozza'} del {itd(doc['data'])}"}))
    if found:
        return max(found, key=lambda x: (x[0], x[1]))[2]
    a = await db.articles.find_one({"id": article_id, "company_id": cid}, {"_id": 0, "prezzo": 1})
    return {"prezzo": (a or {}).get("prezzo") or 0, "sconto": "", "fonte": "articolo"}


@api.put("/parties/{pid}")
async def update_party(pid: str, body: PartyIn, t: dict = Depends(tenant)):
    await _check_conto(t["cid"], body.conto_costo, "conto_costo")
    res = await db.parties.update_one({"id": pid, "company_id": t["cid"]}, {"$set": body.model_dump() | {"da_verificare": False}})
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
    gestione_magazzino: bool = False
    scorta_minima: float = Field(default=0, ge=0)
    scorta_riordino: float = Field(default=0, ge=0)
    fornitore_abituale: Optional[str] = Field(default="", max_length=120)
    conto_ricavo: Optional[str] = Field(default="", max_length=12)

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
    await _check_conto(t["cid"], body.conto_ricavo, "conto_ricavo")
    if await db.articles.find_one({"codice": body.codice, "company_id": t["cid"]}):
        raise ferr(400, "codice", "Codice articolo già esistente")
    doc = {"id": str(uuid.uuid4()), **body.model_dump(), "company_id": t["cid"], "created_at": now_iso()}
    await db.articles.insert_one(doc)
    return await db.articles.find_one({"id": doc["id"]}, {"_id": 0})


@api.put("/articles/{aid}")
async def update_article(aid: str, body: ArticleIn, t: dict = Depends(tenant)):
    await _check_conto(t["cid"], body.conto_ricavo, "conto_ricavo")
    if await db.articles.find_one({"codice": body.codice, "company_id": t["cid"], "id": {"$ne": aid}}):
        raise ferr(400, "codice", "Codice articolo già esistente")
    if not body.gestione_magazzino and await db.stock_moves.find_one({"company_id": t["cid"], "article_id": aid}, {"_id": 1}):
        raise ferr(400, "gestione_magazzino", "L'articolo ha movimenti di magazzino: la gestione non può essere disattivata")
    res = await db.articles.update_one({"id": aid, "company_id": t["cid"]}, {"$set": body.model_dump()})
    if not res.matched_count:
        raise HTTPException(404, "Articolo non trovato")
    await db.stock_moves.update_many({"company_id": t["cid"], "article_id": aid},
                                     {"$set": {"codice": body.codice, "descrizione": body.descrizione, "unita_misura": body.unita_misura or ""}})
    return await db.articles.find_one({"id": aid}, {"_id": 0})


@api.delete("/articles/{aid}")
async def delete_article(aid: str, t: dict = Depends(tenant)):
    if await db.stock_moves.find_one({"company_id": t["cid"], "article_id": aid}, {"_id": 1}):
        raise HTTPException(400, "L'articolo ha movimenti di magazzino: non può essere eliminato")
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
    article_id: Optional[str] = Field(default=None, max_length=40)
    sconto: Optional[str] = Field(default="", max_length=30)
    bollo: bool = False

    @field_validator("sconto")
    @classmethod
    def _sc(cls, v):
        return norm_sconto(v)

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
    tipo_documento: Literal["TD01", "TD04", "TD05", "TD06", "TD24"] = "TD01"
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
    banca_id: Optional[str] = None
    bollo: Optional[bool] = None

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


BOLLO_NATURE = ("N2.1", "N2.2", "N3.5", "N3.6", "N4")
BOLLO_SOGLIA, BOLLO_IMPORTO = 77.47, 2.0
BOLLO_DESC = "Imposta di bollo assolta in modo virtuale"


def _apply_bollo(body: InvoiceIn, cliente: dict) -> dict:
    body.lines = [ln for ln in body.lines if not ln.bollo and ln.descrizione != f"{BOLLO_DESC} (art. 6 DM 17/06/2014)"] or body.lines
    esenti = round(sum(float(line_total(ln.model_dump())) for ln in body.lines if ln.aliquota == 0 and ln.natura in BOLLO_NATURE), 2)
    dovuto = esenti > BOLLO_SOGLIA
    on = dovuto if body.bollo is None else body.bollo
    add = on and bool(cliente.get("bollo_addebito"))
    if add:
        body.lines.append(LineIn(descrizione=f"{BOLLO_DESC} (art. 6 DM 17/06/2014)", quantita=1, prezzo_unitario=BOLLO_IMPORTO, aliquota=0, natura="N1", bollo=True))
    return {"bollo_virtuale": on, "bollo_importo": BOLLO_IMPORTO if on else 0.0, "bollo_addebitato": add, "bollo_esenti": esenti, "bollo_dovuto": dovuto}


async def _party_snapshot(pid: str, cid: str, lines: List[LineIn] = (), cassa: Optional[CassaIn] = None) -> dict:
    p = await db.parties.find_one({"id": pid, "tipo": "cliente", "company_id": cid}, {"_id": 0})
    if not p:
        raise ferr(400, "party_id", "Seleziona un cliente")
    return p


async def _intento(cid: str, cliente: dict, data: str, totals: dict, td: str, exclude: Optional[str] = None, collegata_id: Optional[str] = None) -> Optional[dict]:
    imp = intenti_mod.imponibile_n35(totals.get("riepilogo"))
    if not imp:
        return None
    pref = None
    if td == "TD04" and collegata_id:
        pref = ((await db.invoices.find_one({"id": collegata_id, "company_id": cid}, {"_id": 0, "intento": 1}) or {}).get("intento") or {}).get("id")
    it = await intento_scegli(cid, cliente, data, imp, exclude, nc=td == "TD04", preferito=pref)
    cliente["intento_protocollo"], cliente["intento_data"] = it["protocollo"], it["data"]
    return it


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


_INTENTO_LOCKS: dict = {}


def _serial_company(fn):
    @functools.wraps(fn)
    async def w(*a, **k):
        t = k.get("t") if "t" in k else a[-1]
        lock = _INTENTO_LOCKS.setdefault(t["cid"], asyncio.Lock())
        async with lock:
            return await fn(*a, **k)
    return w


@api.post("/invoices")
@_serial_company
async def create_invoice(body: InvoiceIn, t: dict = Depends(tenant)):
    user, cid = t["user"], t["cid"]
    _check_lines(body.lines)
    cliente = await _party_snapshot(body.party_id, cid, body.lines, body.cassa)
    _check_pa(body, cliente)
    bollo = _apply_bollo(body, cliente)
    anno = int(body.data[:4])
    totals = _totals(body, cliente)
    _check_rate(body, totals)
    intento = await _intento(cid, cliente, body.data, totals, body.tipo_documento, None, body.fattura_collegata_id)
    sez = _sezionale(body.tipo_documento)
    collegata = await _linked_invoice(body, cid, totals["totale"])
    banca = _bank_for_invoice(t["company"], body)
    body.banca_id = banca["id"] if banca else None
    for _ in range(1 if body.numero else 5):
        if body.numero:
            numero = body.numero
        else:
            last = await db.invoices.find_one({"anno": anno, "company_id": cid, "sezionale": sez}, {"_id": 0, "numero": 1}, sort=[("numero", -1)])
            numero = (last["numero"] if last else 0) + 1
        await _check_sequence(cid, sez, anno, numero, body.data)
        doc = {
            "id": str(uuid.uuid4()), **body.model_dump(), **totals, **bollo, "company_id": cid,
            "numero": numero, "anno": anno, "sezionale": sez, "numero_display": _display(numero, sez, anno),
            "fattura_collegata_id": collegata["id"] if collegata else None, "fattura_collegata": collegata,
            "progressivo_invio": await _next_progressivo(cid), "cliente": cliente, "banca": banca, "intento": intento,
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
@_serial_company
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
    bollo = _apply_bollo(body, cliente)
    totals = _totals(body, cliente)
    _check_rate(body, totals)
    intento = await _intento(cid, cliente, body.data, totals, body.tipo_documento, iid, body.fattura_collegata_id)
    collegata = await _linked_invoice(body, cid, totals["totale"], iid)
    banca = _bank_for_invoice(t["company"], body)
    body.banca_id = banca["id"] if banca else None
    numero = body.numero or inv["numero"]
    await _check_sequence(cid, inv.get("sezionale", ""), inv["anno"], numero, body.data, iid)
    try:
        await db.invoices.update_one({"id": iid, "company_id": cid}, {"$set": {**body.model_dump(exclude={"numero"}), **totals, **bollo, "cliente": cliente, "banca": banca, "intento": intento, "updated_at": now_iso(),
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
    if inv.get("autofattura") and inv.get("passive_id"):
        await db.passive_invoices.update_one({"id": inv["passive_id"], "company_id": cid}, {"$unset": {"autofattura_id": "", "autofattura_numero": ""}})
    await ddt_mod.on_invoice_deleted(db, cid, iid)
    return {"ok": True}


def _company_required(t: dict) -> dict:
    c = t["company"]
    if not c.get("partita_iva"):
        raise HTTPException(400, "Completa prima i dati azienda in Impostazioni")
    return c


@api.get("/invoices/{iid}/xml")
async def invoice_xml(iid: str, t: dict = Depends(tenant)):
    inv = await _get_invoice(iid, t["cid"])
    if inv.get("manuale"):
        raise HTTPException(400, "Documento registrato a mano: non ha un file XML FatturaPA")
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
    if (c.get("codice_destinatario") or "0000000") == "0000000" and not c.get("pec") and c.get("partita_iva") and not inv.get("autofattura"):
        return "Errore 00426: Codice Destinatario 0000000 senza PEC destinatario (cliente con P.IVA)"
    if inv["totale"] <= 0 and inv.get("tipo_documento") == "TD01":
        return "Errore 00433: importo totale documento non valido"
    return None


async def _push_status(iid: str, status: str, message: str, extra: dict = None, notifica: str = None):
    await db.invoices.update_one({"id": iid}, {
        "$set": {"status": status, "sdi_message": message, "sdi_notifica": notifica, "updated_at": now_iso(), **(extra or {})},
        "$push": {"sdi_history": {"status": status, "notifica": notifica, "at": now_iso(), "message": message}},
    })
    if status in coge.AUTO_STATI:
        inv_ = await db.invoices.find_one({"id": iid}, {"_id": 0})
        await coge.safe(coge.registra_vendita(db, inv_))
        comp_ = await db.companies.find_one({"id": inv_["company_id"]}, COMPANY_PROJ)
        if comp_ and company_moduli(comp_)["fatture_attive"]:
            asyncio.create_task(coge.safe(com_cortesia(comp_, inv_)))


class InvioMassivoIn(BaseModel):
    ids: List[str] = Field(min_length=1, max_length=500)


@api.get("/invio-sdi/da-inviare")
async def invio_sdi_lista(dal: Optional[str] = None, al: Optional[str] = None, t: dict = Depends(tenant_accounting)):
    q = {"company_id": t["cid"], "status": {"$in": ["bozza", "scartata"]}}
    if dal or al:
        q["data"] = {**({"$gte": dal} if dal else {}), **({"$lte": al} if al else {})}
    proj = {"_id": 0, "id": 1, "numero_display": 1, "numero": 1, "anno": 1, "data": 1, "tipo_documento": 1, "status": 1, "totale": 1, "autofattura": 1,
            "cliente.denominazione": 1, "cliente.codice_destinatario": 1, "cliente.pec": 1}
    return await db.invoices.find(q, proj).sort([("data", 1), ("anno", 1), ("numero", 1)]).to_list(5000)


@api.post("/invio-sdi")
async def invio_sdi_massivo(body: InvioMassivoIn, t: dict = Depends(tenant_accounting)):
    docs = await db.invoices.find({"company_id": t["cid"], "id": {"$in": list(dict.fromkeys(body.ids))}}, {"_id": 0, "id": 1, "numero_display": 1, "data": 1, "anno": 1, "numero": 1}).to_list(500)
    out = []
    for d in sorted(docs, key=lambda x: (x["data"], x.get("anno") or 0, x.get("numero") or 0)):
        try:
            r = await send_sdi(d["id"], t)
            out.append({"id": d["id"], "numero_display": d["numero_display"], "ok": True, "status": r["status"]})
        except HTTPException as e:
            out.append({"id": d["id"], "numero_display": d["numero_display"], "ok": False, "errore": e.detail if isinstance(e.detail, str) else str(e.detail)})
    return {"inviate": sum(x["ok"] for x in out), "errori": sum(not x["ok"] for x in out), "risultati": out}


@api.post("/invoices/{iid}/send")
async def send_sdi(iid: str, t: dict = Depends(tenant_accounting)):
    cid = t["cid"]
    inv = await _get_invoice(iid, cid)
    if inv["status"] not in ("bozza", "scartata"):
        raise HTTPException(400, "Fattura già inviata")
    company = _company_required(t)
    if (inv.get("intento") or {}).get("id"):
        it = await _intento(cid, inv["cliente"], inv["data"], inv, inv.get("tipo_documento"), iid, inv.get("fattura_collegata_id"))
        if it and it["id"] != inv["intento"]["id"]:
            inv["intento"] = it
            await db.invoices.update_one({"id": iid}, {"$set": {"intento": it, "cliente": inv["cliente"]}})
    if inv.get("tipo_documento") == "TD04" and inv.get("fattura_collegata_id"):
        others = await db.invoices.find({"company_id": cid, "fattura_collegata_id": inv["fattura_collegata_id"], "id": {"$ne": iid},
                                         "status": {"$nin": ["scartata", "bozza"]}}, {"_id": 0, "totale": 1}).to_list(500)
        residuo = round(inv["fattura_collegata"]["totale"] - sum(o["totale"] for o in others), 2)
        if inv["totale"] > residuo + 0.005:
            raise HTTPException(400, f"Importo superiore al residuo stornabile della fattura collegata ({_eur(residuo)})")
    if inv["status"] == "scartata":
        inv["progressivo_invio"] = await _next_progressivo(cid)
        await db.invoices.update_one({"id": iid}, {"$set": {"progressivo_invio": inv["progressivo_invio"]}})
    fname = file_name(company, inv)
    cfg = await _sdi_cfg(cid)
    if cfg:
        try:
            sdi_id = await sdip.send(cfg, build_xml(company, inv))
        except sdip.SdiError as e:
            raise HTTPException(400, f"{sdip.LABEL[cfg['provider']]} ha rifiutato l'invio: {e}")
        amb = "ambiente di prova" if cfg["ambiente"] == "sandbox" else "ambiente reale"
        await _push_status(iid, "inviata", f"File {fname} trasmesso a {sdip.LABEL[cfg['provider']]} ({amb}). Id {sdi_id}",
                           {"sdi_id": sdi_id, "sdi_provider": cfg["provider"], "sdi_ambiente": cfg["ambiente"], "sdi_seen": [], "sent_at": now_iso()}, notifica="IN")
        return await _get_invoice(iid, cid)
    sdi_id = str(uuid.uuid4().int)[:10]
    await _push_status(iid, "inviata", f"File {fname} trasmesso all'intermediario (SIMULATO). Id SDI {sdi_id}",
                       {"sdi_id": sdi_id, "sdi_provider": None, "sent_at": now_iso()}, notifica="IN")
    return await _get_invoice(iid, cid)


async def _sdi_poll_invoice(inv: dict, cfg: dict) -> int:
    notes = await sdip.notifications(cfg, inv["sdi_id"])
    seen, new = set(inv.get("sdi_seen") or []), 0
    for n in notes:
        key = n["uuid"] or f"{n['type']}|{n['at']}|{n['message'][:40]}"
        if key in seen:
            continue
        seen.add(key)
        new += 1
        status = sdip.STATUS_BY_TYPE.get(n["type"], inv["status"])
        await _push_status(inv["id"], status, f"Notifica {n['type'] or 'SDI'}: {n['message'] or 'ricevuta'}", {"sdi_seen": list(seen)}, notifica=n["type"] or None)
        inv["status"] = status
    return new


@api.post("/invoices/{iid}/refresh")
async def refresh_sdi(iid: str, t: dict = Depends(tenant)):
    inv = await _get_invoice(iid, t["cid"])
    if inv.get("sdi_provider"):
        cfg = await _sdi_cfg(t["cid"])
        if not cfg or cfg["provider"] != inv["sdi_provider"]:
            raise HTTPException(400, f"La fattura è stata inviata con {sdip.LABEL[inv['sdi_provider']]}: riattiva quel collegamento in Dati azienda")
        try:
            n = await _sdi_poll_invoice(inv, cfg)
        except sdip.SdiError as e:
            raise HTTPException(400, f"Impossibile leggere le notifiche da {sdip.LABEL[cfg['provider']]}: {e}")
        if not n:
            raise HTTPException(400, "Nessuna nuova notifica dallo SDI: riprova più tardi")
        return await _get_invoice(iid, t["cid"])
    if inv["status"] != "inviata":
        raise HTTPException(400, "Nessun esito da aggiornare")
    await _sim_outcome(inv)
    return await _get_invoice(iid, t["cid"])


async def _sim_outcome(inv: dict):
    iid, err, c = inv["id"], _sdi_checks(inv), inv["cliente"]
    if err:
        await _push_status(iid, "scartata", f"Notifica di scarto (NS): {err}", notifica="NS")
    elif (c.get("codice_destinatario") or "0000000") == "0000000" and not c.get("pec"):
        await _push_status(iid, "mancata_consegna", "Notifica di mancata consegna (MC): fattura a disposizione del cliente nell'area riservata Fatture e Corrispettivi", notifica="MC")
    else:
        await _push_status(iid, "consegnata", "Ricevuta di consegna (RC): fattura recapitata al destinatario", notifica="RC")


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
        lines=[LineIn(**{k: ln.get(k) for k in ("descrizione", "quantita", "unita_misura", "prezzo_unitario", "aliquota", "natura", "note", "sconto")}) for ln in orig["lines"] if not ln.get("bollo")] or [LineIn(**{k: ln.get(k) for k in ("descrizione", "quantita", "unita_misura", "prezzo_unitario", "aliquota", "natura", "note", "sconto")}) for ln in orig["lines"]],
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
async def ipa_search(q: str, t: dict = Depends(tenant)):
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
               "netto": 1, "rate": 1, "rate_mod": 1, "scadenza": 1, "tipo_documento": 1, "fattura_collegata_id": 1}


async def _ledger(cid: str, party_id: Optional[str] = None, escludi_reg: Optional[str] = None):
    q = {"company_id": cid, "status": {"$in": list(IVA_STATI)}, "autofattura": {"$ne": True}}
    if party_id:
        q["party_id"] = party_id
    invs = await db.invoices.find(q, LEDGER_PROJ).to_list(20000)
    invs += await db.partite_aperte.find({"company_id": cid, "tipo": "cliente", **({"party_id": party_id} if party_id else {})}, LEDGER_PROJ).to_list(20000)
    pq = {"company_id": cid, **({"party_id": party_id} if party_id else {}), **({"coge_entry_id": {"$ne": escludi_reg}} if escludi_reg else {})}
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
    inv = await db.partite_aperte.find_one({"id": iid, "company_id": t["cid"], "tipo": "cliente"}, {"_id": 0}) or await _get_invoice(iid, t["cid"])
    docs, crediti, pays, _ = await _ledger(t["cid"], inv["party_id"])
    doc = next((d for d in docs if d["id"] == iid), None)
    return {"scadenzario": doc, "pagamenti": sorted([p for p in pays if p["invoice_id"] == iid], key=lambda p: p["data"]), "crediti": crediti}


@api.post("/invoices/{iid}/pagamenti")
async def add_payment(iid: str, body: PagamentoIn, t: dict = Depends(tenant_accounting)):
    cid = t["cid"]
    inv = await db.partite_aperte.find_one({"id": iid, "company_id": cid, "tipo": "cliente"}, {"_id": 0}) or await _get_invoice(iid, cid)
    if inv.get("tipo_documento") == "TD04" or inv["status"] not in (*IVA_STATI, "storico"):
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
    if await db.payments.find_one({"id": pid, "company_id": t["cid"], "riba_effetto_id": {"$exists": True}}, {"_id": 1}):
        raise HTTPException(400, "Incasso da distinta Ri.Ba.: annulla la distinta o registra l'insoluto dalla pagina Effetti Ri.Ba.")
    await _check_payment_coge(db.payments, t["cid"], pid)
    await _check_payment_tx(t["cid"], pid)
    r = await db.payments.delete_one({"id": pid, "company_id": t["cid"]})
    if not r.deleted_count:
        raise HTTPException(404, "Incasso non trovato")
    await _unlink_payment(t["cid"], pid)
    return {"ok": True}


# ---------- Fatture passive ----------
PASSIVE_LIST = {"_id": 0, "xml_b64": 0, "lines": 0, "riepilogo": 0}


async def _supplier(cid: str, f: dict) -> tuple:
    q = [{"partita_iva": f["partita_iva"]}] if f.get("partita_iva") else []
    q += [{"codice_fiscale": f["codice_fiscale"]}] if f.get("codice_fiscale") else []
    if q:
        p = await db.parties.find_one({"company_id": cid, "tipo": "fornitore", "$or": q}, {"_id": 0, "id": 1})
        if p:
            return p["id"], False
    naz = (f.get("nazione") or f.get("paese_iva") or "IT").upper()
    doc = {"id": str(uuid.uuid4()), "company_id": cid, "tipo": "fornitore", "denominazione": f["denominazione"] or "Fornitore senza nome",
           "partita_iva": f.get("partita_iva", ""), "codice_fiscale": f.get("codice_fiscale") or (f.get("partita_iva", "") if naz == "IT" else ""),
           "codice_destinatario": "0000000", "pec": "", "email": f.get("email", ""), "telefono": f.get("telefono", ""),
           "regime_fiscale": f.get("regime_fiscale", ""), "rea": f.get("rea", ""), "iban": f.get("iban", ""), "da_verificare": True, "indirizzo": f.get("indirizzo", ""), "cap": f.get("cap", ""), "comune": f.get("comune", ""),
           "provincia": f.get("provincia", ""), "nazione": naz, "natura_default": "", "riferimento_normativo": "",
           "intento_protocollo": "", "intento_data": "", "pubblica_amministrazione": False, "split_payment": False,
           "origine": "fattura_passiva", "created_at": now_iso()}
    await db.parties.insert_one(doc)
    return doc["id"], True


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
    f["iban"] = next((r["iban"] for d in parsed["docs"] for r in d["rate"] if r.get("iban")), "")
    pid, nuovo = await _supplier(cid, f)
    sup = await db.parties.find_one({"id": pid}, {"_id": 0}) or {}
    for d in parsed["docs"]:
        if await db.passive_invoices.find_one({"company_id": cid, "party_id": pid, "numero": d["numero"], "data": d["data"], "tipo_documento": d["tipo_documento"]}, {"_id": 1}):
            raise ValueError(f"Documento {d['numero']} del {_it_date(d['data'])} di {f['denominazione']} già presente")
    out = []
    for i, d in enumerate(parsed["docs"]):
        coll = None
        if d["tipo_documento"] == "TD04" and d["collegate"]:
            coll = await db.passive_invoices.find_one({"company_id": cid, "party_id": pid, "numero": {"$in": d["collegate"]}, "tipo_documento": {"$ne": "TD04"}}, {"_id": 0, "id": 1})
        doc = {"id": str(uuid.uuid4()), "company_id": cid, "origine": origine, "file_name": file_name, "hash": h if i == 0 else f"{h}:{i}",
               "detraibilita_iva": float(sup.get("detraibilita_iva", 100)),
               "xml_b64": base64.b64encode(xml).decode(), "sdi_progressivo": parsed["progressivo"], "fornitore": f, "party_id": pid,
               **d, "numero_display": d["numero"], "scadenza": d["rate"][-1]["scadenza"] if d["rate"] else d["data"],
               "fattura_collegata_id": coll["id"] if coll else None, "stato_reg": "da_registrare", "note": "",
               "ricevuta_at": now_iso(), "created_by_name": t["user"].get("name") or t["user"]["email"]}
        if sup.get("soggetto_ritenuta") and not d.get("ritenuta_importo") and d["tipo_documento"] in ("TD01", "TD04", "TD06"):
            imp = d.get("imponibile") or 0
            if sup.get("cassa_tipo") and not sup.get("cassa_ritenuta"):
                imp = imp / (1 + (sup.get("cassa_aliquota") or 0) / 100)
            base = round(imp * (sup.get("ritenuta_base") or 100) / 100, 2)
            doc |= _ritenuta_upd(doc, sup.get("ritenuta_aliquota") or 0, base) | {"ritenuta_auto": True}
        doc |= {"ritenuta_tipo": sup.get("ritenuta_tipo") or "", "ritenuta_causale": sup.get("ritenuta_causale") or "", "cassa_tipo": sup.get("cassa_tipo") or ""} if sup.get("soggetto_ritenuta") else {}
        await db.passive_invoices.insert_one(doc)
        await coge.safe(coge.registra_acquisto(db, doc))
        if d["tipo_documento"] != "TD04":
            await db.passive_invoices.update_many({"company_id": cid, "party_id": pid, "tipo_documento": "TD04", "fattura_collegata_id": None, "collegate": d["numero"]},
                                                  {"$set": {"fattura_collegata_id": doc["id"]}})
        out.append({"id": doc["id"], "numero": d["numero"], "fornitore": f["denominazione"], "totale": d["totale"], "nuovo_fornitore_id": pid if nuovo else None})
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


async def _sdi_receive(t: dict, cfg: dict) -> list:
    docs = []
    for rid, raw in await sdip.received(cfg, t["company"]["partita_iva"]):
        try:
            docs += await _import_passive(t, raw, f"SDI_{rid}.xml", "sdi")
        except ValueError:
            continue
    return docs


def _schedule(comp: dict) -> dict:
    return sdis.ScheduleIn().model_dump() | (comp.get("sdi_schedule") or {})


async def _sdi_sync_company(comp: dict, manual_by: Optional[str] = None) -> dict:
    s, m = _schedule(comp), company_moduli(comp)
    run = {"at": now_iso(), "manual_by": manual_by, "fatture": 0, "notifiche": 0, "error": None, "simulato": False}
    try:
        cfg = await _sdi_cfg(comp["id"])
        run["simulato"] = not cfg
        if s["notifiche"] and m["fatturazione"] and m["fatture_attive"]:
            invs = await db.invoices.find({"company_id": comp["id"], "status": "inviata", "sdi_provider": cfg["provider"] if cfg else None}, {"_id": 0}).to_list(500)
            for inv in invs:
                if cfg:
                    run["notifiche"] += await _sdi_poll_invoice(inv, cfg)
                else:
                    await _sim_outcome(inv)
                    run["notifiche"] += 1
        if cfg and s["passive"] and m["fatturazione"] and m["fatture_passive"] and comp.get("partita_iva"):
            docs = await _sdi_receive({"cid": comp["id"], "company": comp, "user": {"name": manual_by or "Ricezione pianificata SDI", "email": "sdi"}}, cfg)
            run["fatture"] = len(docs)
    except (sdip.SdiError, HTTPException) as e:
        run["error"] = str(getattr(e, "detail", e))
    except Exception as e:  # noqa: BLE001
        logging.exception("SDI sync failed")
        run["error"] = f"errore imprevisto: {e.__class__.__name__}"
    await db.companies.update_one({"id": comp["id"]}, {"$set": {"sdi_schedule.last_run": run, "sdi.last_sync_at": run["at"], "sdi.last_sync_error": run["error"]}})
    return run


async def _sdi_loop():
    while True:
        await asyncio.sleep(60)
        try:
            await com_tick()
        except Exception:  # noqa: BLE001
            logging.exception("Comunicazioni tick failed")
        try:
            await riba_tick()
        except Exception:  # noqa: BLE001
            logging.exception("Ri.Ba. tick failed")
        try:
            await _ftp_tick()
        except Exception:  # noqa: BLE001
            logging.exception("FTP backup tick failed")
        try:
            now = now_iso()
            for comp in await db.companies.find({"sdi_schedule.enabled": True, "sdi_schedule.next_run_at": {"$lte": now}}, COMPANY_PROJ).to_list(500):
                nxt = sdis.next_run(_schedule(comp))
                claimed = await db.companies.update_one({"id": comp["id"], "sdi_schedule.next_run_at": comp["sdi_schedule"]["next_run_at"]}, {"$set": {"sdi_schedule.next_run_at": nxt}})
                if claimed.modified_count:
                    await _sdi_sync_company(comp)
            for comp in await db.companies.find({"banca.auto": True, "$or": [{"banca.next_sync_at": {"$lte": now}}, {"banca.next_sync_at": None}]}, COMPANY_PROJ).to_list(500):
                nxt = (datetime.now(timezone.utc) + timedelta(hours=BANK_SYNC_HOURS)).isoformat()
                claimed = await db.companies.update_one({"id": comp["id"], "banca.next_sync_at": comp["banca"].get("next_sync_at")}, {"$set": {"banca.next_sync_at": nxt}})
                if claimed.modified_count:
                    try:
                        await _bank_sync(comp)
                    except HTTPException:
                        pass
        except Exception:  # noqa: BLE001
            logging.exception("SDI scheduler error")


def _schedule_public(comp: dict) -> dict:
    s = _schedule(comp)
    return s | {"descrizione": sdis.describe(s), "provider": (comp.get("sdi") or {}).get("provider") or "simulato"}


@api.get("/company/sdi-schedule")
async def get_sdi_schedule(t: dict = Depends(tenant)):
    return _schedule_public(t["company"])


@api.put("/company/sdi-schedule")
async def put_sdi_schedule(body: sdis.ScheduleIn, t: dict = Depends(tenant_admin)):
    s = body.model_dump()
    s["next_run_at"] = sdis.next_run(s)
    s["last_run"] = (t["company"].get("sdi_schedule") or {}).get("last_run")
    s["updated_at"] = now_iso()
    await db.companies.update_one({"id": t["cid"]}, {"$set": {"sdi_schedule": s}})
    return _schedule_public({**t["company"], "sdi_schedule": s})


@api.post("/company/sdi-schedule/run")
async def run_sdi_schedule(t: dict = Depends(tenant_accounting)):
    if not company_moduli(t["company"], t["user"])["fatturazione"]:
        raise HTTPException(403, "Modulo non attivo per questa azienda o per il tuo utente: Fatturazione")
    run = await _sdi_sync_company(t["company"], manual_by=t["user"].get("name") or t["user"]["email"])
    comp = await db.companies.find_one({"id": t["cid"]}, COMPANY_PROJ)
    return {"run": run, "schedule": _schedule_public(comp)}


@api.post("/passive/sdi-sync")
async def passive_sdi_sync(t: dict = Depends(tenant_accounting)):
    if not t["company"].get("partita_iva"):
        raise HTTPException(400, "Inserisci la Partita IVA nei dati azienda")
    cfg = await _sdi_cfg(t["cid"])
    if cfg:
        try:
            return {"ricevute": await _sdi_receive(t, cfg)}
        except sdip.SdiError as e:
            raise HTTPException(400, f"Impossibile scaricare le fatture da {sdip.LABEL[cfg['provider']]}: {e}")
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
        rc_rows = [{**r, "idx": i} for i, r in enumerate(d.get("riepilogo") or []) if (r.get("natura") or "").startswith("N6")]
        aliq = 22.0 if body.aliquota_rc is None else body.aliquota_rc
        if rc_rows and aliq not in RC_ALIQUOTE:
            raise ferr(422, "aliquota_rc", "Aliquota IVA per il reverse charge non valida (4, 5, 10 o 22%)")
        rc = [{"idx": r["idx"], "natura": r["natura"], "imponibile": r["imponibile"], "aliquota": aliq, "imposta": round(r["imponibile"] * aliq / 100, 2)} for r in rc_rows]
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
                                             "fornitore": 1, "riepilogo": 1, "totale": 1, "split_payment": 1, "reverse_charge": 1, "detraibilita_iva": 1}).sort("protocollo", 1).to_list(20000)
    rows, out = _iva_register(docs, lambda d: {**{k: d.get(k) for k in ("id", "protocollo", "data_registrazione", "data", "numero", "tipo_documento", "split_payment")},
                                               "fornitore": d["fornitore"]["denominazione"], "partita_iva": d["fornitore"].get("partita_iva") or d["fornitore"].get("codice_fiscale")})
    return {"anno": anno, "anni": anni, "rows": rows, **out, "azienda": {k: t["company"].get(k) for k in ("denominazione", "partita_iva")}}


def _iva_register(docs: list, base) -> tuple:
    tot, rows = {}, []
    indet = 0.0
    for d in docs:
        sgn = -1 if d["tipo_documento"] == "TD04" else 1
        pct = float(d.get("detraibilita_iva", 100) if d.get("detraibilita_iva") is not None else 100)
        rcm = {r.get("idx", i): r for i, r in enumerate(d.get("reverse_charge") or [])}
        rie = [{"aliquota": rc["aliquota"], "natura": r["natura"], "imponibile": round(sgn * r["imponibile"], 2), "imposta": round(sgn * rc["imposta"], 2), "rc": True}
               if (rc := rcm.get(i)) else
               {"aliquota": r["aliquota"], "natura": r.get("natura"), "imponibile": round(sgn * r["imponibile"], 2), "imposta": round(sgn * r["imposta"], 2)} for i, r in enumerate(d.get("riepilogo") or [])]
        for r in rie:
            k = f"{r['natura']} RC {r['aliquota']:g}%" if r.get("rc") else r["natura"] or f"{r['aliquota']:g}%"
            x = tot.setdefault(k, {"codice": k, "aliquota": r["aliquota"], "natura": r["natura"], "rc": bool(r.get("rc")), "imponibile": 0.0, "imposta": 0.0, "documenti": 0})
            x["imponibile"] += r["imponibile"]
            x["imposta"] += r["imposta"]
            x["documenti"] += 1
        ind = round(sum(r["imposta"] for r in rie) * (100 - pct) / 100, 2)
        indet += ind
        rows.append({**base(d), "riepilogo": rie, "totale": round(sgn * d["totale"], 2), "detraibilita_iva": pct, "iva_indetraibile": ind})
    totali = sorted(({**v, "imponibile": round(v["imponibile"], 2), "imposta": round(v["imposta"], 2)} for v in tot.values()), key=lambda v: (v["natura"] is not None, -v["aliquota"], v["codice"]))
    split = round(sum(sum(r["imposta"] for r in x["riepilogo"]) for x in rows if x.get("split_payment")), 2)
    rc = round(sum(sum(r["imposta"] for r in x["riepilogo"] if r.get("rc")) for x in rows), 2)
    return rows, {"totali": totali, "imposta_rc": rc, "imponibile": round(sum(v["imponibile"] for v in totali), 2), "imposta": round(sum(v["imposta"] for v in totali), 2),
                  "imposta_split": split, "totale": round(sum(r["totale"] for r in rows), 2), "imposta_indetraibile": round(indet, 2)}


class DetraibilitaIn(BaseModel):
    percentuale: float = Field(ge=0, le=100)


@api.put("/passive/{pid}/detraibilita")
async def set_detraibilita(pid: str, body: DetraibilitaIn, t: dict = Depends(tenant_accounting)):
    doc = await _get_passive(pid, t["cid"])
    await coge.check_annullabile(db, t["cid"], "acquisto", pid)
    await db.passive_invoices.update_one({"id": pid}, {"$set": {"detraibilita_iva": round(body.percentuale, 2)}})
    await coge.annulla(db, t["cid"], "acquisto", pid)
    await coge.safe(coge.registra_acquisto(db, {**doc, "detraibilita_iva": round(body.percentuale, 2)}))
    return {"ok": True, "detraibilita_iva": round(body.percentuale, 2)}


SALES_PROJ = {"_id": 0, "id": 1, "numero": 1, "sezionale": 1, "numero_display": 1, "data": 1, "tipo_documento": 1, "cliente": 1, "riepilogo": 1, "totale": 1, "split_payment": 1}


def _sales_row(d: dict) -> dict:
    c = d.get("cliente") or {}
    return {"id": d["id"], "numero": d["numero_display"], "data": d["data"], "tipo_documento": d["tipo_documento"], "split_payment": d.get("split_payment", False),
            "cliente": c.get("denominazione", ""), "partita_iva": c.get("partita_iva") or c.get("codice_fiscale")}


BOLLI_SCADENZE = {1: ("05-31", 0), 2: ("09-30", 0), 3: ("11-30", 0), 4: ("02-28", 1)}


@api.get("/bolli")
async def bolli_report(anno: int = Query(ge=2000, le=2100), t: dict = Depends(tenant)):
    docs = await db.invoices.find({"company_id": t["cid"], "anno": anno, "bollo_virtuale": True}, {"_id": 0, "id": 1, "numero_display": 1, "data": 1, "tipo_documento": 1, "autofattura": 1,
                                  "status": 1, "bollo_importo": 1, "bollo_addebitato": 1, "bollo_esenti": 1, "totale": 1, "cliente.denominazione": 1}).sort("data", 1).to_list(50000)
    mesi = [{"mese": m, "fatture": 0, "note_credito": 0, "autofatture": 0, "n": 0, "importo": 0.0, "addebitati": 0.0, "bozze": 0} for m in range(1, 13)]
    righe = []
    for d in docs:
        cat = "autofatture" if d.get("autofattura") else "note_credito" if d["tipo_documento"] == "TD04" else "fatture"
        imp = d.get("bollo_importo") or BOLLO_IMPORTO
        bozza = d["status"] in ("bozza", "scartata")
        m = mesi[int(d["data"][5:7]) - 1]
        if bozza:
            m["bozze"] += 1
        else:
            m[cat] += 1
            m["n"] += 1
            m["importo"] = round(m["importo"] + imp, 2)
            m["addebitati"] = round(m["addebitati"] + (imp if d.get("bollo_addebitato") else 0), 2)
        righe.append({"id": d["id"], "numero_display": d["numero_display"], "data": d["data"], "tipo": cat, "cliente": (d.get("cliente") or {}).get("denominazione", ""),
                      "importo": imp, "addebitato": bool(d.get("bollo_addebitato")), "esenti": d.get("bollo_esenti") or 0, "status": d["status"], "da_pagare": not bozza})
    vers = {v["key"]: v async for v in db.f24_versamenti.find({"company_id": t["cid"], "key": {"$regex": f"^BOL-{anno}-"}}, {"_id": 0})}
    trimestri = []
    for q in range(1, 5):
        mm = mesi[(q - 1) * 3:q * 3]
        gg, plus = BOLLI_SCADENZE[q]
        trimestri.append({"trimestre": q, "n": sum(x["n"] for x in mm), "importo": round(sum(x["importo"] for x in mm), 2),
                          "codice_tributo": f"252{q}", "scadenza": f24._lavorativo(date.fromisoformat(f"{anno + plus}-{gg}")).isoformat(),
                          "key": f"BOL-{anno}-{q}", "versato": vers.get(f"BOL-{anno}-{q}"), "concluso": _fine_mese(anno, q * 3) < date.today()})
    return {"anno": anno, "mesi": mesi, "trimestri": trimestri, "righe": righe, "totale": round(sum(x["importo"] for x in mesi), 2),
            "n": sum(x["n"] for x in mesi), "addebitati": round(sum(x["addebitati"] for x in mesi), 2)}


@api.get("/bolli/f24")
async def bolli_f24(anno: int = Query(ge=2000, le=2100), trimestre: int = Query(ge=1, le=4), t: dict = Depends(tenant)):
    rep = await bolli_report(anno, t)
    q = rep["trimestri"][trimestre - 1]
    if q["importo"] <= 0:
        raise HTTPException(400, f"Nessun bollo virtuale da versare nel {trimestre}° trimestre {anno}")
    scad = f24._lavorativo(date.fromisoformat(q["scadenza"])).isoformat()
    banche = t["company"].get("banche") or []
    banca = next((b for b in banche if b.get("predefinita")), None) or (banche[0] if banche else {})
    nota = (f"Imposta di bollo sulle fatture elettroniche del {trimestre}° trimestre {anno}: {q['n']} documenti x 2,00 €. Scadenza del versamento: {f24.itd(scad)}. "
            "Documento predisposto dal programma sulla base dei bolli virtuali delle fatture inviate (bozze e scartate escluse): verificare l'importo "
            "comunicato dall'Agenzia delle Entrate nell'area Fatture e Corrispettivi prima del pagamento. "
            "Se l'importo del 1° trimestre è inferiore a 5.000 € il versamento può essere fatto entro la scadenza del 2° trimestre; "
            "se la somma di 1° e 2° trimestre è inferiore a 5.000 € entro la scadenza del 3° trimestre.")
    deb = {"codice": q["codice_tributo"], "descrizione": f"Imposta di bollo fatture elettroniche {trimestre}° trimestre", "anno_riferimento": anno,
           "importo": q["importo"], "scadenza": scad, "nota": nota}
    pdf = f24.build_pdf(t["company"], banca, deb, [], scad)
    return RawResponse(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="F24_bolli_{anno}_T{trimestre}.pdf"'})


@api.get("/registro-iva-vendite")
async def registro_iva_vendite(anno: Optional[int] = None, dal: Optional[str] = None, al: Optional[str] = None, t: dict = Depends(tenant)):
    cid = t["cid"]
    anni = sorted(set(await db.invoices.distinct("anno", {"company_id": cid, "status": {"$in": list(IVA_STATI)}})) | {datetime.now(timezone.utc).year}, reverse=True)
    anno = anno or anni[0]
    q = {"company_id": cid, "status": {"$in": list(IVA_STATI)}, "anno": anno, "autofattura": {"$ne": True}}
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


class F24Credito(BaseModel):
    codice: str = Field(pattern=r"^[0-9A-Z]{4}$")
    anno: int = Field(ge=2000, le=2100)
    importo: float = Field(gt=0, le=10_000_000)
    descrizione: Optional[str] = Field(default="", max_length=80)


class F24In(BaseModel):
    anno: int = Field(ge=2000, le=2100)
    periodicita: Literal["mensile", "trimestrale"]
    periodo: int = Field(ge=1, le=12)
    crediti: List[F24Credito] = Field(default_factory=list, max_length=5)
    data_versamento: Optional[str] = ""
    banca_id: Optional[str] = None


async def _f24_debito(t: dict, anno: int, per: str, k: int) -> dict:
    liq = await liquidazione_iva(anno, per, t)
    p = next((x for x in liq["periodi"] if x["periodo"] == k), None)
    if not p:
        raise HTTPException(400, "Periodo non valido")
    if p["da_versare"] <= 0:
        raise HTTPException(400, f"{p['label']} {anno}: nessuna IVA da versare")
    return {**f24.tributo(anno, per, k), "importo": round(p["da_versare"], 2), "label": f"{p['label']} {anno}", "interessi": p["interessi"]}


@api.get("/liquidazione-iva/f24")
async def f24_info(anno: int, periodicita: Literal["mensile", "trimestrale"], periodo: int, t: dict = Depends(tenant)):
    banche = t["company"].get("banche") or []
    return {"debito": await _f24_debito(t, anno, periodicita, periodo), "crediti_suggeriti": f24.CREDITI_SUGGERITI,
            "banche": [{k: b.get(k) for k in ("id", "nome", "iban", "predefinita")} for b in banche]}


@api.post("/liquidazione-iva/f24")
async def f24_pdf(body: F24In, t: dict = Depends(tenant)):
    deb = await _f24_debito(t, body.anno, body.periodicita, body.periodo)
    cred = [c.model_dump() | {"importo": round(c.importo, 2)} for c in body.crediti]
    if round(sum(c["importo"] for c in cred), 2) > deb["importo"]:
        raise HTTPException(400, f"I crediti compensati superano l'IVA da versare ({_eur(deb['importo'])})")
    if body.data_versamento:
        try:
            date.fromisoformat(body.data_versamento)
        except ValueError:
            raise ferr(422, "data_versamento", "Data di versamento non valida")
    banche = t["company"].get("banche") or []
    banca = {} if body.banca_id == "none" else next((b for b in banche if b.get("id") == body.banca_id), None) or next((b for b in banche if b.get("predefinita")), None) or (banche[0] if banche else {})
    pdf = f24.build_pdf(t["company"], banca, deb, cred, body.data_versamento or "")
    name = f"F24_IVA_{deb['codice']}_{body.anno}.pdf"
    return RawResponse(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------- Scadenzario fiscale F24 ----------
AVVISO_GIORNI = 5
MESI_IT = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]


def _fine_mese(y: int, m: int) -> date:
    return date(y + (m == 12), 1 if m == 12 else m + 1, 1) - timedelta(days=1)


async def _scadenze_iva(t: dict, per: str, lo: date, hi: date, today: date) -> list:
    out = []
    for anno in (today.year - 1, today.year):
        liq = await liquidazione_iva(anno, per, t)
        for p in liq["periodi"]:
            k = p["periodo"]
            tr = f24.tributo(anno, per, k)
            if p["da_versare"] <= 0 or not lo.isoformat() <= tr["scadenza"] <= hi.isoformat():
                continue
            fine = _fine_mese(anno, k if per == "mensile" else 3 * k)
            out.append({"key": f"IVA-{anno}-{per[0]}-{k}", "tipo": "iva", "codice": tr["codice"], "descrizione": tr["descrizione"],
                        "anno_riferimento": anno, "periodo_label": f"{p['label']} {anno}", "importo": round(p["da_versare"], 2), "scadenza": tr["scadenza"],
                        "provvisorio": fine >= today, "f24": {"anno": anno, "periodicita": per, "periodo": k}})
    return out


async def _ritenute_mesi(cid: str, dal: str, al: Optional[str] = None) -> dict:
    q = {"company_id": cid, "data": {"$gte": dal, **({"$lte": al} if al else {})}, "metodo": {"$ne": "compensazione"}}
    pays = await db.passive_payments.find(q, {"_id": 0, "invoice_id": 1, "importo": 1, "data": 1}).to_list(20000)
    docs = {d["id"]: d for d in await db.passive_invoices.find(
        {"company_id": cid, "id": {"$in": list({p["invoice_id"] for p in pays})}, "ritenuta_importo": {"$gt": 0}},
        {"_id": 0, "id": 1, "ritenuta_importo": 1, "ritenuta_aliquota": 1, "netto": 1, "numero": 1, "numero_display": 1, "data": 1, "fornitore": 1, "party_id": 1}).to_list(20000)}
    allp = await db.passive_payments.find({"company_id": cid, "invoice_id": {"$in": list(docs)}, "metodo": {"$ne": "compensazione"}},
                                          {"_id": 0, "id": 1, "invoice_id": 1, "importo": 1, "data": 1, "created_at": 1}).to_list(50000)
    cum, share = {}, lambda d, s: round(d["ritenuta_importo"] * min(s / d["netto"], 1), 2) if d.get("netto") else d["ritenuta_importo"]
    pids = list({d.get("party_id") for d in docs.values() if d.get("party_id")})
    codici = {x["id"]: x.get("ritenuta_codice_tributo") or "1040" async for x in db.parties.find({"company_id": cid, "id": {"$in": pids}}, {"_id": 0, "id": 1, "ritenuta_codice_tributo": 1})}
    months = {}
    for p in sorted(allp, key=lambda x: (x["data"], x.get("created_at") or "")):
        d = docs[p["invoice_id"]]
        prev = cum.get(d["id"], 0)
        cum[d["id"]] = prev + p["importo"]
        if p["data"] < dal or (al and p["data"] > al):
            continue
        quota = round(share(d, cum[d["id"]]) - (share(d, prev) if prev else 0), 2)
        months.setdefault(p["data"][:7], []).append({"documento": d.get("numero_display") or d.get("numero"), "fornitore": (d.get("fornitore") or {}).get("denominazione"),
                                                     "partita_iva": (d.get("fornitore") or {}).get("partita_iva"), "invoice_id": d["id"], "party_id": d.get("party_id"),
                                                     "data_fattura": d.get("data"), "pagato_il": p["data"], "pagato": round(p["importo"], 2),
                                                     "aliquota": d.get("ritenuta_aliquota"), "ritenuta": quota, "codice": codici.get(d.get("party_id"), "1040")})
    return months


def _rit_righe(items: list, anno: int) -> list:
    agg = {}
    for i in items:
        agg[i["codice"]] = round(agg.get(i["codice"], 0) + i["ritenuta"], 2)
    return [{"codice": c, "descrizione": codici_tributo.descrizione(c), "anno_riferimento": anno, "importo": v} for c, v in sorted(agg.items()) if v > 0]


def _rit_scadenza(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:])
    return f24._lavorativo(date(y + (m == 12), 1 if m == 12 else m + 1, 16)).isoformat()


async def _scadenze_ritenute(cid: str, lo: date, hi: date, today: date) -> list:
    months = await _ritenute_mesi(cid, (lo - timedelta(days=45)).isoformat())
    out = []
    for ym, items in months.items():
        y, m = int(ym[:4]), int(ym[5:])
        scad = _rit_scadenza(ym)
        if not lo.isoformat() <= scad <= hi.isoformat():
            continue
        righe = _rit_righe(items, y)
        out.append({"key": f"RIT-{ym}", "tipo": "ritenute", "codice": " + ".join(r["codice"] for r in righe) or "1040", "descrizione": "Ritenute d'acconto" if len(righe) > 1 else codici_tributo.descrizione(righe[0]["codice"] if righe else "1040"),
                    "righe": righe,
                    "anno_riferimento": y, "periodo_label": f"Compensi pagati a {MESI_IT[m - 1]} {y}", "importo": round(sum(i["ritenuta"] for i in items), 2),
                    "scadenza": scad, "provvisorio": _fine_mese(y, m) >= today, "dettaglio": items})
    return out


async def _scadenze_bolli(t: dict, lo: date, hi: date, today: date) -> list:
    out = []
    for anno in (today.year - 1, today.year):
        for q in (await bolli_report(anno, t))["trimestri"]:
            if q["importo"] > 0 and lo.isoformat() <= q["scadenza"] <= hi.isoformat():
                out.append({"key": f"BOL-{anno}-{q['trimestre']}", "tipo": "bolli", "codice": q["codice_tributo"], "anno_riferimento": anno,
                            "trimestre": q["trimestre"], "descrizione": f"Imposta di bollo fatture elettroniche {q['trimestre']}° trimestre",
                            "periodo_label": f"{q['trimestre']}° trimestre {anno} · {q['n']} {'bollo' if q['n'] == 1 else 'bolli'}", "importo": q["importo"], "scadenza": q["scadenza"],
                            "provvisorio": _fine_mese(anno, q["trimestre"] * 3) >= today})
    return out


async def _scadenze(t: dict) -> list:
    today = date.today()
    lo, hi = today - timedelta(days=90), today + timedelta(days=75)
    per = t["company"].get("periodicita_iva") or "mensile"
    mods_ = company_moduli(t["company"], t["user"])
    items = await _scadenze_iva(t, per, lo, hi, today)
    if mods_["fatture_passive"]:
        items += await _scadenze_ritenute(t["cid"], lo, hi, today)
    if mods_["fatture_attive"]:
        items += await _scadenze_bolli(t, lo, hi, today)
    versati = {v["key"]: v async for v in db.f24_versamenti.find({"company_id": t["cid"]}, {"_id": 0})}
    out = []
    for x in items:
        g = (date.fromisoformat(x["scadenza"]) - today).days
        v = versati.get(x["key"])
        if v and g < 0:
            continue
        x |= {"giorni": g, "versato": v, "stato": "versato" if v else "scaduta" if g < 0 else "in_scadenza" if g <= AVVISO_GIORNI else "prossima"}
        out.append(x)
    return sorted(out, key=lambda x: (x["scadenza"], x["codice"]))


@api.get("/scadenze-fiscali")
async def scadenze_fiscali(t: dict = Depends(tenant)):
    items = await _scadenze(t)
    return {"scadenze": items, "avvisi": [x for x in items if x["stato"] in ("scaduta", "in_scadenza")], "giorni_avviso": AVVISO_GIORNI,
            "periodicita_iva": t["company"].get("periodicita_iva") or "mensile"}


class VersatoIn(BaseModel):
    key: str = Field(pattern=r"^(IVA-\d{4}-[mt]-\d{1,2}|RIT-\d{4}-\d{2}|BOL-\d{4}-[1-4])$")
    data: Optional[str] = None


@api.post("/scadenze-fiscali/versato")
async def segna_versato(body: VersatoIn, t: dict = Depends(tenant_accounting)):
    x = next((x for x in await _scadenze(t) if x["key"] == body.key), None)
    if not x and body.key.startswith("BOL-"):
        anno, q = int(body.key[4:8]), int(body.key[9])
        tr = (await bolli_report(anno, t))["trimestri"][q - 1]
        x = {"codice": tr["codice_tributo"], "importo": tr["importo"], "provvisorio": not tr["concluso"]} if tr["importo"] > 0 else None
    if not x:
        raise HTTPException(404, "Scadenza non trovata")
    if x["provvisorio"]:
        raise HTTPException(400, "Il periodo non è ancora terminato: l'importo è provvisorio")
    data = body.data or date.today().isoformat()
    try:
        date.fromisoformat(data)
    except ValueError:
        raise ferr(422, "data", "Data non valida")
    doc = {"company_id": t["cid"], "key": body.key, "codice": x["codice"], "importo": x["importo"], "data": data,
           "by": t["user"].get("name") or t["user"]["email"], "created_at": now_iso()}
    await db.f24_versamenti.update_one({"company_id": t["cid"], "key": body.key}, {"$set": doc}, upsert=True)
    if body.key.startswith("RIT-"):
        await _rit_coge(t, body.key, x["importo"], data)
    if body.key.startswith("BOL-"):
        await _bolli_coge(t, body.key, x["importo"], data)
    return {"ok": True}


async def _bolli_coge(t: dict, key: str, importo: float, data: str):
    if not company_moduli(t["company"], t["user"])["contabilita"]:
        return
    cid = t["cid"]
    await coge.ensure_seed(db, cid)
    await coge.annulla(db, cid, "bolli", key)
    p = coge.params_of(await db.companies.find_one({"id": cid}, {"_id": 0}) or {})
    anno, q = key[4:8], key[9]
    try:
        await coge._insert(db, cid, p, data, "GE", f"Versamento F24 imposta di bollo fatture elettroniche 252{q} - {q}° trimestre {anno}",
                           [{"conto": "30.14.002", "dare": importo}, {"conto": p["banca"], "avere": importo}],
                           "bolli", ref_id=key, by=t["user"].get("name") or t["user"]["email"])
    except ValueError as e:
        await db.f24_versamenti.delete_one({"company_id": cid, "key": key})
        raise HTTPException(400, f"Versamento non registrato in contabilità: {e}")


async def _rit_coge(t: dict, key: str, importo: float, data: str, conto_banca: Optional[str] = None):
    if not company_moduli(t["company"], t["user"])["contabilita"]:
        return
    cid = t["cid"]
    await coge.ensure_seed(db, cid)
    await coge.annulla(db, cid, "ritenute", key)
    p = coge.params_of(await db.companies.find_one({"id": cid}, {"_id": 0}) or {})
    y, m = int(key[4:8]), int(key[9:11])
    try:
        await coge._insert(db, cid, p, data, "GE", f"Versamento F24 ritenute d'acconto - compensi {MESI_IT[m - 1]} {y}",
                           [{"conto": p["ritenute_operate"], "dare": importo}, {"conto": conto_banca or p["banca"], "avere": importo}],
                           "ritenute", ref_id=key, by=t["user"].get("name") or t["user"]["email"])
    except ValueError as e:
        await db.f24_versamenti.delete_one({"company_id": cid, "key": key})
        raise HTTPException(400, f"Versamento non registrato in contabilità: {e}")


def _f24_info(key: str) -> dict:
    p = key.split("-")
    if p[0] == "IVA":
        anno, per, k = int(p[1]), p[2], int(p[3])
        return {"tipo": "iva", "anno": anno, "periodo_label": f"IVA {MESI_IT[k - 1]} {anno}" if per == "m" else f"IVA {k}° trimestre {anno}",
                "f24": {"anno": anno, "periodicita": "mensile" if per == "m" else "trimestrale", "periodo": k}}
    if p[0] == "RIT":
        return {"tipo": "ritenute", "anno": int(p[1]), "periodo_label": f"Ritenute d'acconto {MESI_IT[int(p[2]) - 1]} {p[1]}"}
    return {"tipo": "bolli", "anno": int(p[1]), "trimestre": int(p[2]), "periodo_label": f"Imposta di bollo {p[2]}° trimestre {p[1]}"}


@api.get("/f24-storico")
async def f24_storico(anno: Optional[int] = Query(default=None, ge=2000, le=2100), tipo: Optional[str] = None, t: dict = Depends(tenant)):
    vers = await db.f24_versamenti.find({"company_id": t["cid"]}, {"_id": 0, "company_id": 0}).to_list(5000)
    keys = [v["key"] for v in vers]
    ent = {e["ref_id"]: e async for e in db.coa_entries.find({"company_id": t["cid"], "origine": {"$in": ["ritenute", "bolli"]}, "ref_id": {"$in": keys}},
                                                           {"_id": 0, "ref_id": 1, "numero": 1, "anno": 1})}
    rows = []
    for v in vers:
        info = _f24_info(v["key"])
        if (anno and int(v["data"][:4]) != anno) or (tipo and info["tipo"] != tipo):
            continue
        e = ent.get(v["key"])
        rows.append({**v, **info, "coge_rif": f"prima nota n. {e['numero']}/{e['anno']}" if e else None})
    rows.sort(key=lambda x: (x["data"], x["key"]), reverse=True)
    tot = {k: round(sum(x["importo"] for x in rows if x["tipo"] == k), 2) for k in ("iva", "ritenute", "bolli")}
    return {"versamenti": rows, "totali": tot, "totale": round(sum(tot.values()), 2), "anni": sorted({int(v["data"][:4]) for v in vers}, reverse=True)}


@api.delete("/scadenze-fiscali/versato/{key}")
async def annulla_versato(key: str, t: dict = Depends(tenant_accounting)):
    ori = "bolli" if key.startswith("BOL-") else "ritenute"
    if key.startswith(("RIT-", "BOL-")):
        await coge.check_annullabile(db, t["cid"], ori, key)
    r = await db.f24_versamenti.delete_one({"company_id": t["cid"], "key": key})
    if not r.deleted_count:
        raise HTTPException(404, "Versamento non trovato")
    await coge.annulla(db, t["cid"], ori, key)
    return {"ok": True}


@api.get("/scadenze-fiscali/{key}/f24")
async def scadenza_f24(key: str, t: dict = Depends(tenant)):
    if not re.fullmatch(r"RIT-\d{4}-(0[1-9]|1[0-2])", key):
        raise HTTPException(404, "Scadenza ritenute non trovata")
    sd = date.fromisoformat(_rit_scadenza(key[4:]))
    x = next((x for x in await _scadenze_ritenute(t["cid"], sd, sd, date.today()) if x["key"] == key), None)
    if not x:
        raise HTTPException(404, "Scadenza ritenute non trovata")
    banche = t["company"].get("banche") or []
    banca = next((b for b in banche if b.get("predefinita")), None) or (banche[0] if banche else {})
    deb = {k: x[k] for k in ("codice", "descrizione", "anno_riferimento", "importo", "scadenza", "righe")}
    pdf = f24.build_pdf(t["company"], banca, deb, [], x["scadenza"])
    return RawResponse(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="F24_ritenute_{key}.pdf"'})


# ---------- Ritenute d'acconto su fatture passive ----------
YM_RX = r"^\d{4}-(0[1-9]|1[0-2])$"


async def _rit_mese(t: dict, ym: str) -> dict:
    y, m = int(ym[:4]), int(ym[5:])
    items = (await _ritenute_mesi(t["cid"], f"{ym}-01", _fine_mese(y, m).isoformat())).get(ym, [])
    per = {}
    for i in items:
        f = per.setdefault(i["party_id"] or i["fornitore"], {"fornitore": i["fornitore"], "partita_iva": i["partita_iva"], "pagato": 0, "ritenuta": 0, "righe": []})
        f["pagato"] = round(f["pagato"] + i["pagato"], 2)
        f["ritenuta"] = round(f["ritenuta"] + i["ritenuta"], 2)
        f["righe"].append(i)
    key = f"RIT-{ym}"
    righe = _rit_righe(items, y)
    v = await db.f24_versamenti.find_one({"company_id": t["cid"], "key": key}, {"_id": 0})
    return {"key": key, "mese": ym, "label": f"{MESI_IT[m - 1]} {y}", "codice": " + ".join(r["codice"] for r in righe) or "1040", "righe": righe, "scadenza": _rit_scadenza(ym),
            "provvisorio": _fine_mese(y, m) >= date.today(), "totale": round(sum(i["ritenuta"] for i in items), 2),
            "pagato": round(sum(i["pagato"] for i in items), 2), "fornitori": sorted(per.values(), key=lambda f: (f["fornitore"] or "").lower()), "versato": v}


@api.get("/ritenute/mese")
async def ritenute_mese(mese: str = Query(pattern=YM_RX), t: dict = Depends(tenant)):
    return await _rit_mese(t, mese)


@api.get("/ritenute/da-versare")
async def ritenute_da_versare(t: dict = Depends(tenant)):
    today = date.today()
    months = await _ritenute_mesi(t["cid"], date(today.year - 2, today.month, 1).isoformat())
    versati = {v["key"] async for v in db.f24_versamenti.find({"company_id": t["cid"], "key": {"$regex": "^RIT-"}}, {"_id": 0, "key": 1})}
    out = []
    for ym, items in sorted(months.items()):
        tot = round(sum(i["ritenuta"] for i in items), 2)
        if tot <= 0 or f"RIT-{ym}" in versati:
            continue
        y, m = int(ym[:4]), int(ym[5:])
        scad = _rit_scadenza(ym)
        out.append({"key": f"RIT-{ym}", "mese": ym, "label": f"{MESI_IT[m - 1]} {y}", "importo": tot, "scadenza": scad, "fornitori": len({i["fornitore"] for i in items}),
                    "giorni": (date.fromisoformat(scad) - today).days, "provvisorio": _fine_mese(y, m) >= today})
    return {"mesi": out, "totale": round(sum(x["importo"] for x in out), 2)}


class RitVersatoIn(BaseModel):
    data: str
    conto_banca: Optional[str] = Field(default=None, max_length=12)


@api.post("/ritenute/{mese}/versato")
async def ritenute_versato(mese: str, body: RitVersatoIn, t: dict = Depends(tenant_accounting)):
    if not re.fullmatch(YM_RX, mese):
        raise HTTPException(404, "Mese non valido")
    x = await _rit_mese(t, mese)
    if x["provvisorio"]:
        raise HTTPException(400, "Il mese non è ancora terminato: l'importo è provvisorio")
    if x["totale"] <= 0:
        raise HTTPException(400, "Nessuna ritenuta da versare per il mese")
    try:
        dv = date.fromisoformat(body.data)
    except ValueError:
        raise ferr(422, "data", "Data non valida")
    if dv > date.today():
        raise ferr(422, "data", "La data del versamento non può essere nel futuro")
    if body.conto_banca and not await db.coa_accounts.find_one({"company_id": t["cid"], "codice": body.conto_banca}, {"_id": 1}):
        raise ferr(422, "conto_banca", "Conto banca inesistente")
    await db.f24_versamenti.update_one({"company_id": t["cid"], "key": x["key"]}, {"$set": {
        "company_id": t["cid"], "key": x["key"], "codice": x["codice"], "importo": x["totale"], "data": body.data,
        "by": t["user"].get("name") or t["user"]["email"], "created_at": now_iso()}}, upsert=True)
    await _rit_coge(t, x["key"], x["totale"], body.data, body.conto_banca)
    return await _rit_mese(t, mese)


@api.get("/ritenute/{mese}/f24")
async def ritenute_f24(mese: str, t: dict = Depends(tenant)):
    if not re.fullmatch(YM_RX, mese):
        raise HTTPException(404, "Mese non valido")
    x = await _rit_mese(t, mese)
    if x["totale"] <= 0:
        raise HTTPException(400, "Nessuna ritenuta per il mese")
    banche = t["company"].get("banche") or []
    banca = next((b for b in banche if b.get("predefinita")), None) or (banche[0] if banche else {})
    deb = {"codice": x["codice"], "descrizione": "Ritenute d'acconto", "anno_riferimento": int(mese[:4]), "importo": x["totale"], "scadenza": x["scadenza"], "righe": x["righe"]}
    pdf = f24.build_pdf(t["company"], banca, deb, [], x["scadenza"])
    return RawResponse(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="F24_ritenute_{mese}.pdf"'})


class RitenutaPassIn(BaseModel):
    aliquota: float = Field(ge=0, le=100)
    imponibile: float = Field(ge=0, le=10_000_000)


def _ritenuta_upd(doc: dict, aliquota: float, imponibile: float) -> dict:
    rit = round(imponibile * aliquota / 100, 2)
    if rit >= doc["totale"]:
        raise ferr(422, "imponibile", "La ritenuta non può superare il totale della fattura")
    netto = round(doc["totale"] - rit - (doc.get("iva", 0) if doc.get("split_payment") else 0), 2)
    rate = [dict(r) for r in doc.get("rate") or []]
    if rate:
        old = sum(r["importo"] for r in rate) or 1
        rate = [{**r, "importo": round(r["importo"] * netto / old, 2)} for r in rate]
        rate[-1]["importo"] = round(netto - sum(r["importo"] for r in rate[:-1]), 2)
    return {"ritenuta_importo": rit, "ritenuta_aliquota": aliquota, "ritenuta_imponibile": round(imponibile, 2), "netto": netto, "rate": rate}


@api.put("/passive/{pid}/ritenuta")
async def set_ritenuta_passiva(pid: str, body: RitenutaPassIn, t: dict = Depends(tenant_accounting)):
    doc = await _get_passive(pid, t["cid"])
    if await db.passive_payments.find_one({"company_id": t["cid"], "invoice_id": pid}, {"_id": 1}):
        raise HTTPException(400, "La fattura ha già dei pagamenti: eliminali prima di cambiare la ritenuta")
    await coge.check_annullabile(db, t["cid"], "acquisto", pid)
    upd = _ritenuta_upd(doc, body.aliquota, body.imponibile) | {"ritenuta_auto": False}
    await db.passive_invoices.update_one({"id": pid}, {"$set": upd})
    await coge.annulla(db, t["cid"], "acquisto", pid)
    await coge.safe(coge.registra_acquisto(db, {**doc, **upd}))
    return {**upd, "ok": True}


MIN_VERSAMENTO = 25.82
CORR_ALIQ = ((22.0, 1.0), (10.0, 0.6), (4.0, 0.3))


def _corr_demo(t: dict, day: date) -> dict:
    rng = random.Random(f"{t['cid']}-{day.isoformat()}")
    righe = []
    for aliq, p in CORR_ALIQ:
        if rng.random() < p:
            lordo = round(rng.uniform(80, 1500) * (1.4 if day.weekday() == 5 else 1), 2)
            imp = round(lordo / (1 + aliq / 100), 2)
            righe.append({"aliquota": aliq, "natura": None, "imponibile": imp, "imposta": round(lordo - imp, 2)})
    piva = t["company"].get("partita_iva") or "000000"
    return {"id": str(uuid.uuid4()), "company_id": t["cid"], "data": day.isoformat(), "anno": day.year, "matricola": f"99MEX{piva[-6:]}",
            "n_documenti": rng.randint(8, 90), "tipo_documento": "COR", "riepilogo": righe, "totale": round(sum(r["imponibile"] + r["imposta"] for r in righe), 2),
            "origine": "cassetto_simulato", "created_at": now_iso()}


@api.post("/corrispettivi/sync")
async def corrispettivi_sync(t: dict = Depends(tenant_accounting)):
    today = datetime.now(timezone.utc).date()
    last = await db.corrispettivi.find_one({"company_id": t["cid"]}, {"_id": 0, "data": 1}, sort=[("data", -1)])
    start = max(date.fromisoformat(last["data"]) + timedelta(days=1), today - timedelta(days=62)) if last else today - timedelta(days=30)
    docs = [_corr_demo(t, start + timedelta(days=i)) for i in range((today - start).days) if (start + timedelta(days=i)).weekday() != 6]
    docs = [d for d in docs if d["riepilogo"]]
    n_ins = 0
    if docs:
        try:
            n_ins = len((await db.corrispettivi.insert_many([dict(d) for d in docs], ordered=False)).inserted_ids)
        except BulkWriteError as e:
            n_ins = e.details.get("nInserted", 0)
    return {"ricevuti": n_ins, "dal": start.isoformat(), "al": (today - timedelta(days=1)).isoformat()}


@api.get("/corrispettivi")
async def list_corrispettivi(anno: Optional[int] = None, dal: Optional[str] = None, al: Optional[str] = None, t: dict = Depends(tenant)):
    cid = t["cid"]
    anni = sorted(set(await db.corrispettivi.distinct("anno", {"company_id": cid})) | {datetime.now(timezone.utc).year}, reverse=True)
    anno = anno or anni[0]
    q = {"company_id": cid, "anno": anno}
    rng = {k: v for k, v in (("$gte", dal), ("$lte", al)) if v and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v)}
    if rng:
        q["data"] = rng
    docs = await db.corrispettivi.find(q, {"_id": 0}).sort("data", 1).to_list(5000)
    rows, out = _iva_register(docs, lambda d: {k: d[k] for k in ("id", "data", "matricola", "n_documenti", "origine")})
    return {"anno": anno, "anni": anni, "rows": rows, **out, "azienda": {k: t["company"].get(k) for k in ("denominazione", "partita_iva")}}


@api.get("/corrispettivi/riepilogo")
async def corrispettivi_riepilogo(t: dict = Depends(tenant)):
    today = datetime.now(timezone.utc).date()
    since = (today - timedelta(days=30)).isoformat()
    docs = await db.corrispettivi.find({"company_id": t["cid"], "data": {"$gte": min(since, f"{today.year}-01-01")}}, {"_id": 0, "data": 1, "totale": 1, "n_documenti": 1}).sort("data", 1).to_list(5000)
    mese = today.isoformat()[:7]
    anno_docs = [d for d in docs if d["data"].startswith(str(today.year))]
    return {"anno": today.year, "ultimo": docs[-1] if docs else None,
            "mese": round(sum(d["totale"] for d in docs if d["data"].startswith(mese)), 2), "totale_anno": round(sum(d["totale"] for d in anno_docs), 2),
            "giorni": [d for d in docs if d["data"] >= since],
            "mesi": [{"mese": m, "totale": round(sum(d["totale"] for d in anno_docs if int(d["data"][5:7]) == m), 2)} for m in range(1, 13)]}


@api.delete("/corrispettivi/{cid_}")
async def delete_corrispettivo(cid_: str, t: dict = Depends(tenant_accounting)):
    r = await db.corrispettivi.delete_one({"id": cid_, "company_id": t["cid"]})
    if not r.deleted_count:
        raise HTTPException(404, "Corrispettivo non trovato")
    return {"ok": True}


async def _liq_calc(cid: str, anno: int, periodicita: str, credito: float) -> dict:
    sales = await db.invoices.find({"company_id": cid, "status": {"$in": list(IVA_STATI)}, "anno": anno, "autofattura": {"$ne": True}}, SALES_PROJ).to_list(50000)
    purch = await db.passive_invoices.find({"company_id": cid, "stato_reg": "registrata", "anno_registrazione": anno},
                                           {"_id": 0, "data_registrazione": 1, "tipo_documento": 1, "riepilogo": 1, "totale": 1, "split_payment": 1, "reverse_charge": 1, "detraibilita_iva": 1}).to_list(50000)
    corr = await db.corrispettivi.find({"company_id": cid, "anno": anno}, {"_id": 0, "data": 1, "tipo_documento": 1, "riepilogo": 1, "totale": 1}).to_list(50000)
    n = 12 if periodicita == "mensile" else 4
    per = (lambda m: m) if n == 12 else (lambda m: (m - 1) // 3 + 1)
    buckets = {k: {"vendite": [], "acquisti": [], "corr": []} for k in range(1, n + 1)}
    for d in corr:
        buckets[per(int(d["data"][5:7]))]["corr"].append(d)
    for d in sales:
        buckets[per(int(d["data"][5:7]))]["vendite"].append(d)
    for d in purch:
        buckets[per(int(d["data_registrazione"][5:7]))]["acquisti"].append(d)
    mesi = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
    periodi, debito_prec = [], 0.0
    for k in range(1, n + 1):
        _, v = _iva_register(buckets[k]["vendite"], lambda d: {"split_payment": d.get("split_payment", False)})
        _, a = _iva_register(buckets[k]["acquisti"], lambda d: {})
        a["imposta"] = round(a["imposta"] - a["imposta_indetraibile"], 2)
        _, c = _iva_register(buckets[k]["corr"], lambda d: {})
        debito = round(v["imposta"] - v["imposta_split"] + a["imposta_rc"] + c["imposta"], 2)
        saldo = round(debito - a["imposta"] - credito, 2)
        interessi = round(saldo * 0.01, 2) if n == 4 and k < 4 and saldo > 0 else 0.0
        dovuto = round(saldo + interessi + debito_prec, 2) if saldo > 0 else round(debito_prec + min(saldo, 0), 2)
        sotto_soglia = 0 < dovuto <= MIN_VERSAMENTO and k < n
        periodi.append({"periodo": k, "label": mesi[k - 1] if n == 12 else f"{k}° trimestre", "vendite": v, "acquisti": a,
                        "iva_debito": debito, "iva_split": v["imposta_split"], "iva_rc": a["imposta_rc"], "iva_corrispettivi": c["imposta"], "corrispettivi": c, "documenti_corrispettivi": len(buckets[k]["corr"]), "iva_credito": a["imposta"], "iva_indetraibile": a["imposta_indetraibile"], "credito_precedente": credito,
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
    await coge.check_annullabile(db, t["cid"], "acquisto", pid)
    if await db.passive_payments.find_one({"company_id": t["cid"], "$or": [{"invoice_id": pid}, {"nc_id": pid}]}, {"_id": 1}):
        raise HTTPException(400, "Elimina prima i pagamenti registrati su questo documento")
    await db.passive_invoices.delete_one({"id": pid, "company_id": t["cid"]})
    await coge.annulla(db, t["cid"], "acquisto", pid)
    return {"ok": True}


async def _ledger_passive(cid: str, party_id: Optional[str] = None, escludi_reg: Optional[str] = None):
    q = {"company_id": cid, "stato_reg": {"$ne": "contestata"}, **({"party_id": party_id} if party_id else {})}
    rows = await db.passive_invoices.find(q, {"_id": 0, "id": 1, "numero_display": 1, "data": 1, "party_id": 1, "fornitore.denominazione": 1, "totale": 1,
                                               "netto": 1, "rate": 1, "rate_mod": 1, "scadenza": 1, "tipo_documento": 1, "fattura_collegata_id": 1}).to_list(20000)
    invs = [{**r, "numero": 0, "cliente": {"denominazione": r["fornitore"]["denominazione"]}} for r in rows]
    invs += [{**r, "cliente": {"denominazione": r["fornitore"]["denominazione"]}} for r in await db.partite_aperte.find(
        {"company_id": cid, "tipo": "fornitore", **({"party_id": party_id} if party_id else {})}, {**LEDGER_PROJ, "fornitore.denominazione": 1}).to_list(20000)]
    pays = await db.passive_payments.find({"company_id": cid, **({"party_id": party_id} if party_id else {}), **({"coge_entry_id": {"$ne": escludi_reg}} if escludi_reg else {})},
                                          {"_id": 0}).to_list(50000)
    today = datetime.now(timezone.utc).date().isoformat()
    docs, crediti = build_ledger(invs, pays, today)
    return docs, crediti, pays, today


@api.get("/scadenzario-passivo")
async def scadenzario_passivo(party_id: Optional[str] = None, t: dict = Depends(tenant)):
    docs, crediti, _, today = await _ledger_passive(t["cid"], party_id)
    return _scad_response(docs, crediti, today)


@api.get("/passive/{pid}/pagamenti")
async def passive_payments(pid: str, t: dict = Depends(tenant)):
    d = await db.partite_aperte.find_one({"id": pid, "company_id": t["cid"], "tipo": "fornitore"}, {"_id": 0}) or await _get_passive(pid, t["cid"])
    docs, crediti, pays, _ = await _ledger_passive(t["cid"], d["party_id"])
    return {"scadenzario": next((x for x in docs if x["id"] == pid), None),
            "pagamenti": sorted([p for p in pays if p["invoice_id"] == pid], key=lambda p: p["data"]), "crediti": crediti}


@api.post("/passive/{pid}/pagamenti")
async def add_passive_payment(pid: str, body: PagamentoIn, t: dict = Depends(tenant_accounting)):
    cid = t["cid"]
    d = await db.partite_aperte.find_one({"id": pid, "company_id": cid, "tipo": "fornitore"}, {"_id": 0}) or await _get_passive(pid, cid)
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
    await _check_payment_coge(db.passive_payments, t["cid"], pid)
    await _check_payment_tx(t["cid"], pid)
    r = await db.passive_payments.delete_one({"id": pid, "company_id": t["cid"]})
    if not r.deleted_count:
        raise HTTPException(404, "Pagamento non trovato")
    await _unlink_payment(t["cid"], pid)
    return {"ok": True}


# ---------- Saldaconto (partite aperte/chiuse dalla prima nota) ----------
async def _check_payment_coge(coll, cid: str, pid: str):
    p = await coll.find_one({"id": pid, "company_id": cid}, {"_id": 0, "coge_entry_id": 1, "coge_rif": 1})
    if p and p.get("coge_entry_id"):
        raise HTTPException(400, f"Movimento registrato in contabilità ({p.get('coge_rif') or 'prima nota'}): modificalo o eliminalo dalla prima nota")


def _partita(d: dict, pays: list) -> dict:
    aperte = [r for r in d["rate"] if r["residuo"] > 0.005]
    return {"invoice_id": d["id"], "numero_display": d["numero_display"], "data": d["data"], "party_id": d["party_id"], "nome": d["cliente"],
            "scadenza": (aperte or d["rate"] or [{"scadenza": d["data"]}])[0]["scadenza"], "netto": d["netto"], "residuo": d["residuo"],
            "pagato": round(d["netto"] - d["residuo"], 2), "stato": "chiusa" if d["residuo"] <= 0.005 else ("parziale" if d["netto"] - d["residuo"] > 0.005 else "aperta"),
            "pagamenti": sorted([{k: p.get(k) for k in ("id", "data", "importo", "metodo", "note", "coge_entry_id", "coge_rif")} for p in pays if p["invoice_id"] == d["id"]],
                                key=lambda p: p["data"])}


async def _partite(cid: str, party_id: str, passivo: bool, escludi_reg: Optional[str] = None) -> list:
    docs, _, pays, _ = await (_ledger_passive if passivo else _ledger)(cid, party_id, escludi_reg)
    out = [_partita(d, pays) for d in docs]
    return sorted(out, key=lambda x: (x["scadenza"], x["data"], x["numero_display"]))


def _sc_importi(righe: list, p: dict) -> dict:
    out = {}
    for r in righe:
        if r.get("party_id") and r["conto"] in (p["clienti"], p["fornitori"]):
            pas = r["conto"] == p["fornitori"]
            k = (pas, r["party_id"])
            out[k] = round(out.get(k, 0) + ((r["dare"] - r["avere"]) if pas else (r["avere"] - r["dare"])), 2)
    return out


async def _sc_doc(cid: str, it):
    coll = db.passive_invoices if it.passivo else db.invoices
    proj = {"_id": 0, "party_id": 1, "numero_display": 1}
    return await coll.find_one({"id": it.invoice_id, "company_id": cid}, proj) or await db.partite_aperte.find_one(
        {"id": it.invoice_id, "company_id": cid, "tipo": "fornitore" if it.passivo else "cliente"}, proj)


async def _sc_check(cid: str, data: str, righe: list, items: list, p: dict):
    importi = _sc_importi(righe, p)
    cache, used = {}, {}
    for it in items:
        inv = await _sc_doc(cid, it)
        if not inv:
            raise HTTPException(400, "Partita non trovata")
        k = (it.passivo, inv["party_id"])
        if importi.get(k, 0) <= 0:
            raise HTTPException(400, f"La fattura {inv['numero_display']} non è del {'fornitore' if it.passivo else 'cliente'} indicato in una riga di {'pagamento (Dare fornitori)' if it.passivo else 'incasso (Avere clienti)'}")
        if k not in cache:
            cache[k] = {x["invoice_id"]: x for x in await _partite(cid, inv["party_id"], it.passivo)}
        x = cache[k].get(it.invoice_id)
        if not x:
            raise HTTPException(400, f"La fattura {inv['numero_display']} non è una partita saldabile")
        if data < x["data"]:
            raise HTTPException(400, f"La data della registrazione non può precedere la fattura {x['numero_display']}")
        if it.importo > x["residuo"] + 0.005:
            raise HTTPException(400, f"Fattura {x['numero_display']}: importo superiore al residuo ({_eur(x['residuo'])})")
        x["residuo"] = round(x["residuo"] - it.importo, 2)
        used[k] = round(used.get(k, 0) + it.importo, 2)
        if used[k] > importi[k] + 0.005:
            raise HTTPException(400, f"Il totale abbinato ({_eur(used[k])}) supera l'importo della riga del {'fornitore' if it.passivo else 'cliente'} ({_eur(importi[k])})")


async def _sc_apply(cid: str, entry: dict, items: list, user: dict):
    rif = f"prima nota n. {entry['numero']}/{entry['anno']}"
    p = coge.params_of(await db.companies.find_one({"id": cid}, {"_id": 0}) or {})
    metodo = "contanti" if any(r["conto"] == p.get("cassa") for r in entry["righe"]) else "bonifico"
    for it in items:
        pcoll = db.passive_payments if it.passivo else db.payments
        inv = await _sc_doc(cid, it)
        dist = {"distinta_pag_id": entry["ref_id"]} if entry.get("origine") == "pagamenti" and it.passivo else {}
        await pcoll.insert_one({"id": str(uuid.uuid4()), "data": entry["data"], "importo": round(it.importo, 2), "metodo": metodo, "note": f"Contabilità: {rif}",
                                "nc_id": None, "company_id": cid, "invoice_id": it.invoice_id, "party_id": inv["party_id"], "numero_display": inv["numero_display"],
                                "nc_numero": None, "coge_entry_id": entry["id"], "coge_rif": rif, "created_by": user["user_id"],
                                "created_by_name": user.get("name") or user["email"], "created_at": now_iso(), **dist})
    if entry.get("origine") == "pagamenti":
        await pagforn.ricalcola(db, cid, entry["ref_id"], entry["data"])


async def _sc_remove(cid: str, rid: str):
    q = {"company_id": cid, "coge_entry_id": rid}
    old = (await db.payments.find(q, {"_id": 0}).to_list(1000), await db.passive_payments.find(q, {"_id": 0}).to_list(1000))
    await db.payments.delete_many(q)
    await db.passive_payments.delete_many(q)
    for x in old[0] + old[1]:
        await _unlink_payment(cid, x["id"])
    return old


async def _sc_restore(old):
    if old[0]:
        await db.payments.insert_many(old[0])
    if old[1]:
        await db.passive_payments.insert_many(old[1])


SALDACONTO = SimpleNamespace(check=_sc_check, apply=_sc_apply, remove=_sc_remove, restore=_sc_restore)


@api.get("/contabilita/saldaconto/partite")
async def saldaconto_partite(party_id: str, tipo: Literal["cliente", "fornitore"], escludi_reg: Optional[str] = None, t: dict = Depends(tenant)):
    if not await db.parties.find_one({"id": party_id, "company_id": t["cid"]}, {"_id": 1}):
        raise HTTPException(404, "Anagrafica non trovata")
    rows = await _partite(t["cid"], party_id, tipo == "fornitore", escludi_reg)
    return {"aperte": [r for r in rows if r["stato"] != "chiusa"], "chiuse": [r for r in rows if r["stato"] == "chiusa"]}


class SaldoAutoIn(BaseModel):
    party_id: str
    tipo: Literal["cliente", "fornitore"]
    importo: float = Field(gt=0, le=10_000_000)
    escludi_reg: Optional[str] = None


@api.post("/contabilita/saldaconto/auto")
async def saldaconto_auto(body: SaldoAutoIn, t: dict = Depends(tenant)):
    rows = [r for r in await _partite(t["cid"], body.party_id, body.tipo == "fornitore", body.escludi_reg) if r["stato"] != "chiusa"]
    resto, out = round(body.importo, 2), []
    for r in rows:
        if resto <= 0.005:
            break
        v = round(min(resto, r["residuo"]), 2)
        out.append({"invoice_id": r["invoice_id"], "numero_display": r["numero_display"], "importo": v, "passivo": body.tipo == "fornitore"})
        resto = round(resto - v, 2)
    return {"righe": out, "non_abbinato": max(resto, 0)}


@api.get("/contabilita/saldaconto/registrazione/{rid}")
async def saldaconto_reg(rid: str, t: dict = Depends(tenant)):
    q = {"company_id": t["cid"], "coge_entry_id": rid}
    out = {}
    for coll, pas in ((db.payments, False), (db.passive_payments, True)):
        for x in await coll.find(q, {"_id": 0, "invoice_id": 1, "importo": 1, "numero_display": 1}).to_list(1000):
            k = (pas, x["invoice_id"])
            out[k] = {**x, "passivo": pas, "importo": round(out.get(k, {}).get("importo", 0) + x["importo"], 2)}
    return list(out.values())


@api.get("/sistema/avvisi")
async def sistema_avvisi(refresh: bool = False, _: dict = Depends(admin_user)):
    cert = await sistema.cert_status(APP_URL, refresh)
    bk = sistema.backup_status()
    av = sistema.avvisi(cert, bk)
    for c in await db.companies.find({"ftp_backup.attivo": True}, {"_id": 0, "id": 1, "denominazione": 1, "ftp_backup.ultimo": 1, "ftp_backup.updated_at": 1}).to_list(500):
        u = c["ftp_backup"].get("ultimo") or {}
        ref = u.get("data") or c["ftp_backup"].get("updated_at") or now_iso()
        vecchio = (datetime.now(timezone.utc) - datetime.fromisoformat(ref)).total_seconds() > 48 * 3600
        if u and not u.get("ok"):
            av.append({"id": f"ftp-{c['id']}", "livello": "rosso", "titolo": f"Backup FTP di {c['denominazione']} non riuscito", "testo": u.get("errore") or ""})
        elif vecchio:
            av.append({"id": f"ftp-{c['id']}", "livello": "giallo", "titolo": f"Backup FTP di {c['denominazione']} non aggiornato", "testo": "Nessun invio riuscito negli ultimi 2 giorni."})
    return {"avvisi": av, "certificato": cert, "backup": bk}


# ---------- Estratto conto e solleciti ----------
async def _party_ledger(t: dict, pid: str):
    party = await db.parties.find_one({"id": pid, "company_id": t["cid"], "tipo": {"$ne": "fornitore"}}, {"_id": 0})
    if not party:
        raise HTTPException(404, "Cliente non trovato")
    docs, crediti, pays, today = await _ledger(t["cid"], pid)
    invs = await db.invoices.find({"company_id": t["cid"], "party_id": pid, "status": {"$in": list(IVA_STATI)}}, LEDGER_PROJ).to_list(20000)
    return party, docs, crediti, pays, invs, today


EXPORT_STATI = ["inviata", "consegnata", "mancata_consegna"]
EXPORT_MAX_MB = 20
_DATE = r"^\d{4}-\d{2}-\d{2}$"


class ExportSendIn(BaseModel):
    dal: str = Field(pattern=_DATE)
    al: str = Field(pattern=_DATE)
    to: EmailStr
    note: Optional[str] = Field(default="", max_length=2000)


def _period(dal: str, al: str):
    try:
        date.fromisoformat(dal)
        date.fromisoformat(al)
    except (TypeError, ValueError):
        raise HTTPException(400, "Indica un periodo valido")
    if dal > al:
        raise HTTPException(400, "La data di inizio deve precedere quella di fine")


async def _export_docs(t: dict, dal: str, al: str, full: bool):
    _period(dal, al)
    m, rng = company_moduli(t["company"], t["user"]), {"company_id": t["cid"], "data": {"$gte": dal, "$lte": al}}
    att = pas = None
    if m["fatture_attive"]:
        att = await db.invoices.find({**rng, "status": {"$in": EXPORT_STATI}}, {"_id": 0, "history": 0}).sort([("data", 1), ("numero", 1)]).to_list(10000)
    if m["fatture_passive"]:
        pas = await db.passive_invoices.find(rng, {"_id": 0} if full else PASSIVE_LIST).sort("data", 1).to_list(10000)
    return att, pas


async def _export_zip(t: dict, dal: str, al: str):
    company = _company_required(t)
    att, pas = await _export_docs(t, dal, al, True)
    if not (att or pas):
        raise HTTPException(400, "Nessuna fattura da esportare nel periodo scelto")
    for x in pas or []:
        x["_xml"] = base64.b64decode(x["xml_b64"])
    root = export_comm.safe(f"Fatture_{company['denominazione']}_{dal}_{al}")
    data = await asyncio.to_thread(export_comm.build_zip, company, att, pas, lambda x: (build_xml(company, x), file_name(company, x)), root)
    return data, f"{root}.zip", len(att or []), len(pas or [])


@api.get("/export/commercialista")
async def export_info(dal: str, al: str, t: dict = Depends(tenant_accounting)):
    att, pas = await _export_docs(t, dal, al, False)
    tot = lambda xs: round(sum((-1 if x["tipo_documento"] == "TD04" else 1) * x["totale"] for x in xs or []), 2)  # noqa: E731
    log = await db.export_log.find({"company_id": t["cid"]}, {"_id": 0}).sort("at", -1).to_list(10)
    return {"attive": None if att is None else len(att), "passive": None if pas is None else len(pas),
            "totale_attive": tot(att), "totale_passive": tot(pas), "email": t["company"].get("commercialista_email") or "", "log": log}


@api.get("/export/commercialista.zip")
async def export_zip(dal: str, al: str, t: dict = Depends(tenant_accounting)):
    data, name, _, _ = await _export_zip(t, dal, al)
    return RawResponse(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"', "X-Filename": name,
                                                                    "Access-Control-Expose-Headers": "X-Filename"})


@api.post("/export/commercialista/send")
async def export_send(body: ExportSendIn, t: dict = Depends(tenant_accounting)):
    smtp = await _company_smtp(t["cid"])
    data, name, na, np_ = await _export_zip(t, body.dal, body.al)
    mb = len(data) / 1024 / 1024
    if mb > EXPORT_MAX_MB:
        raise HTTPException(400, f"Il file pesa {mb:.1f} MB, troppo per un allegato email (max {EXPORT_MAX_MB} MB): scegli un periodo più breve o scarica lo ZIP")
    c, e = t["company"], _html.escape
    righe = "".join(f"<li>{e(lbl)}: <b>{n}</b></li>" for lbl, n in (("Fatture emesse (inviate allo SDI)", na), ("Fatture ricevute", np_)) if n)
    note = f"<p>{e(body.note).replace(chr(10), '<br>')}</p>" if body.note else ""
    html = (f"<p>Buongiorno,</p><p>in allegato le fatture elettroniche di <b>{e(c['denominazione'])}</b> dal {_it_date(body.dal)} al {_it_date(body.al)}:</p>"
            f"<ul>{righe}</ul>{note}<p>Il file ZIP contiene gli XML, le copie PDF di cortesia e il riepilogo Excel.</p><p>Cordiali saluti<br>{e(t['user'].get('name') or '')}<br>{e(c['denominazione'])}</p>")
    await send_email(smtp=smtp, to=body.to, subject=f"Fatture {c['denominazione']} dal {_it_date(body.dal)} al {_it_date(body.al)}", html=html,
                     reply_to=t["user"].get("email"), attachments=[{"filename": name, "content": base64.b64encode(data).decode(), "mime": "application/zip"}])
    entry = {"id": str(uuid.uuid4()), "company_id": t["cid"], "at": now_iso(), "dal": body.dal, "al": body.al, "to": body.to, "attive": na, "passive": np_,
             "size_kb": round(len(data) / 1024), "by": t["user"].get("name") or t["user"]["email"]}
    await db.export_log.insert_one(dict(entry))
    await db.companies.update_one({"id": t["cid"]}, {"$set": {"commercialista_email": body.to}})
    return entry


# ---------- Banca e riconciliazione ----------
BANK_SYNC_HOURS = 6
TX_PROJ = {"_id": 0}


class BancaCfgIn(BaseModel):
    ambiente: Literal["sandbox", "production"] = "sandbox"
    email: Optional[str] = Field(default="", max_length=255)
    password: Optional[str] = Field(default=None, max_length=255)
    auto: bool = True


class ContoIn(BaseModel):
    nome: str = Field(min_length=1, max_length=80)
    iban: Optional[str] = Field(default="", max_length=34)
    banca: Optional[str] = Field(default="", max_length=80)


class RiconciliaIn(BaseModel):
    tipo: Literal["incasso", "pagamento", "corrispettivi", "iva", "altro"]
    ref_ids: List[str] = Field(default_factory=list, max_length=20)
    categoria: Optional[str] = None
    note: Optional[str] = Field(default="", max_length=300)
    salva_regola: Optional[str] = Field(default=None, max_length=120)


class RegolaIn(BaseModel):
    nome: str = Field(min_length=1, max_length=80)
    contiene: str = Field(min_length=2, max_length=200)
    segno: Literal["entrata", "uscita", "entrambi"] = "uscita"
    importo_min: Optional[float] = Field(default=None, ge=0)
    importo_max: Optional[float] = Field(default=None, ge=0)
    categoria: str
    note: Optional[str] = Field(default="", max_length=200)
    attiva: bool = True

    @field_validator("categoria")
    @classmethod
    def _cat(cls, v):
        if v not in bk.CATEGORIE:
            raise ValueError("Scegli una categoria valida")
        return v

    @model_validator(mode="after")
    def _imp(self):
        if self.importo_min is not None and self.importo_max is not None and self.importo_min > self.importo_max:
            raise ValueError("L'importo minimo supera il massimo")
        return self


def _banca_public(comp: dict) -> dict:
    b, s = comp.get("banca") or {}, comp.get("sdi") or {}
    own = bool(b.get("email") and (b.get("has_password") or b.get("password_enc")))
    return {"ambiente": b.get("ambiente") or s.get("ambiente") or "sandbox", "email": b.get("email") or "", "has_password": bool(b.get("has_password") or b.get("password_enc")),
            "usa_sdi": not own and s.get("provider") == "acube", "configurato": own or s.get("provider") == "acube", "auto": b.get("auto", True),
            "last_sync_at": b.get("last_sync_at"), "last_sync_error": b.get("last_sync_error"), "next_sync_at": b.get("next_sync_at")}


async def _banca_cfg(cid: str) -> dict:
    c = await db.companies.find_one({"id": cid}, {"_id": 0, "banca": 1, "sdi": 1})
    b = (c or {}).get("banca") or {}
    try:
        if b.get("email") and b.get("password_enc"):
            return {"email": b["email"], "password": FERNET.decrypt(b["password_enc"].encode()).decode(), "ambiente": b.get("ambiente") or "sandbox"}
        cfg = await _sdi_cfg(cid)
    except InvalidToken:
        raise HTTPException(400, "Credenziali A-Cube non leggibili: inseriscile di nuovo")
    if cfg and cfg["provider"] == "acube":
        return {"email": cfg["email"], "password": cfg["password"], "ambiente": b.get("ambiente") or cfg["ambiente"]}
    raise HTTPException(400, "Collegamento A-Cube Open Banking non configurato: inserisci le credenziali nella pagina Riconciliazione")


@api.get("/banca/config")
async def get_banca_cfg(t: dict = Depends(tenant)):
    return _banca_public(t["company"]) | {"categorie": bk.CATEGORIE}


@api.put("/banca/config")
async def put_banca_cfg(body: BancaCfgIn, t: dict = Depends(tenant_admin)):
    old = t["company"].get("banca") or {}
    full = await db.companies.find_one({"id": t["cid"]}, {"_id": 0, "banca.password_enc": 1})
    new = {**old, "ambiente": body.ambiente, "email": (body.email or "").strip().lower(), "auto": body.auto, "next_sync_at": None, "last_sync_error": None}
    new.pop("password_enc", None)
    if not new["email"]:
        pass
    elif body.password:
        new["password_enc"] = FERNET.encrypt(body.password.strip().encode()).decode()
    elif ((full or {}).get("banca") or {}).get("password_enc"):
        new["password_enc"] = full["banca"]["password_enc"]
    if new["email"] and not new.get("password_enc"):
        raise ferr(400, "password", "Inserisci la password dell'account A-Cube")
    new["has_password"] = bool(new.get("password_enc"))
    await db.companies.update_one({"id": t["cid"]}, {"$set": {"banca": new}})
    return _banca_public({**t["company"], "banca": new})


async def _check_payment_tx(cid: str, pid: str):
    tx = await db.bank_tx.find_one({"company_id": cid, "match.payment_ids": pid}, {"_id": 0, "id": 1})
    if tx:
        await coge.check_annullabile(db, cid, "banca", tx["id"])


async def _unlink_payment(cid: str, pid: str):
    async for tx in db.bank_tx.find({"company_id": cid, "match.payment_ids": pid}, {"_id": 0, "id": 1, "match.payment_ids": 1}):
        others = [x for x in tx["match"]["payment_ids"] if x != pid]
        if others:
            await db.payments.delete_many({"company_id": cid, "id": {"$in": others}})
            await db.passive_payments.delete_many({"company_id": cid, "id": {"$in": others}})
        await db.bank_tx.update_one({"id": tx["id"]}, {"$set": {"stato": "da_riconciliare", "match": None}})
        await coge.annulla(db, cid, "banca", tx["id"])


async def _acc_stats(cid: str) -> dict:
    rows = await db.bank_tx.aggregate([{"$match": {"company_id": cid}}, {"$group": {"_id": {"a": "$account_id", "s": "$stato"}, "n": {"$sum": 1}}}]).to_list(1000)
    out = {}
    for r in rows:
        out.setdefault(r["_id"]["a"], {})[r["_id"]["s"]] = r["n"]
    return out


@api.get("/banca/conti")
async def bank_accounts(t: dict = Depends(tenant)):
    accs = await db.bank_accounts.find({"company_id": t["cid"]}, {"_id": 0}).sort("nome", 1).to_list(200)
    st = await _acc_stats(t["cid"])
    soon = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
    for a in accs:
        a["da_riconciliare"] = st.get(a["id"], {}).get("da_riconciliare", 0)
        a["movimenti"] = sum(st.get(a["id"], {}).values())
        a["consenso_in_scadenza"] = bool(a.get("consent_expires_at") and a["consent_expires_at"] < soon)
    return accs


@api.post("/banca/conti")
async def add_bank_account(body: ContoIn, t: dict = Depends(tenant_accounting)):
    a = {"id": str(uuid.uuid4()), "company_id": t["cid"], "fonte": "file", "nome": body.nome.strip(), "iban": (body.iban or "").replace(" ", "").upper(),
         "banca": body.banca or "", "saldo": None, "created_at": now_iso()}
    await db.bank_accounts.insert_one(dict(a))
    return a


@api.delete("/banca/conti/{aid}")
async def del_bank_account(aid: str, t: dict = Depends(tenant_admin)):
    if await db.bank_tx.find_one({"company_id": t["cid"], "account_id": aid, "stato": "riconciliato"}, {"_id": 1}):
        raise HTTPException(400, "Il conto ha movimenti riconciliati: annulla prima le riconciliazioni")
    r = await db.bank_accounts.delete_one({"id": aid, "company_id": t["cid"]})
    if not r.deleted_count:
        raise HTTPException(404, "Conto non trovato")
    await db.bank_tx.delete_many({"company_id": t["cid"], "account_id": aid})
    return {"ok": True}


async def _insert_tx(cid: str, account_id: str, movs: list, prefix_ids: Optional[list] = None) -> tuple:
    new = dup = 0
    seen = {}
    for i, m in enumerate(movs):
        if prefix_ids:
            eid = prefix_ids[i]
        else:
            k = seen[(m["data"], m["importo"], m["descrizione"])] = seen.get((m["data"], m["importo"], m["descrizione"]), -1) + 1
            eid = bk.ext_id(account_id, m, k)
        doc = {"id": str(uuid.uuid4()), "company_id": cid, "account_id": account_id, "ext_id": eid, "data": m["data"], "valuta": m.get("valuta") or m["data"],
               "importo": m["importo"], "descrizione": m.get("descrizione") or "", "controparte": m.get("controparte") or "", "causale": m.get("causale") or "",
               "stato": "da_riconciliare", "match": None, "created_at": now_iso()}
        r = await db.bank_tx.update_one({"company_id": cid, "ext_id": eid}, {"$setOnInsert": doc}, upsert=True)
        if r.upserted_id:
            new += 1
        else:
            dup += 1
    return new, dup


@api.post("/banca/conti/{aid}/import")
async def import_bank_file(aid: str, file: UploadFile = File(...), t: dict = Depends(tenant_accounting)):
    acc = await db.bank_accounts.find_one({"id": aid, "company_id": t["cid"]}, {"_id": 0})
    if not acc:
        raise HTTPException(404, "Conto non trovato")
    raw = await file.read()
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(400, "File troppo grande (max 10 MB)")
    try:
        p = bk.parse_file(raw, file.filename or "")
    except (bk.BankError, ValueError, IndexError, bk.csv.Error) as e:
        raise HTTPException(400, f"File non leggibile: {e}")
    new, dup = await _insert_tx(t["cid"], aid, p["movimenti"])
    upd = {"last_import_at": now_iso(), "last_import_file": file.filename}
    if p["saldo"] is not None:
        upd |= {"saldo": p["saldo"], "saldo_at": p["saldo_data"]}
    await db.bank_accounts.update_one({"id": aid}, {"$set": upd})
    auto = await _auto_match(t)
    return {"nuovi": new, "duplicati": dup, "auto": auto, "formato": "CBI" if p["saldo"] is not None or p["iban"] else "CSV"}


@api.post("/banca/psd2/connect")
async def psd2_connect(request: Request, t: dict = Depends(tenant_admin)):
    company = _company_required(t)
    cfg = await _banca_cfg(t["cid"])
    origin = request.headers.get("origin") or ""
    try:
        await bk.ensure_registry(cfg, company["partita_iva"], company.get("email") or t["user"]["email"], company["denominazione"])
        url = await bk.connect_url(cfg, company["partita_iva"], f"{origin}/riconciliazione?psd2=ok")
    except bk.BankError as e:
        raise HTTPException(400, f"Collegamento banca non avviato: {e}")
    return {"url": url}


@api.get("/banca/conti/{aid}/reconnect")
async def psd2_reconnect(aid: str, t: dict = Depends(tenant_admin)):
    acc = await db.bank_accounts.find_one({"id": aid, "company_id": t["cid"], "fonte": "psd2"}, {"_id": 0})
    if not acc:
        raise HTTPException(404, "Conto PSD2 non trovato")
    try:
        d = await bk.ob(await _banca_cfg(t["cid"]), "GET", f"/accounts/{acc['acube_uuid']}/reconnect")
    except bk.BankError as e:
        raise HTTPException(400, f"Rinnovo consenso non avviato: {e}")
    url = d.get("connectUrl") or d.get("reconnectUrl") or d.get("url")
    if not url:
        raise HTTPException(400, "A-Cube non ha restituito il link di rinnovo")
    return {"url": url}


async def _bank_sync(comp: dict) -> dict:
    cid, err, res = comp["id"], None, {"conti": 0, "nuovi": 0, "auto": 0}
    try:
        cfg = await _banca_cfg(cid)
        fiscal = comp.get("partita_iva")
        if not fiscal:
            raise HTTPException(400, "Inserisci la Partita IVA nei dati azienda")
        uuids = {}
        for a in await bk.accounts(cfg, fiscal):
            if not a.get("uuid"):
                continue
            r = await db.bank_accounts.find_one_and_update(
                {"company_id": cid, "acube_uuid": a["uuid"]},
                {"$set": {"nome": a.get("name") or a.get("providerName") or "Conto", "iban": a.get("iban") or "", "banca": a.get("providerName") or "",
                          "saldo": a.get("balance"), "saldo_at": now_iso()[:10], "consent_expires_at": a.get("consentExpiresAt"), "enabled": a.get("enabled", True)},
                 "$setOnInsert": {"id": str(uuid.uuid4()), "company_id": cid, "fonte": "psd2", "acube_uuid": a["uuid"], "created_at": now_iso()}},
                upsert=True, return_document=True, projection={"_id": 0, "id": 1})
            uuids[a["uuid"]] = r["id"]
        res["conti"] = len(uuids)
        last = await db.bank_tx.find_one({"company_id": cid, "ext_id": {"$regex": "^acube:"}}, {"_id": 0, "data": 1}, sort=[("data", -1)])
        since = ((date.fromisoformat(last["data"]) - timedelta(days=10)) if last else (datetime.now(timezone.utc).date() - timedelta(days=90))).isoformat()
        by_acc = {}
        for raw in await bk.transactions(cfg, fiscal, since):
            m = bk.map_tx(raw)
            if m["pending"] or not m["data"] or m["account_uuid"] not in uuids:
                continue
            by_acc.setdefault(uuids[m["account_uuid"]], []).append(m)
        for aid, movs in by_acc.items():
            n, _ = await _insert_tx(cid, aid, movs, [f"acube:{m['riferimento']}" for m in movs])
            res["nuovi"] += n
        res["auto"] = await _auto_match({"cid": cid, "company": comp, "user": {"name": "Riconciliazione automatica", "email": "banca", "user_id": "system"}})
    except bk.BankError as e:
        err = str(e)
    except HTTPException as e:
        err = str(e.detail)
    await db.companies.update_one({"id": cid}, {"$set": {"banca.last_sync_at": now_iso(), "banca.last_sync_error": err}})
    if err:
        raise HTTPException(400, err)
    return res


@api.post("/banca/psd2/sync")
async def psd2_sync(t: dict = Depends(tenant_accounting)):
    return await _bank_sync(t["company"])


async def _match_ctx(cid: str) -> dict:
    att, _, _, _ = await _ledger(cid)
    pas, _, _, _ = await _ledger_passive(cid)
    done = await db.bank_tx.find({"company_id": cid, "stato": "riconciliato", "match.tipo": {"$in": ["corrispettivi", "iva"]}}, {"_id": 0, "match.ref_ids": 1}).to_list(5000)
    used = {r for d in done for r in d["match"]["ref_ids"]}
    since = (datetime.now(timezone.utc).date() - timedelta(days=400)).isoformat()
    corr = await db.corrispettivi.aggregate([{"$match": {"company_id": cid, "data": {"$gte": since}}},
                                             {"$group": {"_id": "$data", "totale": {"$sum": "$totale"}}}]).to_list(1000)
    iva, y = [], datetime.now(timezone.utc).year
    for per in ("mensile", "trimestrale"):
        prev = 0.0
        for anno in (y - 2, y - 1, y):
            liq = await _liq_calc(cid, anno, per, prev)
            prev = liq["credito_finale"]
            if anno < y - 1:
                continue
            iva += [{"key": f"{anno}-{per[0]}-{p['periodo']}", "label": f"{p['label']} {anno}", "da_versare": p["da_versare"]} for p in liq["periodi"] if p["da_versare"] > 0]
    return {"attive": [d for d in att if d["residuo"] > 0.005], "passive": [d for d in pas if d["residuo"] > 0.005],
            "corr": [{"data": c["_id"], "totale": round(c["totale"], 2)} for c in corr if c["_id"] not in used], "iva": [p for p in iva if p["key"] not in used]}


def _cands(tx: dict, ctx: dict) -> list:
    return bk.candidates(tx, ctx["attive"], ctx["passive"], ctx["corr"], ctx["iva"])


async def _reconcile(t: dict, tx: dict, body: RiconciliaIn, ctx: dict, auto: bool = False) -> dict:
    cid, amount = t["cid"], abs(tx["importo"])
    match = {"tipo": body.tipo, "ref_ids": body.ref_ids, "auto": auto, "by": t["user"].get("name") or t["user"]["email"], "at": now_iso(), "note": body.note or "",
             "payment_ids": [], "righe": []}
    if body.tipo in ("incasso", "pagamento"):
        if (body.tipo == "incasso") != (tx["importo"] > 0):
            raise HTTPException(400, "Gli incassi si abbinano ai movimenti in entrata, i pagamenti a quelli in uscita")
        if not body.ref_ids:
            raise HTTPException(400, "Seleziona almeno una fattura")
        pool = {d["id"]: d for d in ctx["attive" if body.tipo == "incasso" else "passive"]}
        rest, coll = amount, db.payments if body.tipo == "incasso" else db.passive_payments
        for rid in body.ref_ids:
            d = pool.get(rid)
            if not d:
                raise HTTPException(400, "Fattura non trovata o già saldata")
            if tx["data"] < d["data"]:
                raise HTTPException(400, f"Il movimento del {_it_date(tx['data'])} precede la fattura {d['numero_display']}")
            imp = round(min(rest, d["residuo"]), 2)
            if imp <= 0:
                break
            p = {"id": str(uuid.uuid4()), "data": tx["data"], "importo": imp, "metodo": "bonifico", "note": f"Banca: {tx['descrizione'][:150]}", "nc_id": None,
                 "company_id": cid, "invoice_id": rid, "party_id": d["party_id"], "numero_display": d["numero_display"], "nc_numero": None, "bank_tx_id": tx["id"],
                 "created_by": t["user"].get("user_id"), "created_by_name": match["by"], "created_at": now_iso()}
            await coll.insert_one(p)
            d["residuo"] = round(d["residuo"] - imp, 2)
            rest = round(rest - imp, 2)
            match["payment_ids"].append(p["id"])
            match["righe"].append({"ref_id": rid, "label": f"Fattura {d['numero_display']} · {d['cliente']}", "importo": imp, "party_id": d["party_id"]})
        match["label"] = ", ".join(r["label"] for r in match["righe"])
        match["ref_ids"] = [r["ref_id"] for r in match["righe"]]
        match["non_abbinato"] = rest
    elif body.tipo in ("corrispettivi", "iva"):
        c = next((x for x in _cands(tx, ctx) if x["tipo"] == body.tipo and x["ref_id"] in body.ref_ids), None)
        if not c:
            raise HTTPException(400, "Riferimento non valido per questo movimento")
        match["label"] = c["label"]
        match["ref_ids"] = [c["ref_id"]]
        (ctx["corr"] if body.tipo == "corrispettivi" else ctx["iva"])[:] = [x for x in ctx["corr" if body.tipo == "corrispettivi" else "iva"]
                                                                          if (x.get("data") or x.get("key")) != c["ref_id"]]
    else:
        if body.categoria not in bk.CATEGORIE:
            raise ferr(400, "categoria", "Scegli una categoria")
        match["label"] = body.categoria + (f" · {body.note}" if body.note else "")
        match["categoria"] = body.categoria
    r = await db.bank_tx.update_one({"id": tx["id"], "company_id": cid, "stato": "da_riconciliare"}, {"$set": {"stato": "riconciliato", "match": match}})
    if not r.modified_count:
        for pid in match["payment_ids"]:
            await db.payments.delete_one({"id": pid, "company_id": cid})
            await db.passive_payments.delete_one({"id": pid, "company_id": cid})
        raise HTTPException(409, "Movimento già riconciliato")
    await coge.safe(coge.registra_banca(db, cid, tx, match))
    return {**tx, "stato": "riconciliato", "match": match}


async def _auto_match(t: dict) -> int:
    txs = await db.bank_tx.find({"company_id": t["cid"], "stato": "da_riconciliare"}, TX_PROJ).sort("data", 1).to_list(5000)
    if not txs:
        return 0
    ctx, n = await _match_ctx(t["cid"]), 0
    rules = await db.bank_rules.find({"company_id": t["cid"], "attiva": True}, {"_id": 0}).sort("created_at", 1).to_list(500)
    for tx in txs:
        a = bk.safe_auto(_cands(tx, ctx))
        rule = None if a else next((r for r in rules if bk.rule_matches(r, tx)), None)
        if not (a or rule):
            continue
        body = RiconciliaIn(tipo=a["tipo"], ref_ids=[a["ref_id"]]) if a else RiconciliaIn(tipo="altro", categoria=rule["categoria"], note=rule.get("note") or "")
        try:
            await _reconcile(t, tx, body, ctx, auto=True)
            n += 1
            if rule:
                await db.bank_rules.update_one({"id": rule["id"]}, {"$inc": {"applicata": 1}})
                await db.bank_tx.update_one({"id": tx["id"]}, {"$set": {"match.rule_id": rule["id"], "match.rule_nome": rule["nome"]}})
        except HTTPException:
            continue
    return n


async def _get_tx(tid: str, cid: str) -> dict:
    tx = await db.bank_tx.find_one({"id": tid, "company_id": cid}, TX_PROJ)
    if not tx:
        raise HTTPException(404, "Movimento non trovato")
    return tx


@api.get("/banca/movimenti")
async def bank_movements(stato: Optional[str] = "da_riconciliare", account_id: Optional[str] = None, q: Optional[str] = None,
                         t: dict = Depends(tenant)):
    f = {"company_id": t["cid"], **({"stato": stato} if stato in ("da_riconciliare", "riconciliato", "ignorato") else {}),
         **({"account_id": account_id} if account_id else {})}
    if q:
        f["$or"] = [{"descrizione": {"$regex": re.escape(q), "$options": "i"}}, {"controparte": {"$regex": re.escape(q), "$options": "i"}}]
    rows = await db.bank_tx.find(f, TX_PROJ).sort([("data", -1), ("created_at", -1)]).to_list(1000)
    if any(r["stato"] == "da_riconciliare" for r in rows):
        ctx = await _match_ctx(t["cid"])
        for r in rows:
            if r["stato"] == "da_riconciliare":
                c = _cands(r, ctx)
                r["proposta"] = c[0] if c and c[0]["score"] >= 50 else None
    tot = await db.bank_tx.aggregate([{"$match": {"company_id": t["cid"]}}, {"$group": {"_id": "$stato", "n": {"$sum": 1}}}]).to_list(10)
    return {"movimenti": rows, "conteggi": {x["_id"]: x["n"] for x in tot}}


@api.get("/banca/movimenti/{tid}/candidati")
async def bank_candidates(tid: str, t: dict = Depends(tenant_accounting)):
    tx = await _get_tx(tid, t["cid"])
    ctx = await _match_ctx(t["cid"])
    docs = ctx["attive"] if tx["importo"] > 0 else ctx["passive"]
    return {"proposte": _cands(tx, ctx), "categorie": bk.CATEGORIE,
            "fatture": [{"id": d["id"], "numero_display": d["numero_display"], "data": d["data"], "cliente": d["cliente"], "residuo": d["residuo"]}
                        for d in sorted(docs, key=lambda d: d["data"])]}


@api.post("/banca/movimenti/{tid}/riconcilia")
async def bank_reconcile(tid: str, body: RiconciliaIn, t: dict = Depends(tenant_accounting)):
    tx = await _get_tx(tid, t["cid"])
    if tx["stato"] != "da_riconciliare":
        raise HTTPException(400, "Movimento già riconciliato o ignorato")
    rule = None
    if body.tipo == "altro" and (body.salva_regola or "").strip():
        txt = body.salva_regola.strip()
        if len(txt) < 2:
            raise ferr(422, "salva_regola", "Il testo della regola deve avere almeno 2 caratteri")
        if body.categoria not in bk.CATEGORIE:
            raise ferr(400, "categoria", "Scegli una categoria")
        rule = RegolaIn(nome=txt[:80], contiene=txt, segno="entrata" if tx["importo"] > 0 else "uscita", categoria=body.categoria, note=body.note or "")
    res = await _reconcile(t, tx, body, await _match_ctx(t["cid"]))
    if rule:
        dup = await db.bank_rules.find_one({"company_id": t["cid"], "contiene": {"$regex": f"^{re.escape(rule.contiene)}$", "$options": "i"},
                                            "segno": rule.segno, "categoria": rule.categoria}, {"_id": 1})
        if not dup:
            await _save_rule(t, rule)
            res["altri_riconciliati"] = await _auto_match(t)
        res["regola_creata"] = not dup
    return res


async def _save_rule(t: dict, body: RegolaIn, rid: Optional[str] = None) -> dict:
    d = body.model_dump() | {"contiene": body.contiene.strip()}
    if rid:
        r = await db.bank_rules.find_one_and_update({"id": rid, "company_id": t["cid"]}, {"$set": d}, return_document=True, projection={"_id": 0})
        if not r:
            raise HTTPException(404, "Regola non trovata")
        return r
    d |= {"id": str(uuid.uuid4()), "company_id": t["cid"], "applicata": 0, "created_at": now_iso(), "created_by": t["user"].get("name") or t["user"]["email"]}
    await db.bank_rules.insert_one(dict(d))
    return d


@api.get("/banca/regole")
async def list_rules(t: dict = Depends(tenant_accounting)):
    return {"regole": await db.bank_rules.find({"company_id": t["cid"]}, {"_id": 0}).sort("created_at", 1).to_list(500), "categorie": bk.CATEGORIE}


@api.post("/banca/regole")
async def add_rule(body: RegolaIn, t: dict = Depends(tenant_accounting)):
    return await _save_rule(t, body)


@api.put("/banca/regole/{rid}")
async def upd_rule(rid: str, body: RegolaIn, t: dict = Depends(tenant_accounting)):
    return await _save_rule(t, body, rid)


@api.delete("/banca/regole/{rid}")
async def del_rule(rid: str, t: dict = Depends(tenant_accounting)):
    r = await db.bank_rules.delete_one({"id": rid, "company_id": t["cid"]})
    if not r.deleted_count:
        raise HTTPException(404, "Regola non trovata")
    return {"ok": True}


@api.post("/banca/regole/prova")
async def test_rule(body: RegolaIn, t: dict = Depends(tenant_accounting)):
    txs = await db.bank_tx.find({"company_id": t["cid"], "stato": "da_riconciliare"}, TX_PROJ).sort("data", -1).to_list(5000)
    hit = [x for x in txs if bk.rule_matches(body.model_dump() | {"attiva": True}, x)]
    return {"n": len(hit), "esempi": [{k: x[k] for k in ("id", "data", "importo", "descrizione")} for x in hit[:5]]}


@api.get("/banca/previsione")
async def cash_forecast(giorni: int = 90, scaduti: bool = True, t: dict = Depends(tenant)):
    giorni = max(7, min(giorni, 365))
    m = company_moduli(t["company"], t["user"])
    today = datetime.now(timezone.utc).date()
    end = (today + timedelta(days=giorni)).isoformat()
    accs = await db.bank_accounts.find({"company_id": t["cid"]}, {"_id": 0, "saldo": 1}).to_list(200)
    senza_saldo = sum(1 for a in accs if a.get("saldo") is None)
    saldo0 = round(sum(a.get("saldo") or 0 for a in accs), 2)
    voci = []
    for kind, ok, loader in (("incasso", m["fatture_attive"], _ledger), ("pagamento", m["fatture_passive"], _ledger_passive)):
        if not ok:
            continue
        docs, _, _, _ = await loader(t["cid"])
        for d in docs:
            for r in d.get("rate") or []:
                if r["residuo"] <= 0.005 or r["scadenza"] > end:
                    continue
                scad = r["scadenza"] < today.isoformat()
                if scad and not scaduti:
                    continue
                voci.append({"data": today.isoformat() if scad else r["scadenza"], "scadenza": r["scadenza"], "scaduta": scad, "tipo": kind,
                             "importo": r["residuo"] if kind == "incasso" else -r["residuo"], "label": f"{d['numero_display']} · {d['cliente']}" + (f" (rata {r['n']}/{r['di']})" if r["di"] > 1 else ""),
                             "invoice_id": d["id"]})
    voci.sort(key=lambda v: (v["data"], -v["importo"]))
    by_day, serie, saldo, minimo = {}, [], saldo0, None
    for v in voci:
        by_day.setdefault(v["data"], []).append(v)
    for i in range(giorni + 1):
        dd = (today + timedelta(days=i)).isoformat()
        ent = round(sum(v["importo"] for v in by_day.get(dd, []) if v["importo"] > 0), 2)
        usc = round(-sum(v["importo"] for v in by_day.get(dd, []) if v["importo"] < 0), 2)
        saldo = round(saldo + ent - usc, 2)
        serie.append({"data": dd, "entrate": ent, "uscite": usc, "saldo": saldo})
        if minimo is None or saldo < minimo["saldo"]:
            minimo = {"data": dd, "saldo": saldo}
    tot_in = round(sum(v["importo"] for v in voci if v["importo"] > 0), 2)
    tot_out = round(-sum(v["importo"] for v in voci if v["importo"] < 0), 2)
    return {"saldo_iniziale": saldo0, "saldo_finale": saldo, "entrate": tot_in, "uscite": tot_out, "minimo": minimo, "giorni": giorni,
            "conti": len(accs), "conti_senza_saldo": senza_saldo, "serie": serie, "voci": voci,
            "scaduti": {"incassi": round(sum(v["importo"] for v in voci if v["scaduta"] and v["importo"] > 0), 2),
                        "pagamenti": round(-sum(v["importo"] for v in voci if v["scaduta"] and v["importo"] < 0), 2)}}


@api.post("/banca/movimenti/{tid}/annulla")
async def bank_unreconcile(tid: str, t: dict = Depends(tenant_accounting)):
    tx = await _get_tx(tid, t["cid"])
    if tx["stato"] == "da_riconciliare":
        raise HTTPException(400, "Il movimento non è riconciliato")
    await coge.check_annullabile(db, t["cid"], "banca", tid)
    ids = ((tx.get("match") or {}).get("payment_ids")) or []
    if ids:
        await db.payments.delete_many({"company_id": t["cid"], "id": {"$in": ids}})
        await db.passive_payments.delete_many({"company_id": t["cid"], "id": {"$in": ids}})
    await db.bank_tx.update_one({"id": tid}, {"$set": {"stato": "da_riconciliare", "match": None}})
    await coge.annulla(db, t["cid"], "banca", tid)
    return {**tx, "stato": "da_riconciliare", "match": None}


@api.post("/banca/movimenti/{tid}/ignora")
async def bank_ignore(tid: str, t: dict = Depends(tenant_accounting)):
    tx = await _get_tx(tid, t["cid"])
    if tx["stato"] != "da_riconciliare":
        raise HTTPException(400, "Movimento già riconciliato o ignorato")
    m = {"tipo": "ignorato", "label": "Ignorato", "by": t["user"].get("name") or t["user"]["email"], "at": now_iso(), "payment_ids": []}
    await db.bank_tx.update_one({"id": tid}, {"$set": {"stato": "ignorato", "match": m}})
    return {**tx, "stato": "ignorato", "match": m}


@api.post("/banca/auto")
async def bank_auto(t: dict = Depends(tenant_accounting)):
    return {"riconciliati": await _auto_match(t)}


@api.get("/banca/riepilogo")
async def bank_summary(t: dict = Depends(tenant)):
    accs = await bank_accounts(t)
    return {"conti": [{k: a.get(k) for k in ("id", "nome", "banca", "iban", "fonte", "saldo", "saldo_at", "da_riconciliare", "consenso_in_scadenza")} for a in accs],
            "saldo_totale": round(sum(a.get("saldo") or 0 for a in accs), 2), "da_riconciliare": sum(a["da_riconciliare"] for a in accs),
            "config": _banca_public(t["company"])}


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
            '</td></tr></table>')
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
    smtp = await _company_smtp(t["cid"])
    pdf = _statement_pdf(t, party, docs, crediti, pays, invs, today)
    name = re.sub(r"[^A-Za-z0-9]+", "_", party["denominazione"])[:40]
    email_id = await send_email(smtp=smtp, to=to, subject=subject, html=html, reply_to=smtp.get("reply_to") or t["company"].get("email") or None,
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
@api.get("/dashboard/riquadri")
async def dashboard_riquadri(t: dict = Depends(tenant)):
    cid = t["cid"]
    oggi = datetime.now(timezone.utc).date().isoformat()
    fra10 = (datetime.now(timezone.utc).date() + timedelta(days=10)).isoformat()
    mese = oggi[:7]
    cnt = lambda coll, q: coll.count_documents({"company_id": cid, **q})  # noqa: E731

    def scaduto(docs):
        rr = [r for d in docs for r in d["rate"] if r["residuo"] > 0.005 and r["scadenza"] < oggi]
        return len(rr), round(sum(r["residuo"] for r in rr), 2)

    cli_n, cli_imp = scaduto((await _ledger(cid))[0])
    for_n, for_imp = scaduto((await _ledger_passive(cid))[0])
    arts = await db.articles.find({"company_id": cid, "gestione_magazzino": True, "scorta_minima": {"$gt": 0}}, {"_id": 0, "giacenza": 1, "scorta_minima": 1}).to_list(20000)
    return {
        "bozze": await cnt(db.invoices, {"status": "bozza"}), "scartate": await cnt(db.invoices, {"status": "scartata"}),
        "autofatture_bozza": await cnt(db.invoices, {"status": "bozza", "autofattura": True}),
        "passive_da_registrare": await cnt(db.passive_invoices, {"stato_reg": "da_registrare"}),
        "fornitori_da_verificare": await cnt(db.parties, {"tipo": "fornitore", "da_verificare": True}),
        "clienti_scaduto_n": cli_n, "clienti_scaduto": cli_imp, "fornitori_scaduto_n": for_n, "fornitori_scaduto": for_imp,
        "riba_insoluti_mese": await cnt(db.riba_effetti, {"stato": "insoluto", "insoluto.data": {"$regex": f"^{mese}"}}),
        "riba_in_scadenza": await cnt(db.riba_effetti, {"stato": "presentato", "scadenza": {"$gte": oggi, "$lte": fra10}}),
        "ddt_da_fatturare": await cnt(db.ddts, {"status": "confermato"}),
        "sottoscorta": sum(1 for a in arts if (a.get("giacenza") or 0) <= a["scorta_minima"]),
        "movimenti_mese": await cnt(db.coa_entries, {"data": {"$regex": f"^{mese}"}}),
        "movimenti_modificati": await cnt(db.coa_entries, {"modificata": True, "data": {"$regex": f"^{mese}"}}),
    }


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


async def _seed_admin():
    try:
        await db.users.update_one({"email": ADMIN_EMAIL}, {"$setOnInsert": {
            "user_id": f"user_{uuid.uuid4().hex[:12]}", "email": ADMIN_EMAIL, "name": "Amministratore", "picture": None,
            "password_hash": hash_password(ADMIN_PASSWORD), "email_verified": True, "role": "admin", "status": "approved", "created_at": now_iso()}}, upsert=True)
    except DuplicateKeyError:
        pass
    await db.users.update_one({"email": ADMIN_EMAIL, "password_hash": {"$in": [None, ""]}},
                              {"$set": {"password_hash": hash_password(ADMIN_PASSWORD), "email_verified": True, "role": "admin", "status": "approved"}})


@app.on_event("startup")
async def init_indexes():
    await _migrate_single_company()
    await db.invoices.update_many({"sezionale": {"$exists": False}}, {"$set": {"sezionale": ""}})
    await db.invoices.create_index([("company_id", 1), ("sezionale", 1), ("anno", 1), ("numero", 1)], unique=True, name="company_sez_anno_numero")
    await db.payments.create_index([("company_id", 1), ("invoice_id", 1)])
    await db.passive_invoices.create_index([("company_id", 1), ("hash", 1)], unique=True)
    await db.passive_payments.create_index([("company_id", 1), ("invoice_id", 1)])
    await db.corrispettivi.create_index([("company_id", 1), ("data", 1), ("matricola", 1)], unique=True)
    await db.bank_tx.create_index([("company_id", 1), ("ext_id", 1)], unique=True)
    await db.bank_tx.create_index([("company_id", 1), ("stato", 1), ("data", -1)])
    await db.passive_invoices.create_index([("company_id", 1), ("anno_registrazione", 1), ("protocollo", 1)])
    await db.invoices.create_index("fattura_collegata_id")
    await db.users.create_index("email", unique=True)
    await db.password_reset_tokens.create_index("expires_at", expireAfterSeconds=0)
    await db.login_attempts.create_index("identifier")
    await db.articles.create_index([("company_id", 1), ("codice", 1)], unique=True, name="company_codice")
    await db.parties.create_index("company_id")
    await db.companies.create_index("id", unique=True)
    await _seed_admin()
    await archivio_indexes(db)
    await coge.ensure_indexes(db)
    await cons.ensure_indexes(db)
    await ddt_mod.ensure_indexes(db)
    await db.riba_effetti.create_index([("company_id", 1), ("stato", 1), ("scadenza", 1)])
    await db.riba_effetti.create_index([("company_id", 1), ("invoice_id", 1)])
    await db.passive_payments.create_index([("company_id", 1), ("distinta_pag_id", 1)])
    await db.pag_distinte.create_index([("company_id", 1), ("data", -1)])
    await db.intenti.create_index([("company_id", 1), ("party_id", 1), ("anno", 1)])
    asyncio.create_task(_sdi_loop())


app.include_router(api)
app.include_router(build_archivio_router(db, tenant, tenant_accounting))
app.include_router(build_updater_router(approved_user), prefix="/api")
app.include_router(build_magazzino_router(db, tenant, tenant_accounting))
app.include_router(coge.build_router(db, tenant, tenant_accounting, SALDACONTO))
app.include_router(build_chiusure_router(db, tenant, tenant_accounting))
com_router, com_cortesia, com_tick = build_comunicazioni(db, tenant, tenant_accounting, {
    "smtp": _company_smtp, "send": send_email, "ledger": _ledger, "proj": COMPANY_PROJ, "pdf": courtesy_pdf, "app_url": APP_URL, "diritti": diritti})
app.include_router(com_router)
app.include_router(cons.build(db, tenant, tenant_accounting, tenant_admin, {
    "fernet": FERNET, "sdi_cfg": _sdi_cfg, "sent": SENT, "ferr": ferr, "f24_pdf": f24.build_pdf,
    "xml": lambda comp, inv: (build_xml(comp, inv), file_name(comp, inv)),
    "registro_iva_vendite": registro_iva_vendite, "registro_iva_acquisti": registro_iva_acquisti, "corrispettivi": list_corrispettivi}))
app.include_router(ddt_mod.build(db, tenant, {"ferr": ferr, "aliquote": ALIQUOTE, "nature": NATURE, "LineIn": LineIn, "InvoiceIn": InvoiceIn, "create_invoice": create_invoice}))
app.include_router(ddt_mod.build_public(db))
riba_router, riba_tick = riba_mod.build(db, tenant, tenant_accounting, {"ledger": _ledger, "ferr": ferr})
app.include_router(riba_router)
app.include_router(riba_mod.build_scadenze(db, tenant, ferr))
app.include_router(codici_tributo.build(tenant))
app.include_router(pagforn.build(db, tenant, tenant_accounting, {"ledger": _ledger_passive, "ferr": ferr, "check_tx": _check_payment_tx, "unlink": _unlink_payment}))
intenti_router, intento_scegli = intenti_mod.build(db, tenant, ferr)
app.include_router(intenti_router)
regpas_router, crea_autofattura = registra_passiva.build(db, tenant_accounting, {"ferr": ferr, "next_progressivo": _next_progressivo})
app.include_router(regpas_router)
app.include_router(reg_veloce.build(db, tenant_accounting, {"ferr": ferr, "aliquote": ALIQUOTE, "nature": NATURE, "intento": intento_scegli, "lock": _INTENTO_LOCKS,
                                                              "autofattura": crea_autofattura}))
app.include_router(importazione.build(db, tenant_admin, {"PartyIn": PartyIn, "ArticleIn": ArticleIn, "norm_sconto": norm_sconto}))

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

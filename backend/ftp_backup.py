import io
import gzip
import json
import ftplib
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

ROME = ZoneInfo("Europe/Rome")
SKIP = {"companies", "users", "user_sessions", "login_attempts", "password_reset_tokens"}


async def build_archive(db, comp: dict):
    cid = comp["id"]
    dati, conteggi = {}, {}
    for name in sorted(await db.list_collection_names()):
        if name in SKIP or name.startswith("system."):
            continue
        docs = await db[name].find({"company_id": cid}, {"_id": 0}).to_list(None)
        if docs:
            dati[name], conteggi[name] = docs, len(docs)
    azienda = {k: v for k, v in comp.items() if k not in ("ftp_backup",)}
    utenti = await db.users.find({"company_ids": cid}, {"_id": 0, "password_hash": 0, "email_log": 0}).to_list(None)
    now = datetime.now(ROME)
    payload = {"formato": "fatturazione-backup-azienda/1", "creato_il": now.isoformat(), "azienda": azienda, "utenti": utenti, "collezioni": dati}
    raw = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    ident = "".join(ch for ch in (comp.get("partita_iva") or cid[:8]) if ch.isalnum())
    return gzip.compress(raw, 6), f"backup-{ident}-{now:%Y-%m-%d_%H%M}.json.gz", conteggi


def _connect(cfg: dict, password: str):
    ftp = ftplib.FTP_TLS(timeout=30) if cfg.get("tls", True) else ftplib.FTP(timeout=30)
    ftp.connect(cfg["host"], int(cfg.get("porta") or 21))
    ftp.login(cfg.get("utente") or "anonymous", password or "")
    if isinstance(ftp, ftplib.FTP_TLS):
        ftp.prot_p()
    for part in [p for p in (cfg.get("cartella") or "").replace("\\", "/").split("/") if p]:
        try:
            ftp.cwd(part)
        except ftplib.error_perm:
            ftp.mkd(part)
            ftp.cwd(part)
    return ftp


def _err(e: Exception) -> str:
    if isinstance(e, ftplib.error_perm) and "AUTH" in str(e):
        return f"Il server non supporta la connessione cifrata (FTPS): disattivate l'opzione o chiedete al fornitore ({e})"
    if isinstance(e, ftplib.error_perm):
        return f"Accesso negato o operazione non permessa: {e}"
    if isinstance(e, (TimeoutError, OSError)) and not isinstance(e, ftplib.Error):
        return f"Server FTP non raggiungibile: {e}"
    return f"{e.__class__.__name__}: {e}"


def _upload(cfg, password, filename, data):
    ftp = _connect(cfg, password)
    try:
        ftp.storbinary(f"STOR {filename}", io.BytesIO(data))
    finally:
        try:
            ftp.quit()
        except Exception:  # noqa: BLE001
            ftp.close()


def _test(cfg, password):
    ftp = _connect(cfg, password)
    try:
        return ftp.pwd()
    finally:
        try:
            ftp.quit()
        except Exception:  # noqa: BLE001
            ftp.close()


async def upload(cfg, password, filename, data):
    try:
        await asyncio.to_thread(_upload, cfg, password, filename, data)
        return None
    except Exception as e:  # noqa: BLE001
        return _err(e)


async def test(cfg, password):
    try:
        return await asyncio.to_thread(_test, cfg, password), None
    except Exception as e:  # noqa: BLE001
        return None, _err(e)


def due(cfg: dict, now: datetime) -> bool:
    return bool(cfg.get("attivo")) and now.strftime("%H:%M") >= (cfg.get("ora") or "02:00") and cfg.get("ultimo_giorno") != now.date().isoformat()

import os
import ssl
import json
import time
import socket
import asyncio
from datetime import datetime, timezone
from urllib.parse import urlparse

_cache: dict = {}
CERT_TTL = 6 * 3600


def _cert_info(host: str, port: int) -> dict:
    out = {"host": host, "scadenza": None, "giorni": None, "errore": None, "verificato_il": datetime.now(timezone.utc).isoformat()}
    try:
        with socket.create_connection((host, port), timeout=6) as s, ssl.create_default_context().wrap_socket(s, server_hostname=host) as t:
            exp = datetime.fromtimestamp(ssl.cert_time_to_seconds(t.getpeercert()["notAfter"]), timezone.utc)
        out.update(scadenza=exp.isoformat(), giorni=(exp - datetime.now(timezone.utc)).days)
    except ssl.SSLCertVerificationError as e:
        out.update(errore=f"Certificato non valido o scaduto: {e.verify_message}", invalido=True)
    except (OSError, ssl.SSLError) as e:
        out.update(errore=f"Impossibile verificare il certificato su {host}:{port} ({e.__class__.__name__})")
    return out


async def cert_status(app_url: str, refresh: bool = False):
    u = urlparse(app_url)
    if u.scheme != "https" or not u.hostname:
        return None
    hit = _cache.get("cert")
    if hit and not refresh and time.time() - hit[0] < CERT_TTL:
        return hit[1]
    info = await asyncio.to_thread(_cert_info, u.hostname, u.port or 443)
    _cache["cert"] = (time.time(), info)
    return info


def backup_status():
    path = os.environ.get("BACKUP_STATUS_FILE")
    if not path:
        return None
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"mancante": True}
    except (OSError, ValueError) as e:
        return {"errore": f"Stato backup illeggibile: {e}"}


def avvisi(cert, bk) -> list:
    out = []
    if cert:
        g = cert.get("giorni")
        if cert.get("invalido") or (g is not None and g <= 7):
            out.append({"id": "cert", "livello": "rosso", "titolo": "Certificato HTTPS in scadenza" if g is not None and g >= 0 else "Certificato HTTPS non valido",
                        "testo": cert.get("errore") or f"Il certificato di {cert['host']} scade tra {g} giorni. Il rinnovo automatico non sta funzionando: lanciate C:\\win-acme\\wacs.exe --renew --force"})
        elif g is not None and g <= 21:
            out.append({"id": "cert", "livello": "giallo", "titolo": "Certificato HTTPS in scadenza",
                        "testo": f"Il certificato di {cert['host']} scade tra {g} giorni. Di norma si rinnova da solo 30 giorni prima: controllate l'attività pianificata di win-acme."})
        elif cert.get("errore"):
            out.append({"id": "cert", "livello": "giallo", "titolo": "Certificato HTTPS non verificabile", "testo": cert["errore"]})
    if bk is not None:
        if bk.get("mancante"):
            out.append({"id": "backup", "livello": "rosso", "titolo": "Nessun backup trovato", "testo": "Il backup notturno non è mai stato eseguito: controllate l'attività pianificata \"Backup Fatturazione\"."})
        elif bk.get("errore") and not bk.get("data"):
            out.append({"id": "backup", "livello": "rosso", "titolo": "Stato del backup non leggibile", "testo": bk["errore"]})
        else:
            try:
                ore = (datetime.now(timezone.utc) - datetime.fromisoformat(bk["data"])).total_seconds() / 3600
            except (KeyError, ValueError, TypeError):
                ore = 9999
            if not bk.get("backup_ok"):
                out.append({"id": "backup", "livello": "rosso", "titolo": "Backup notturno fallito", "testo": bk.get("errore") or "Il salvataggio del database non è riuscito."})
            elif ore > 48:
                out.append({"id": "backup", "livello": "rosso", "titolo": "Backup non aggiornato", "testo": f"L'ultimo backup riuscito risale a {int(ore // 24)} giorni fa."})
            elif bk.get("ftp_ok") is False:
                out.append({"id": "backup-ftp", "livello": "giallo", "titolo": "Copia del backup su FTP non riuscita",
                            "testo": f"Il backup locale è riuscito, ma la copia sul server FTP no: {bk.get('ftp_errore') or 'errore sconosciuto'}"})
    return out

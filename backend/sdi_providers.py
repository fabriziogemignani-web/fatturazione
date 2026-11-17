import base64
import time
from datetime import datetime, timedelta, timezone
import httpx

LABEL = {"openapi": "Openapi.it", "acube": "A-Cube", "aruba": "Aruba"}
BASE = {
    "openapi": {"sandbox": "https://test.sdi.openapi.it", "production": "https://sdi.openapi.it"},
    "acube": {"sandbox": "https://api-sandbox.acubeapi.com", "production": "https://api.acubeapi.com"},
    "aruba": {"sandbox": "https://demows.fatturazioneelettronica.aruba.it", "production": "https://ws.fatturazioneelettronica.aruba.it"},
}
ACUBE_LOGIN = {"sandbox": "https://common-sandbox.api.acubeapi.com/login", "production": "https://common.api.acubeapi.com/login"}
ARUBA_AUTH = {"sandbox": "https://demoauth.fatturazioneelettronica.aruba.it/auth/signin", "production": "https://auth.fatturazioneelettronica.aruba.it/auth/signin"}
ARUBA_STATO = {"consegnata": "RC", "scartata": "NS", "errore elaborazione": "NS", "non consegnata": "MC", "impossibilità di recapito": "MC",
               "accettata": "NE", "rifiutata": "NE", "decorrenza termini": "DT"}
STATUS_BY_TYPE = {"NS": "scartata", "RC": "consegnata", "MC": "mancata_consegna", "AT": "mancata_consegna", "NE": "consegnata", "DT": "consegnata"}
_tokens = {}


class SdiError(Exception):
    pass


def _items(d):
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        for k in ("data", "hydra:member", "member", "items"):
            if isinstance(d.get(k), list):
                return d[k]
    return []


def _uuid(d):
    if isinstance(d, dict):
        if d.get("uuid"):
            return d["uuid"]
        for v in d.values():
            u = _uuid(v)
            if u:
                return u
    return None


def _err(r: httpx.Response) -> str:
    try:
        d = r.json()
        msg = d.get("message") or d.get("detail") or d.get("hydra:description") or d.get("error") or d
    except ValueError:
        msg = r.text
    if r.status_code in (401, 403):
        return f"credenziali non valide o servizio non attivo ({r.status_code})"
    return f"{r.status_code}: {str(msg)[:400]}"


async def _acube_token(cfg) -> str:
    key = (cfg["email"], cfg["ambiente"])
    tok = _tokens.get(key)
    if tok and tok[1] > time.time() + 300:
        return tok[0]
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(ACUBE_LOGIN[cfg["ambiente"]], json={"email": cfg["email"], "password": cfg["password"]})
    if r.status_code != 200:
        raise SdiError(f"accesso A-Cube non riuscito: {_err(r)}")
    t = r.json().get("token")
    _tokens[key] = (t, time.time() + 23 * 3600)
    return t


async def _aruba_token(cfg) -> str:
    key = ("aruba", cfg["email"], cfg["ambiente"])
    tok = _tokens.get(key)
    if tok and tok[1] > time.time() + 120:
        return tok[0]
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(ARUBA_AUTH[cfg["ambiente"]], data={"grant_type": "password", "username": cfg["email"], "password": cfg["password"]})
    except httpx.HTTPError as e:
        raise SdiError(f"Aruba non raggiungibile: {e.__class__.__name__}")
    if r.status_code != 200:
        raise SdiError(f"accesso Aruba non riuscito: {_err(r)}")
    d = r.json()
    _tokens[key] = (d["access_token"], time.time() + int(d.get("expires_in") or 1800))
    return d["access_token"]


def _aruba_ok(r: httpx.Response) -> dict:
    try:
        d = r.json()
    except ValueError:
        raise SdiError("risposta di Aruba non leggibile")
    if isinstance(d, dict) and d.get("errorCode") not in (None, "", "0000"):
        raise SdiError(f"Aruba {d['errorCode']}: {d.get('errorDescription') or ''}"[:400])
    return d


async def _req(cfg, method, path, **kw):
    p = cfg["provider"]
    tok = cfg["token"] if p == "openapi" else await _aruba_token(cfg) if p == "aruba" else await _acube_token(cfg)
    headers = {"Authorization": f"Bearer {tok}", "Accept": "application/json", **kw.pop("headers", {})}
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.request(method, BASE[p][cfg["ambiente"]] + path, headers=headers, **kw)
    except httpx.HTTPError as e:
        raise SdiError(f"{LABEL[p]} non raggiungibile: {e.__class__.__name__}")
    if r.status_code == 401 and p == "acube":
        _tokens.pop((cfg["email"], cfg["ambiente"]), None)
    if r.status_code == 401 and p == "aruba":
        _tokens.pop(("aruba", cfg["email"], cfg["ambiente"]), None)
    if r.status_code >= 400:
        raise SdiError(_err(r))
    return r


async def check(cfg):
    if cfg["provider"] == "aruba":
        _aruba_ok(await _req(cfg, "GET", "/services/invoice/out/findByUsername", params={"username": cfg["email"], "page": 1, "size": 1}))
        return
    await _req(cfg, "GET", "/invoices", params={"page": 1})


async def send(cfg, xml: str) -> str:
    if cfg["provider"] == "aruba":
        d = _aruba_ok(await _req(cfg, "POST", "/services/invoice/upload", json={"dataFile": base64.b64encode(xml.encode("utf-8")).decode()}))
        if not d.get("uploadFileName"):
            raise SdiError("risposta di Aruba senza nome file")
        return d["uploadFileName"]
    r = await _req(cfg, "POST", "/invoices", content=xml.encode("utf-8"), headers={"Content-Type": "application/xml"})
    try:
        rid = _uuid(r.json())
    except ValueError:
        rid = None
    if not rid:
        raise SdiError("risposta dell'intermediario senza identificativo")
    return rid


def _note(n):
    msg = n.get("message")
    if isinstance(msg, dict):
        msg = msg.get("message") or msg.get("descrizione") or str(msg)
    t = str(n.get("type") or n.get("notification_type") or "").upper()[:3]
    return {"type": t, "message": str(msg or "")[:500], "at": n.get("created_at") or n.get("date") or "", "uuid": n.get("uuid") or ""}


async def notifications(cfg, rid: str) -> list:
    if cfg["provider"] == "aruba":
        d = _aruba_ok(await _req(cfg, "GET", "/services/invoice/out/getByFilename", params={"filename": rid, "includeFile": "false"}))
        out = []
        for x in d.get("invoices") or []:
            st = str(x.get("status") or "").strip()
            code = ARUBA_STATO.get(st.lower())
            if code:
                out.append({"type": code, "message": (x.get("statusDescription") or st)[:500], "at": d.get("lastUpdate") or "", "uuid": f"{rid}:{st}"})
        return out
    path = f"/invoices_notifications/{rid}" if cfg["provider"] == "openapi" else f"/invoices/{rid}/notifications"
    out = [_note(n) for n in _items((await _req(cfg, "GET", path)).json()) if isinstance(n, dict)]
    if not out and cfg["provider"] == "acube":
        marking = (await _req(cfg, "GET", f"/invoices/{rid}")).json().get("marking")
        if marking in ("invoice-error", "quarantena", "rejected"):
            out = [{"type": "NS", "message": f"Stato A-Cube: {marking}", "at": "", "uuid": f"{rid}:{marking}"}]
    return sorted(out, key=lambda n: n["at"])


async def received(cfg, piva: str) -> list:
    if cfg["provider"] == "aruba":
        start = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%dT00:00:00")
        rows = _aruba_ok(await _req(cfg, "GET", "/services/invoice/in/findByUsername",
                                    params={"username": cfg["email"], "page": 1, "size": 100, "startDate": start})).get("content") or []
        out = []
        for x in rows:
            fn = x.get("filename") if isinstance(x, dict) else None
            if not fn:
                continue
            f = x.get("file") or _aruba_ok(await _req(cfg, "GET", "/services/invoice/in/getByFilename", params={"filename": fn, "includeFile": "true"})).get("file")
            if f:
                out.append((fn, base64.b64decode(f)))
        return out
    if cfg["provider"] == "openapi":
        rows = _items((await _req(cfg, "GET", "/invoices", params={"type": 1, "page": 1})).json())
        dl = "/invoices_download/{}"
    else:
        rows = _items((await _req(cfg, "GET", "/invoices", params={"recipient.business_vat_number_code": piva, "itemsPerPage": 50})).json())
        dl = "/invoices/{}"
    out = []
    for x in rows:
        rid = x.get("uuid") if isinstance(x, dict) else None
        if rid:
            r = await _req(cfg, "GET", dl.format(rid), headers={"Accept": "application/xml"})
            out.append((rid, r.content))
    return out

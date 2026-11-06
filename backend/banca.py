import csv
import hashlib
import io
import re
import time
from datetime import date, datetime, timedelta

import httpx

OB_BASE = {"sandbox": "https://ob-sandbox.api.acubeapi.com", "production": "https://ob.api.acubeapi.com"}
LOGIN = "https://common.api.acubeapi.com/login"
CATEGORIE = ["Spese e commissioni bancarie", "Stipendi e contributi", "F24 altri tributi", "Giroconto tra conti", "Finanziamenti e mutui",
             "Prelievo / versamento contanti", "Altro"]
_tokens = {}


class BankError(Exception):
    pass


# ---------- parsing file ----------
def _num(s: str) -> float:
    s = (s or "").strip().replace("€", "").replace("EUR", "").replace(" ", "").replace("\u00a0", "")
    if not s:
        return 0.0
    neg = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    s = s.strip("-+()")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    v = float(s)
    return -v if neg else v


def _date(s: str):
    s = (s or "").strip()[:10]
    for f in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y", "%d%m%y", "%Y%m%d"):
        try:
            return datetime.strptime(s, f).date().isoformat()
        except ValueError:
            continue
    return None


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="ignore")


def parse_cbi(text: str) -> dict:
    movs, cur, saldo, saldo_data, iban = [], None, None, None, None
    for line in text.splitlines():
        ln = line.rstrip("\r\n").ljust(120)
        tipo = ln[1:3]
        if tipo == "61":
            bban = ln[51:74].strip()
            iban = iban or (f"IT??{bban}" if bban else None)
        elif tipo == "62":
            imp_s = ln[26:41]
            imp = _num(imp_s) if "," in imp_s else int(re.sub(r"\D", "", imp_s) or 0) / 100
            cur = {"data": _date(ln[19:25]), "valuta": _date(ln[13:19]), "importo": round(-imp if ln[25] == "D" else imp, 2),
                   "causale": ln[41:43].strip(), "riferimento": ln[61:77].strip(), "descrizione": ln[86:120].strip()}
            movs.append(cur)
        elif tipo == "63" and cur:
            cur["descrizione"] = f"{cur['descrizione']} {ln[13:120].strip()}".strip()
        elif tipo == "64":
            s = ln[20:35]
            v = _num(s) if "," in s else int(re.sub(r"\D", "", s) or 0) / 100
            saldo, saldo_data = round(-v if ln[19] == "D" else v, 2), _date(ln[13:19])
    if not movs and saldo is None:
        raise BankError("Il file non sembra un estratto CBI (record 61/62/64 non trovati)")
    return {"movimenti": [m for m in movs if m["data"]], "saldo": saldo, "saldo_data": saldo_data, "iban": iban}


_COLS = {
    "data": ("data contabile", "data operazione", "data registrazione", "data movimento", "data"),
    "valuta": ("data valuta", "valuta"),
    "importo": ("importo", "amount", "ammontare"),
    "dare": ("dare", "addebiti", "addebito", "uscite", "uscita", "importo addebito"),
    "avere": ("avere", "accrediti", "accredito", "entrate", "entrata", "importo accredito"),
    "descrizione": ("descrizione operazione", "descrizione", "causale descrizione", "dettagli", "dettaglio", "operazione", "causale", "note"),
}


def _map_header(row: list) -> dict:
    h = [c.strip().lower() for c in row]
    out = {}
    for key, names in _COLS.items():
        for n in names:
            idx = next((i for i, c in enumerate(h) if c == n and i not in out.values()), None)
            if idx is None:
                idx = next((i for i, c in enumerate(h) if n in c and i not in out.values() and not (key == "data" and "valuta" in c)), None)
            if idx is not None:
                out[key] = idx
                break
    desc = [i for i, c in enumerate(h) if any(k in c for k in ("descrizione", "causale", "dettagl", "beneficiario", "ordinante", "controparte")) and i not in (out.get("data"), out.get("valuta"))]
    out["desc_cols"] = desc or ([out["descrizione"]] if "descrizione" in out else [])
    return out


def parse_csv(text: str) -> dict:
    sample = text[:5000]
    delim = max([";", ",", "\t", "|"], key=lambda d: sample.count(d))
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    hi = next((i for i, r in enumerate(rows[:40]) if "data" in " ".join(r).lower() and len(r) >= 3), None)
    if hi is None:
        raise BankError("Intestazione del CSV non trovata: serve almeno una colonna Data e una Importo (o Dare/Avere)")
    m = _map_header(rows[hi])
    if "data" not in m or not ({"importo"} <= m.keys() or {"dare", "avere"} & m.keys()):
        raise BankError("Colonne non riconosciute: servono Data e Importo (oppure Dare/Avere)")
    movs = []
    for r in rows[hi + 1:]:
        if len(r) <= m["data"]:
            continue
        d = _date(r[m["data"]])
        if not d:
            continue
        get = lambda k: r[m[k]] if k in m and m[k] < len(r) else ""  # noqa: E731
        try:
            imp = _num(get("importo")) if "importo" in m else _num(get("avere")) - abs(_num(get("dare")))
        except ValueError:
            continue
        if not imp:
            continue
        desc = " ".join(r[i].strip() for i in m["desc_cols"] if i < len(r) and r[i].strip())
        movs.append({"data": d, "valuta": _date(get("valuta")) or d, "importo": round(imp, 2), "causale": "", "riferimento": "", "descrizione": desc[:500]})
    if not movs:
        raise BankError("Nessun movimento trovato nel CSV")
    return {"movimenti": movs, "saldo": None, "saldo_data": None, "iban": None}


def parse_file(raw: bytes, name: str) -> dict:
    text = _decode(raw)
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    if first[1:3] == "RH" or re.search(r"^ 6[12]", text, re.M):
        return parse_cbi(text)
    return parse_csv(text)


def ext_id(account_id: str, m: dict, k: int) -> str:
    return "file:" + hashlib.sha1(f"{account_id}|{m['data']}|{m['importo']:.2f}|{m['descrizione']}|{k}".encode()).hexdigest()[:24]


# ---------- A-Cube Open Banking ----------
async def _token(cfg) -> str:
    key = (cfg["email"], cfg["ambiente"])
    tok = _tokens.get(key)
    if tok and tok[1] > time.time() + 300:
        return tok[0]
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(LOGIN, json={"email": cfg["email"], "password": cfg["password"], "environment": cfg["ambiente"]})
    if r.status_code != 200:
        raise BankError(f"accesso A-Cube non riuscito ({r.status_code}): controlla email e password")
    _tokens[key] = (r.json()["token"], time.time() + 23 * 3600)
    return _tokens[key][0]


async def ob(cfg, method: str, path: str, ok=(200, 201, 202, 204), **kw):
    headers = {"Authorization": f"Bearer {await _token(cfg)}", "Accept": "application/ld+json"}
    try:
        async with httpx.AsyncClient(timeout=40) as c:
            r = await c.request(method, OB_BASE[cfg["ambiente"]] + path, headers=headers, **kw)
    except httpx.HTTPError as e:
        raise BankError(f"A-Cube non raggiungibile: {e.__class__.__name__}")
    if r.status_code == 401:
        _tokens.pop((cfg["email"], cfg["ambiente"]), None)
    if r.status_code not in ok:
        try:
            msg = r.json().get("hydra:description") or r.json().get("detail") or r.json().get("message") or r.text
        except ValueError:
            msg = r.text
        raise BankError(f"A-Cube {r.status_code}: {str(msg)[:300]}")
    return r.json() if r.content else {}


def members(d):
    if isinstance(d, list):
        return d
    return d.get("hydra:member") or d.get("member") or []


async def ensure_registry(cfg, fiscal: str, email: str, name: str):
    try:
        await ob(cfg, "GET", f"/business-registry/{fiscal}")
    except BankError:
        await ob(cfg, "POST", "/business-registry", json={"fiscalId": fiscal, "email": email, "businessName": name})
        try:
            await ob(cfg, "POST", f"/business-registry/{fiscal}/enable")
        except BankError:
            pass


async def connect_url(cfg, fiscal: str, redirect: str) -> str:
    d = await ob(cfg, "POST", f"/business-registry/{fiscal}/connect", json={"locale": "it", "redirectUrl": redirect})
    url = d.get("connectUrl")
    if not url:
        raise BankError("A-Cube non ha restituito il link di collegamento")
    return url


async def accounts(cfg, fiscal: str) -> list:
    return members(await ob(cfg, "GET", f"/business-registry/{fiscal}/accounts", params={"itemsPerPage": 100}))


async def transactions(cfg, fiscal: str, since: str) -> list:
    out, page = [], 1
    while page <= 50:
        d = await ob(cfg, "GET", f"/business-registry/{fiscal}/transactions", params={"madeOn[after]": since, "itemsPerPage": 100, "page": page})
        rows = members(d)
        out += rows
        if not rows or not (d.get("hydra:view") or {}).get("hydra:next"):
            break
        page += 1
    return out


def map_tx(t: dict) -> dict:
    extra = t.get("extra") or {}
    cp = t.get("counterpart") or extra.get("counterpart") or extra.get("counterparty") or extra.get("payee") or extra.get("payer") or ""
    if isinstance(cp, dict):
        cp = cp.get("name") or ""
    return {"data": (t.get("madeOn") or "")[:10], "valuta": (t.get("madeOn") or "")[:10], "importo": round(float(t.get("amount") or 0), 2),
            "descrizione": (t.get("description") or "")[:500], "controparte": str(cp)[:200], "causale": "", "riferimento": str(t.get("id") or ""),
            "account_uuid": t.get("accountUuid") or (t.get("account") or "").split("/")[-1], "pending": (t.get("status") or "").lower() == "pending"}


# ---------- abbinamento ----------
_STOP = {"srl", "spa", "snc", "sas", "s.r.l.", "s.p.a.", "di", "e", "la", "il", "de", "del", "della", "srls", "societa", "società"}


def _tokens_of(s: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]{3,}", (s or "").lower()) if w not in _STOP}


def score_doc(tx: dict, d: dict) -> int:
    text = f"{tx.get('descrizione', '')} {tx.get('controparte', '')}".lower()
    amount = abs(tx["importo"])
    s = 0
    if abs(amount - d["residuo"]) < 0.01:
        s += 55
    elif any(abs(amount - r["residuo"]) < 0.01 for r in d.get("rate") or [] if r["residuo"] > 0):
        s += 50
    elif amount < d["residuo"]:
        s += 10
    else:
        return 0
    num = str(d["numero_display"]).lower()
    base = num.split("/")[0].lstrip("0")
    if num in text or re.search(rf"(fatt|ft|fattura|n\.?|nr\.?|num)\s*\.?\s*0*{re.escape(base)}\b", text):
        s += 35
    name = _tokens_of(d["cliente"])
    if name and name & _tokens_of(text):
        s += 25
    if tx["data"] < d["data"]:
        s -= 40
    return max(min(s, 100), 0)


def candidates(tx: dict, attive: list, passive: list, corr: list, iva: list) -> list:
    out = []
    amount = abs(tx["importo"])
    if tx["importo"] > 0:
        for d in attive:
            sc = score_doc(tx, d)
            if sc >= 30:
                out.append({"tipo": "incasso", "ref_id": d["id"], "label": f"Fattura {d['numero_display']} · {d['cliente']}", "residuo": d["residuo"], "score": sc})
        t0 = date.fromisoformat(tx["data"])
        for c in corr:
            cd = date.fromisoformat(c["data"])
            if abs(amount - c["totale"]) < 0.01 and timedelta(0) <= t0 - cd <= timedelta(days=7):
                out.append({"tipo": "corrispettivi", "ref_id": c["data"], "label": f"Corrispettivi del {cd.strftime('%d/%m/%Y')}", "residuo": c["totale"], "score": 70})
    else:
        for d in passive:
            sc = score_doc(tx, d)
            if sc >= 30:
                out.append({"tipo": "pagamento", "ref_id": d["id"], "label": f"Fattura {d['numero_display']} · {d['cliente']}", "residuo": d["residuo"], "score": sc})
        f24 = bool(re.search(r"\bf\s?24\b|delega|agenzia entrate|tribut", tx.get("descrizione", "").lower()))
        for p in iva:
            if abs(amount - p["da_versare"]) < 0.01:
                out.append({"tipo": "iva", "ref_id": p["key"], "label": f"Versamento IVA {p['label']}", "residuo": p["da_versare"], "score": 90 if f24 else 60})
    return sorted(out, key=lambda x: -x["score"])[:8]


def safe_auto(c: list):
    if not c or c[0]["score"] < 80:
        return None
    if len(c) > 1 and c[1]["score"] >= 50:
        return None
    return c[0]

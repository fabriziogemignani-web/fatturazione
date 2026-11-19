import base64
import logging
import re
import uuid
from datetime import datetime, timezone
from html import escape
from typing import List, Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator

ROME = ZoneInfo("Europe/Rome")
log = logging.getLogger("comunicazioni")

TESTI = {
    "cortesia": ("Fattura {numero} del {data} - {azienda}",
                 "Gentile {cliente},\n\nin allegato la copia di cortesia della fattura n. {numero} del {data} di {totale}, trasmessa al Sistema di Interscambio.\n"
                 "Il documento fiscalmente valido è quello che ricevete tramite SDI.\n\nCordiali saluti\n{azienda}"),
    "promemoria": ("Promemoria scadenza pagamento - {azienda}",
                   "Gentile {cliente},\n\nvi ricordiamo che sono in scadenza i seguenti pagamenti:\n{elenco}\nTotale: {totale}\n{iban}\n"
                   "Se avete già provveduto, ignorate questo messaggio.\n\nCordiali saluti\n{azienda}"),
    "sollecito1": ("Sollecito di pagamento - {azienda}",
                   "Gentile {cliente},\n\ndalle nostre verifiche risultano non ancora saldati i seguenti pagamenti:\n{elenco}\nTotale scaduto: {totale}\n{iban}\n"
                   "Vi preghiamo di provvedere appena possibile. Se avete già pagato, ignorate questo messaggio.\n\nCordiali saluti\n{azienda}"),
    "sollecito2": ("Secondo sollecito di pagamento - {azienda}",
                   "Gentile {cliente},\n\nnonostante il nostro precedente sollecito risultano ancora insoluti i seguenti pagamenti:\n{elenco}\nTotale scaduto: {totale}\n{iban}\n"
                   "Vi chiediamo di saldare entro 7 giorni.\n\nCordiali saluti\n{azienda}"),
    "sollecito3": ("Diffida al pagamento - {azienda}",
                   "Spett.le {cliente},\n\ncon la presente vi diffidiamo formalmente a saldare entro 10 giorni i seguenti importi scaduti:\n{elenco}\nTotale scaduto: {totale}\n{iban}\n"
                   "In mancanza saremo costretti a tutelare i nostri diritti nelle sedi opportune.\n\nDistinti saluti\n{azienda}"),
}
DEFAULT = {"cortesia_auto": False, "promemoria_auto": False, "promemoria_giorni": 5, "solleciti_auto": False, "livelli": [7, 21, 45], "ora": 8,
           "testi": {k: {"oggetto": o, "corpo": c} for k, (o, c) in TESTI.items()}}
TIPI = {"cortesia": "Fattura di cortesia", "promemoria": "Promemoria scadenza", "sollecito": "Sollecito"}


def eur(v) -> str:
    return "€ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def itd(d: str) -> str:
    return "/".join(reversed(d[:10].split("-"))) if d else ""


def cfg_of(comp: dict) -> dict:
    c = {**DEFAULT, **(comp.get("comunicazioni") or {})}
    c["testi"] = {k: {**DEFAULT["testi"][k], **((c.get("testi") or {}).get(k) or {})} for k in TESTI}
    return c


def render(tpl: dict, vals: dict, elenco: str = "") -> tuple:
    ctx = {k: escape(str(v)) for k, v in vals.items()}
    body = escape(tpl["corpo"]).replace("\n", "<br>")
    subj = tpl["oggetto"]
    for k, v in vals.items():
        body = body.replace("{" + k + "}", ctx[k])
        subj = subj.replace("{" + k + "}", str(v))
    body = body.replace("{elenco}", elenco)
    return subj.replace("{elenco}", ""), f'<div style="font-family:Arial,sans-serif;font-size:14px;color:#0f172a;line-height:1.5">{body}</div>'


def _rata(r: dict) -> str:
    return f" rata {r['n']}" if r.get("di", 1) > 1 else ""


def tabella(rows: list, ritardo: bool) -> str:
    td = 'style="padding:6px 8px;border-bottom:1px solid #e2e8f0;font-size:13px"'
    head = "".join(f'<th align="left" style="padding:6px 8px;font-size:12px">{h}</th>' for h in (["Documento", "Scadenza"] + (["Ritardo"] if ritardo else []) + ["Importo"]))
    body = "".join(f"<tr><td {td}>{escape(r['numero_display'])}{_rata(r)}</td><td {td}>{itd(r['scadenza'])}</td>"
                   + (f"<td {td}>{r.get('giorni_ritardo', 0)} gg</td>" if ritardo else "") + f"<td {td} align=\"right\"><b>{eur(r['residuo'])}</b></td></tr>" for r in rows)
    return f'<table cellspacing="0" style="border-collapse:collapse;margin:8px 0;max-width:560px;width:100%"><tr style="background:#0f172a;color:#fff">{head}</tr>{body}</table>'


class TestoIn(BaseModel):
    oggetto: str = Field(min_length=1, max_length=200)
    corpo: str = Field(min_length=1, max_length=5000)


PIXEL = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")


class CortesiaIn(BaseModel):
    to: Optional[str] = Field(default=None, max_length=254)

    @field_validator("to")
    @classmethod
    def _to(cls, v):
        v = (v or "").strip()
        if v and not re.fullmatch(r"[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+", v):
            raise ValueError("Indirizzo email non valido")
        return v or None


class MassivaIn(BaseModel):
    ids: List[str] = Field(min_length=1, max_length=50)
    escludi_inviate: bool = True


class InvioElencoIn(BaseModel):
    party_ids: List[str] = Field(min_length=1, max_length=200)
    cosa: List[Literal["fatture", "promemoria", "scadenze"]] = Field(min_length=1, max_length=3)


class CfgIn(BaseModel):
    cortesia_auto: bool = False
    promemoria_auto: bool = False
    promemoria_giorni: int = Field(default=5, ge=1, le=30)
    solleciti_auto: bool = False
    livelli: List[int] = Field(default_factory=lambda: [7, 21, 45], min_length=3, max_length=3)
    ora: int = Field(default=8, ge=6, le=20)
    testi: dict

    @field_validator("livelli")
    @classmethod
    def _liv(cls, v):
        if not (0 < v[0] < v[1] < v[2] <= 365):
            raise ValueError("I giorni dei tre livelli devono essere crescenti (es. 7, 21, 45)")
        return v

    @field_validator("testi")
    @classmethod
    def _testi(cls, v):
        return {k: TestoIn(**(v.get(k) or {})).model_dump() for k in TESTI}


def build(db, tenant, tenant_accounting, deps) -> tuple:
    r = APIRouter(prefix="/api/comunicazioni")

    async def _log(cid, tipo, party, to, oggetto, importo, keys, esito, errore=None, livello=None, auto=True, docs=None, track=None):
        await db.com_log.insert_one({"id": str(uuid.uuid4()), "company_id": cid, "tipo": tipo, "livello": livello, "party_id": party.get("id"),
                                     "cliente": party.get("denominazione"), "to": to, "oggetto": oggetto, "importo": importo, "documenti": docs or [],
                                     "keys": keys if esito == "ok" else [], "esito": esito, "errore": errore, "auto": auto,
                                     "track": track if esito == "ok" else None, "aperta_il": None, "aperture": 0,
                                     "created_at": datetime.now(timezone.utc).isoformat()})

    async def _send(cid, comp, party, tipo, subj, html, importo, keys, livello=None, auto=True, attach=None, docs=None, to=None, track=None):
        to = (to or party.get("email") or party.get("pec") or "").strip()
        if "@" not in to:
            err = "Cliente senza email o PEC in anagrafica"
            await _log(cid, tipo, party, to, subj, importo, keys, "errore", err, livello, auto, docs)
            return err
        try:
            smtp = await deps["smtp"](cid)
            if track and deps["app_url"].startswith("https://"):
                html += f'<img src="{deps["app_url"]}/api/comunicazioni/t/{track}.gif" width="1" height="1" alt="" style="display:block;border:0">'
            else:
                track = None
            await deps["send"](smtp=smtp, to=to, subject=subj, html=html, reply_to=smtp.get("reply_to") or comp.get("email") or None, attachments=attach)
        except Exception as e:  # noqa: BLE001
            err = str(getattr(e, "detail", e))[:300]
            await _log(cid, tipo, party, to, subj, importo, keys, "errore", err, livello, auto, docs)
            return err
        await _log(cid, tipo, party, to, subj, importo, keys, "ok", None, livello, auto, docs, track)
        return True

    def _vals(comp, party, **kw):
        iban = comp.get("iban") or next((b.get("iban") for b in comp.get("banche") or [] if b.get("predefinita")), "")
        return {"cliente": party.get("denominazione", ""), "azienda": comp.get("denominazione", ""), "iban": f"Coordinate per il bonifico: IBAN {iban}" if iban else "", **kw}

    async def cortesia(comp: dict, inv: dict, auto: bool = True, to: Optional[str] = None) -> bool:
        cid = comp["id"]
        cfg = cfg_of(comp)
        key = f"C-{inv['id']}"
        if inv.get("autofattura"):
            return False
        if auto and (not cfg["cortesia_auto"] or "comunicazioni" in (comp.get("menu_off") or []) or await db.com_log.find_one({"company_id": cid, "keys": key}, {"_id": 1})):
            return False
        party = await db.parties.find_one({"id": inv.get("party_id"), "company_id": cid}, {"_id": 0}) or {**(inv.get("cliente") or {}), "id": inv.get("party_id")}
        subj, html = render(cfg["testi"]["cortesia"], _vals(comp, party, numero=inv["numero_display"], data=itd(inv["data"]), totale=eur(inv["totale"]), scadenza=itd(inv.get("scadenza") or "")))
        pdf = deps["pdf"](comp, inv["cliente"], inv)
        name = f"Fattura_{inv['numero_display'].replace('/', '-')}.pdf"
        return await _send(cid, comp, party, "cortesia", subj, html, inv["totale"], [key], auto=auto, docs=[inv["numero_display"]],
                           attach=[{"filename": name, "content": base64.b64encode(pdf).decode()}], to=to, track=uuid.uuid4().hex)

    async def _aperte(cid):
        docs, _, _, today = await deps["ledger"](cid)
        parties = {p["id"]: p for p in await db.parties.find({"company_id": cid, "tipo": {"$ne": "fornitore"}}, {"_id": 0}).to_list(20000)}
        by = {}
        for d in docs:
            for x in d["rate"]:
                if x["residuo"] > 0:
                    by.setdefault(d["party_id"], []).append({**x, "di": len(d["rate"]), "invoice_id": d["id"], "numero_display": d["numero_display"],
                                                             "cliente": d.get("cliente") if isinstance(d.get("cliente"), str) else (d.get("cliente") or {}).get("denominazione", "")})
        return by, parties, today

    def _livello(cfg, x):
        return max((i + 1 for i, g in enumerate(cfg["livelli"]) if x.get("giorni_ritardo", 0) >= g), default=0)

    async def _promemoria(cid, comp, cfg, party, rows, auto):
        tot = round(sum(x["residuo"] for x in rows), 2)
        subj, html = render(cfg["testi"]["promemoria"], _vals(comp, party, totale=eur(tot)), tabella(rows, False))
        return await _send(cid, comp, party, "promemoria", subj, html, tot, [f"P-{x['invoice_id']}-{x['n']}-{x['scadenza']}" for x in rows], auto=auto,
                           docs=sorted({x["numero_display"] for x in rows}))

    async def _sollecito(cid, comp, cfg, party, scad, liv, keys, auto):
        tot = round(sum(x["residuo"] for x in scad), 2)
        subj, html = render(cfg["testi"][f"sollecito{liv}"], _vals(comp, party, totale=eur(tot)), tabella(scad, True))
        return await _send(cid, comp, party, "sollecito", subj, html, tot, keys, livello=liv, auto=auto, docs=sorted({x["numero_display"] for x in scad}))

    async def run_company(comp: dict, auto: bool = True) -> dict:
        cid = comp["id"]
        cfg = cfg_of(comp)
        out = {"promemoria": 0, "solleciti": 0, "errori": 0}
        if not (cfg["promemoria_auto"] or cfg["solleciti_auto"]) and auto:
            return out
        by, parties, today = await _aperte(cid)
        oggi = datetime.now(ROME).date()
        sent = set(await db.com_log.distinct("keys", {"company_id": cid}))
        for pid, rows in by.items():
            party = parties.get(pid) or {"id": pid, "denominazione": rows[0].get("cliente", "")}
            if cfg["promemoria_auto"] or not auto:
                lim = oggi.toordinal() + cfg["promemoria_giorni"]
                due = [x for x in rows if not x["scaduta"] and datetime.fromisoformat(x["scadenza"]).toordinal() <= lim and f"P-{x['invoice_id']}-{x['n']}-{x['scadenza']}" not in sent]
                if due:
                    ok = await _promemoria(cid, comp, cfg, party, due, auto)
                    out["promemoria" if ok is True else "errori"] += 1
            if cfg["solleciti_auto"] or not auto:
                scad = [x for x in rows if x["scaduta"]]
                todo, liv = [], 0
                for x in scad:
                    lv = _livello(cfg, x)
                    if lv and f"S{lv}-{x['invoice_id']}-{x['n']}" not in sent:
                        todo.append((x, lv))
                        liv = max(liv, lv)
                if todo:
                    keys = [f"S{k}-{x['invoice_id']}-{x['n']}" for x, lv in todo for k in range(1, lv + 1)]
                    ok = await _sollecito(cid, comp, cfg, party, scad, liv, keys, auto)
                    out["solleciti" if ok is True else "errori"] += 1
        await db.companies.update_one({"id": cid}, {"$set": {"com_last_run": {"at": datetime.now(timezone.utc).isoformat(), "data": today, "auto": auto, **out}}})
        return out

    async def aggiorna_elenco(comp: dict, auto: bool = True) -> dict:
        cid, cfg = comp["id"], cfg_of(comp)
        by, parties, _ = await _aperte(cid)
        oggi = datetime.now(ROME).date().toordinal()
        ultimi = {u["_id"]: u for u in await db.com_log.aggregate([
            {"$match": {"company_id": cid, "esito": "ok"}}, {"$sort": {"created_at": 1}},
            {"$group": {"_id": "$party_id", "at": {"$last": "$created_at"}, "tipo": {"$last": "$tipo"}, "livello": {"$last": "$livello"}}}]).to_list(20000)}
        at = datetime.now(timezone.utc).isoformat()
        righe = []
        for pid, rows in by.items():
            scad = [x for x in rows if x["scaduta"]]
            vicine = [x for x in rows if not x["scaduta"] and datetime.fromisoformat(x["scadenza"]).toordinal() <= oggi + cfg["promemoria_giorni"]]
            if not (scad or vicine):
                continue
            p = parties.get(pid) or {}
            u = ultimi.get(pid)
            righe.append({"company_id": cid, "party_id": pid, "cliente": p.get("denominazione") or rows[0]["cliente"], "email": p.get("email") or p.get("pec") or "",
                          "scaduto": round(sum(x["residuo"] for x in scad), 2), "n_scadute": len(scad), "max_ritardo": max((x.get("giorni_ritardo", 0) for x in scad), default=0),
                          "livello": max((_livello(cfg, x) for x in scad), default=0), "in_scadenza": round(sum(x["residuo"] for x in vicine), 2), "n_in_scadenza": len(vicine),
                          "prossima_scadenza": min((x["scadenza"] for x in vicine), default=None), "fatture_aperte": len({x["invoice_id"] for x in rows}),
                          "ultimo_invio": {"at": u["at"], "tipo": u["tipo"], "livello": u.get("livello")} if u else None, "aggiornato_il": at, "auto": auto})
        await db.com_elenco.delete_many({"company_id": cid})
        if righe:
            await db.com_elenco.insert_many(righe)
        stato = {"at": at, "auto": auto, "clienti": len(righe)}
        await db.companies.update_one({"id": cid}, {"$set": {"com_elenco_run": stato}})
        return stato

    async def loop_tick():
        now = datetime.now(ROME)
        today = now.date().isoformat()
        for comp in await db.companies.find({"com_elenco_day": {"$ne": today}, "moduli.fatture_attive": {"$ne": False}}, deps["proj"]).to_list(500):
            if now.hour < cfg_of(comp)["ora"]:
                continue
            claimed = await db.companies.update_one({"id": comp["id"], "com_elenco_day": {"$ne": today}}, {"$set": {"com_elenco_day": today}})
            if claimed.modified_count:
                try:
                    await aggiorna_elenco(comp)
                except Exception:  # noqa: BLE001
                    log.exception("Aggiornamento elenco clienti da sollecitare fallito")
        q = {"$or": [{"comunicazioni.promemoria_auto": True}, {"comunicazioni.solleciti_auto": True}], "com_last_day": {"$ne": today}}
        for comp in await db.companies.find(q, deps["proj"]).to_list(500):
            if now.hour < cfg_of(comp)["ora"] or (comp.get("moduli") or {}).get("fatture_attive") is False or "comunicazioni" in (comp.get("menu_off") or []):
                continue
            claimed = await db.companies.update_one({"id": comp["id"], "com_last_day": {"$ne": today}}, {"$set": {"com_last_day": today}})
            if claimed.modified_count:
                try:
                    await run_company(comp)
                except Exception:  # noqa: BLE001
                    log.exception("Invio comunicazioni pianificate fallito")

    @r.get("/config")
    async def get_cfg(t: dict = Depends(tenant)):
        return {"config": cfg_of(t["company"]), "segnaposto": ["{cliente}", "{azienda}", "{numero}", "{data}", "{totale}", "{scadenza}", "{elenco}", "{iban}"],
                "ultimo": t["company"].get("com_last_run")}

    @r.put("/config")
    async def put_cfg(body: CfgIn, t: dict = Depends(tenant)):
        testi, acc = deps["diritti"](t["user"])["testi_comunicazioni"], t["user"].get("role") in ("admin", "contabile")
        if not (testi or acc):
            raise HTTPException(403, "Operazione riservata ad Admin o Contabile")
        cur, new = cfg_of(t["company"]), body.model_dump()
        if not acc:
            new = {**cur, "testi": new["testi"]}
        if not testi:
            new["testi"] = cur["testi"]
        await db.companies.update_one({"id": t["cid"]}, {"$set": {"comunicazioni": new}})
        return {"config": new}

    @r.get("/log")
    async def get_log(limit: int = 50, tipo: str = "", t: dict = Depends(tenant)):
        f = {"company_id": t["cid"], **({"tipo": tipo} if tipo in TIPI else {})}
        rows = await db.com_log.find(f, {"_id": 0, "keys": 0}).sort("created_at", -1).to_list(min(max(limit, 1), 500))
        since = datetime.fromordinal(datetime.now(timezone.utc).toordinal() - 7).isoformat()
        stats = {k: await db.com_log.count_documents({"company_id": t["cid"], "tipo": k, "esito": "ok", "created_at": {"$gte": since}}) for k in TIPI}
        errori = await db.com_log.count_documents({"company_id": t["cid"], "esito": "errore", "created_at": {"$gte": since}})
        return {"log": rows, "settimana": stats, "errori": errori, "tipi": TIPI, "ultimo": t["company"].get("com_last_run")}

    @r.get("/elenco")
    async def elenco(t: dict = Depends(tenant)):
        stato = t["company"].get("com_elenco_run") or await aggiorna_elenco(t["company"], auto=False)
        righe = await db.com_elenco.find({"company_id": t["cid"]}, {"_id": 0, "company_id": 0}).sort([("scaduto", -1), ("in_scadenza", -1)]).to_list(5000)
        return {"righe": righe, "stato": stato}

    @r.post("/elenco/aggiorna")
    async def elenco_aggiorna(t: dict = Depends(tenant_accounting)):
        return await aggiorna_elenco(t["company"], auto=False)

    @r.post("/elenco/invia")
    async def elenco_invia(body: InvioElencoIn, t: dict = Depends(tenant_accounting)):
        cid, comp = t["cid"], t["company"]
        cfg = cfg_of(comp)
        by, parties, _ = await _aperte(cid)
        out = {"fatture": 0, "promemoria": 0, "solleciti": 0, "errori": [], "saltati": []}
        for pid in dict.fromkeys(body.party_ids):
            rows = by.get(pid) or []
            party = parties.get(pid) or {"id": pid, "denominazione": rows[0]["cliente"] if rows else pid}
            nome = party.get("denominazione")
            if not rows:
                out["saltati"].append({"cliente": nome, "motivo": "nessuna rata aperta"})
                continue
            if "fatture" in body.cosa:
                invs = await db.invoices.find({"company_id": cid, "id": {"$in": list({x["invoice_id"] for x in rows})}, "status": {"$nin": ["bozza", "scartata"]}},
                                              {"_id": 0}).sort("data", 1).to_list(30)
                for inv in invs:
                    res = await cortesia(comp, inv, auto=False)
                    if res is True:
                        out["fatture"] += 1
                    else:
                        out["errori"].append({"cliente": nome, "cosa": f"fattura {inv['numero_display']}", "errore": res or "invio non riuscito"})
                if not invs:
                    out["saltati"].append({"cliente": nome, "motivo": "nessuna fattura elettronica aperta da inviare"})
            if "promemoria" in body.cosa:
                due = [x for x in rows if not x["scaduta"]]
                res = await _promemoria(cid, comp, cfg, party, due, False) if due else "nessuna rata ancora da scadere"
                if res is True:
                    out["promemoria"] += 1
                else:
                    out["errori" if due else "saltati"].append({"cliente": nome, "cosa": "promemoria", "errore": res, "motivo": res})
            if "scadenze" in body.cosa:
                scad = [x for x in rows if x["scaduta"]]
                if scad:
                    liv = max(1, max(_livello(cfg, x) for x in scad))
                    res = await _sollecito(cid, comp, cfg, party, scad, liv, [f"S{k}-{x['invoice_id']}-{x['n']}" for x in scad for k in range(1, liv + 1)], False)
                    if res is True:
                        out["solleciti"] += 1
                    else:
                        out["errori"].append({"cliente": nome, "cosa": "sollecito", "errore": res})
                else:
                    out["saltati"].append({"cliente": nome, "motivo": "nessuna rata scaduta"})
        at = datetime.now(timezone.utc).isoformat()
        for pid in body.party_ids:
            u = await db.com_log.find_one({"company_id": cid, "party_id": pid, "esito": "ok"}, {"_id": 0, "created_at": 1, "tipo": 1, "livello": 1}, sort=[("created_at", -1)])
            if u and u["created_at"] <= at:
                await db.com_elenco.update_one({"company_id": cid, "party_id": pid}, {"$set": {"ultimo_invio": {"at": u["created_at"], "tipo": u["tipo"], "livello": u.get("livello")}}})
        return out

    @r.post("/esegui")
    async def esegui(t: dict = Depends(tenant_accounting)):
        return await run_company(t["company"], auto=False)

    @r.post("/cortesia/{iid}")
    async def invia_cortesia(iid: str, body: Optional[CortesiaIn] = None, t: dict = Depends(tenant_accounting)):
        inv = await db.invoices.find_one({"id": iid, "company_id": t["cid"]}, {"_id": 0})
        if not inv:
            raise HTTPException(404, "Fattura non trovata")
        if inv.get("status") in ("bozza", "scartata"):
            raise HTTPException(400, "La fattura non è stata trasmessa allo SDI")
        res = await cortesia(t["company"], inv, auto=False, to=body.to if body else None)
        if res is not True:
            raise HTTPException(400, res or "Invio non riuscito")
        return {"ok": True}

    @r.get("/cortesia-inviate")
    async def cortesia_inviate(t: dict = Depends(tenant)):
        out = {}
        async for x in db.com_log.find({"company_id": t["cid"], "tipo": "cortesia", "esito": "ok"},
                                       {"_id": 0, "keys": 1, "to": 1, "created_at": 1, "aperta_il": 1, "aperture": 1, "track": 1}).sort("created_at", 1):
            for k in x.get("keys") or []:
                if k.startswith("C-"):
                    prev = out.get(k[2:]) or {}
                    out[k[2:]] = {"inviata_il": x["created_at"], "to": x.get("to"), "tracciata": bool(x.get("track")) or prev.get("tracciata", False),
                                  "aperta_il": x.get("aperta_il") or prev.get("aperta_il"), "aperture": (x.get("aperture") or 0) + prev.get("aperture", 0)}
        return out

    @r.get("/t/{token}.gif", include_in_schema=False)
    async def pixel(token: str):
        if re.fullmatch(r"[0-9a-f]{32}", token):
            ts = datetime.now(timezone.utc).isoformat()
            await db.com_log.update_one({"track": token}, {"$inc": {"aperture": 1}, "$set": {"ultima_apertura": ts}})
            await db.com_log.update_one({"track": token, "aperta_il": None}, {"$set": {"aperta_il": ts}})
        return Response(PIXEL, media_type="image/gif", headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache"})

    @r.post("/cortesia-massiva")
    async def cortesia_massiva(body: MassivaIn, t: dict = Depends(tenant_accounting)):
        invs = await db.invoices.find({"id": {"$in": body.ids}, "company_id": t["cid"]}, {"_id": 0}).to_list(len(body.ids))
        gia = set(await db.com_log.distinct("keys", {"company_id": t["cid"], "tipo": "cortesia", "esito": "ok"})) if body.escludi_inviate else set()
        out = {"inviate": 0, "saltate": [], "errori": []}
        for inv in sorted(invs, key=lambda x: (x["data"], x["numero_display"])):
            if inv.get("status") in ("bozza", "scartata"):
                out["saltate"].append({"numero": inv["numero_display"], "motivo": "non trasmessa allo SDI"})
            elif f"C-{inv['id']}" in gia:
                out["saltate"].append({"numero": inv["numero_display"], "motivo": "già inviata"})
            else:
                res = await cortesia(t["company"], inv, auto=False)
                if res is True:
                    out["inviate"] += 1
                else:
                    out["errori"].append({"numero": inv["numero_display"], "cliente": (inv.get("cliente") or {}).get("denominazione"), "errore": res})
        return out

    return r, cortesia, loop_tick

import re
import uuid
import logging
from datetime import datetime, timezone, date
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from pymongo import ReturnDocument
from pymongo.errors import BulkWriteError, DuplicateKeyError

from contabilita_dati import PIANO, CAUSALI, CODICI_IVA, CODICI_IVA_DETR, PARAMETRI, RUOLI, TIPI, tipo_conto
from banca import CATEGORIE
import stampe_fiscali as stampe_mod
import integrita

log = logging.getLogger("contabilita")
AUTO_STATI = ("consegnata", "mancata_consegna")
HOOKS: dict = {}
ORIGINI = {"manuale": "Manuale", "vendita": "Vendite", "acquisto": "Acquisti", "banca": "Banca", "liquidazione": "Liquidazione IVA", "prorata": "Pro rata IVA", "pagamenti": "Pagamenti fornitori", "bolli": "Versamento bolli", "ritenute": "Versamento ritenute",
           "chiusura": "Chiusura esercizio", "apertura": "Apertura esercizio", "ratei": "Ratei e risconti", "pagamento": "Pagamenti e incassi", "carta": "Addebito carte"}
_seeded = set()


def _now():
    return datetime.now(timezone.utc).isoformat()


def r2(x) -> float:
    return round(float(x or 0) + 1e-9, 2)


def attiva(comp: dict) -> bool:
    m = (comp or {}).get("moduli") or {}
    return m.get("fatturazione", True) is not False and m.get("contabilita", True) is not False


def params_of(comp: dict) -> dict:
    p = {**PARAMETRI, **((comp or {}).get("contabilita") or {})}
    p["categorie"] = {**PARAMETRI["categorie"], **(p.get("categorie") or {})}
    return p


async def ensure_seed(db, cid: str):
    if cid in _seeded:
        return
    for coll, docs in (
        (db.coa_accounts, [{"codice": c, "descrizione": d, "livello": c.count(".") + 1, "tipo": tipo_conto(c)} for c, d in PIANO]),
        (db.coa_causali, [{"codice": c, "descrizione": d, "registro": r, "conto_dare": "", "conto_avere": ""} for c, d, r in CAUSALI]),
        (db.coa_iva, [{"codice": c, "descrizione": d, "aliquota": a, "natura": n, "reverse_charge": rc, "detraibilita": 100.0} for c, d, a, n, rc in CODICI_IVA]),
    ):
        if not await coll.find_one({"company_id": cid}, {"_id": 1}):
            try:
                await coll.insert_many([{"id": str(uuid.uuid4()), "company_id": cid, **d, "sistema": True, "created_at": _now()} for d in docs], ordered=False)
            except BulkWriteError:
                pass
    extra = [(db.coa_iva, c, {"descrizione": d, "aliquota": a, "natura": None, "reverse_charge": False, "detraibilita": det}) for c, d, a, det in CODICI_IVA_DETR]
    extra.append((db.coa_accounts, "30.14.008", {"descrizione": "IVA indetraibile", "livello": 3, "tipo": tipo_conto("30.14.008")}))
    for coll, c, d in extra:
        try:
            await coll.update_one({"company_id": cid, "codice": c}, {"$setOnInsert": {"id": str(uuid.uuid4()), **d, "sistema": True, "created_at": _now()}}, upsert=True)
        except DuplicateKeyError:
            pass
    await db.companies.update_one({"id": cid, "contabilita": {"$exists": False}}, {"$set": {"contabilita": PARAMETRI}})
    _seeded.add(cid)


async def codice_fornitore(db, cid: str, sup: dict, riep: list):
    cod = await db.coa_iva.find_one({"company_id": cid, "codice": sup.get("codice_iva")}, {"_id": 0}) if (sup or {}).get("codice_iva") else None
    if cod and cod.get("detraibilita") is not None:
        for x in riep:
            if x.get("aliquota") and float(cod.get("aliquota") or 0) == x["aliquota"] and x.get("detraibilita") is None:
                x |= {"codice_iva": cod["codice"], "detraibilita": float(cod["detraibilita"])}


def pct_riga(doc: dict, r: dict) -> float:
    v = (r or {}).get("detraibilita")
    return float(v) if v is not None else float(doc.get("detraibilita_iva") if doc.get("detraibilita_iva") is not None else 100)


async def _company(db, cid: str) -> dict:
    return await db.companies.find_one({"id": cid}, {"_id": 0, "id": 1, "moduli": 1, "contabilita": 1, "coge_chiusi": 1, "pro_rata": 1}) or {}


async def anni_chiusi(db, cid: str) -> list:
    return sorted((await _company(db, cid)).get("coge_chiusi") or [])


async def check_aperto(db, cid: str, anno: int):
    if anno in await anni_chiusi(db, cid):
        raise HTTPException(400, f"L'esercizio {anno} è chiuso: per modificarlo annulla prima la chiusura")


def _norm(righe: list) -> list:
    out = []
    for r in righe:
        v = r2(r2(r.get("dare")) - r2(r.get("avere")))
        if not v:
            continue
        out.append({"conto": r["conto"], "dare": max(v, 0.0), "avere": max(-v, 0.0), "party_id": r.get("party_id"), "party_nome": r.get("party_nome"),
                    "codice_iva": r.get("codice_iva") or "", "note": r.get("note") or ""})
    return out


async def _insert(db, cid: str, p: dict, data: str, causale: str, descrizione: str, righe: list, origine: str,
                  ref_id: Optional[str] = None, extra: Optional[dict] = None, by: str = "Automatico") -> Optional[dict]:
    righe = _norm(righe)
    diff = r2(sum(r["dare"] for r in righe) - sum(r["avere"] for r in righe))
    if diff and abs(diff) <= 0.05 and origine != "manuale":
        righe += _norm([{"conto": p["arr_attivi"], "avere": diff} if diff > 0 else {"conto": p["arr_passivi"], "dare": -diff}])
    elif diff:
        raise ValueError(f"Registrazione non quadrata: dare e avere differiscono di {diff:.2f} €")
    if len(righe) < 2:
        raise ValueError("La registrazione deve avere almeno due righe con importo")
    accs = {a["codice"]: a for a in await db.coa_accounts.find({"company_id": cid, "codice": {"$in": list({r["conto"] for r in righe})}}, {"_id": 0}).to_list(500)}
    for r in righe:
        a = accs.get(r["conto"])
        if not a or a["livello"] != 3:
            raise ValueError(f"Conto {r['conto']} inesistente o non è un sottoconto: controlla i parametri contabili")
        r["conto_descrizione"] = a["descrizione"]
    caus = await db.coa_causali.find_one({"company_id": cid, "codice": causale}, {"_id": 0, "descrizione": 1})
    await stampe_mod.check_giornale(db, cid, data)
    anno = int(data[:4])
    if origine not in ("chiusura", "apertura") and anno in await anni_chiusi(db, cid):
        raise ValueError(f"L'esercizio {anno} è chiuso: annulla la chiusura per registrare")
    cnt = await db.counters.find_one_and_update({"key": f"coge_{cid}_{anno}"}, {"$inc": {"v": 1}}, upsert=True, return_document=ReturnDocument.AFTER)
    doc = {"id": str(uuid.uuid4()), "company_id": cid, "anno": anno, "numero": cnt["v"], "data": data, "causale": causale,
           "causale_descrizione": caus["descrizione"] if caus else causale, "descrizione": descrizione[:200], "origine": origine, "ref_id": ref_id,
           "righe": righe, "totale": r2(sum(r["dare"] for r in righe)), **(extra or {}), "created_by": by, "created_at": _now()}
    try:
        await db.coa_entries.insert_one(dict(doc))
    except DuplicateKeyError:
        return None
    return doc


async def _ready(db, cid: str, origine: str, ref_id: str):
    comp = await _company(db, cid)
    if not attiva(comp):
        return None
    await ensure_seed(db, cid)
    if await db.coa_entries.find_one({"company_id": cid, "origine": origine, "ref_id": ref_id}, {"_id": 1}):
        return None
    return params_of(await _company(db, cid))


async def registra_vendita(db, inv: dict) -> Optional[dict]:
    if inv.get("status") not in AUTO_STATI or inv.get("autofattura"):
        return None
    cid = inv["company_id"]
    p = await _ready(db, cid, "vendita", inv["id"])
    if not p:
        return None
    s = -1 if inv.get("tipo_documento") == "TD04" else 1
    cli = inv.get("cliente") or {}
    arts = {}
    if p["contropartita_vendite"] == "articolo":
        ids = [ln.get("article_id") for ln in inv["lines"] if ln.get("article_id")]
        arts = {a["id"]: a.get("conto_ricavo") for a in await db.articles.find({"company_id": cid, "id": {"$in": ids}}, {"_id": 0, "id": 1, "conto_ricavo": 1}).to_list(1000)}
    ricavi = {}
    for ln in inv["lines"]:
        c = "30.14.002" if ln.get("bollo") else arts.get(ln.get("article_id")) or p["ricavi"]
        ricavi[c] = ricavi.get(c, 0) + (ln.get("prezzo_totale") or 0)
    if inv.get("cassa_importo"):
        ricavi[p["ricavi_cassa"]] = ricavi.get(p["ricavi_cassa"], 0) + inv["cassa_importo"]
    split = inv.get("iva_split") or 0
    party = {"party_id": inv.get("party_id"), "party_nome": cli.get("denominazione")}
    righe = [{"conto": p["clienti"], "dare": s * r2(inv["netto"]), **party}, {"conto": p["ritenute_subite"], "dare": s * r2(inv.get("ritenuta_importo"))}]
    righe += [{"conto": c, "avere": s * r2(v)} for c, v in ricavi.items()]
    righe.append({"conto": p["iva_vendite"], "avere": s * r2((inv.get("iva") or 0) - split)})
    nc = s < 0
    iva = [{"aliquota": r["aliquota"], "natura": r.get("natura"), "imponibile": s * r2(r["imponibile"]), "imposta": s * r2(r["imposta"])} for r in inv.get("riepilogo") or []]
    return await _insert(db, cid, p, inv["data"], "NV" if nc else "FV",
                         f"{'Nota di credito' if nc else 'Fattura'} n. {inv['numero_display']} a {cli.get('denominazione') or ''}", righe, "vendita", inv["id"],
                         {"documento": inv["numero_display"], "data_documento": inv["data"], "iva": iva, "party_id": inv.get("party_id")})


async def registra_acquisto(db, doc: dict) -> Optional[dict]:
    cid = doc["company_id"]
    p = await _ready(db, cid, "acquisto", doc["id"])
    if not p:
        return None
    caus, descr, righe, data, extra = await acquisto_righe(db, doc, p)
    if (doc.get("ai_analisi") or {}).get("dubbia") and not (doc.get("ai_analisi") or {}).get("rivista"):
        extra = {**(extra or {}), "ai_dubbia": True}
    return await _insert(db, cid, p, data, caus, descr, righe, "acquisto", doc["id"], extra)


async def acquisto_righe(db, doc: dict, p: dict):
    cid = doc["company_id"]
    s = -1 if doc.get("tipo_documento") == "TD04" else 1
    costo = p["costi"]
    forn = await db.parties.find_one({"id": doc.get("party_id"), "company_id": cid}, {"_id": 0, "conto_costo": 1, "denominazione": 1}) or {}
    if p["contropartita_acquisti"] == "fornitore" and forn.get("conto_costo"):
        costo = forn["conto_costo"]
    if doc.get("ai_conto"):
        costo = doc["ai_conto"]
    riep = doc.get("riepilogo") or []
    rc = r2(sum(r2((r.get("imponibile") or 0) * float(p["aliquota_rc"]) / 100) for r in riep if (r.get("natura") or "").startswith("N6") and not r.get("imposta")))
    if doc.get("reverse_charge"):
        rc = r2(sum(r.get("imposta") or 0 for r in doc["reverse_charge"]))
    iva, tot, rit = r2(doc.get("iva")), r2(doc.get("totale")), r2(doc.get("ritenuta_importo"))
    split = iva if doc.get("split_payment") else 0
    iva_det = r2(iva - sum((r.get("imposta") or 0) * (100 - pct_riga(doc, r)) / 100 for r in riep))
    if doc.get("reverse_charge"):
        rc_det = r2(rc - sum((x.get("imposta") or 0) * (100 - pct_riga(doc, riep[x["idx"]] if x.get("idx") is not None and x["idx"] < len(riep) else {})) / 100 for x in doc["reverse_charge"]))
    else:
        rc_det = r2(rc * pct_riga(doc, {}) / 100)
    ind = r2(iva - iva_det + rc - rc_det)
    nome = forn.get("denominazione") or (doc.get("fornitore") or {}).get("denominazione") or ""
    party = {"party_id": doc.get("party_id"), "party_nome": nome}
    righe = [{"conto": costo, "dare": s * r2(tot - iva_det + rc - rc_det)}, {"conto": p["iva_acquisti"], "dare": s * r2(iva_det + rc_det)},
             {"conto": p["iva_vendite"], "avere": s * rc}, {"conto": p["iva_split"], "avere": s * split},
             {"conto": p["fornitori"], "avere": s * r2(tot - rit - split), **party}, {"conto": p["ritenute_operate"], "avere": s * rit}]
    if ind and p.get("iva_indetraibile") and p["iva_indetraibile"] != costo:
        righe[0]["dare"] = r2(righe[0]["dare"] - s * ind)
        righe.insert(1, {"conto": p["iva_indetraibile"], "dare": s * ind})
    rc_all = doc.get("righe_costo") or []
    rcost = [{**x, "conto": x.get("conto") or costo} for x in rc_all] if any(x.get("conto") for x in rc_all) else []
    base = r2(sum(x["imponibile"] for x in rcost))
    if rcost and base and len({x["conto"] for x in rcost} | {costo}) > 1:
        totc = righe[0]["dare"]
        quote = [{"conto": x["conto"], "dare": r2(totc * x["imponibile"] / base)} for x in rcost]
        quote[-1]["dare"] = r2(totc - sum(q["dare"] for q in quote[:-1]))
        righe = quote + righe[1:]
    elif rcost:
        righe[0]["conto"] = rcost[0]["conto"]
    rimb = r2(sum(r.get("imponibile") or 0 for r in riep if (r.get("natura") or "").startswith("N1") and not r.get("imposta")))
    fuori = r2(tot - r2(sum(r.get("imponibile") or 0 for r in riep)) - iva)
    if doc.get("bollo") and fuori >= r2(doc["bollo"]) - 0.01:
        rimb = r2(rimb + r2(doc["bollo"]))
    if rimb and not rcost and abs(righe[0]["dare"]) >= rimb:
        righe[0]["dare"] = r2(righe[0]["dare"] - s * rimb)
        righe.insert(1, {"conto": p["spese_anticipate"], "dare": s * rimb})
    nc = s < 0
    data = (doc.get("ricevuta_at") or "")[:10] or doc["data"]
    data = doc.get("data_registrazione") or max(data, doc["data"])
    iva_rows = [{"aliquota": r.get("aliquota"), "natura": r.get("natura"), "imponibile": s * r2(r.get("imponibile")), "imposta": s * r2(r.get("imposta"))} for r in riep]
    return ("NA" if nc else "FA", f"{'Nota di credito' if nc else 'Fattura'} n. {doc.get('numero_display') or doc.get('numero')} da {nome}", righe, data,
            {"documento": doc.get("numero_display") or doc.get("numero"), "data_documento": doc["data"], "iva": iva_rows, "reverse_charge": rc, "iva_indetraibile": s * ind,
             "party_id": doc.get("party_id")})


async def registra_banca(db, cid: str, tx: dict, match: dict) -> Optional[dict]:
    if (match or {}).get("tipo") in (None, "ignorato"):
        return None
    p = await _ready(db, cid, "banca", tx["id"])
    if not p:
        return None
    v = r2(tx["importo"])
    sg = 1 if v > 0 else -1
    tipo = match["tipo"]
    righe = [{"conto": p["banca"], "dare": v}]
    if tipo in ("incasso", "pagamento"):
        conto = p["clienti" if tipo == "incasso" else "fornitori"]
        names = {}
        for r in match.get("righe") or []:
            pid = r.get("party_id")
            if pid and pid not in names:
                names[pid] = (await db.parties.find_one({"id": pid, "company_id": cid}, {"_id": 0, "denominazione": 1}) or {}).get("denominazione")
            righe.append({"conto": conto, "avere": sg * r2(r["importo"]), "party_id": pid, "party_nome": names.get(pid)})
        if r2(match.get("non_abbinato")):
            righe.append({"conto": p["transitorio"], "avere": sg * r2(match["non_abbinato"])})
        caus = "IN" if tipo == "incasso" else "PG"
    elif tipo == "corrispettivi":
        righe.append({"conto": p["cassa"], "avere": v})
        caus = "VC"
    elif tipo == "iva":
        righe.append({"conto": p["erario_iva"], "avere": v})
        caus = "VI"
    else:
        cat = match.get("categoria") or "Altro"
        righe.append({"conto": p["categorie"].get(cat) or p["transitorio"], "avere": v})
        caus = "MB"
    return await _insert(db, cid, p, tx["data"], caus, (match.get("label") or tx.get("descrizione") or "Movimento bancario")[:200], righe, "banca", tx["id"],
                         {"documento": "", "data_documento": tx["data"]})


async def conti_pagamento(db, cid: str) -> Optional[dict]:
    comp = await db.companies.find_one({"id": cid}, {"_id": 0, "moduli": 1, "banche": 1, "contabilita": 1}) or {}
    if not attiva(comp):
        return None
    await ensure_seed(db, cid)
    p = params_of(comp)
    banche = comp.get("banche") or []
    codes = {p["banca"], p["cassa"], p["carta"], *[b.get("conto_coge") for b in banche if b.get("conto_coge")]}
    accs = {a["codice"]: a["descrizione"] for a in await db.coa_accounts.find(
        {"company_id": cid, "livello": 3, "$or": [{"codice": {"$regex": r"^06\.0[13]\."}}, {"codice": {"$in": list(codes)}}]}, {"_id": 0, "codice": 1, "descrizione": 1}).to_list(500)}
    out, seen = [], set()

    def add(conto, label, tipo):
        if conto in accs and conto not in seen:
            seen.add(conto)
            out.append({"conto": conto, "label": label or accs[conto], "descrizione": accs[conto], "tipo": tipo})

    for b in sorted(banche, key=lambda b: not b.get("predefinita")):
        add(b.get("conto_coge") or (p["banca"] if b.get("predefinita") or len(banche) == 1 else ""), f"Banca {b['nome']}", "banca")
    add(p["banca"], None, "banca")
    for c in sorted(accs):
        if c.startswith("06.01."):
            add(c, None, "banca")
    add(p["carta"], None, "carta")
    for c in sorted(accs):
        if c.startswith("06.03."):
            add(c, None, "carta")
    add(p["cassa"], None, "cassa")
    first = {k: next((o["conto"] for o in out if o["tipo"] == k), "") for k in ("banca", "carta", "cassa")}
    default = {m: first["cassa"] if m == "contanti" else first["carta"] if m == "carta" else first["banca"]
               for m in ("bonifico", "contanti", "assegno", "carta", "riba", "rid", "altro")}
    return {"conti": out, "default": default}


async def registra_pagamento(db, cid: str, pay: dict, conto: str, passivo: bool, nome: str, by: str) -> Optional[dict]:
    p = await _ready(db, cid, "pagamento", pay["id"])
    if not p:
        return None
    party = {"party_id": pay["party_id"], "party_nome": nome}
    v, rit = r2(pay["importo"]), r2(pay.get("ritenuta_subita"))
    if passivo:
        righe = [{"conto": p["fornitori"], "dare": v, **party}, {"conto": conto, "avere": v}]
        caus, desc = "PG", f"Pagamento fatt. {pay['numero_display']} - {nome}"
    else:
        righe = [{"conto": conto, "dare": v}, {"conto": p["ritenute_subite"], "dare": rit}, {"conto": p["clienti"], "avere": r2(v + rit), **party}]
        caus, desc = "IN", f"Incasso fatt. {pay['numero_display']} - {nome}"
    return await _insert(db, cid, p, pay["data"], caus, desc, righe, "pagamento", pay["id"],
                         {"documento": pay["numero_display"], "data_documento": pay["data"], "party_id": pay["party_id"]}, by=by)


async def annulla(db, cid: str, origine: str, ref_id: str):
    await db.coa_entries.delete_many({"company_id": cid, "origine": origine, "ref_id": ref_id, "anno": {"$nin": await anni_chiusi(db, cid)}})


async def check_annullabile(db, cid: str, origine: str, ref_id: str):
    e = await db.coa_entries.find_one({"company_id": cid, "origine": origine, "ref_id": ref_id}, {"_id": 0, "anno": 1, "data": 1})
    if e:
        await check_aperto(db, cid, e["anno"])
        try:
            await stampe_mod.check_giornale(db, cid, e["data"])
        except ValueError as ex:
            raise HTTPException(400, str(ex))
    if origine == "acquisto" and HOOKS.get("iva_lock"):
        await HOOKS["iva_lock"](cid, ref_id)


async def safe(coro):
    try:
        return await coro
    except Exception as e:  # noqa: BLE001
        log.warning("Registrazione contabile automatica non eseguita: %s", e)
        return None


# ---------- Schemi ----------
CODE_RX = re.compile(r"^\d{2}(\.\d{2}(\.\d{3})?)?$")


def _d(v):
    try:
        return date.fromisoformat(v).isoformat()
    except (TypeError, ValueError):
        raise ValueError("Data non valida")


class ContoIn(BaseModel):
    codice: str
    descrizione: str = Field(min_length=1, max_length=120)
    tipo: Optional[Literal["attivita", "passivita", "costo", "ricavo", "chiusura"]] = None
    ratei_risconti: bool = False

    @field_validator("codice")
    @classmethod
    def _c(cls, v):
        v = (v or "").strip()
        if not CODE_RX.fullmatch(v):
            raise ValueError("Codice nel formato 00 (mastro), 00.00 (conto) o 00.00.000 (sottoconto)")
        return v


class ContoPatch(BaseModel):
    descrizione: str = Field(min_length=1, max_length=120)
    ratei_risconti: Optional[bool] = None


class RateoPN(BaseModel):
    competenza_dal: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    competenza_al: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    tipo: Literal["rateo", "risconto"]
    note: Optional[str] = Field(default="", max_length=300)


class CausaleIn(BaseModel):
    codice: str = Field(min_length=1, max_length=6, pattern=r"^[A-Z0-9]+$")
    descrizione: str = Field(min_length=1, max_length=80)
    registro: Literal["nessuno", "vendite", "acquisti"] = "nessuno"
    conto_dare: Optional[str] = ""
    conto_avere: Optional[str] = ""


class IvaIn(BaseModel):
    codice: str = Field(min_length=1, max_length=8, pattern=r"^[A-Z0-9.]+$")
    descrizione: str = Field(min_length=1, max_length=80)
    aliquota: float = Field(ge=0, le=100)
    natura: Optional[str] = None
    reverse_charge: bool = False
    detraibilita: float = Field(default=100, ge=0, le=100)


class ParamIn(BaseModel):
    conti: dict
    contropartita_vendite: Literal["unica", "articolo"] = "unica"
    contropartita_acquisti: Literal["unica", "fornitore"] = "unica"
    aliquota_rc: float = Field(default=22, ge=0, le=100)
    categorie: dict = Field(default_factory=dict)


class RigaIn(BaseModel):
    conto: str
    dare: float = Field(default=0, ge=0)
    avere: float = Field(default=0, ge=0)
    party_id: Optional[str] = None
    codice_iva: Optional[str] = ""
    note: Optional[str] = Field(default="", max_length=200)


class SaldoIn(BaseModel):
    invoice_id: str
    importo: float = Field(gt=0, le=10_000_000)
    passivo: bool = False


class RegIn(BaseModel):
    data: str
    causale: str
    descrizione: str = Field(min_length=1, max_length=200)
    righe: List[RigaIn] = Field(min_length=2, max_length=100)
    saldaconto: List[SaldoIn] = Field(default_factory=list, max_length=500)
    rateo: Optional["RateoPN"] = None

    @field_validator("data")
    @classmethod
    def _data(cls, v):
        return _d(v)


class RigeneraIn(BaseModel):
    ricrea: bool = False


class AddebitoIn(BaseModel):
    conto: str = Field(pattern=r"^\d{2}\.\d{2}\.\d{3}$")
    mese: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    data: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    banca: str = Field(pattern=r"^\d{2}\.\d{2}\.\d{3}$")

    @field_validator("data")
    @classmethod
    def _d(cls, v):
        try:
            return date.fromisoformat(v).isoformat()
        except ValueError:
            raise ValueError("Data non valida")


def build_router(db, tenant, tenant_accounting, sc=None) -> APIRouter:
    r = APIRouter(prefix="/api/contabilita")

    async def seeded(t: dict = Depends(tenant)) -> dict:
        await ensure_seed(db, t["cid"])
        return t

    async def seeded_acc(t: dict = Depends(tenant_accounting)) -> dict:
        await ensure_seed(db, t["cid"])
        return t

    async def accounts(cid: str) -> list:
        return await db.coa_accounts.find({"company_id": cid}, {"_id": 0}).sort("codice", 1).to_list(5000)

    async def leaf(cid: str, codice: str, label: str) -> dict:
        a = await db.coa_accounts.find_one({"company_id": cid, "codice": codice}, {"_id": 0})
        if not a or a["livello"] != 3:
            raise HTTPException(400, f"{label}: scegli un sottoconto esistente (formato 00.00.000)")
        return a

    # --- Piano dei conti
    @r.get("/conti")
    async def list_conti(t: dict = Depends(seeded)):
        rows = await accounts(t["cid"])
        used = set(await db.coa_entries.distinct("righe.conto", {"company_id": t["cid"]}))
        for a in rows:
            a["movimentato"] = a["codice"] in used
        return {"conti": rows, "tipi": TIPI}

    @r.post("/conti")
    async def add_conto(body: ContoIn, t: dict = Depends(seeded)):
        cid, c = t["cid"], body.codice
        if await db.coa_accounts.find_one({"company_id": cid, "codice": c}, {"_id": 1}):
            raise HTTPException(400, f"Il codice {c} esiste già")
        lv = c.count(".") + 1
        parent = None
        if lv > 1:
            parent = await db.coa_accounts.find_one({"company_id": cid, "codice": c.rsplit(".", 1)[0]}, {"_id": 0})
            if not parent:
                raise HTTPException(400, f"Crea prima il {'mastro' if lv == 2 else 'conto'} {c.rsplit('.', 1)[0]}")
        tipo = parent["tipo"] if parent else (body.tipo or tipo_conto(c))
        doc = {"id": str(uuid.uuid4()), "company_id": cid, "codice": c, "descrizione": body.descrizione.strip(), "livello": lv, "tipo": tipo,
               "ratei_risconti": bool(body.ratei_risconti), "sistema": False, "created_at": _now()}
        await db.coa_accounts.insert_one(dict(doc))
        return doc

    @r.put("/conti/{aid}")
    async def upd_conto(aid: str, body: ContoPatch, t: dict = Depends(seeded)):
        a = await db.coa_accounts.find_one_and_update({"id": aid, "company_id": t["cid"]}, {"$set": {"descrizione": body.descrizione.strip(), **({"ratei_risconti": body.ratei_risconti} if body.ratei_risconti is not None else {})}},
                                                       return_document=ReturnDocument.AFTER, projection={"_id": 0})
        if not a:
            raise HTTPException(404, "Conto non trovato")
        return a

    @r.delete("/conti/{aid}")
    async def del_conto(aid: str, t: dict = Depends(seeded)):
        cid = t["cid"]
        a = await db.coa_accounts.find_one({"id": aid, "company_id": cid}, {"_id": 0})
        if not a:
            raise HTTPException(404, "Conto non trovato")
        c = a["codice"]
        if await db.coa_accounts.find_one({"company_id": cid, "codice": {"$regex": f"^{re.escape(c)}\\."}}, {"_id": 1}):
            raise HTTPException(400, "Il conto ha dei sottoconti: eliminali prima")
        if await db.coa_entries.find_one({"company_id": cid, "righe.conto": c}, {"_id": 1}):
            raise HTTPException(400, "Il conto ha movimenti contabili: non può essere eliminato")
        p = params_of(await _company(db, cid))
        if c in [p[k] for k, _ in RUOLI] or c in p["categorie"].values():
            raise HTTPException(400, "Il conto è usato nei parametri contabili dell'azienda")
        if await db.articles.find_one({"company_id": cid, "conto_ricavo": c}, {"_id": 1}) or await db.parties.find_one({"company_id": cid, "conto_costo": c}, {"_id": 1}):
            raise HTTPException(400, "Il conto è usato come contropartita in articoli o fornitori")
        await db.coa_accounts.delete_one({"id": aid})
        return {"ok": True}

    # --- Causali e codici IVA
    def crud(path: str, coll, model, label: str):
        @r.get(path)
        async def _list(tutti: bool = False, t: dict = Depends(seeded)):
            q = {"company_id": t["cid"], **({} if tutti or model is CausaleIn else {"attivo": {"$ne": False}})}
            return await coll.find(q, {"_id": 0}).sort("codice", 1).to_list(1000)

        @r.put(path + "/{xid}/attivo")
        async def _attivo(xid: str, body: dict, t: dict = Depends(seeded)):
            res = await coll.update_one({"id": xid, "company_id": t["cid"]}, {"$set": {"attivo": bool(body.get("attivo"))}})
            if not res.matched_count:
                raise HTTPException(404, f"{label} non trovato")
            return {"ok": True}

        async def _check(t, body):
            if model is CausaleIn:
                for k in ("conto_dare", "conto_avere"):
                    if getattr(body, k):
                        await leaf(t["cid"], getattr(body, k), "Conto proposto")

        @r.post(path)
        async def _add(body: model, t: dict = Depends(seeded)):
            await _check(t, body)
            if await coll.find_one({"company_id": t["cid"], "codice": body.codice}, {"_id": 1}):
                raise HTTPException(400, f"{label} {body.codice} già esistente")
            doc = {"id": str(uuid.uuid4()), "company_id": t["cid"], **body.model_dump(), "sistema": False, "created_at": _now()}
            await coll.insert_one(dict(doc))
            return doc

        @r.put(path + "/{xid}")
        async def _upd(xid: str, body: model, t: dict = Depends(seeded)):
            await _check(t, body)
            cur = await coll.find_one({"id": xid, "company_id": t["cid"]}, {"_id": 0})
            if not cur:
                raise HTTPException(404, f"{label} non trovato")
            d = body.model_dump()
            if cur.get("sistema"):
                d["codice"] = cur["codice"]
            elif d["codice"] != cur["codice"] and await coll.find_one({"company_id": t["cid"], "codice": d["codice"]}, {"_id": 1}):
                raise HTTPException(400, f"{label} {d['codice']} già esistente")
            await coll.update_one({"id": xid}, {"$set": d})
            return {**cur, **d}

        @r.delete(path + "/{xid}")
        async def _del(xid: str, t: dict = Depends(seeded)):
            cur = await coll.find_one({"id": xid, "company_id": t["cid"]}, {"_id": 0})
            if not cur:
                raise HTTPException(404, f"{label} non trovato")
            if cur.get("sistema"):
                raise HTTPException(400, f"{label} di sistema: non può essere eliminato")
            field = "causale" if model is CausaleIn else "righe.codice_iva"
            if await db.coa_entries.find_one({"company_id": t["cid"], field: cur["codice"]}, {"_id": 1}):
                raise HTTPException(400, f"{label} usato in registrazioni contabili")
            if model is IvaIn:
                usi = [lbl for coll, f, lbl in (("passive_invoices", "riepilogo.codice_iva", "fatture ricevute"), ("passive_invoices", "righe_costo.codice_iva", "fatture ricevute"),
                                                ("parties", "codice_iva", "anagrafiche"), ("articles", "codice_iva", "articoli"))
                       if await db[coll].find_one({"company_id": t["cid"], f: cur["codice"]}, {"_id": 1})]
                if usi:
                    raise HTTPException(400, f"{label} movimentato ({', '.join(sorted(set(usi)))}): non può essere eliminato")
            await coll.delete_one({"id": xid})
            return {"ok": True}

    crud("/causali", db.coa_causali, CausaleIn, "Causale")
    crud("/codici-iva", db.coa_iva, IvaIn, "Codice IVA")

    @r.get("/conti-pagamento")
    async def get_conti_pag(t: dict = Depends(tenant)):
        return await conti_pagamento(db, t["cid"]) or {"conti": [], "default": {}}

    @r.post("/pagamenti-mancanti")
    async def pagamenti_mancanti(t: dict = Depends(seeded_acc)):
        cid = t["cid"]
        opts = await conti_pagamento(db, cid)
        if opts is None:
            raise HTTPException(400, "Contabilità generale non attiva")
        validi = {o["conto"] for o in opts["conti"]}
        legati = set()
        async for tx in db.bank_tx.find({"company_id": cid, "match.payment_ids": {"$exists": True}}, {"_id": 0, "match.payment_ids": 1}):
            legati |= set((tx.get("match") or {}).get("payment_ids") or [])
        by = t["user"].get("name") or t["user"]["email"]
        res, errori, names = {"pagamenti": 0, "incassi": 0, "saltati": 0}, [], {}
        q = {"company_id": cid, "$or": [{"coge_entry_id": None}, {"coge_entry_id": {"$exists": False}}], "metodo": {"$nin": ["compensazione", "ritenuta"]},
             "riba_effetto_id": {"$exists": False}, "distinta_pag_id": {"$exists": False}}
        for coll, passivo in ((db.passive_payments, True), (db.payments, False)):
            for pay in sorted(await coll.find(q, {"_id": 0}).to_list(50000), key=lambda x: x["data"]):
                if pay["id"] in legati:
                    continue
                if passivo:
                    inv = await db.passive_invoices.find_one({"id": pay["invoice_id"], "company_id": cid}, {"_id": 0, "stato_reg": 1, "data_registrazione": 1})
                    if inv and inv.get("stato_reg") != "registrata":
                        res["saltati"] += 1
                        errori.append(f"Pagamento fatt. {pay['numero_display']} del {pay['data']}: la fattura non è ancora registrata")
                        continue
                    if inv and pay["data"] < (inv.get("data_registrazione") or ""):
                        res["saltati"] += 1
                        errori.append(f"Pagamento fatt. {pay['numero_display']} del {pay['data']}: precede la registrazione della fattura ({inv['data_registrazione']}), correggi la data")
                        continue
                conto = pay.get("conto") if pay.get("conto") in validi else opts["default"].get(pay["metodo"])
                if pay["party_id"] not in names:
                    names[pay["party_id"]] = (await db.parties.find_one({"id": pay["party_id"], "company_id": cid}, {"_id": 0, "denominazione": 1}) or {}).get("denominazione") or ""
                try:
                    e = await registra_pagamento(db, cid, pay, conto, passivo, names[pay["party_id"]], by)
                except ValueError as ex:
                    res["saltati"] += 1
                    errori.append(f"{'Pagamento' if passivo else 'Incasso'} fatt. {pay['numero_display']} del {pay['data']}: {ex}")
                    continue
                if not e:
                    e = await db.coa_entries.find_one({"company_id": cid, "origine": "pagamento", "ref_id": pay["id"]}, {"_id": 0, "id": 1, "numero": 1, "anno": 1})
                    if not e:
                        continue
                upd = {"coge_entry_id": e["id"], "coge_rif": f"prima nota n. {e['numero']}/{e['anno']}", "conto": conto}
                await coll.update_one({"id": pay["id"], "company_id": cid}, {"$set": upd})
                if not passivo:
                    await coll.update_many({"company_id": cid, "parent_payment_id": pay["id"]}, {"$set": upd})
                res["pagamenti" if passivo else "incassi"] += 1
        return res | {"errori": errori[:20]}

    async def _carte(cid: str) -> list:
        opts = await conti_pagamento(db, cid)
        return [o for o in (opts or {"conti": []})["conti"] if o["tipo"] == "carta"]

    @r.get("/carte/estratto")
    async def estratto_carte(mese: str, t: dict = Depends(seeded)):
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", mese):
            raise HTTPException(400, "Mese non valido")
        cid = t["cid"]
        y, m = int(mese[:4]), int(mese[5:])
        fine = f"{y + (m == 12)}-{(m % 12) + 1:02d}-01"
        out = []
        for c in await _carte(cid):
            rows = await db.coa_entries.find({"company_id": cid, "righe.conto": c["conto"], "data": {"$gte": f"{mese}-01", "$lt": fine}, "origine": {"$ne": "carta"}},
                                             {"_id": 0}).sort([("data", 1), ("numero", 1)]).to_list(5000)
            mov = []
            for e in rows:
                v = r2(sum(x["avere"] - x["dare"] for x in e["righe"] if x["conto"] == c["conto"]))
                party = next((x.get("party_nome") for x in e["righe"] if x.get("party_nome")), None)
                mov.append({"id": e["id"], "data": e["data"], "numero": e["numero"], "anno": e["anno"], "causale": e["causale"], "descrizione": e["descrizione"],
                            "party_nome": party, "addebito": max(v, 0.0), "accredito": max(-v, 0.0)})
            add = await db.coa_entries.find({"company_id": cid, "origine": "carta", "ref_id": {"$regex": f"^{re.escape(c['conto'])}:{mese}:"}}, {"_id": 0, "id": 1, "numero": 1, "anno": 1, "data": 1, "totale": 1, "righe": 1}).to_list(10)
            tot = r2(sum(x["addebito"] - x["accredito"] for x in mov))
            fatto = r2(sum(e["totale"] for e in add))
            out.append({**c, "movimenti": mov, "totale_spese": r2(sum(x["addebito"] for x in mov)), "totale_accrediti": r2(sum(x["accredito"] for x in mov)),
                        "totale": tot, "addebitato": fatto, "da_addebitare": r2(tot - fatto),
                        "addebiti": [{"id": e["id"], "numero": e["numero"], "anno": e["anno"], "data": e["data"], "importo": e["totale"],
                                      "banca": next((x["conto"] for x in e["righe"] if x["avere"] > 0), "")} for e in add]})
        return {"mese": mese, "carte": out}

    @r.post("/carte/addebito")
    async def addebito_carta(body: AddebitoIn, t: dict = Depends(seeded_acc)):
        cid = t["cid"]
        opts = await conti_pagamento(db, cid) or {"conti": []}
        if body.conto not in {o["conto"] for o in opts["conti"] if o["tipo"] == "carta"}:
            raise HTTPException(400, "Carta non valida")
        if body.banca not in {o["conto"] for o in opts["conti"] if o["tipo"] == "banca"}:
            raise HTTPException(400, "Seleziona la banca di addebito")
        if body.data < f"{body.mese}-01":
            raise HTTPException(400, "La data di addebito non può precedere il mese dell'estratto conto")
        est = next(c for c in (await estratto_carte(body.mese, t))["carte"] if c["conto"] == body.conto)
        if est["da_addebitare"] <= 0.005:
            raise HTTPException(400, "Nessun importo da addebitare per questo mese")
        p = params_of(await _company(db, cid))
        try:
            e = await _insert(db, cid, p, body.data, "GC", f"Addebito estratto conto {est['label']} - {body.mese[5:]}/{body.mese[:4]}",
                              [{"conto": body.conto, "dare": est["da_addebitare"]}, {"conto": body.banca, "avere": est["da_addebitare"]}], "carta", f"{body.conto}:{body.mese}:{uuid.uuid4().hex[:8]}",
                              {"documento": f"E/C {body.mese}", "data_documento": body.data}, by=t["user"].get("name") or t["user"]["email"])
        except ValueError as ex:
            raise HTTPException(400, str(ex))
        return e

    # --- Parametri
    @r.get("/parametri")
    async def get_params(t: dict = Depends(seeded)):
        return {"parametri": params_of(await _company(db, t["cid"])), "ruoli": RUOLI, "categorie": CATEGORIE}

    @r.put("/parametri")
    async def put_params(body: ParamIn, t: dict = Depends(seeded)):
        cid = t["cid"]
        out = {}
        for k, lab in RUOLI:
            c = (body.conti.get(k) or "").strip()
            await leaf(cid, c, lab)
            out[k] = c
        cats = {}
        for cat in CATEGORIE:
            c = (body.categorie.get(cat) or "").strip()
            await leaf(cid, c, f"Categoria bancaria «{cat}»")
            cats[cat] = c
        out |= {"contropartita_vendite": body.contropartita_vendite, "contropartita_acquisti": body.contropartita_acquisti,
                "aliquota_rc": body.aliquota_rc, "categorie": cats}
        await db.companies.update_one({"id": cid}, {"$set": {"contabilita": out}})
        return {"parametri": out, "ruoli": RUOLI, "categorie": CATEGORIE}

    # --- Registrazioni (prima nota / libro giornale)
    def _range(dal, al):
        return {**({"$gte": dal} if dal else {}), **({"$lte": al} if al else {})}

    async def _blocchi(cid: str, rows: list) -> dict:
        chiusi = set(await anni_chiusi(db, cid))
        lk = await stampe_mod.lock_date(db, cid, "giornale")
        vid = [x["ref_id"] for x in rows if x["origine"] == "vendita" and x.get("ref_id")]
        aid = [x["ref_id"] for x in rows if x["origine"] == "acquisto" and x.get("ref_id")]
        inv = {d["id"]: d async for d in db.invoices.find({"company_id": cid, "id": {"$in": vid}, "status": {"$in": ["consegnata", "mancata_consegna"]}}, {"_id": 0, "id": 1, "numero_display": 1})}
        pas = {d["id"]: d async for d in db.passive_invoices.find({"company_id": cid, "id": {"$in": aid}, "origine": {"$in": ["sdi", "sdi_simulato"]}}, {"_id": 0, "id": 1, "numero_display": 1})}
        out = {}
        for x in rows:
            o, ref = x["origine"], x.get("ref_id")
            if x["anno"] in chiusi:
                out[x["id"]] = f"L'esercizio {x['anno']} è chiuso: per modificarlo annulla prima la chiusura"
            elif lk and x.get("data") and x["data"] <= lk:
                out[x["id"]] = f"Il libro giornale è stampato in definitiva fino al {lk[8:10]}/{lk[5:7]}/{lk[:4]}: riapri i movimenti nei parametri azienda"
            elif o == "ratei":
                out[x["id"]] = "Le scritture di ratei e risconti si annullano dall'archivio Ratei e risconti"
            elif o.startswith("riba"):
                out[x["id"]] = "Le registrazioni Ri.Ba. si annullano dalla distinta o dall'effetto in Effetti Ri.Ba."
            elif o == "vendita" and ref in inv:
                out[x["id"]] = f"La fattura {inv[ref]['numero_display']} è stata accettata dallo SDI: la sua registrazione non si può eliminare (puoi modificarla)"
            elif o == "acquisto" and ref in pas:
                out[x["id"]] = f"La fattura passiva {pas[ref].get('numero_display')} è stata consegnata dallo SDI: la sua registrazione non si può eliminare (puoi modificarla)"
        return out

    @r.get("/registrazioni")
    async def list_reg(dal: Optional[str] = None, al: Optional[str] = None, origine: Optional[str] = None, q: Optional[str] = None, da_verificare: bool = False,
                       t: dict = Depends(seeded)):
        f = {"company_id": t["cid"], **({"origine": origine} if origine in ORIGINI else {}), **({"da_verificare": True} if da_verificare else {})}
        if dal or al:
            f["data"] = _range(dal, al)
        if q:
            rx = {"$regex": re.escape(q), "$options": "i"}
            f["$or"] = [{"descrizione": rx}, {"documento": rx}, {"righe.conto": rx}, {"righe.party_nome": rx}, {"causale": rx}]
        rows = await db.coa_entries.find(f, {"_id": 0}).sort([("data", 1), ("anno", 1), ("numero", 1)]).to_list(20000)
        blk = await _blocchi(t["cid"], rows)
        for x in rows:
            x["eliminabile"], x["motivo_blocco"] = x["id"] not in blk, blk.get(x["id"])
        return {"registrazioni": rows, "dare": r2(sum(x["totale"] for x in rows)), "avere": r2(sum(sum(y["avere"] for y in x["righe"]) for x in rows)),
                "origini": ORIGINI, "da_verificare": await db.coa_entries.count_documents({"company_id": t["cid"], "da_verificare": True})}

    class VerIn(BaseModel):
        ids: List[str] = Field(min_length=1, max_length=2000)

    @r.post("/registrazioni/verificate")
    async def verificate(body: VerIn, t: dict = Depends(tenant_accounting)):
        res = await db.coa_entries.update_many({"company_id": t["cid"], "id": {"$in": body.ids}, "da_verificare": True},
                                               {"$set": {"da_verificare": False, "verificata_da": t["user"].get("name") or t["user"]["email"], "verificata_at": _now()}})
        return {"verificate": res.modified_count}

    @r.get("/registrazioni-da-verificare")
    async def da_verificare(t: dict = Depends(seeded)):
        f = {"company_id": t["cid"], "da_verificare": True}
        ultime = await db.coa_entries.find(f, {"_id": 0, "id": 1, "numero": 1, "data": 1, "descrizione": 1, "totale": 1}).sort([("data", -1), ("numero", -1)]).to_list(5)
        agg = await db.coa_entries.aggregate([{"$match": f}, {"$group": {"_id": None, "n": {"$sum": 1}, "tot": {"$sum": "$totale"}}}]).to_list(1)
        return {"n": agg[0]["n"] if agg else 0, "totale": r2(agg[0]["tot"]) if agg else 0.0, "ultime": ultime}

    @r.get("/registrazioni/{rid}")
    async def get_reg(rid: str, t: dict = Depends(seeded)):
        e = await db.coa_entries.find_one({"company_id": t["cid"], "id": rid}, {"_id": 0})
        if not e:
            raise HTTPException(404, "Registrazione non trovata")
        return e

    async def _manual_righe(cid: str, body: RegIn) -> list:
        if not await db.coa_causali.find_one({"company_id": cid, "codice": body.causale}, {"_id": 1}):
            raise HTTPException(400, "Causale contabile non valida")
        out = []
        for i, x in enumerate(body.righe, 1):
            if bool(r2(x.dare)) == bool(r2(x.avere)):
                raise HTTPException(400, f"Riga {i}: indica un importo in Dare oppure in Avere")
            await leaf(cid, x.conto, f"Riga {i}")
            nome = None
            if x.party_id:
                pt = await db.parties.find_one({"id": x.party_id, "company_id": cid}, {"_id": 0, "denominazione": 1})
                if not pt:
                    raise HTTPException(400, f"Riga {i}: cliente/fornitore non trovato")
                nome = pt["denominazione"]
            if x.codice_iva and not await db.coa_iva.find_one({"company_id": cid, "codice": x.codice_iva}, {"_id": 1}):
                raise HTTPException(400, f"Riga {i}: codice IVA non valido")
            out.append({**x.model_dump(), "party_nome": nome})
        d, a = r2(sum(x["dare"] for x in out)), r2(sum(x["avere"] for x in out))
        if d != a:
            raise HTTPException(400, f"Registrazione non quadrata: Dare {d:.2f} € · Avere {a:.2f} € (differenza {abs(d - a):.2f} €)")
        return out

    @r.post("/registrazioni")
    @integrita.atomico
    async def add_reg(body: RegIn, t: dict = Depends(seeded_acc)):
        cid = t["cid"]
        righe = await _manual_righe(cid, body)
        p = params_of(await _company(db, cid))
        import ratei as rr_mod
        if body.rateo:
            rr_mod.valida(body.rateo, lambda c, f, m: HTTPException(c, m), body.data)
        if body.saldaconto:
            await sc.check(cid, body.data, _norm(righe), body.saldaconto, p)
        try:
            doc = await _insert(db, cid, p, body.data, body.causale, body.descrizione, righe, "manuale",
                                by=t["user"].get("name") or t["user"]["email"])
        except ValueError as e:
            raise HTTPException(400, str(e))
        if body.saldaconto:
            await sc.apply(cid, doc, body.saldaconto, t["user"])
        if body.rateo:
            await rr_mod.da_prima_nota(db, cid, doc, body.rateo, t["user"].get("name") or t["user"]["email"])
        return doc

    @r.put("/registrazioni/{rid}")
    @integrita.atomico
    async def upd_reg(rid: str, body: RegIn, t: dict = Depends(seeded_acc)):
        cid = t["cid"]
        cur = await db.coa_entries.find_one({"id": rid, "company_id": cid}, {"_id": 0})
        if not cur:
            raise HTTPException(404, "Registrazione non trovata")
        vf = integrita.verifica_versione(cur, t)
        await check_aperto(db, cid, cur["anno"])
        if cur["origine"] == "ratei":
            raise HTTPException(400, "Le scritture di ratei e risconti si modificano dall'archivio Ratei e risconti")
        if cur["origine"] == "pagamento":
            raise HTTPException(400, "Movimento creato dal pagamento della fattura: per correggerlo elimina il pagamento (o questa registrazione) e registralo di nuovo")
        if body.data[:4] != str(cur["anno"]):
            raise HTTPException(400, "Non puoi spostare la registrazione in un altro anno: eliminala e ricreala")
        try:
            await stampe_mod.check_giornale(db, cid, body.data)
            await stampe_mod.check_giornale(db, cid, cur["data"])
        except ValueError as ex:
            raise HTTPException(400, str(ex))
        if cur["origine"] == "pagamenti" and not body.saldaconto:
            raise HTTPException(400, "Il movimento di una distinta di pagamento deve restare abbinato alle fatture fornitore: per eliminarlo annulla la distinta da Pagamenti fornitori")
        righe = _norm(await _manual_righe(cid, body))
        import ratei as rr_mod
        if body.rateo:
            rr_mod.valida(body.rateo, lambda c, f, m: HTTPException(c, m), body.data)
            await rr_mod.check_elimina_doc(db, cid, rid)
        accs = {a["codice"]: a["descrizione"] for a in await db.coa_accounts.find({"company_id": cid, "codice": {"$in": [x["conto"] for x in righe]}}, {"_id": 0}).to_list(500)}
        for x in righe:
            x["conto_descrizione"] = accs.get(x["conto"], "")
        old = await sc.remove(cid, rid)
        if body.saldaconto:
            try:
                await sc.check(cid, body.data, righe, body.saldaconto, params_of(await _company(db, cid)))
            except HTTPException:
                await sc.restore(old)
                raise
        caus = await db.coa_causali.find_one({"company_id": cid, "codice": body.causale}, {"_id": 0, "descrizione": 1})
        upd = {"data": body.data, "causale": body.causale, "causale_descrizione": caus["descrizione"], "descrizione": body.descrizione, "righe": righe,
               "totale": r2(sum(x["dare"] for x in righe)), "updated_at": _now(), "modificata": cur["origine"] != "manuale",
               "modificata_da": t["user"].get("name") or t["user"]["email"]}
        res = await db.coa_entries.update_one({"id": rid, **vf}, {"$set": upd, "$inc": {"version": 1}})
        if not res.matched_count:
            raise HTTPException(409, integrita.CONFLITTO)
        upd["version"] = int(cur.get("version") or 0) + 1
        if body.saldaconto:
            await sc.apply(cid, {**cur, **upd}, body.saldaconto, t["user"])
        if body.rateo:
            await rr_mod.da_prima_nota(db, cid, {**cur, **upd}, body.rateo, t["user"].get("name") or t["user"]["email"])
        return {**cur, **upd}

    @r.delete("/registrazioni/{rid}")
    @integrita.atomico
    async def del_reg(rid: str, t: dict = Depends(seeded_acc)):
        cur = await db.coa_entries.find_one({"id": rid, "company_id": t["cid"]}, {"_id": 0, "origine": 1, "anno": 1, "ref_id": 1, "data": 1})
        if not cur:
            raise HTTPException(404, "Registrazione non trovata")
        ori, ref = cur["origine"], cur.get("ref_id")
        motivo = (await _blocchi(t["cid"], [{**cur, "id": rid}])).get(rid)
        if motivo:
            raise HTTPException(400, motivo)
        import ratei as rr_mod
        if ori == "manuale":
            await rr_mod.elimina_doc(db, t["cid"], rid)
        await db.coa_entries.delete_one({"id": rid})
        await sc.remove(t["cid"], rid)
        if ori == "pagamenti":
            await db.passive_payments.delete_many({"company_id": t["cid"], "distinta_pag_id": ref})
            await db.pag_distinte.delete_one({"company_id": t["cid"], "id": ref})
        if ori in ("ritenute", "bolli"):
            await db.f24_versamenti.delete_one({"company_id": t["cid"], "key": ref})
        return {"ok": True}

    @r.post("/rigenera")
    async def rigenera(body: RigeneraIn, t: dict = Depends(seeded_acc)):
        cid = t["cid"]
        if not attiva(await _company(db, cid)):
            raise HTTPException(400, "Modulo contabilità non attivo")
        if body.ricrea:
            await db.coa_entries.delete_many({"company_id": cid, "origine": {"$in": ["vendita", "acquisto", "banca"]}, "anno": {"$nin": await anni_chiusi(db, cid)}})
        res, errori = {"vendite": 0, "acquisti": 0, "banca": 0, "autofatture": 0}, []
        p = params_of(await _company(db, cid))
        oggi = date.today().isoformat()
        chiusi = await anni_chiusi(db, cid)
        async for doc in db.passive_invoices.find({"company_id": cid, "stato_reg": "da_registrare"}, {"_id": 0, "id": 1, "data": 1, "riepilogo": 1, "reverse_charge": 1, "fornitore": 1, "party_id": 1}).sort([("data", 1), ("numero", 1)]):
            dr = min(max(doc["data"], f"{doc['data'][:4]}-01-01"), oggi)
            if int(dr[:4]) in chiusi:
                errori.append(f"Fattura passiva del {doc['data']}: esercizio chiuso, registrala a mano")
                continue
            last = await db.passive_invoices.find_one({"company_id": cid, "anno_registrazione": int(dr[:4])}, {"_id": 0, "protocollo": 1}, sort=[("protocollo", -1)])
            gest = ((await db.parties.find_one({"id": doc.get("party_id"), "company_id": cid}, {"_id": 0, "gestione_iva": 1})) or {}).get("gestione_iva") or ""
            est = HOOKS["is_estero"](doc.get("fornitore") or {}) or gest in ("intra_ue", "extra_ue")
            rc = doc.get("reverse_charge") or HOOKS["rc_righe"]({**doc, "estero": est}, float(p["aliquota_rc"]))
            await db.passive_invoices.update_one({"id": doc["id"], "company_id": cid, "stato_reg": "da_registrare"}, {"$set": {
                "stato_reg": "registrata", "data_registrazione": dr, "anno_registrazione": int(dr[:4]), "protocollo": ((last or {}).get("protocollo") or 0) + 1,
                "reverse_charge": rc or None, "estero": est, "registrata_auto": True, "updated_at": _now()}})
            try:
                await check_annullabile(db, cid, "acquisto", doc["id"])
                await annulla(db, cid, "acquisto", doc["id"])
                await registra_acquisto(db, await db.passive_invoices.find_one({"id": doc["id"], "company_id": cid}, {"_id": 0, "xml_b64": 0, "lines": 0}))
            except HTTPException:
                pass
            except Exception as e:  # noqa: BLE001
                errori.append(f"Fattura passiva del {doc['data']}: {e}")
            full = await db.passive_invoices.find_one({"id": doc["id"], "company_id": cid}, {"_id": 0, "xml_b64": 0, "lines": 0})
            tipo_af = HOOKS["proposta_tipo"](full) if rc else None
            if tipo_af == "TD17" and not HOOKS["is_estero"](full.get("fornitore") or {}):
                errori.append(f"Fattura del {doc['data']}: fornitore estero senza paese estero nei dati, completa il fornitore e crea l'autofattura TD17 dalla fattura")
                tipo_af = None
            if tipo_af and not full.get("autofattura_id"):
                try:
                    await HOOKS["crea_autofattura"](t, full, tipo_af)
                    res["autofatture"] += 1
                except Exception as e:  # noqa: BLE001
                    errori.append(f"Autofattura per fattura del {doc['data']} non creata ({getattr(e, 'detail', e)}): creala dalla fattura ricevuta")
            res["acquisti"] += 1
        jobs = []
        async for inv in db.invoices.find({"company_id": cid, "status": {"$in": list(AUTO_STATI)}}, {"_id": 0, "xml_b64": 0}).sort([("data", 1), ("numero", 1)]):
            jobs.append((inv["data"], "vendite", f"Fattura {inv['numero_display']}", lambda x=inv: registra_vendita(db, x)))
        async for doc in db.passive_invoices.find({"company_id": cid}, {"_id": 0, "xml_b64": 0, "lines": 0}):
            jobs.append((doc["data"], "acquisti_coge", f"Fattura passiva {doc.get('numero')}", lambda x=doc: registra_acquisto(db, x)))
        async for tx in db.bank_tx.find({"company_id": cid, "stato": "riconciliato"}, {"_id": 0}):
            jobs.append((tx["data"], "banca", f"Movimento del {tx['data']}", lambda x=tx: registra_banca(db, cid, x, x.get("match") or {})))
        for _, k, lab, job in sorted(jobs, key=lambda j: j[0]):
            try:
                if await job() and k in res:
                    res[k] += 1
            except Exception as e:  # noqa: BLE001
                errori.append(f"{lab}: {e}")
        return {**res, "errori": errori[:20]}

    # --- Mastrini e bilancio
    @r.get("/mastrino")
    async def mastrino(conto: str, dal: Optional[str] = None, al: Optional[str] = None, party_id: Optional[str] = None, solo_definitive: bool = False,
                       t: dict = Depends(seeded)):
        cid = t["cid"]
        acc = await db.coa_accounts.find_one({"company_id": cid, "codice": conto}, {"_id": 0})
        if not acc:
            raise HTTPException(404, "Conto non trovato")
        rx = re.compile(f"^{re.escape(conto)}(\\.|$)")
        f = {"company_id": cid, "righe.conto": {"$regex": f"^{re.escape(conto)}(\\.|$)"}, **({"provvisoria": {"$ne": True}} if solo_definitive else {})}
        if al:
            f["data"] = {"$lte": al}
        rows = await db.coa_entries.find(f, {"_id": 0}).sort([("data", 1), ("anno", 1), ("numero", 1)]).to_list(50000)
        saldo0, movs, parties, saldo = 0.0, [], {}, 0.0
        for e in rows:
            mine = [x for x in e["righe"] if rx.match(x["conto"])]
            for x in mine:
                if x.get("party_id"):
                    parties[x["party_id"]] = x.get("party_nome") or ""
            if party_id:
                mine = [x for x in mine if x.get("party_id") == party_id]
            if not mine:
                continue
            d, a = r2(sum(x["dare"] for x in mine)), r2(sum(x["avere"] for x in mine))
            if dal and e["data"] < dal:
                saldo0 = r2(saldo0 + d - a)
                continue
            if not movs:
                saldo = saldo0
            saldo = r2(saldo + d - a)
            contro = sorted({f"{x['conto']} {x.get('conto_descrizione', '')}" for x in e["righe"] if not rx.match(x["conto"])})
            movs.append({"id": e["id"], "numero": e["numero"], "anno": e["anno"], "data": e["data"], "causale": e["causale"], "descrizione": e["descrizione"],
                         "documento": e.get("documento") or "", "origine": e["origine"], "dare": d, "avere": a, "saldo": saldo,
                         "party_nome": next((x.get("party_nome") for x in mine if x.get("party_nome")), None), "contropartite": contro[:4]})
        td, ta = r2(sum(m["dare"] for m in movs)), r2(sum(m["avere"] for m in movs))
        return {"conto": acc, "saldo_iniziale": saldo0, "dare": td, "avere": ta, "saldo_finale": r2(saldo0 + td - ta), "movimenti": movs,
                "parties": [{"id": k, "nome": v} for k, v in sorted(parties.items(), key=lambda kv: kv[1] or "")]}

    @r.get("/bilancio")
    async def bilancio(dal: Optional[str] = None, al: Optional[str] = None, chiusura: bool = False, solo_definitive: bool = False, t: dict = Depends(seeded)):
        cid = t["cid"]
        f = {"company_id": cid, **({"data": _range(dal, al)} if dal or al else {}), **({"provvisoria": {"$ne": True}} if solo_definitive else {})}
        prov = await db.coa_entries.count_documents({**f, "provvisoria": True}) if not solo_definitive else 0
        if not chiusura:
            f["$nor"] = [{"origine": "chiusura"}, {"origine": "apertura", **({"data": {"$gt": dal}} if dal else {})}]
        tot = {}
        async for e in db.coa_entries.find(f, {"_id": 0, "righe": 1}):
            for x in e["righe"]:
                v = tot.setdefault(x["conto"], [0.0, 0.0])
                v[0] += x["dare"]
                v[1] += x["avere"]
        accs = {a["codice"]: a for a in await accounts(cid)}
        agg = {}
        for c, (d, a) in tot.items():
            for k in {c, c[:5], c[:2]}:
                v = agg.setdefault(k, [0.0, 0.0])
                v[0] += d
                v[1] += a
        righe = []
        for c in sorted(agg):
            d, a = r2(agg[c][0]), r2(agg[c][1])
            acc = accs.get(c) or {"descrizione": "(conto eliminato)", "livello": c.count(".") + 1, "tipo": tipo_conto(c)}
            righe.append({"codice": c, "descrizione": acc["descrizione"], "livello": acc["livello"], "tipo": acc["tipo"], "dare": d, "avere": a, "saldo": r2(d - a)})
        foglie = [x for x in righe if x["livello"] == 3]
        sez = {k: r2(sum(x["saldo"] for x in foglie if x["tipo"] == k)) for k in TIPI}
        ricavi, costi = -sez["ricavo"], sez["costo"]
        return {"righe": righe, "dare": r2(sum(x["dare"] for x in foglie)), "avere": r2(sum(x["avere"] for x in foglie)),
                "attivita": sez["attivita"], "passivita": -sez["passivita"], "costi": costi, "ricavi": ricavi, "risultato": r2(ricavi - costi), "tipi": TIPI,
                "provvisorie": prov}

    return r


async def ensure_indexes(db):
    await db.coa_accounts.create_index([("company_id", 1), ("codice", 1)], unique=True)
    await db.coa_causali.create_index([("company_id", 1), ("codice", 1)], unique=True)
    await db.coa_iva.create_index([("company_id", 1), ("codice", 1)], unique=True)
    await db.coa_entries.create_index([("company_id", 1), ("data", 1), ("numero", 1)])
    await db.coa_entries.create_index([("company_id", 1), ("origine", 1), ("ref_id", 1)], unique=True,
                                      partialFilterExpression={"ref_id": {"$type": "string"}}, name="coge_ref_unique")

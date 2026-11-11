import re
import unicodedata
import uuid
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import List, Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

import contabilita as coge
from contabilita_dati import tipo_conto

EFFETTI = "05.01.004"
SPESE_BANCA = "30.07.011"
RECUPERO_SPESE = "20.05.001"
CAUSALI_RIBA = [("RB", "Presentazione effetti Ri.Ba."), ("RS", "Effetti Ri.Ba. a scadenza"), ("RI", "Insoluto Ri.Ba.")]
DATE_RX = r"^\d{4}-\d{2}-\d{2}$"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _today():
    return datetime.now(ZoneInfo("Europe/Rome")).date().isoformat()


def _r2(v):
    return round(float(v or 0) + 0.0, 2)


def _a(s, n):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9 .,'/&()+-]", " ", s)[:n].ljust(n)


def _n(v, n):
    return str(v).rjust(n, "0")[-n:]


def _dmy(iso):
    return f"{iso[8:10]}{iso[5:7]}{iso[2:4]}"


def cbi_riba(comp: dict, banca: dict, dist: dict, effetti: list) -> str:
    sia, abi, cab = banca["sia"], banca["abi"], banca["cab"]
    conto = (banca.get("iban") or "")[15:27]
    oggi = _dmy(dist["data"])
    supporto = _a(f"{oggi}{dist['id'].replace('-', '')}", 20)
    piva = comp.get("partita_iva") or comp.get("codice_fiscale") or ""
    rows = [" IB" + _a(sia, 5) + _n(abi, 5) + oggi + supporto + " " * 6 + " " * 59 + " " * 7 + " " * 2 + "E" + " " + " " * 5]
    tot = 0
    for k, e in enumerate(effetti, 1):
        c, p = e["cliente"], _n(k, 7)
        cents = int(round(e["importo"] * 100))
        tot += cents
        cod = c.get("codice_fiscale") or c.get("partita_iva") or ""
        rows += [
            " 14" + p + " " * 12 + _dmy(e["scadenza"]) + "30000" + _n(cents, 13) + "-" + _n(abi, 5) + _n(cab, 5) + _a(conto, 12)
            + _n(c.get("appoggio_abi") or "", 5) + _n(c.get("appoggio_cab") or "", 5) + " " * 12 + _a(sia, 5) + "4" + _a(cod, 16) + " " * 6 + "E",
            " 20" + p + _a(comp.get("denominazione"), 24) + _a(comp.get("indirizzo"), 24) + _a(f"{comp.get('cap', '')} {comp.get('comune', '')}", 24)
            + _a(f"P.IVA {piva}", 24) + " " * 14,
            " 30" + p + _a(c.get("denominazione"), 60) + _a(cod, 16) + " " * 34,
            " 40" + p + _a(c.get("indirizzo"), 30) + _n(c.get("cap") or "", 5) + _a(f"{(c.get('comune') or '')[:22]} {c.get('provincia') or ''}", 25)
            + _a(c.get("appoggio_banca"), 50),
            " 50" + p + _a(f"FATT. N. {e['numero_display']} DEL {e['data_doc'][8:10]}/{e['data_doc'][5:7]}/{e['data_doc'][:4]}"
                           + (f" RATA {e['rata_n']}" if e.get("rate_totali", 1) > 1 else ""), 80) + " " * 10 + _a(piva, 16) + " " * 4,
            " 51" + p + _n(e["ricevuta"], 10) + _a(comp.get("denominazione"), 20) + " " * 80,
            " 70" + p + " " * 110,
        ]
    rows.append(" EF" + _a(sia, 5) + _n(abi, 5) + oggi + supporto + " " * 6 + _n(len(effetti), 7) + _n(tot, 15) + _n(0, 15)
                + _n(len(rows) + 1, 7) + " " * 24 + "E" + " " * 6)
    return "\r\n".join(rows) + "\r\n"


def parse_esiti(txt: str) -> list:
    recs = defaultdict(dict)
    for line in txt.splitlines():
        if len(line) < 46 or line[0] != " ":
            continue
        tp, prog = line[1:3], line[3:10]
        if tp == "14" and line[33:46].strip().isdigit():
            d = line[22:28]
            recs[prog].update(scadenza=f"20{d[4:6]}-{d[2:4]}-{d[0:2]}" if d.isdigit() else "", importo=int(line[33:46]) / 100, codice=line[97:113].strip())
        elif tp == "51":
            recs[prog]["ricevuta"] = line[10:20].strip()
    return [r for r in recs.values() if r.get("importo")]


class DistintaIn(BaseModel):
    banca_iban: str
    data: str = Field(pattern=DATE_RX)
    effetti: List[str] = Field(min_length=1, max_length=1000)


class InsolutoIn(BaseModel):
    data: str = Field(pattern=DATE_RX)
    spese_banca: float = Field(default=0, ge=0, le=10_000)
    spese_cliente: float = Field(default=0, ge=0, le=10_000)
    nuova_scadenza: str = Field(pattern=DATE_RX)


class RataIn(BaseModel):
    scadenza: str = Field(pattern=DATE_RX)
    importo: float = Field(gt=0, le=100_000_000)


class RateIn(BaseModel):
    rate: List[RataIn] = Field(min_length=1, max_length=60)

    @field_validator("rate")
    @classmethod
    def _ord(cls, v):
        return sorted(v, key=lambda r: r.scadenza)


def build(db, tenant, tenant_accounting, deps) -> APIRouter:
    r = APIRouter(prefix="/api/riba")
    ledger, ferr = deps["ledger"], deps["ferr"]

    async def _params(cid, origine, ref):
        p = await coge._ready(db, cid, origine, ref)
        if p:
            for c, d in CAUSALI_RIBA:
                await db.coa_causali.update_one({"company_id": cid, "codice": c}, {"$setOnInsert": {"id": str(uuid.uuid4()), "descrizione": d, "registro": "nessuno",
                                                                                                    "conto_dare": "", "conto_avere": "", "sistema": True, "created_at": _now()}}, upsert=True)
        return p

    async def _conto_sbf(cid: str, banca: dict) -> str:
        await coge.ensure_seed(db, cid)
        if banca.get("conto_sbf") and await db.coa_accounts.find_one({"company_id": cid, "codice": banca["conto_sbf"]}, {"_id": 1}):
            return banca["conto_sbf"]
        codes = [a["codice"] for a in await db.coa_accounts.find({"company_id": cid, "codice": {"$regex": r"^13\.01\.\d{3}$"}}, {"_id": 0, "codice": 1}).to_list(1000)]
        code = f"13.01.{max([int(c[-3:]) for c in codes] + [100]) + 1:03d}"
        await db.coa_accounts.insert_one({"id": str(uuid.uuid4()), "company_id": cid, "codice": code, "descrizione": f"Banca c/effetti SBF - {banca['nome']}"[:80],
                                          "livello": 3, "tipo": tipo_conto(code), "sistema": False, "created_at": _now()})
        await db.companies.update_one({"id": cid, "banche.iban": banca["iban"]}, {"$set": {"banche.$.conto_sbf": code}})
        return code

    async def _candidati(cid: str) -> list:
        docs, _, _, _ = await ledger(cid, None)
        mp12 = {x["id"] for x in await db.invoices.find({"company_id": cid, "modalita_pagamento": "MP12"}, {"_id": 0, "id": 1}).to_list(50000)}
        mp12 |= {x["id"] for x in await db.partite_aperte.find({"company_id": cid, "tipo": "cliente", "modalita_pagamento": "MP12"}, {"_id": 0, "id": 1}).to_list(50000)}
        attivi = {(e["invoice_id"], e["rata_n"]) for e in await db.riba_effetti.find({"company_id": cid, "stato": {"$in": ["presentato", "maturato"]}},
                                                                                   {"_id": 0, "invoice_id": 1, "rata_n": 1}).to_list(50000)}
        sel = [d for d in docs if d["id"] in mp12]
        pids = list({d["party_id"] for d in sel})
        parties = {p["id"]: p for p in await db.parties.find({"company_id": cid, "id": {"$in": pids}}, {"_id": 0, "listino": 0}).to_list(len(pids) + 1)}
        out = []
        for d in sel:
            p = parties.get(d["party_id"]) or {}
            for x in d["rate"]:
                if x["residuo"] > 0.005 and (d["id"], x["n"]) not in attivi:
                    out.append({"key": f"{d['id']}:{x['n']}", "invoice_id": d["id"], "rata_n": x["n"], "rate_totali": x["di"], "scadenza": x["scadenza"],
                                "importo": x["residuo"], "numero_display": d["numero_display"], "data_doc": d["data"], "party_id": d["party_id"],
                                "cliente": {k: p.get(k) or "" for k in ("denominazione", "partita_iva", "codice_fiscale", "indirizzo", "cap", "comune", "provincia",
                                                                         "appoggio_banca", "appoggio_abi", "appoggio_cab")} | {"denominazione": p.get("denominazione") or d["cliente"]},
                                "manca_appoggio": not (p.get("appoggio_abi") and p.get("appoggio_cab"))})
        return sorted(out, key=lambda e: (e["scadenza"], e["numero_display"]))

    async def matura(cid: str, fino_al: Optional[str] = None):
        fino_al = fino_al or _today()
        for e in await db.riba_effetti.find({"company_id": cid, "stato": "presentato", "scadenza": {"$lte": fino_al}}, {"_id": 0}).to_list(5000):
            if not (await db.riba_effetti.update_one({"id": e["id"], "stato": "presentato"}, {"$set": {"stato": "maturato", "maturato_il": e["scadenza"]}})).modified_count:
                continue
            p = await _params(cid, "riba_scadenza", e["id"])
            if p and e.get("conto_sbf"):
                await coge.safe(coge._insert(db, cid, p, max(e["scadenza"], e["data_distinta"]), "RS", f"Ri.Ba. {e['numero_display']} a scadenza - {e['cliente']['denominazione']}",
                                             [{"conto": e["conto_sbf"], "dare": e["importo"]},
                                              {"conto": EFFETTI, "avere": e["importo"], "party_id": e["party_id"], "party_nome": e["cliente"]["denominazione"]}],
                                             "riba_scadenza", e["id"], {"documento": e["numero_display"], "data_documento": e["data_doc"]}))

    async def tick():
        for cid in await db.riba_effetti.distinct("company_id", {"stato": "presentato", "scadenza": {"$lte": _today()}}):
            await matura(cid)

    def _banca(comp: dict, iban: str) -> dict:
        b = next((x for x in comp.get("banche") or [] if x.get("iban") == iban), None)
        if not b:
            raise ferr(400, "banca_iban", "Seleziona una banca dell'azienda")
        miss = [lab for k, lab in (("abi", "ABI"), ("cab", "CAB"), ("sia", "codice SIA")) if not b.get(k)]
        if miss:
            raise ferr(400, "banca_iban", f"Completa nella banca {b['nome']}: {', '.join(miss)} (Dati azienda → Banche)")
        return b

    @r.get("/da-presentare")
    async def da_presentare(t: dict = Depends(tenant)):
        await matura(t["cid"])
        return await _candidati(t["cid"])

    @r.get("/distinte")
    async def distinte(t: dict = Depends(tenant)):
        await matura(t["cid"])
        ds = await db.riba_distinte.find({"company_id": t["cid"]}, {"_id": 0}).sort([("data", -1), ("numero", -1)]).to_list(1000)
        stati = defaultdict(lambda: defaultdict(int))
        for e in await db.riba_effetti.find({"company_id": t["cid"]}, {"_id": 0, "distinta_id": 1, "stato": 1}).to_list(100000):
            stati[e["distinta_id"]][e["stato"]] += 1
        return [d | {"stati": dict(stati[d["id"]])} for d in ds]

    @r.get("/distinte/{did}")
    async def distinta(did: str, t: dict = Depends(tenant)):
        d = await db.riba_distinte.find_one({"id": did, "company_id": t["cid"]}, {"_id": 0})
        if not d:
            raise HTTPException(404, "Distinta non trovata")
        return d | {"effetti": await db.riba_effetti.find({"distinta_id": did, "company_id": t["cid"]}, {"_id": 0}).sort("prog", 1).to_list(1000)}

    @r.post("/distinte")
    async def crea(body: DistintaIn, t: dict = Depends(tenant_accounting)):
        cid, comp = t["cid"], t["company"]
        banca = _banca(comp, body.banca_iban)
        cand = {c["key"]: c for c in await _candidati(cid)}
        sel = [cand.get(k) for k in dict.fromkeys(body.effetti)]
        if not all(sel):
            raise HTTPException(400, "Uno o più effetti non sono più da presentare: aggiorna l'elenco")
        for c in sel:
            prima = [x for x in cand.values() if x["invoice_id"] == c["invoice_id"] and x["rata_n"] < c["rata_n"]]
            if any(x["key"] not in body.effetti for x in prima):
                raise HTTPException(400, f"Fattura {c['numero_display']}: presenta prima la rata {prima[0]['rata_n']}")
            if c["manca_appoggio"]:
                raise HTTPException(400, f"Cliente {c['cliente']['denominazione']}: inserisci ABI e CAB della banca d'appoggio nell'anagrafica")
        sbf = await _conto_sbf(cid, banca)
        anno = int(body.data[:4])
        cnt = await db.counters.find_one_and_update({"key": f"riba_{cid}_{anno}"}, {"$inc": {"v": 1}}, upsert=True, return_document=True)
        num = cnt["v"]
        did = str(uuid.uuid4())
        tot = _r2(sum(c["importo"] for c in sel))
        dist = {"id": did, "company_id": cid, "numero": num, "anno": anno, "numero_display": f"{num}/{anno}", "data": body.data, "banca_iban": banca["iban"],
                "banca_nome": banca["nome"], "conto_sbf": sbf, "totale": tot, "n_effetti": len(sel), "created_by": t["user"].get("name") or t["user"]["email"], "created_at": _now()}
        effetti = []
        for k, c in enumerate(sel, 1):
            eid = str(uuid.uuid4())
            pay = {"id": str(uuid.uuid4()), "company_id": cid, "invoice_id": c["invoice_id"], "party_id": c["party_id"], "numero_display": c["numero_display"],
                   "data": body.data, "importo": c["importo"], "metodo": "riba", "note": f"Ri.Ba. distinta {dist['numero_display']}", "nc_id": None, "nc_numero": None,
                   "riba_effetto_id": eid, "created_by": t["user"]["user_id"], "created_by_name": dist["created_by"], "created_at": _now()}
            await db.payments.insert_one(pay)
            effetti.append({**{k2: c[k2] for k2 in ("invoice_id", "rata_n", "rate_totali", "scadenza", "importo", "numero_display", "data_doc", "party_id", "cliente")},
                            "id": eid, "company_id": cid, "distinta_id": did, "distinta_numero": dist["numero_display"], "data_distinta": body.data, "prog": k,
                            "ricevuta": f"{anno % 100:02d}{num:04d}{k:04d}", "conto_sbf": sbf, "stato": "presentato", "payment_id": pay["id"], "created_at": _now()})
        await db.riba_effetti.insert_many([dict(e) for e in effetti])
        await db.riba_distinte.insert_one(dict(dist))
        p = await _params(cid, "riba", did)
        if p:
            righe = [{"conto": p["banca"], "dare": tot}, {"conto": sbf, "avere": tot}]
            for e in effetti:
                righe += [{"conto": EFFETTI, "dare": e["importo"], "party_id": e["party_id"], "party_nome": e["cliente"]["denominazione"]},
                          {"conto": p["clienti"], "avere": e["importo"], "party_id": e["party_id"], "party_nome": e["cliente"]["denominazione"]}]
            await coge.safe(coge._insert(db, cid, p, body.data, "RB", f"Presentazione distinta Ri.Ba. {dist['numero_display']} - {banca['nome']}", righe, "riba", did,
                                         {"documento": dist["numero_display"], "data_documento": body.data}))
        await matura(cid)
        return dist

    @r.get("/distinte/{did}/cbi")
    async def cbi(did: str, t: dict = Depends(tenant)):
        d = await distinta(did, t)
        banca = _banca(t["company"], d["banca_iban"])
        txt = cbi_riba(t["company"], banca, d, d["effetti"])
        return Response(txt.encode("ascii", "replace"), media_type="text/plain", headers={"Content-Disposition": f'attachment; filename="RIBA_{d["anno"]}_{d["numero"]:04d}.txt"'})

    @r.delete("/distinte/{did}")
    async def annulla(did: str, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        d = await distinta(did, t)
        if any(e["stato"] != "presentato" for e in d["effetti"]):
            raise HTTPException(400, "La distinta ha effetti già scaduti o insoluti: non può essere annullata")
        await coge.check_annullabile(db, cid, "riba", did)
        await db.payments.delete_many({"company_id": cid, "riba_effetto_id": {"$in": [e["id"] for e in d["effetti"]]}})
        await coge.annulla(db, cid, "riba", did)
        await db.riba_effetti.delete_many({"company_id": cid, "distinta_id": did})
        await db.riba_distinte.delete_one({"id": did, "company_id": cid})
        return {"ok": True}

    @r.post("/effetti/{eid}/insoluto")
    async def insoluto(eid: str, body: InsolutoIn, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        await matura(cid, body.data)
        e = await db.riba_effetti.find_one({"id": eid, "company_id": cid}, {"_id": 0})
        if not e:
            raise HTTPException(404, "Effetto non trovato")
        if e["stato"] == "insoluto":
            raise HTTPException(400, "Effetto già registrato come insoluto")
        if e["stato"] == "presentato":
            raise ferr(400, "data", "L'insoluto si registra dalla data di scadenza dell'effetto")
        if body.data < e["data_distinta"]:
            raise ferr(400, "data", "La data dell'insoluto non può precedere la presentazione della distinta")
        if body.data > _today():
            raise ferr(400, "data", "La data dell'insoluto non può essere futura")
        if body.nuova_scadenza < body.data:
            raise ferr(400, "nuova_scadenza", "La nuova scadenza non può precedere la data dell'insoluto")
        if not (await db.riba_effetti.update_one({"id": eid, "stato": "maturato"}, {"$set": {"stato": "insoluto", "insoluto": body.model_dump() | {"registrato_il": _now()}}})).modified_count:
            raise HTTPException(409, "Effetto già aggiornato da un'altra operazione")
        await db.payments.delete_one({"company_id": cid, "id": e["payment_id"]})
        coll = db.invoices if await db.invoices.find_one({"id": e["invoice_id"], "company_id": cid}, {"_id": 1}) else db.partite_aperte
        doc = await coll.find_one({"id": e["invoice_id"], "company_id": cid}, {"_id": 0, "rate": 1, "rate_mod": 1, "scadenza": 1, "data": 1, "netto": 1, "totale": 1})
        rate = [dict(x) for x in (doc.get("rate_mod") or doc.get("rate") or [{"scadenza": doc.get("scadenza") or doc["data"], "importo": doc.get("netto", doc["totale"])}])]
        rate.sort(key=lambda x: x["scadenza"])
        if e["rata_n"] <= len(rate):
            rate[e["rata_n"] - 1]["scadenza"] = body.nuova_scadenza
        await coll.update_one({"id": e["invoice_id"], "company_id": cid}, {"$set": {"rate_mod": rate}})
        nome = e["cliente"]["denominazione"]
        if body.spese_cliente:
            await db.partite_aperte.insert_one({"id": str(uuid.uuid4()), "company_id": cid, "tipo": "cliente", "party_id": e["party_id"], "numero": 0,
                                                "numero_display": f"Spese insoluto {e['numero_display']}", "data": body.data, "scadenza": body.nuova_scadenza,
                                                "totale": _r2(body.spese_cliente), "netto": _r2(body.spese_cliente),
                                                "rate": [{"scadenza": body.nuova_scadenza, "importo": _r2(body.spese_cliente)}], "tipo_documento": "TD01",
                                                "status": "storico", "stato_reg": "registrata", "modalita_pagamento": "MP12", "cliente": {"denominazione": nome},
                                                "riba_effetto_id": eid, "created_at": _now()})
        p = await _params(cid, "riba_insoluto", eid)
        if p:
            pp = {"party_id": e["party_id"], "party_nome": nome}
            righe = [{"conto": p["clienti"], "dare": e["importo"], **pp}, {"conto": p["banca"], "avere": e["importo"]}]
            if body.spese_banca:
                righe += [{"conto": SPESE_BANCA, "dare": body.spese_banca}, {"conto": p["banca"], "avere": body.spese_banca}]
            if body.spese_cliente:
                righe += [{"conto": p["clienti"], "dare": body.spese_cliente, **pp}, {"conto": RECUPERO_SPESE, "avere": body.spese_cliente}]
            await coge.safe(coge._insert(db, cid, p, body.data, "RI", f"Insoluto Ri.Ba. {e['numero_display']} - {nome}", righe, "riba_insoluto", eid,
                                         {"documento": e["numero_display"], "data_documento": e["data_doc"]}))
        return await db.riba_effetti.find_one({"id": eid}, {"_id": 0})

    @r.post("/esiti")
    async def esiti(file: UploadFile = File(...), t: dict = Depends(tenant_accounting)):
        raw = await file.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise HTTPException(400, "File troppo grande (max 2 MB)")
        recs = parse_esiti(raw.decode("latin-1"))
        if not recs:
            raise HTTPException(400, "Nessuna disposizione Ri.Ba. trovata nel file: serve il flusso esiti CBI (record 14 e 51)")
        eff = await db.riba_effetti.find({"company_id": t["cid"], "stato": {"$in": ["presentato", "maturato"]}}, {"_id": 0}).to_list(50000)
        by_ric = {e["ricevuta"]: e for e in eff}
        out, usati = [], set()
        for x in recs:
            e = by_ric.get(x.get("ricevuta")) or next((e for e in eff if e["id"] not in usati and abs(e["importo"] - x["importo"]) < 0.005 and e["scadenza"] == x["scadenza"]
                                                       and (not x.get("codice") or x["codice"] in (e["cliente"].get("codice_fiscale"), e["cliente"].get("partita_iva")))), None)
            if e and e["id"] not in usati:
                usati.add(e["id"])
            out.append({"riga": x, "effetto": e if e and e["id"] in usati else None})
        return out

    return r, tick


def build_scadenze(db, tenant, ferr) -> APIRouter:
    r = APIRouter(prefix="/api/scadenze")

    @r.put("/{kind}/{iid}")
    async def modifica(kind: Literal["invoices", "passive"], iid: str, body: RateIn, t: dict = Depends(tenant)):
        cid = t["cid"]
        tipo = "cliente" if kind == "invoices" else "fornitore"
        coll = db.invoices if kind == "invoices" else db.passive_invoices
        doc = await coll.find_one({"id": iid, "company_id": cid}, {"_id": 0, "data": 1, "netto": 1, "totale": 1})
        if not doc:
            coll = db.partite_aperte
            doc = await coll.find_one({"id": iid, "company_id": cid, "tipo": tipo}, {"_id": 0, "data": 1, "netto": 1, "totale": 1})
        if not doc:
            raise HTTPException(404, "Documento non trovato")
        if kind == "invoices" and await db.riba_effetti.find_one({"company_id": cid, "invoice_id": iid, "stato": {"$in": ["presentato", "maturato"]}}, {"_id": 1}):
            raise ferr(400, "rate", "Ci sono effetti Ri.Ba. presentati in banca per questo documento: per cambiare la scadenza registra prima l'insoluto")
        netto = _r2(doc.get("netto", doc["totale"]))
        s = _r2(sum(x.importo for x in body.rate))
        if abs(s - netto) > 0.01:
            raise ferr(422, "rate", f"La somma delle rate ({s:.2f} €) deve essere uguale al netto da pagare ({netto:.2f} €)".replace(".", ","))
        if any(x.scadenza < doc["data"] for x in body.rate):
            raise ferr(422, "rate", "Una scadenza non può precedere la data del documento")
        try:
            [date.fromisoformat(x.scadenza) for x in body.rate]
        except ValueError:
            raise ferr(422, "rate", "Data di scadenza non valida")
        rate = [{"scadenza": x.scadenza, "importo": _r2(x.importo)} for x in body.rate]
        await coll.update_one({"id": iid, "company_id": cid}, {"$set": {"rate_mod": rate, "rate_mod_at": _now(), "rate_mod_by": t["user"].get("name") or t["user"]["email"]}})
        return {"ok": True, "rate": rate}

    return r

import uuid
from datetime import date, datetime, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import ai_agent
import contabilita as coge
import ratei
import stampe_fiscali as stampe_mod
from fatturapa import compute_totals

DATE_RX = r"^\d{4}-\d{2}-\d{2}$"
RC_ALIQUOTE = (4.0, 5.0, 10.0, 22.0)
UE = {"AT", "BE", "BG", "CY", "HR", "DK", "EE", "FI", "FR", "DE", "GR", "IE", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "CZ", "RO", "SK", "SI", "ES", "SE", "HU"}
TIPI_AF = {"TD16": "Integrazione fattura reverse charge interno", "TD17": "Integrazione/autofattura acquisto servizi dall'estero",
           "TD18": "Integrazione acquisto beni intracomunitari", "TD19": "Integrazione/autofattura acquisto beni ex art. 17 c.2"}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _r2(v):
    return round(float(v or 0) + 0.0, 2)


def is_estero(f: dict) -> bool:
    return any((f.get(k) or "IT").upper() != "IT" for k in ("paese_iva", "nazione"))


def rc_righe(doc: dict, aliq: float) -> list:
    est = doc.get("estero") or is_estero(doc.get("fornitore") or {})
    return [{"idx": i, "natura": r.get("natura") or "N6.9", "imponibile": _r2(r.get("imponibile")), "aliquota": aliq, "imposta": _r2(_r2(r.get("imponibile")) * aliq / 100)}
            for i, r in enumerate(doc.get("riepilogo") or []) if ((r.get("natura") or "").startswith("N6") or (est and not r.get("imposta"))) and r.get("imponibile")]


def proposta_tipo(doc: dict) -> Optional[str]:
    f = doc.get("fornitore") or {}
    if not (doc.get("estero") or is_estero(f)):
        return "TD16" if any((r.get("natura") or "").startswith("N6") for r in doc.get("riepilogo") or []) else None
    return "TD17"


class RigaReg(BaseModel):
    aliquota: float = Field(ge=0, le=100)
    natura: Optional[str] = None
    imponibile: float = Field(ge=-100_000_000, le=100_000_000)
    imposta: float = Field(ge=-100_000_000, le=100_000_000)
    conto: Optional[str] = Field(default="", max_length=20)
    codice_iva: Optional[str] = Field(default="", max_length=8)
    detraibilita: Optional[float] = Field(default=None, ge=0, le=100)


class RegPassIn(BaseModel):
    data_registrazione: str = Field(pattern=DATE_RX)
    numero: str = Field(min_length=1, max_length=20)
    data: str = Field(pattern=DATE_RX)
    riepilogo: List[RigaReg] = Field(min_length=1, max_length=30)
    aliquota_rc: float = 22.0
    detraibilita_iva: float = Field(default=100, ge=0, le=100)
    autofattura: Optional[Literal["TD16", "TD17", "TD18", "TD19"]] = None
    ritenuta_aliquota: Optional[float] = Field(default=None, ge=0, le=100)
    ritenuta_imponibile: Optional[float] = Field(default=None, ge=0, le=100_000_000)
    rateo: Optional[ratei.RateoIn] = None
    registro_iva_id: Optional[str] = Field(default=None, max_length=64)


def build(db, tenant_accounting, deps):
    r = APIRouter(prefix="/api/passive")
    ferr, next_prog = deps["ferr"], deps["next_progressivo"]

    async def _doc(cid, pid):
        d = await db.passive_invoices.find_one({"id": pid, "company_id": cid}, {"_id": 0, "xml_b64": 0})
        if not d:
            raise HTTPException(404, "Fattura ricevuta non trovata")
        return d

    async def _applica(cid: str, d: dict, body: RegPassIn) -> dict:
        pt = (await db.parties.find_one({"id": d.get("party_id"), "company_id": cid}, {"_id": 0, "gestione_iva": 1, "codice_iva": 1})) or {}
        gest = pt.get("gestione_iva") or ""
        codici = {c["codice"]: c async for c in db.coa_iva.find({"company_id": cid, "codice": {"$in": [x.codice_iva for x in body.riepilogo if x.codice_iva] + [pt.get("codice_iva") or ""]}}, {"_id": 0})}
        today = datetime.now(timezone.utc).date().isoformat()
        try:
            date.fromisoformat(body.data)
            date.fromisoformat(body.data_registrazione)
        except ValueError:
            raise ferr(422, "data", "Data non valida")
        if body.data_registrazione < body.data or body.data_registrazione > today:
            raise ferr(422, "data_registrazione", "La data di registrazione deve essere tra la data del documento e oggi")
        if body.aliquota_rc not in RC_ALIQUOTE:
            raise ferr(422, "aliquota_rc", "Aliquota IVA per il reverse charge non valida (4, 5, 10 o 22%)")
        accs = {a["codice"] for a in await db.coa_accounts.find({"company_id": cid, "codice": {"$in": [x.conto for x in body.riepilogo if x.conto]}}, {"_id": 0, "codice": 1}).to_list(100)}
        for i, x in enumerate(body.riepilogo):
            if x.conto and x.conto not in accs:
                raise ferr(422, f"riepilogo.{i}.conto", f"Riga {i + 1}: conto {x.conto} inesistente nel piano dei conti")
            if x.aliquota == 0 and not x.natura:
                raise ferr(422, f"riepilogo.{i}.natura", f"Riga {i + 1}: indica la natura IVA per l'aliquota 0%")
        riep = []
        for x in body.riepilogo:
            nat = x.natura if x.aliquota == 0 else None
            cod = codici.get(x.codice_iva or "") or codici.get(pt.get("codice_iva") or "")
            if not cod or float(cod.get("aliquota") or 0) != x.aliquota or (x.aliquota == 0):
                cod = None
            det = x.detraibilita if x.detraibilita is not None else (float(cod["detraibilita"]) if cod and cod.get("detraibilita") is not None else None)
            ex = {"codice_iva": cod["codice"] if cod and (x.codice_iva or x.detraibilita is None) else (x.codice_iva or ""), "detraibilita": det} if det is not None else {}
            g = next((r for r in riep if r["aliquota"] == x.aliquota and r["natura"] == nat and r.get("detraibilita") == ex.get("detraibilita")), None)
            if g:
                g["imponibile"], g["imposta"] = _r2(g["imponibile"] + x.imponibile), _r2(g["imposta"] + x.imposta)
            else:
                riep.append({"aliquota": x.aliquota, "natura": nat, "imponibile": _r2(x.imponibile), "imposta": _r2(x.imposta), **ex})
        imp, iva = _r2(sum(x["imponibile"] for x in riep)), _r2(sum(x["imposta"] for x in riep))
        tot = _r2(imp + iva + (d.get("totale", 0) - d.get("imponibile", 0) - d.get("iva", 0) if d.get("origine") != "manuale" else 0))
        rit = _r2(d.get("ritenuta_importo"))
        rupd = {}
        if body.ritenuta_aliquota is not None:
            rbase = _r2(body.ritenuta_imponibile if body.ritenuta_imponibile is not None else imp)
            rit = _r2(rbase * body.ritenuta_aliquota / 100)
            rupd = {"ritenuta_importo": rit, "ritenuta_aliquota": body.ritenuta_aliquota if rit else 0, "ritenuta_imponibile": rbase if rit else 0, "ritenuta_auto": False}
            if rit and rit >= tot:
                raise ferr(422, "ritenuta_aliquota", "La ritenuta non può superare il totale della fattura")
        netto = _r2(tot - rit - (iva if d.get("split_payment") else 0))
        rate = [dict(x) for x in d.get("rate") or []]
        if rate:
            old = sum(x["importo"] for x in rate) or 1
            rate = [{**x, "importo": _r2(x["importo"] * netto / old)} for x in rate]
            rate[-1]["importo"] = _r2(netto - sum(x["importo"] for x in rate[:-1]))
        if d.get("rate_mod"):
            rm = [dict(x) for x in d["rate_mod"]]
            om = sum(x["importo"] for x in rm) or 1
            rm = [{**x, "importo": _r2(x["importo"] * netto / om)} for x in rm]
            rm[-1]["importo"] = _r2(netto - sum(x["importo"] for x in rm[:-1]))
            rupd["rate_mod"] = rm
        upd = {"numero": body.numero, "numero_display": body.numero, "data": body.data, "riepilogo": riep, "imponibile": imp, "iva": iva, "totale": tot, "netto": netto,
               "rate": rate, "detraibilita_iva": body.detraibilita_iva, "righe_costo": [{"conto": x.conto or "", "imponibile": _r2(x.imponibile), "aliquota": x.aliquota, "natura": x.natura or ""} for x in body.riepilogo] if any(x.conto for x in body.riepilogo) else [],
               "data_registrazione": body.data_registrazione, "anno_registrazione": int(body.data_registrazione[:4]), "estero": is_estero(d.get("fornitore") or {}) or gest in ("intra_ue", "extra_ue")} | rupd
        if any(d.get(k) != upd[k] for k in ("numero", "data", "riepilogo", "totale")) and not d.get("originale"):
            upd["originale"] = {k: d.get(k) for k in ("numero", "data", "riepilogo", "imponibile", "iva", "totale", "netto")}
        upd["reverse_charge"] = rc_righe({**d, **upd}, body.aliquota_rc) or None
        return upd

    def _proposta_rit(pt, doc):
        forf = pt.get("regime_percipiente") == "forfettario"
        if not (pt.get("soggetto_ritenuta") or forf) or doc.get("ritenuta_auto") is False or doc.get("tipo_documento") not in ("TD01", "TD06"):
            return None
        base = deps["base_ritenuta"](pt, doc) if pt.get("soggetto_ritenuta") else 0
        imp = doc.get("imponibile") or 0
        cassa = 0
        if pt.get("cassa_tipo") and not forf:
            cassa = (doc.get("cassa_info") or {}).get("importo") or round(imp - imp / (1 + (pt.get("cassa_aliquota") or 0) / 100), 2)
        aliq = float(pt.get("ritenuta_aliquota") or 0) if base else 0
        return {"aliquota": aliq, "imponibile": base, "importo": round(base * aliq / 100, 2), "cassa": cassa,
                "cassa_in_base": bool(pt.get("cassa_ritenuta")), "regime": pt.get("regime_percipiente") or "ordinario"}

    @r.post("/{pid}/registrazione/anteprima")
    async def anteprima(pid: str, body: RegPassIn, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        d = await _doc(cid, pid)
        upd = await _applica(cid, d, body)
        p = coge.params_of(await coge._company(db, cid))
        caus, descr, righe, data, extra_ = await coge.acquisto_righe(db, {**d, **upd}, p)
        pt = await db.parties.find_one({"id": d.get("party_id"), "company_id": cid}, {"_id": 0}) or {}
        rr = await db.ratei_risconti.find_one({"company_id": cid, "doc_id": pid}, {"_id": 0, "competenza_dal": 1, "competenza_al": 1, "tipo": 1, "note": 1})
        return {"ratei_risconti": bool(pt.get("ratei_risconti")), "aliquota_rc_fornitore": pt.get("aliquota_rc"), "iva_indetraibile": (extra_ or {}).get("iva_indetraibile"), "rateo_esistente": rr, "avvisi_percipiente": deps["avvisi_percipiente"](pt),
                "ritenuta_proposta": _proposta_rit(pt, {**d, **{k: v for k, v in upd.items() if not k.startswith("ritenuta")}}),"causale": caus, "descrizione": descr, "data": data, "righe": [x for x in righe if x.get("dare") or x.get("avere")], **upd,
                "autofattura_proposta": (pt.get("rc_default") or proposta_tipo({**d, **upd})) if upd["reverse_charge"] else None}

    @r.post("/{pid}/registrazione")
    async def registra(pid: str, body: RegPassIn, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        d = await _doc(cid, pid)
        if d["stato_reg"] == "registrata":
            raise HTTPException(400, "Fattura già registrata")
        await coge.check_aperto(db, cid, int(body.data_registrazione[:4]))
        upd = await _applica(cid, d, body)
        if body.autofattura and not upd["reverse_charge"]:
            raise ferr(422, "autofattura", "L'autofattura serve solo per reverse charge o acquisti dall'estero senza IVA")
        if body.autofattura and await db.invoices.find_one({"company_id": cid, "autofattura": True, "passive_id": pid}, {"_id": 1}):
            raise ferr(400, "autofattura", "Esiste già un'autofattura per questo documento: scegli 'Nessuna autofattura'")
        await coge.check_annullabile(db, cid, "acquisto", pid)
        await coge.HOOKS["iva_lock"](cid, pid, body.data_registrazione, body.registro_iva_id)
        try:
            await stampe_mod.check_giornale(db, cid, body.data_registrazione)
        except ValueError as ex:
            raise HTTPException(400, str(ex))
        if body.registro_iva_id and not await db.iva_registri.find_one({"company_id": cid, "id": body.registro_iva_id, "tipo": "acquisti"}):
            raise ferr(422, "registro_iva_id", "Registro IVA acquisti non valido")
        if body.rateo:
            ratei.valida(body.rateo, ferr, body.data_registrazione)
        else:
            await ratei.elimina_doc(db, cid, pid)
        last = await db.passive_invoices.find_one({"company_id": cid, "anno_registrazione": upd["anno_registrazione"]}, {"_id": 0, "protocollo": 1}, sort=[("protocollo", -1)])
        upd |= {"stato_reg": "registrata", "protocollo": ((last or {}).get("protocollo") or 0) + 1, "updated_at": _now(),
                **({"registro_iva_id": body.registro_iva_id} if body.registro_iva_id else {})}
        await db.passive_invoices.update_one({"id": pid, "company_id": cid}, {"$set": upd})
        await coge.annulla(db, cid, "acquisto", pid)
        doc = {**d, **upd}
        await coge.safe(coge.registra_acquisto(db, doc))
        await coge.safe(ai_agent.impara(db, cid, d, [x.model_dump() for x in body.riepilogo], t["user"].get("name") or t["user"]["email"]))
        if body.rateo:
            await ratei.da_registrazione(db, cid, "acquisto", doc, body.rateo, t["user"].get("name") or t["user"]["email"])
        af = await crea_autofattura(t, doc, body.autofattura) if body.autofattura else None
        return {**doc, "autofattura_id": af["id"] if af else None}

    async def crea_autofattura(t: dict, doc: dict, tipo: str) -> dict:
        cid, comp = t["cid"], t["company"]
        if await db.invoices.find_one({"company_id": cid, "autofattura": True, "passive_id": doc["id"]}, {"_id": 1}):
            raise HTTPException(400, "Autofattura già creata per questo documento")
        f = doc.get("fornitore") or {}
        naz = next(((f.get(k) or "").upper() for k in ("paese_iva", "nazione") if (f.get(k) or "IT").upper() != "IT"), "IT")
        ced = {"denominazione": f.get("denominazione") or "", "nazione": naz, "partita_iva": f.get("partita_iva") or ("" if naz in UE or naz == "IT" else "OO99999999999"),
               "codice_fiscale": f.get("codice_fiscale") if naz == "IT" else "", "indirizzo": f.get("indirizzo") or "-", "cap": f.get("cap") if naz == "IT" and f.get("cap") else "00000",
               "comune": f.get("comune") or "-", "provincia": f.get("provincia") if naz == "IT" else "", "regime_fiscale": "RF01"}
        cli = {k: comp.get(k) or "" for k in ("denominazione", "partita_iva", "codice_fiscale", "indirizzo", "cap", "comune", "provincia", "pec")} | {
            "nazione": "IT", "codice_destinatario": comp.get("codice_destinatario") or "0000000"}
        lines = [{"descrizione": f"{TIPI_AF[tipo]} - fattura n. {doc['numero']} del {doc['data'][8:10]}/{doc['data'][5:7]}/{doc['data'][:4]}", "quantita": 1,
                  "prezzo_unitario": x["imponibile"], "aliquota": x["aliquota"], "natura": None, "unita_misura": "", "sconto": ""} for x in doc["reverse_charge"]]
        if doc.get("tipo_documento") == "TD04":
            lines = [{**ln, "prezzo_unitario": -ln["prezzo_unitario"]} for ln in lines]
        tot = compute_totals(lines)
        anno = int(doc["data_registrazione"][:4])
        last = await db.invoices.find_one({"company_id": cid, "anno": anno, "sezionale": "AF"}, {"_id": 0, "numero": 1}, sort=[("numero", -1)])
        n = (last["numero"] if last else 0) + 1
        inv = {"id": str(uuid.uuid4()), "company_id": cid, "autofattura": True, "passive_id": doc["id"], "tipo_documento": tipo, "sezionale": "AF", "anno": anno, "numero": n,
               "numero_display": f"AF{n}/{anno}", "data": doc["data_registrazione"], "cedente": ced, "cliente": cli, "party_id": None, "lines": lines, **tot,
               "netto": tot["totale"], "rate": [], "scadenza": None, "modalita_pagamento": "MP05", "causale": TIPI_AF[tipo],
               "fattura_collegata": {"numero_display": doc["numero"], "data": doc["data"]}, "status": "bozza", "progressivo_invio": await next_prog(cid),
               "sdi_history": [], "created_by": t["user"]["user_id"], "created_by_name": t["user"].get("name") or t["user"]["email"], "created_at": _now()}
        await db.invoices.insert_one(dict(inv))
        await db.passive_invoices.update_one({"id": doc["id"]}, {"$set": {"autofattura_id": inv["id"], "autofattura_numero": inv["numero_display"]}})
        return inv

    @r.post("/{pid}/autofattura")
    async def autofattura(pid: str, tipo: Literal["TD16", "TD17", "TD18", "TD19"], t: dict = Depends(tenant_accounting)):
        d = await _doc(t["cid"], pid)
        if d["stato_reg"] != "registrata" or not d.get("reverse_charge"):
            raise HTTPException(400, "Registra prima la fattura con il reverse charge")
        return await crea_autofattura(t, d, tipo)

    return r, crea_autofattura

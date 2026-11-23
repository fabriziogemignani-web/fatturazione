import base64
import os
import tempfile
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator

import ai_agent
import ai_crediti
import contabilita as coge

AVVISO_GIORNI = 15
DEF_CONTI = {"conto_debito": "13.05.003", "conto_sanzioni": "30.14.003", "conto_interessi": "40.02.001"}
SYS_PDF = ("Sei un contabile italiano. Ricevi il PDF di un piano di rateizzazione dell'Agenzia delle Entrate (avviso bonario, controllo formale) "
           "o dell'Agenzia delle Entrate-Riscossione (cartelle). Estrai i dati e rispondi SOLO con JSON: "
           '{"ente": "Agenzia delle Entrate|Agenzia delle Entrate-Riscossione|altro", "numero": "numero piano, protocollo o avviso", '
           '"descrizione": "oggetto: tributo, anno, cartelle (max 200 caratteri)", "data": "AAAA-MM-GG data del piano o della comunicazione", '
           '"rate": [{"scadenza": "AAAA-MM-GG", "capitale": numero, "sanzioni": numero, "interessi": numero, "totale": numero}], '
           '"codici_tributo": ["..."], "note": "avvertenze importanti, es. decadenza (max 300 caratteri)"}. '
           "Importi in euro con il punto decimale. In 'interessi' metti interessi di dilazione e compensi di riscossione/aggio. "
           "Se una rata riporta solo il totale, mettilo in 'capitale' e 0 negli altri. Non inventare rate assenti.")


def _now():
    return datetime.now(timezone.utc).isoformat()


def r2(v) -> float:
    return round(float(v or 0) + 0.0, 2)


class RataIn(BaseModel):
    scadenza: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    capitale: float = Field(default=0, ge=0)
    sanzioni: float = Field(default=0, ge=0)
    interessi: float = Field(default=0, ge=0)


class PianoIn(BaseModel):
    ente: str = Field(min_length=1, max_length=80)
    numero: Optional[str] = Field(default="", max_length=80)
    descrizione: Optional[str] = Field(default="", max_length=300)
    data: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    conto_debito: Optional[str] = Field(default=DEF_CONTI["conto_debito"], max_length=12)
    conto_sanzioni: Optional[str] = Field(default=DEF_CONTI["conto_sanzioni"], max_length=12)
    conto_interessi: Optional[str] = Field(default=DEF_CONTI["conto_interessi"], max_length=12)
    note: Optional[str] = Field(default="", max_length=500)
    pdf_id: Optional[str] = None
    rate: List[RataIn] = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def _ok(self):
        if any(r.capitale + r.sanzioni + r.interessi <= 0 for r in self.rate):
            raise ValueError("Ogni rata deve avere un importo")
        self.rate.sort(key=lambda r: r.scadenza)
        return self


class PagaIn(BaseModel):
    data: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    conto: Optional[str] = Field(default="", max_length=12)


def _stato(r: dict, today: str) -> str:
    if r.get("pagamento"):
        return "pagata"
    if r["scadenza"] < today:
        return "scaduta"
    return "in_scadenza" if r["scadenza"] <= (date.fromisoformat(today) + timedelta(days=AVVISO_GIORNI)).isoformat() else "da_pagare"


def _arricchisci(p: dict, today: str) -> dict:
    rate = [{**r, "stato": _stato(r, today)} for r in p["rate"]]
    aperte = [r for r in rate if r["stato"] != "pagata"]
    return {**p, "rate": rate, "totale": r2(sum(r["totale"] for r in rate)), "pagato": r2(sum(r["totale"] for r in rate if r["stato"] == "pagata")),
            "residuo": r2(sum(r["totale"] for r in aperte)), "rate_pagate": len(rate) - len(aperte), "rate_scadute": sum(1 for r in aperte if r["stato"] == "scaduta"),
            "prossima": aperte[0] if aperte else None}


def build(db, tenant, tenant_accounting, deps) -> APIRouter:
    r = APIRouter(prefix="/api")
    ferr = deps["ferr"]

    async def _get(pid: str, cid: str) -> dict:
        p = await db.rateizzazioni.find_one({"id": pid, "company_id": cid, "annullata": {"$ne": True}}, {"_id": 0})
        if not p:
            raise HTTPException(404, "Piano di rateizzazione non trovato")
        return p

    async def _check_conti(cid: str, body: PianoIn):
        if not coge.attiva(await coge._company(db, cid)):
            return
        await coge.ensure_seed(db, cid)
        for f in ("conto_debito", "conto_sanzioni", "conto_interessi"):
            c = getattr(body, f)
            if not c or not await db.coa_accounts.find_one({"company_id": cid, "codice": c, "livello": 3}, {"_id": 1}):
                raise ferr(400, f, "Scegli un sottoconto esistente del piano dei conti")

    def _rate(body: PianoIn) -> list:
        return [{"n": i, **x.model_dump(), "totale": r2(x.capitale + x.sanzioni + x.interessi), "pagamento": None} for i, x in enumerate(body.rate, 1)]

    @r.post("/rateizzazioni/leggi-pdf")
    async def leggi_pdf(file: UploadFile = File(...), t: dict = Depends(tenant_accounting)):
        ai_crediti.controlla(t["company"])
        raw = await file.read()
        if not raw.startswith(b"%PDF"):
            raise HTTPException(400, "Il file non è un PDF")
        if len(raw) > 15 * 1024 * 1024:
            raise HTTPException(400, "PDF troppo grande (massimo 15 MB)")
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(raw)
            path = f.name
        txt, tokens = "", 0
        try:
            chat = ai_agent.LlmChat(api_key=ai_agent._key(), session_id=f"rat-{t['cid']}-{uuid.uuid4().hex[:8]}", system_message=SYS_PDF).with_model(*ai_agent.MODEL)
            msg = ai_agent.UserMessage(text="Estrai il piano di rateizzazione da questo PDF.", file_contents=[ai_agent.FileContentWithMimeType(file_path=path, mime_type="application/pdf")])
            async for ev in chat.stream_message(msg):
                if isinstance(ev, ai_agent.TextDelta):
                    txt += ev.content or ""
                elif isinstance(ev, ai_agent.StreamDone):
                    tokens = ev.usage.total_tokens if ev.usage else 0
                    break
            out = ai_agent._json(txt)
        except HTTPException:
            raise
        except Exception as ex:  # noqa: BLE001
            raise HTTPException(502, f"Lettura del PDF non riuscita: {ai_agent._err_ia(ex)}")
        finally:
            os.unlink(path)
        await ai_crediti.addebita(db, t["cid"], tokens or len(txt) // 3, "rateizzazione")
        pdf_id = str(uuid.uuid4())
        await db.rateizzazioni_pdf.insert_one({"id": pdf_id, "company_id": t["cid"], "nome": file.filename, "pdf_b64": base64.b64encode(raw).decode(), "created_at": _now()})
        rate = []
        for x in out.get("rate") or []:
            try:
                sc = date.fromisoformat(str(x.get("scadenza"))[:10]).isoformat()
            except ValueError:
                continue
            cap, san, inte = r2(x.get("capitale")), r2(x.get("sanzioni")), r2(x.get("interessi"))
            if cap + san + inte <= 0 and r2(x.get("totale")) > 0:
                cap = r2(x.get("totale"))
            rate.append({"scadenza": sc, "capitale": cap, "sanzioni": san, "interessi": inte})
        try:
            dt = date.fromisoformat(str(out.get("data"))[:10]).isoformat()
        except ValueError:
            dt = rate[0]["scadenza"] if rate else date.today().isoformat()
        cod = ", ".join(out.get("codici_tributo") or [])
        return {"pdf_id": pdf_id, "ente": (out.get("ente") or "Agenzia delle Entrate")[:80], "numero": (out.get("numero") or "")[:80],
                "descrizione": ((out.get("descrizione") or "") + (f" · tributi {cod}" if cod else ""))[:300], "data": dt,
                "note": (out.get("note") or "")[:500], "rate": sorted(rate, key=lambda x: x["scadenza"]), **DEF_CONTI}

    @r.get("/rateizzazioni")
    async def elenco(t: dict = Depends(tenant)):
        today = date.today().isoformat()
        rows = await db.rateizzazioni.find({"company_id": t["cid"], "annullata": {"$ne": True}}, {"_id": 0}).sort("data", -1).to_list(500)
        return {"piani": [_arricchisci(p, today) for p in rows], "conti_pagamento": await coge.conti_pagamento(db, t["cid"])}

    @r.post("/rateizzazioni")
    async def crea(body: PianoIn, t: dict = Depends(tenant_accounting)):
        await _check_conti(t["cid"], body)
        doc = {"id": str(uuid.uuid4()), "company_id": t["cid"], **body.model_dump(exclude={"rate"}), "rate": _rate(body),
               "created_by": t["user"].get("name") or t["user"]["email"], "created_at": _now()}
        await db.rateizzazioni.insert_one(doc)
        return _arricchisci(await _get(doc["id"], t["cid"]), date.today().isoformat())

    @r.put("/rateizzazioni/{pid}")
    async def modifica(pid: str, body: PianoIn, t: dict = Depends(tenant_accounting)):
        p = await _get(pid, t["cid"])
        if any(x.get("pagamento") for x in p["rate"]):
            raise HTTPException(400, "Il piano ha rate già pagate: annulla prima i pagamenti per modificarlo")
        await _check_conti(t["cid"], body)
        await db.rateizzazioni.update_one({"id": pid, "company_id": t["cid"]}, {"$set": {**body.model_dump(exclude={"rate"}), "rate": _rate(body), "updated_at": _now()}})
        return _arricchisci(await _get(pid, t["cid"]), date.today().isoformat())

    @r.delete("/rateizzazioni/{pid}")
    async def annulla(pid: str, t: dict = Depends(tenant_accounting)):
        p = await _get(pid, t["cid"])
        if any(x.get("pagamento") for x in p["rate"]):
            raise HTTPException(400, "Il piano ha rate già pagate: non può essere eliminato")
        await db.rateizzazioni.update_one({"id": pid, "company_id": t["cid"]}, {"$set": {"annullata": True, "annullata_il": _now()}})
        return {"ok": True}

    @r.get("/rateizzazioni/{pid}/pdf")
    async def pdf(pid: str, t: dict = Depends(tenant)):
        p = await _get(pid, t["cid"])
        f = await db.rateizzazioni_pdf.find_one({"id": p.get("pdf_id"), "company_id": t["cid"]}, {"_id": 0}) if p.get("pdf_id") else None
        if not f:
            raise HTTPException(404, "PDF del piano non disponibile")
        return Response(base64.b64decode(f["pdf_b64"]), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="piano-{pid[:8]}.pdf"'})

    @r.post("/rateizzazioni/{pid}/rate/{n}/paga")
    async def paga(pid: str, n: int, body: PagaIn, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        p = await _get(pid, cid)
        rata = next((x for x in p["rate"] if x["n"] == n), None)
        if not rata:
            raise HTTPException(404, "Rata non trovata")
        if rata.get("pagamento"):
            raise HTTPException(400, "Rata già pagata")
        if body.data < p["data"]:
            raise ferr(400, "data", "La data del pagamento non può precedere la data del piano")
        by = t["user"].get("name") or t["user"]["email"]
        pag = {"data": body.data, "conto": None, "coge_rif": None, "by": by, "at": _now()}
        opts = await coge.conti_pagamento(db, cid)
        if opts is not None:
            conto = body.conto or opts["default"].get("bonifico") or (opts["conti"][0]["conto"] if opts["conti"] else "")
            if conto not in {o["conto"] for o in opts["conti"]}:
                raise ferr(400, "conto", "Seleziona la banca o la cassa da cui hai pagato")
            cp = coge.params_of(await coge._company(db, cid))
            righe = [{"conto": p["conto_debito"], "dare": rata["capitale"]}, {"conto": p["conto_sanzioni"], "dare": rata["sanzioni"]},
                     {"conto": p["conto_interessi"], "dare": rata["interessi"]}, {"conto": conto, "avere": rata["totale"]}]
            try:
                e = await coge._insert(db, cid, cp, body.data, "GE", f"Rata {n}/{len(p['rate'])} rateizzazione {p['ente']} {p.get('numero') or ''}".strip(),
                                       righe, "rateizzazione", ref_id=f"{pid}-{n}", by=by)
            except ValueError as ex:
                raise HTTPException(400, f"Pagamento non registrato in prima nota: {ex}")
            pag |= {"conto": conto, "coge_entry_id": e["id"] if e else None, "coge_rif": f"prima nota n. {e['numero']}/{e['anno']}" if e else None}
        await db.rateizzazioni.update_one({"id": pid, "company_id": cid, "rate.n": n}, {"$set": {"rate.$.pagamento": pag}})
        return _arricchisci(await _get(pid, cid), date.today().isoformat())

    @r.delete("/rateizzazioni/{pid}/rate/{n}/paga")
    async def annulla_paga(pid: str, n: int, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        p = await _get(pid, cid)
        rata = next((x for x in p["rate"] if x["n"] == n), None)
        if not rata or not rata.get("pagamento"):
            raise HTTPException(400, "La rata non risulta pagata")
        await coge.check_annullabile(db, cid, "rateizzazione", f"{pid}-{n}")
        await coge.annulla(db, cid, "rateizzazione", f"{pid}-{n}")
        await db.rateizzazioni.update_one({"id": pid, "company_id": cid, "rate.n": n}, {"$set": {"rate.$.pagamento": None}})
        return _arricchisci(await _get(pid, cid), date.today().isoformat())

    async def _rate_aperte(cid: str) -> list:
        rows = await db.rateizzazioni.find({"company_id": cid, "annullata": {"$ne": True}}, {"_id": 0, "id": 1, "ente": 1, "numero": 1, "rate": 1}).to_list(500)
        return [{**x, "piano_id": p["id"], "ente": p["ente"], "numero": p.get("numero") or "", "di": len(p["rate"])} for p in rows for x in p["rate"] if not x.get("pagamento")]

    @r.get("/rateizzazioni-avvisi")
    async def avvisi(t: dict = Depends(tenant)):
        today = date.today().isoformat()
        lim = (date.today() + timedelta(days=AVVISO_GIORNI)).isoformat()
        rate = sorted((x for x in await _rate_aperte(t["cid"]) if x["scadenza"] <= lim), key=lambda x: x["scadenza"])
        sc = [x for x in rate if x["scadenza"] < today]
        return {"giorni": AVVISO_GIORNI, "scadute": sc, "in_scadenza": [x for x in rate if x["scadenza"] >= today],
                "totale_scaduto": r2(sum(x["totale"] for x in sc)), "totale_in_scadenza": r2(sum(x["totale"] for x in rate if x["scadenza"] >= today))}

    async def _saldi_contabili(cid: str, conti: list) -> dict:
        if not conti:
            return {}
        agg = db.coa_entries.aggregate([{"$match": {"company_id": cid}}, {"$unwind": "$righe"}, {"$match": {"righe.conto": {"$in": conti}}},
                                        {"$group": {"_id": "$righe.conto", "d": {"$sum": "$righe.dare"}, "a": {"$sum": "$righe.avere"}}}])
        return {x["_id"]: r2(x["d"] - x["a"]) async for x in agg}

    @r.get("/situazione-finanziaria")
    async def situazione(mesi: int = 6, t: dict = Depends(tenant)):
        mesi = max(1, min(mesi, 24))
        cid, today = t["cid"], date.today()
        accs = await db.bank_accounts.find({"company_id": cid}, {"_id": 0, "nome": 1, "banca": 1, "iban": 1, "saldo": 1, "saldo_at": 1}).to_list(200)
        opts = await coge.conti_pagamento(db, cid)
        cb = [o for o in (opts or {}).get("conti", []) if o["tipo"] in ("banca", "cassa")]
        sc = await _saldi_contabili(cid, [o["conto"] for o in cb])
        contabili = [{"conto": o["conto"], "nome": o["label"], "tipo": o["tipo"], "saldo": sc.get(o["conto"], 0.0)} for o in cb]
        con_saldo = [a for a in accs if a.get("saldo") is not None]
        if con_saldo:
            saldo0, fonte = r2(sum(a["saldo"] for a in con_saldo)), "estratto"
        else:
            saldo0, fonte = r2(sum(c["saldo"] for c in contabili)), "contabilita" if contabili else "nessuna"
        m = deps["moduli"](t["company"], t["user"])
        voci = []
        for tipo, ok, loader in (("incasso", m["fatture_attive"], deps["ledger"]), ("fornitore", m["fatture_passive"], deps["ledger_passive"])):
            if ok:
                for d in (await loader(cid))[0]:
                    for x in d.get("rate") or []:
                        if x["residuo"] > 0.005:
                            voci.append({"tipo": tipo, "scadenza": x["scadenza"], "importo": x["residuo"] if tipo == "incasso" else -x["residuo"],
                                         "label": f"{d['numero_display']} · {d['cliente']}", "ref": d["id"]})
        for x in await _rate_aperte(cid):
            voci.append({"tipo": "rateizzazione", "scadenza": x["scadenza"], "importo": -x["totale"], "label": f"Rata {x['n']}/{x['di']} {x['ente']} {x['numero']}".strip(), "ref": x["piano_id"]})
        for x in await deps["scadenze"](t):
            if not x.get("versato") and (x.get("importo") or 0) > 0:
                voci.append({"tipo": "fisco", "scadenza": x["scadenza"], "importo": -x["importo"], "label": f"F24 {x['descrizione']} · {x['periodo_label']}", "ref": x["key"],
                             "provvisorio": x.get("provvisorio")})
        m0 = today.replace(day=1)
        chiavi = []
        y, mm = m0.year, m0.month
        for _ in range(mesi):
            chiavi.append(f"{y}-{mm:02d}")
            y, mm = (y + 1, 1) if mm == 12 else (y, mm + 1)
        fine = chiavi[-1]
        KEYS = ("incasso", "fornitore", "rateizzazione", "fisco")
        righe = {k: {"mese": k, **{x: 0.0 for x in KEYS}} for k in chiavi}
        scaduto = {x: 0.0 for x in KEYS}
        for v in voci:
            k = v["scadenza"][:7]
            if v["scadenza"] < today.isoformat():
                scaduto[v["tipo"]] += v["importo"]
                v["scaduta"] = True
                k = chiavi[0]
            if k <= fine:
                righe[k][v["tipo"]] += v["importo"]
        saldo, out, minimo = saldo0, [], None
        for k in chiavi:
            rr = {x: r2(righe[k][x]) for x in KEYS}
            netto = r2(sum(rr.values()))
            saldo = r2(saldo + netto)
            out.append({"mese": k, **rr, "netto": netto, "saldo": saldo})
            if minimo is None or saldo < minimo["saldo"]:
                minimo = {"mese": k, "saldo": saldo}
        vicine = sorted((v for v in voci if v["scadenza"][:7] <= fine), key=lambda v: v["scadenza"])
        return {"saldo_iniziale": saldo0, "fonte_saldo": fonte, "banche_estratto": accs, "banche_contabili": contabili, "mesi": out, "minimo": minimo,
                "saldo_finale": saldo, "scaduto": {x: r2(v) for x, v in scaduto.items()},
                "totali": {x: r2(sum(o[x] for o in out)) for x in KEYS}, "voci": vicine[:300]}

    return r

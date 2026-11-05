import csv
import io
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError, DocumentTooLarge

from archivio_parser import extract_xml_files, parse_fattura

MAX_UPLOAD_FILES = 50
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
LIST_PROJ = {"_id": 0, "xml": 0, "righe": 0, "riepilogo": 0, "pagamenti": 0, "trasmissione": 0}
MAX_STORED_XML = 12 * 1024 * 1024
ATTACH_RX = re.compile(r"(<(?:\w+:)?Attachment>).*?(</(?:\w+:)?Attachment>)", re.S)


def norm_vat(v: str) -> str:
    v = re.sub(r"[\s.\-]", "", v or "").upper()
    return v[2:] if re.match(r"^[A-Z]{2}\d", v) else v


def _now():
    return datetime.now(timezone.utc).isoformat()


def _fmt(n):
    return f"{n:.2f}".replace(".", ",")


def _safe(v) -> str:
    s = str(v or "")
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def build_router(db, tenant, tenant_accounting) -> APIRouter:
    r = APIRouter(prefix="/api/archivio")
    INV, ANAG = db.arch_invoices, db.arch_anagrafiche

    async def upsert_anag(cid: str, party: dict, ruolo: str) -> Optional[str]:
        chiave = norm_vat(party.get("piva")) or (party.get("codice_fiscale") or "").upper()
        if not chiave:
            return None
        fields = {k: v for k, v in party.items() if v} | {"chiave": chiave, "ruolo": ruolo, "updated_at": _now()}
        q = {"company_id": cid, "ruolo": ruolo, "chiave": chiave}
        upd = {"$set": fields, "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": _now()}}
        try:
            doc = await ANAG.find_one_and_update(q, upd, upsert=True, return_document=True)
        except DuplicateKeyError:
            doc = await ANAG.find_one_and_update(q, {"$set": fields}, return_document=True)
        return doc["id"]

    async def store(t: dict, inv: dict, raw: str, filename: str) -> dict:
        cid, comp = t["cid"], t["company"]
        mine = {x for x in (norm_vat(comp.get("partita_iva")), (comp.get("codice_fiscale") or "").upper()) if x}
        ced, ces = inv["cedente"], inv["cessionario"]
        attiva = bool(mine & {norm_vat(ced.get("piva")), (ced.get("codice_fiscale") or "").upper()})
        passiva = bool(mine & {norm_vat(ces.get("piva")), (ces.get("codice_fiscale") or "").upper()})
        if not attiva and not passiva:
            return {"status": "error", "message": f"La P.IVA {comp.get('partita_iva')} non compare né come cedente né come cessionario", "numero": inv["numero"]}
        tipo = "attiva" if attiva else "passiva"
        ctrp = ces if attiva else ced
        dedup = f"{norm_vat(ced.get('piva')) or ced.get('codice_fiscale')}|{inv['tipo_documento']}|{inv['numero']}|{inv['data']}"
        if await INV.find_one({"company_id": cid, "dedup_key": dedup}, {"_id": 1}):
            return {"status": "duplicate", "message": "Fattura già presente in archivio", "numero": inv["numero"], "tipo": tipo}
        anag_id = await upsert_anag(cid, ctrp, "cliente" if attiva else "fornitore")
        stripped = len(raw) > MAX_STORED_XML
        if stripped:
            raw = ATTACH_RX.sub(r"\1\2", raw)
        doc = {**inv, "id": str(uuid.uuid4()), "company_id": cid, "tipo": tipo, "controparte_id": anag_id, "allegati_rimossi": stripped,
               "controparte_nome": ctrp.get("denominazione", ""), "controparte_piva": norm_vat(ctrp.get("piva")) or ctrp.get("codice_fiscale", ""),
               "filename": filename, "xml": raw, "dedup_key": dedup, "created_at": _now()}
        try:
            await INV.insert_one(doc)
        except DuplicateKeyError:
            return {"status": "duplicate", "message": "Fattura già presente in archivio", "numero": inv["numero"], "tipo": tipo}
        except DocumentTooLarge:
            return {"status": "error", "message": "Fattura troppo grande da archiviare (oltre 16 MB anche senza allegati)", "numero": inv["numero"]}
        return {"status": "ok", "message": f"Fattura {tipo} importata" + (" (allegati PDF non conservati: file troppo grande)" if stripped else ""), "numero": inv["numero"], "tipo": tipo, "id": doc["id"]}

    @r.post("/upload")
    async def upload(files: List[UploadFile] = File(...), t: dict = Depends(tenant_accounting)):
        if len(files) > MAX_UPLOAD_FILES:
            raise HTTPException(400, f"Massimo {MAX_UPLOAD_FILES} file per richiesta")
        if not t["company"].get("partita_iva"):
            raise HTTPException(400, "Inserisci la Partita IVA in Dati azienda prima di importare")
        results = []
        for f in files:
            data = await f.read(MAX_UPLOAD_BYTES + 1)
            if len(data) > MAX_UPLOAD_BYTES:
                results.append({"filename": f.filename, "status": "error", "message": "File troppo grande (max 100 MB)"})
                continue
            for name, xml_bytes, err in extract_xml_files(f.filename or "file", data):
                if err:
                    results.append({"filename": name, "status": "error", "message": err})
                    continue
                try:
                    invoices, raw = parse_fattura(xml_bytes)
                except ValueError as e:
                    results.append({"filename": name, "status": "error", "message": str(e)})
                    continue
                for inv in invoices:
                    results.append({"filename": name, **await store(t, inv, raw, name)})
        return {"results": results}

    def query(cid, tipo=None, anno=None, q=None, anagrafica_id=None, tipo_documento=None):
        qq = {"company_id": cid}
        for k, v in (("tipo", tipo), ("anno", anno), ("controparte_id", anagrafica_id)):
            if v:
                qq[k] = v
        if tipo_documento:
            qq["tipo_documento"] = tipo_documento.upper()
        if q and q.strip():
            rx = {"$regex": re.escape(q.strip()), "$options": "i"}
            qq["$or"] = [{"numero": rx}, {"controparte_nome": rx}, {"controparte_piva": rx}, {"causale": rx}, {"righe.descrizione": rx}, {"filename": rx}]
        return qq

    def sort(order):
        return [("anno", DESCENDING), ("numero_key", DESCENDING if order == "desc" else ASCENDING)]

    @r.get("/invoices")
    async def list_invoices(tipo: Optional[str] = None, anno: Optional[int] = None, q: Optional[str] = None, anagrafica_id: Optional[str] = None,
                            order: str = "asc", page: int = 1, limit: int = 50, tipo_documento: Optional[str] = None, t: dict = Depends(tenant)):
        qq = query(t["cid"], tipo, anno, q, anagrafica_id, tipo_documento)
        limit = max(1, min(limit, 200))
        items = await INV.find(qq, LIST_PROJ).sort(sort(order)).skip((max(page, 1) - 1) * limit).limit(limit).to_list(limit)
        agg = await INV.aggregate([{"$match": qq}, {"$group": {"_id": None, "t": {"$sum": "$totale"}, "n": {"$sum": 1}}}]).to_list(1)
        return {"items": items, "total": agg[0]["n"] if agg else 0, "page": page, "limit": limit, "somma_totale": round(agg[0]["t"], 2) if agg else 0}

    @r.get("/years")
    async def years(tipo: Optional[str] = None, t: dict = Depends(tenant)):
        return sorted(await INV.distinct("anno", {"company_id": t["cid"], **({"tipo": tipo} if tipo else {})}), reverse=True)

    @r.get("/doc-types")
    async def doc_types(tipo: Optional[str] = None, anno: Optional[int] = None, t: dict = Depends(tenant)):
        rows = await INV.aggregate([{"$match": query(t["cid"], tipo, anno)}, {"$group": {"_id": "$tipo_documento", "n": {"$sum": 1}}}, {"$sort": {"_id": 1}}]).to_list(100)
        return [{"code": x["_id"], "n": x["n"]} for x in rows if x["_id"]]

    @r.get("/export")
    async def export(tipo: Optional[str] = None, anno: Optional[int] = None, q: Optional[str] = None, anagrafica_id: Optional[str] = None,
                     order: str = "asc", tipo_documento: Optional[str] = None, t: dict = Depends(tenant)):
        buf = io.StringIO()
        buf.write("\ufeff")
        w = csv.writer(buf, delimiter=";")
        w.writerow(["Tipo", "Anno", "Numero", "Data", "Tipo documento", "Cliente/Fornitore", "P.IVA/CF", "Imponibile", "IVA", "Totale", "Divisa", "File"])
        async for d in INV.find(query(t["cid"], tipo, anno, q, anagrafica_id, tipo_documento), LIST_PROJ).sort(sort(order)):
            w.writerow([d["tipo"], d["anno"], _safe(d["numero"]), d["data"], _safe(d.get("tipo_documento")), _safe(d.get("controparte_nome")),
                        _safe(d.get("controparte_piva")), _fmt(d.get("imponibile", 0)), _fmt(d.get("imposta", 0)), _fmt(d.get("totale", 0)),
                        _safe(d.get("divisa")), _safe(d.get("filename"))])
        name = f"archivio_{tipo or 'tutte'}_{anno or 'tutti-anni'}.csv"
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @r.get("/invoices/{iid}")
    async def get_invoice(iid: str, t: dict = Depends(tenant)):
        d = await INV.find_one({"id": iid, "company_id": t["cid"]}, {"_id": 0, "xml": 0})
        if not d:
            raise HTTPException(404, "Fattura non trovata")
        return d

    @r.get("/invoices/{iid}/xml")
    async def get_xml(iid: str, t: dict = Depends(tenant)):
        d = await INV.find_one({"id": iid, "company_id": t["cid"]}, {"xml": 1, "numero": 1, "filename": 1})
        if not d:
            raise HTTPException(404, "Fattura non trovata")
        fname = re.sub(r"\.p7m$", "", (d.get("filename") or f"fattura_{d['numero']}").split("/")[-1], flags=re.I)
        fname = fname if fname.lower().endswith(".xml") else fname + ".xml"
        fname = re.sub(r'[^\w.\-]', "_", fname)
        return Response(d["xml"], media_type="application/xml", headers={"Content-Disposition": f'attachment; filename="{fname}"'})

    @r.delete("/invoices/{iid}")
    async def delete_invoice(iid: str, t: dict = Depends(tenant_accounting)):
        d = await INV.find_one_and_delete({"id": iid, "company_id": t["cid"]}, {"controparte_id": 1})
        if not d:
            raise HTTPException(404, "Fattura non trovata")
        aid = d.get("controparte_id")
        if aid and not await INV.count_documents({"company_id": t["cid"], "controparte_id": aid}, limit=1):
            await ANAG.delete_one({"id": aid, "company_id": t["cid"]})
        return {"ok": True}

    @r.get("/anagrafiche")
    async def list_anag(ruolo: Optional[str] = None, q: Optional[str] = None, anno: Optional[int] = None, t: dict = Depends(tenant)):
        qq = {"company_id": t["cid"], **({"ruolo": ruolo} if ruolo else {})}
        if q and q.strip():
            rx = {"$regex": re.escape(q.strip()), "$options": "i"}
            qq["$or"] = [{"denominazione": rx}, {"chiave": rx}, {"codice_fiscale": rx}, {"comune": rx}]
        docs = await ANAG.find(qq, {"_id": 0}).sort("denominazione", ASCENDING).to_list(5000)
        m = {"company_id": t["cid"], **({"tipo": "attiva" if ruolo == "cliente" else "passiva"} if ruolo else {}), **({"anno": anno} if anno else {})}
        counts = {c["_id"]: c async for c in INV.aggregate([{"$match": m}, {"$group": {"_id": "$controparte_id", "n": {"$sum": 1}, "totale": {"$sum": "$totale"}}}])}
        out = []
        for a in docs:
            c = counts.get(a["id"], {})
            if anno and not c:
                continue
            out.append(a | {"n_fatture": c.get("n", 0), "totale_fatture": round(c.get("totale", 0), 2)})
        return out

    @r.get("/anagrafiche/{aid}")
    async def get_anag(aid: str, t: dict = Depends(tenant)):
        a = await ANAG.find_one({"id": aid, "company_id": t["cid"]}, {"_id": 0})
        if not a:
            raise HTTPException(404, "Anagrafica non trovata")
        tipo = "attiva" if a["ruolo"] == "cliente" else "passiva"
        agg = await INV.aggregate([{"$match": {"company_id": t["cid"], "controparte_id": aid, "tipo": tipo}},
                                   {"$group": {"_id": "$anno", "n": {"$sum": 1}, "totale": {"$sum": "$totale"}}}, {"$sort": {"_id": -1}}]).to_list(100)
        return a | {"per_anno": [{"anno": g["_id"], "n": g["n"], "totale": round(g["totale"], 2)} for g in agg],
                    "n_fatture": sum(g["n"] for g in agg), "totale_fatture": round(sum(g["totale"] for g in agg), 2)}

    @r.get("/stats")
    async def stats(anno: Optional[int] = None, t: dict = Depends(tenant)):
        m = {"company_id": t["cid"], **({"anno": anno} if anno else {})}
        groups = await INV.aggregate([{"$match": m}, {"$group": {"_id": "$tipo", "n": {"$sum": 1}, "totale": {"$sum": "$totale"}, "imposta": {"$sum": "$imposta"}}}]).to_list(10)
        monthly = await INV.aggregate([{"$match": m}, {"$group": {"_id": {"m": {"$substr": ["$data", 5, 2]}, "t": "$tipo"}, "totale": {"$sum": "$totale"}}}]).to_list(100)
        months = [{"mese": f"{i:02d}", "attiva": 0, "passiva": 0} for i in range(1, 13)]
        for x in monthly:
            if x["_id"]["m"].isdigit() and 1 <= int(x["_id"]["m"]) <= 12:
                months[int(x["_id"]["m"]) - 1][x["_id"]["t"]] = round(x["totale"], 2)
        return {"per_tipo": {g["_id"]: {"n": g["n"], "totale": round(g["totale"], 2), "imposta": round(g["imposta"], 2)} for g in groups},
                "mensile": months, "recenti": await INV.find(m, LIST_PROJ).sort("created_at", DESCENDING).limit(6).to_list(6),
                "n_clienti": await ANAG.count_documents({"company_id": t["cid"], "ruolo": "cliente"}),
                "n_fornitori": await ANAG.count_documents({"company_id": t["cid"], "ruolo": "fornitore"})}

    return r


async def ensure_indexes(db):
    await db.arch_invoices.create_index([("company_id", 1), ("dedup_key", 1)], unique=True)
    await db.arch_invoices.create_index([("company_id", 1), ("tipo", 1), ("anno", -1), ("numero_key", 1)])
    await db.arch_invoices.create_index([("company_id", 1), ("controparte_id", 1)])
    await db.arch_invoices.create_index("id", unique=True)
    await db.arch_anagrafiche.create_index([("company_id", 1), ("ruolo", 1), ("chiave", 1)], unique=True)
    await db.arch_anagrafiche.create_index("id", unique=True)

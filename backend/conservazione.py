import base64
import hashlib
import json
import re
import uuid
from datetime import date, datetime, timezone
from io import BytesIO
from typing import List, Literal, Optional
from xml.sax.saxutils import escape

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

import sdi_providers as sdip
from estratto import eur, itd, _tbl

TIPI = {
    "fattura_emessa": ("Fatture emesse", "fatture"),
    "fattura_ricevuta": ("Fatture ricevute", "fatture"),
    "registro_iva_vendite": ("Registro IVA vendite", "registro-iva-vendite"),
    "registro_iva_acquisti": ("Registro IVA acquisti", "registro-iva-acquisti"),
    "libro_giornale": ("Libro giornale", "libro-giornale"),
    "corrispettivi": ("Registro corrispettivi", None),
    "f24": ("Modelli F24", None),
}
ANNUALI = {"registro_iva_vendite", "registro_iva_acquisti", "libro_giornale", "corrispettivi"}
BASE = {"sandbox": "https://preservation-sandbox.api.acubeapi.com", "production": "https://preservation.api.acubeapi.com"}
LIST_PROJ = {"_id": 0, "content_b64": 0, "allegati.content_b64": 0, "acube.receipt_b64": 0}
TRIB = {"1040": "Ritenute su redditi di lavoro autonomo"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def table_pdf(company: dict, titolo: str, anno: int, head: list, rows: list, widths: list, right: tuple, riepilogo: Optional[list] = None) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm, title=f"{titolo} {anno}")
    ss = getSampleStyleSheet()
    sm = ParagraphStyle("sm", parent=ss["Normal"], fontSize=8.5, leading=11)
    e = lambda s: escape(str(s or ""))  # noqa: E731
    story = [Paragraph(f"<b>{e(company.get('denominazione'))}</b> · P.IVA {e(company.get('partita_iva'))} · {e(company.get('indirizzo'))} {e(company.get('cap'))} {e(company.get('comune'))}", sm),
             Paragraph(f"{e(titolo)} — anno {anno}", ss["Heading2"]),
             Paragraph(f"Documento generato il {itd(date.today().isoformat())} per l'archivio di conservazione · {len(rows)} righe", sm), Spacer(1, 6)]
    body = [[str(c)[:70] for c in r] for r in rows] or [["Nessun movimento nell'anno"] + [""] * (len(head) - 1)]
    story.append(_tbl([head] + body, [w * mm for w in widths], right_cols=right))
    if riepilogo:
        story += [Spacer(1, 10), Paragraph("Riepilogo", ss["Heading3"])]
        story.append(_tbl(riepilogo, [60 * mm] + [40 * mm] * (len(riepilogo[0]) - 1), right_cols=tuple(range(1, len(riepilogo[0])))))
    doc.build(story)
    return buf.getvalue()


def _iva_riepilogo(r: dict) -> list:
    return [["Aliquota / natura", "Documenti", "Imponibile", "Imposta"]] + [[x["codice"], x["documenti"], eur(x["imponibile"]), eur(x["imposta"])] for x in r["totali"]] + \
        [["Totale", "", eur(r["imponibile"]), eur(r["imposta"])]]


def _sum(rie, k):
    return round(sum(x[k] for x in rie), 2)


class ArchiviaIn(BaseModel):
    tipo: Literal[tuple(TIPI)]
    anno: int = Field(ge=2000, le=2100)
    rif: List[str] = Field(min_length=1, max_length=100)


class IdsIn(BaseModel):
    ids: List[str] = Field(default_factory=list, max_length=100)


class CfgIn(BaseModel):
    usa_sdi: bool = False
    ambiente: Literal["sandbox", "production"] = "sandbox"
    email: Optional[str] = Field(default="", max_length=255)
    password: Optional[str] = Field(default=None, max_length=255)


def build(db, tenant, tenant_accounting, tenant_admin, deps) -> APIRouter:
    r = APIRouter(prefix="/api/conservazione")
    fernet = deps["fernet"]

    # ---------- documenti da archiviare
    async def _genera(t: dict, tipo: str, anno: int, rif: str) -> dict:
        comp, cid = t["company"], t["cid"]
        if tipo == "fattura_emessa":
            inv = await db.invoices.find_one({"id": rif, "company_id": cid, "status": {"$in": list(deps["sent"])}}, {"_id": 0})
            if not inv:
                raise ValueError("fattura non trovata o non trasmessa allo SDI")
            xml, fname = deps["xml"](comp, inv)
            ric = [h for h in inv.get("sdi_history") or [] if h.get("status") != "bozza"]
            c = inv.get("cliente") or {}
            return {"titolo": f"Fattura {inv['numero_display']} del {itd(inv['data'])} - {c.get('denominazione', '')}", "file_name": fname, "mime": "application/xml",
                    "content": xml.encode() if isinstance(xml, str) else xml,
                    "allegati": [("ricevute_sdi.json", "application/json", json.dumps({"sdi_id": inv.get("sdi_id"), "stato": inv["status"], "notifiche": ric}, ensure_ascii=False, indent=1).encode())],
                    "meta": {"numero": inv["numero_display"], "data": inv["data"], "totale": inv["totale"],
                             "controparte": {"denominazione_organizzazione": c.get("denominazione") or "-", "codice_fiscale_partita_iva": c.get("partita_iva") or c.get("codice_fiscale") or "-"}}}
        if tipo == "fattura_ricevuta":
            p = await db.passive_invoices.find_one({"id": rif, "company_id": cid}, {"_id": 0})
            if not p:
                raise ValueError("fattura ricevuta non trovata")
            f = p.get("fornitore") or {}
            name = re.sub(r"(?i)\.p7m$", "", re.sub(r"[^\w.\-]", "_", p.get("file_name") or f"fattura_{p['numero']}.xml"))
            info = {k: v for k, v in p.items() if k.startswith("sdi") or k in ("origine", "created_at", "hash", "stato_reg", "protocollo", "data_registrazione")}
            return {"titolo": f"Fattura {p['numero']} del {itd(p['data'])} - {f.get('denominazione', '')}", "file_name": name if name.endswith(".xml") else name + ".xml",
                    "mime": "application/xml", "content": base64.b64decode(p["xml_b64"]),
                    "allegati": [("dati_ricezione_sdi.json", "application/json", json.dumps(info, ensure_ascii=False, indent=1, default=str).encode())],
                    "meta": {"numero": p["numero"], "data": p["data"], "totale": p.get("totale"),
                             "controparte": {"denominazione_organizzazione": f.get("denominazione") or "-", "codice_fiscale_partita_iva": f.get("partita_iva") or f.get("codice_fiscale") or "-"}}}
        if tipo == "f24":
            v = await db.f24_versamenti.find_one({"company_id": cid, "key": rif}, {"_id": 0})
            if not v:
                raise ValueError("versamento F24 non trovato")
            banche = comp.get("banche") or []
            banca = next((b for b in banche if b.get("predefinita")), None) or (banche[0] if banche else {})
            deb = {"codice": v["codice"], "descrizione": TRIB.get(v["codice"], "Versamento IVA"), "anno_riferimento": int(rif[4:8]), "importo": v["importo"], "scadenza": v["data"]}
            pdf = deps["f24_pdf"](comp, banca, deb, [], v["data"])
            return {"titolo": f"F24 {v['codice']} {rif} versato il {itd(v['data'])} - {eur(v['importo'])}", "file_name": f"F24_{rif}.pdf", "mime": "application/pdf",
                    "content": pdf, "allegati": [], "meta": {"data": v["data"], "importo": v["importo"]}}
        if tipo in ("registro_iva_vendite", "registro_iva_acquisti", "corrispettivi"):
            x = await deps[tipo](anno=anno, dal=None, al=None, t=t)
            if tipo == "registro_iva_vendite":
                head, w, right = ["Numero", "Data", "Tipo", "Cliente", "P.IVA / CF", "Imponibile", "Imposta", "Totale"], [24, 22, 14, 80, 34, 32, 30, 32], (5, 6, 7)
                rows = [[d["numero"], itd(d["data"]), d["tipo_documento"], d["cliente"], d["partita_iva"] or "", eur(_sum(d["riepilogo"], "imponibile")),
                         eur(_sum(d["riepilogo"], "imposta")), eur(d["totale"])] for d in x["rows"]]
            elif tipo == "registro_iva_acquisti":
                head, w, right = ["Prot.", "Registrata", "Data doc.", "Numero", "Fornitore", "P.IVA / CF", "Imponibile", "Imposta", "Indetraib.", "Totale"], [14, 22, 22, 26, 66, 32, 26, 24, 22, 26], (6, 7, 8, 9)
                rows = [[d.get("protocollo") or "", itd(d.get("data_registrazione") or ""), itd(d["data"]), d["numero"], d["fornitore"], d["partita_iva"] or "",
                         eur(_sum(d["riepilogo"], "imponibile")), eur(_sum(d["riepilogo"], "imposta")), eur(d["iva_indetraibile"]), eur(d["totale"])] for d in x["rows"]]
            else:
                head, w, right = ["Data", "Matricola", "Documenti", "Imponibile", "Imposta", "Totale"], [30, 60, 30, 50, 50, 50], (2, 3, 4, 5)
                rows = [[itd(d["data"]), d.get("matricola") or "", d.get("n_documenti") or "", eur(_sum(d["riepilogo"], "imponibile")),
                         eur(_sum(d["riepilogo"], "imposta")), eur(d["totale"])] for d in x["rows"]]
            pdf = table_pdf(comp, TIPI[tipo][0], anno, head, rows, w, right, _iva_riepilogo(x))
        else:
            ents = await db.coa_entries.find({"company_id": cid, "anno": anno}, {"_id": 0}).sort([("data", 1), ("numero", 1)]).to_list(50000)
            rows = []
            for en in ents:
                for i, rg in enumerate(en["righe"]):
                    first = i == 0
                    rows.append([itd(en["data"]) if first else "", en["numero"] if first else "", en["causale"] if first else "", en["descrizione"] if first else "",
                                 rg["conto"], (rg.get("conto_descrizione") or "") + (f" - {rg['party_nome']}" if rg.get("party_nome") else ""),
                                 eur(rg["dare"]) if rg["dare"] else "", eur(rg["avere"]) if rg["avere"] else ""])
            dare = round(sum(rg["dare"] for en in ents for rg in en["righe"]), 2)
            avere = round(sum(rg["avere"] for en in ents for rg in en["righe"]), 2)
            pdf = table_pdf(comp, "Libro giornale", anno, ["Data", "N.", "Caus.", "Descrizione", "Conto", "Descrizione conto", "Dare", "Avere"], rows,
                            [20, 12, 14, 70, 22, 76, 29, 29], (6, 7), [["", "Registrazioni", "Dare", "Avere"], ["Totale", str(len(ents)), eur(dare), eur(avere)]])
        return {"titolo": f"{TIPI[tipo][0]} {anno}", "file_name": f"{tipo}_{anno}.pdf", "mime": "application/pdf", "content": pdf, "allegati": [], "meta": {}}

    @r.get("/candidati")
    async def candidati(tipo: Literal[tuple(TIPI)], anno: int, t: dict = Depends(tenant)):
        cid = t["cid"]
        done = set(await db.cons_docs.distinct("rif", {"company_id": cid, "tipo": tipo}))
        if tipo == "fattura_emessa":
            xs = await db.invoices.find({"company_id": cid, "anno": anno, "status": {"$in": list(deps["sent"])}},
                                        {"_id": 0, "id": 1, "numero_display": 1, "data": 1, "cliente.denominazione": 1, "totale": 1}).sort([("data", 1), ("numero", 1)]).to_list(10000)
            items = [{"rif": x["id"], "label": f"Fattura {x['numero_display']} - {(x.get('cliente') or {}).get('denominazione', '')}", "data": x["data"], "importo": x["totale"]} for x in xs]
        elif tipo == "fattura_ricevuta":
            xs = await db.passive_invoices.find({"company_id": cid, "data": {"$regex": f"^{anno}-"}},
                                                {"_id": 0, "id": 1, "numero": 1, "data": 1, "fornitore.denominazione": 1, "totale": 1}).sort("data", 1).to_list(10000)
            items = [{"rif": x["id"], "label": f"Fattura {x['numero']} - {(x.get('fornitore') or {}).get('denominazione', '')}", "data": x["data"], "importo": x.get("totale")} for x in xs]
        elif tipo == "f24":
            xs = await db.f24_versamenti.find({"company_id": cid, "key": {"$regex": f"^(IVA|RIT)-{anno}-"}}, {"_id": 0}).sort("data", 1).to_list(500)
            items = [{"rif": x["key"], "label": f"F24 codice {x['codice']} ({x['key']})", "data": x["data"], "importo": x["importo"]} for x in xs]
        else:
            items = [{"rif": str(anno), "label": f"{TIPI[tipo][0]} {anno}", "data": f"{anno}-12-31", "importo": None,
                      "nota": None if anno < date.today().year else "Disponibile a fine anno"}]
        return {"items": [{**i, "archiviato": i["rif"] in done} for i in items]}

    @r.post("/archivia")
    async def archivia(body: ArchiviaIn, t: dict = Depends(tenant_accounting)):
        if body.tipo in ANNUALI and (body.rif != [str(body.anno)] or body.anno >= date.today().year):
            raise HTTPException(400, "I registri annuali si archiviano solo ad anno concluso")
        out = {"archiviati": 0, "gia_presenti": 0, "errori": []}
        for rif in dict.fromkeys(body.rif):
            if await db.cons_docs.find_one({"company_id": t["cid"], "tipo": body.tipo, "rif": rif}, {"_id": 1}):
                out["gia_presenti"] += 1
                continue
            try:
                g = await _genera(t, body.tipo, body.anno, rif)
            except ValueError as e:
                out["errori"].append({"rif": rif, "errore": str(e)})
                continue
            doc = {"id": str(uuid.uuid4()), "company_id": t["cid"], "tipo": body.tipo, "anno": body.anno, "rif": rif, "titolo": g["titolo"],
                   "file_name": g["file_name"], "mime": g["mime"], "size": len(g["content"]), "sha256": _sha(g["content"]),
                   "content_b64": base64.b64encode(g["content"]).decode(), "meta": g["meta"],
                   "allegati": [{"file_name": n, "mime": m, "size": len(b), "sha256": _sha(b), "content_b64": base64.b64encode(b).decode()} for n, m, b in g["allegati"]],
                   "conserva_fino": f"{body.anno + 10}-12-31", "acube": None, "created_at": _now(), "created_by": t["user"].get("name") or t["user"]["email"]}
            try:
                await db.cons_docs.insert_one(dict(doc))
                out["archiviati"] += 1
            except DuplicateKeyError:
                out["gia_presenti"] += 1
        return out

    @r.get("")
    async def elenco(anno: Optional[int] = None, tipo: Optional[str] = None, t: dict = Depends(tenant)):
        q = {"company_id": t["cid"], **({"anno": anno} if anno else {}), **({"tipo": tipo} if tipo in TIPI else {})}
        docs = await db.cons_docs.find(q, LIST_PROJ).sort([("anno", -1), ("tipo", 1), ("created_at", 1)]).to_list(20000)
        cfg = await _cfg(t["company"])
        anni = sorted(set(await db.cons_docs.distinct("anno", {"company_id": t["cid"]})) | {date.today().year, date.today().year - 1}, reverse=True)
        for d in docs:
            d["conservatore"] = bool(TIPI[d["tipo"]][1])
        return {"documenti": docs, "anni": anni, "tipi": [{"id": k, "label": v[0], "conservatore": bool(v[1])} for k, v in TIPI.items()],
                "collegato": bool(cfg), "ambiente": (cfg or {}).get("ambiente")}

    async def _doc(t, did, proj=None):
        d = await db.cons_docs.find_one({"id": did, "company_id": t["cid"]}, proj or {"_id": 0})
        if not d:
            raise HTTPException(404, "Documento non trovato nell'archivio")
        return d

    @r.get("/{did}/file")
    async def scarica(did: str, allegato: Optional[int] = None, t: dict = Depends(tenant)):
        d = await _doc(t, did)
        f = d if allegato is None else (d["allegati"][allegato] if 0 <= allegato < len(d["allegati"]) else None)
        if not f:
            raise HTTPException(404, "Allegato non trovato")
        return Response(base64.b64decode(f["content_b64"]), media_type=f["mime"], headers={"Content-Disposition": f'attachment; filename="{f["file_name"]}"'})

    @r.post("/{did}/verifica")
    async def verifica(did: str, t: dict = Depends(tenant)):
        d = await _doc(t, did)
        try:
            ok = all(_sha(base64.b64decode(f["content_b64"], validate=True)) == f["sha256"] for f in [d, *d["allegati"]])
        except ValueError:
            ok = False
        v = {"at": _now(), "ok": ok}
        await db.cons_docs.update_one({"id": did}, {"$set": {"verifica": v}})
        return v

    # ---------- conservatore A-Cube
    async def _cfg(comp: dict) -> Optional[dict]:
        c = comp.get("conservazione") or {}
        if c.get("usa_sdi"):
            s = await deps["sdi_cfg"](comp["id"])
            return {"email": s["email"], "password": s["password"], "ambiente": s["ambiente"]} if s and s["provider"] == "acube" and s["password"] else None
        if c.get("email") and c.get("password_enc"):
            return {"email": c["email"], "password": fernet.decrypt(c["password_enc"].encode()).decode(), "ambiente": c.get("ambiente") or "sandbox"}
        return None

    async def _req(cfg, method, path, **kw):
        tok = await sdip._acube_token(cfg)
        try:
            async with httpx.AsyncClient(timeout=90) as c:
                res = await c.request(method, BASE[cfg["ambiente"]] + path, headers={"Authorization": f"Bearer {tok}", "Accept": "application/json", **kw.pop("headers", {})}, **kw)
        except httpx.HTTPError as e:
            raise sdip.SdiError(f"conservatore A-Cube non raggiungibile: {e.__class__.__name__}")
        if res.status_code == 401:
            sdip._tokens.pop((cfg["email"], cfg["ambiente"]), None)
        if res.status_code >= 400:
            raise sdip.SdiError(sdip._err(res))
        return res

    async def _legal_entity(cfg, comp):
        piva = comp.get("partita_iva") or comp.get("codice_fiscale")
        items = sdip._items((await _req(cfg, "GET", "/legal-entities/it", params={"itemsPerPage": 100})).json())
        if not any(x.get("fiscal_id") == piva for x in items):
            await _req(cfg, "POST", "/legal-entities/it", json={"fiscal_id": piva, "name": comp.get("denominazione")}, headers={"Content-Type": "application/json"})
        await db.companies.update_one({"id": comp["id"]}, {"$set": {"conservazione.legal_entity": piva}})

    def _metadata(comp: dict, d: dict) -> dict:
        sogg = {"denominazione_organizzazione": comp["denominazione"], "codice_fiscale_partita_iva": comp.get("partita_iva") or comp.get("codice_fiscale")}
        base = {"riservato": False, "verifica": {"firmato_digitalmente": False, "sigillato_elettronicamente": False, "marcatura_temporale": False,
                                                 "conformita_copie_immagine_su_supporto_informatico": False},
                "versione_del_documento": "1", "soggetto_che_effettua_la_registrazione": sogg}
        if TIPI[d["tipo"]][1] == "fatture":
            em, cp = d["tipo"] == "fattura_emessa", d["meta"]["controparte"]
            return {**base, "data_fattura": d["meta"]["data"], "numero_fattura": str(d["meta"]["numero"]), "tipologia_di_flusso": "U" if em else "E",
                    "mittente": sogg if em else cp, "destinatario": cp if em else sogg, "oggetto": d["titolo"][:250]}
        return {**base, "data_registrazione_documento": d["created_at"][:10], "numero_registrazione_documento": f"{d['tipo']}-{d['anno']}"}

    def _cfg_public(comp: dict) -> dict:
        c = comp.get("conservazione") or {}
        s = comp.get("sdi") or {}
        return {"usa_sdi": bool(c.get("usa_sdi")), "ambiente": c.get("ambiente") or "sandbox", "email": c.get("email") or "", "has_password": bool(c.get("password_enc")),
                "sdi_acube": s.get("provider") == "acube", "legal_entity": c.get("legal_entity"), "updated_at": c.get("updated_at")}

    @r.get("/config")
    async def get_cfg(t: dict = Depends(tenant)):
        return _cfg_public(t["company"])

    @r.put("/config")
    async def put_cfg(body: CfgIn, t: dict = Depends(tenant_admin)):
        cur = t["company"].get("conservazione") or {}
        email = (body.email or "").strip().lower()
        if not body.usa_sdi and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", email):
            raise deps["ferr"](422, "email", "Email dell'account A-Cube non valida")
        if body.usa_sdi and (t["company"].get("sdi") or {}).get("provider") != "acube":
            raise deps["ferr"](422, "usa_sdi", "Il collegamento SDI di questa azienda non usa A-Cube")
        pw = fernet.encrypt(body.password.encode()).decode() if body.password else cur.get("password_enc")
        if not body.usa_sdi and not pw:
            raise deps["ferr"](422, "password", "Inserisci la password dell'account A-Cube")
        new = {"usa_sdi": body.usa_sdi, "ambiente": body.ambiente, "email": email, "password_enc": pw, "updated_at": _now(), "legal_entity": None}
        await db.companies.update_one({"id": t["cid"]}, {"$set": {"conservazione": new}})
        return _cfg_public({**t["company"], "conservazione": new})

    @r.post("/config/test")
    async def test_cfg(t: dict = Depends(tenant_admin)):
        cfg = await _cfg(t["company"])
        if not cfg:
            raise HTTPException(400, "Configura prima il collegamento al conservatore")
        try:
            await _legal_entity(cfg, t["company"])
        except sdip.SdiError as e:
            raise HTTPException(400, f"Collegamento al conservatore non riuscito: {e}")
        return {"ok": True, "message": f"Collegamento A-Cube ({'prova' if cfg['ambiente'] == 'sandbox' else 'reale'}) riuscito: azienda registrata presso il conservatore"}

    async def _set(did, **kw):
        await db.cons_docs.update_one({"id": did}, {"$set": {f"acube.{k}": v for k, v in kw.items()}})

    @r.post("/invia")
    async def invia(body: IdsIn, t: dict = Depends(tenant_accounting)):
        cfg = await _cfg(t["company"])
        if not cfg:
            raise HTTPException(400, "Configura prima il collegamento al conservatore A-Cube")
        if not body.ids:
            raise HTTPException(400, "Seleziona almeno un documento")
        try:
            if (t["company"].get("conservazione") or {}).get("legal_entity") != (t["company"].get("partita_iva") or t["company"].get("codice_fiscale")):
                await _legal_entity(cfg, t["company"])
        except sdip.SdiError as e:
            raise HTTPException(400, f"Registrazione dell'azienda presso il conservatore non riuscita: {e}")
        out = {"inviati": 0, "saltati": 0, "errori": []}
        for did in dict.fromkeys(body.ids):
            d = await db.cons_docs.find_one({"id": did, "company_id": t["cid"]}, {"_id": 0})
            slug = TIPI[d["tipo"]][1] if d else None
            if not d or not slug or (d.get("acube") or {}).get("sent_metadata_at"):
                out["saltati"] += 1
                continue
            a = d.get("acube") or {}
            try:
                if not a.get("uuid"):
                    res = await _req(cfg, "POST", f"/preserved-documents/it/{slug}", files={"file": (d["file_name"], base64.b64decode(d["content_b64"]), d["mime"])})
                    a = {"uuid": res.json()["uuid"], "status": "to_be_stored", "ambiente": cfg["ambiente"], "uploaded_at": _now(), "error": None}
                    await db.cons_docs.update_one({"id": did}, {"$set": {"acube": a}})
                res = (await _req(cfg, "POST", f"/preserved-documents/it/{slug}/{a['uuid']}/send", json=_metadata(t["company"], d),
                                  headers={"Content-Type": "application/json"})).json()
                await _set(did, status=res.get("status") or "sent_metadata", status_history=res.get("status_history"), error=res.get("error_message"),
                           preserved_object_id=res.get("preserved_object_id"), sent_metadata_at=_now())
                out["inviati"] += 1
            except (sdip.SdiError, KeyError, ValueError) as e:
                await db.cons_docs.update_one({"id": did}, {"$set": {"acube": {**a, "error": str(e), "error_at": _now()}}})
                out["errori"].append({"id": did, "titolo": d["titolo"], "errore": str(e)})
        return out

    @r.post("/aggiorna")
    async def aggiorna(body: IdsIn, t: dict = Depends(tenant_accounting)):
        cfg = await _cfg(t["company"])
        if not cfg:
            raise HTTPException(400, "Configura prima il collegamento al conservatore A-Cube")
        q = {"company_id": t["cid"], "acube.uuid": {"$ne": None}, "acube.receipt_at": None, **({"id": {"$in": body.ids}} if body.ids else {})}
        out = {"aggiornati": 0, "conservati": 0, "errori": []}
        for d in await db.cons_docs.find(q, {"_id": 0, "id": 1, "tipo": 1, "titolo": 1, "acube": 1}).to_list(200):
            slug, u = TIPI[d["tipo"]][1], d["acube"]["uuid"]
            try:
                st = (await _req(cfg, "GET", f"/preserved-documents/it/{slug}/{u}")).json()
                upd = {"status": st.get("status"), "status_history": st.get("status_history"), "error": st.get("error_message"), "checked_at": _now()}
                if st.get("status") == "stored":
                    rc = await _req(cfg, "GET", f"/preserved-documents/it/{slug}/{u}/receipt", headers={"Accept": "application/pdf"})
                    upd |= {"receipt_b64": base64.b64encode(rc.content).decode(), "receipt_at": _now()}
                    out["conservati"] += 1
                await _set(d["id"], **upd)
                out["aggiornati"] += 1
            except sdip.SdiError as e:
                out["errori"].append({"id": d["id"], "titolo": d["titolo"], "errore": str(e)})
        return out

    @r.get("/{did}/ricevuta")
    async def ricevuta(did: str, t: dict = Depends(tenant)):
        d = await _doc(t, did, {"_id": 0, "acube": 1, "file_name": 1})
        rb = (d.get("acube") or {}).get("receipt_b64")
        if not rb:
            raise HTTPException(404, "Ricevuta di conservazione non ancora disponibile")
        return Response(base64.b64decode(rb), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="Ricevuta_conservazione_{d["file_name"].rsplit(".", 1)[0]}.pdf"'})

    return r


async def ensure_indexes(db):
    await db.cons_docs.create_index([("company_id", 1), ("tipo", 1), ("rif", 1)], unique=True)
    await db.cons_docs.create_index([("company_id", 1), ("anno", 1)])

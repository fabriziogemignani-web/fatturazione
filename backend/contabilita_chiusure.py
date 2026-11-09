from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from contabilita import _insert, _company, params_of, ensure_seed, r2, anni_chiusi, check_aperto

ESCLUSE = ["liquidazione", "chiusura", "apertura"]
MESI = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]


def periodi(anno: int, per: str) -> list:
    out = []
    for k in range(1, 13 if per == "mensile" else 5):
        m0, m1 = (k, k) if per == "mensile" else (3 * k - 2, 3 * k)
        end = date(anno + (m1 == 12), 1 if m1 == 12 else m1 + 1, 1).toordinal() - 1
        out.append({"periodo": k, "label": MESI[k - 1] if per == "mensile" else f"{k}° trimestre", "dal": f"{anno}-{m0:02d}-01",
                    "al": date.fromordinal(end).isoformat(), "ref": f"LI-{anno}-{per[0]}-{k}"})
    return out


class LiqIn(BaseModel):
    anno: int = Field(ge=2000, le=2100)
    periodicita: Literal["mensile", "trimestrale"]
    periodo: int = Field(ge=1, le=12)


def build_router(db, tenant, tenant_accounting) -> APIRouter:
    r = APIRouter(prefix="/api/contabilita")

    async def ctx(cid: str) -> dict:
        await ensure_seed(db, cid)
        return params_of(await _company(db, cid))

    # ---------- Liquidazione IVA ----------
    async def iva_periodo(cid: str, p: dict, dal: str, al: str):
        deb = cred = 0.0
        async for e in db.coa_entries.find({"company_id": cid, "data": {"$gte": dal, "$lte": al}, "origine": {"$nin": ESCLUSE}}, {"_id": 0, "righe": 1}):
            for x in e["righe"]:
                if x["conto"] == p["iva_vendite"]:
                    deb += x["avere"] - x["dare"]
                elif x["conto"] == p["iva_acquisti"]:
                    cred += x["dare"] - x["avere"]
        return r2(deb), r2(cred)

    async def liq_rows(cid: str, anno: int, per: str) -> list:
        p = await ctx(cid)
        regs = await db.coa_entries.find({"company_id": cid, "origine": "liquidazione", "data": {"$gte": f"{anno}-01-01", "$lte": f"{anno}-12-31"}},
                                         {"_id": 0, "id": 1, "ref_id": 1, "numero": 1, "anno": 1, "data": 1, "periodo_dal": 1, "periodo_al": 1}).to_list(100)
        rows = []
        for x in periodi(anno, per):
            deb, cred = await iva_periodo(cid, p, x["dal"], x["al"])
            saldo = r2(deb - cred)
            mine = next((g for g in regs if g["ref_id"] == x["ref"]), None)
            other = next((g for g in regs if g["ref_id"] != x["ref"] and g.get("periodo_dal", "9") <= x["al"] and g.get("periodo_al", "0") >= x["dal"]), None)
            rows.append({**x, "iva_vendite": deb, "iva_acquisti": cred, "saldo": saldo,
                         "interessi": r2(saldo * 0.01) if per == "trimestrale" and x["periodo"] < 4 and saldo > 0 else 0.0,
                         "registrazione": mine, "bloccato": "Periodo già liquidato con l'altra periodicità" if other else None})
        return rows

    @r.get("/liquidazioni")
    async def liquidazioni(anno: int, periodicita: Literal["mensile", "trimestrale"] = "mensile", t: dict = Depends(tenant)):
        return {"periodi": await liq_rows(t["cid"], anno, periodicita), "chiuso": anno in await anni_chiusi(db, t["cid"])}

    @r.post("/liquidazioni")
    async def registra_liq(body: LiqIn, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        await check_aperto(db, cid, body.anno)
        x = next((x for x in await liq_rows(cid, body.anno, body.periodicita) if x["periodo"] == body.periodo), None)
        if not x:
            raise HTTPException(400, "Periodo non valido")
        if x["registrazione"]:
            raise HTTPException(400, f"{x['label']} {body.anno} è già registrata in contabilità")
        if x["bloccato"]:
            raise HTTPException(400, x["bloccato"])
        if not x["iva_vendite"] and not x["iva_acquisti"]:
            raise HTTPException(400, "Nessuna IVA da liquidare nel periodo")
        p = await ctx(cid)
        saldo, interessi = x["saldo"], x["interessi"]
        righe = [{"conto": p["iva_vendite"], "dare": x["iva_vendite"]}, {"conto": p["iva_acquisti"], "avere": x["iva_acquisti"]},
                 {"conto": p["erario_iva"], "avere": saldo + interessi}, {"conto": p["interessi_iva"], "dare": interessi}]
        esito = f"a debito {saldo:.2f} €" if saldo > 0 else f"a credito {-saldo:.2f} €"
        try:
            return await _insert(db, cid, p, x["al"], "LI", f"Liquidazione IVA {x['label']} {body.anno} · {esito}".replace(".", ","), righe, "liquidazione", x["ref"],
                                 {"documento": f"{x['label']} {body.anno}", "periodo_dal": x["dal"], "periodo_al": x["al"]},
                                 by=t["user"].get("name") or t["user"]["email"])
        except ValueError as e:
            raise HTTPException(400, str(e))

    @r.delete("/liquidazioni/{rid}")
    async def annulla_liq(rid: str, t: dict = Depends(tenant_accounting)):
        e = await db.coa_entries.find_one({"id": rid, "company_id": t["cid"], "origine": "liquidazione"}, {"_id": 0, "anno": 1})
        if not e:
            raise HTTPException(404, "Registrazione di liquidazione non trovata")
        await check_aperto(db, t["cid"], e["anno"])
        await db.coa_entries.delete_one({"id": rid})
        return {"ok": True}

    # ---------- Chiusura / apertura ----------
    async def saldi(cid: str, anno: int):
        tot = {}
        async for e in db.coa_entries.find({"company_id": cid, "anno": anno, "origine": {"$ne": "chiusura"}}, {"_id": 0, "righe": 1}):
            for x in e["righe"]:
                k = (x["conto"], x.get("party_id"))
                v = tot.setdefault(k, {"s": 0.0, "party_nome": x.get("party_nome")})
                v["s"] += x["dare"] - x["avere"]
        accs = {a["codice"]: a for a in await db.coa_accounts.find({"company_id": cid}, {"_id": 0, "codice": 1, "descrizione": 1, "tipo": 1}).to_list(5000)}
        return {k: {**v, "s": r2(v["s"])} for k, v in tot.items() if r2(v["s"])}, accs

    def piano(anno: int, sal: dict, accs: dict, p: dict) -> dict:
        ce, ut, spc, spa = p["conto_economico"], p["utile_esercizio"], p["sp_chiusura"], p["sp_apertura"]
        tipo = lambda c: (accs.get(c) or {}).get("tipo")  # noqa: E731
        row = lambda c, party, nome, v: {"conto": c, "dare": v, "party_id": party, "party_nome": nome}  # noqa: E731
        eco = [(c, pt, v) for (c, pt), v in sal.items() if tipo(c) in ("costo", "ricavo")]
        ce_s = r2(sum(v["s"] for _, _, v in eco) + (sal.get((ce, None)) or {}).get("s", 0))
        pat = {k: dict(v) for k, v in sal.items() if tipo(k[0]) not in ("costo", "ricavo") and k[0] not in (ce, spc)}
        u = pat.setdefault((ut, None), {"s": 0.0, "party_nome": None})
        u["s"] = r2(u["s"] + ce_s)
        att = [(c, pt, v) for (c, pt), v in pat.items() if tipo(c) != "passivita" and v["s"]]
        pas = [(c, pt, v) for (c, pt), v in pat.items() if tipo(c) == "passivita" and v["s"]]
        fine, ini = f"{anno}-12-31", f"{anno + 1}-01-01"
        out = [
            ("CH", fine, f"Chiusura conti economici {anno}", [row(c, pt, v["party_nome"], -v["s"]) for c, pt, v in eco] + [row(ce, None, None, r2(sum(v["s"] for _, _, v in eco)))]),
            ("CH", fine, f"Rilevazione {'utile' if ce_s <= 0 else 'perdita'} d'esercizio {anno}", [row(ce, None, None, -ce_s), row(ut, None, None, ce_s)]),
            ("CH", fine, f"Chiusura conti patrimoniali attivi {anno}", [row(c, pt, v["party_nome"], -v["s"]) for c, pt, v in att] + [row(spc, None, None, r2(sum(v["s"] for _, _, v in att)))]),
            ("CH", fine, f"Chiusura conti patrimoniali passivi {anno}", [row(c, pt, v["party_nome"], -v["s"]) for c, pt, v in pas] + [row(spc, None, None, r2(sum(v["s"] for _, _, v in pas)))]),
            ("AP", ini, f"Riapertura conti patrimoniali attivi {anno + 1}", [row(c, pt, v["party_nome"], v["s"]) for c, pt, v in att] + [row(spa, None, None, -r2(sum(v["s"] for _, _, v in att)))]),
            ("AP", ini, f"Riapertura conti patrimoniali passivi {anno + 1}", [row(c, pt, v["party_nome"], v["s"]) for c, pt, v in pas] + [row(spa, None, None, -r2(sum(v["s"] for _, _, v in pas)))]),
        ]
        scritture = []
        for i, (caus, data, desc, righe) in enumerate(out, 1):
            righe = [x for x in righe if r2(x["dare"])]
            for x in righe:
                x["dare"], x["avere"] = max(r2(x["dare"]), 0.0), max(-r2(x["dare"]), 0.0)
                x["conto_descrizione"] = (accs.get(x["conto"]) or {}).get("descrizione", "")
            if len(righe) >= 2:
                scritture.append({"n": i, "causale": caus, "data": data, "descrizione": desc, "righe": righe,
                                  "origine": "chiusura" if caus == "CH" else "apertura", "ref": f"{'CH' if caus == 'CH' else 'AP'}-{anno}-{i}",
                                  "totale": r2(sum(x["dare"] for x in righe))})
        return {"scritture": scritture, "risultato": r2(-ce_s), "attivita": r2(sum(v["s"] for _, _, v in att)), "passivita": r2(-sum(v["s"] for _, _, v in pas))}

    async def stato(cid: str, anno: int) -> dict:
        chiusi = await anni_chiusi(db, cid)
        motivo = None
        if anno in chiusi:
            motivo = "Esercizio già chiuso"
        elif anno >= date.today().year:
            motivo = f"L'esercizio {anno} non è ancora terminato"
        elif anno - 1 not in chiusi and await db.coa_entries.find_one({"company_id": cid, "anno": anno - 1}, {"_id": 1}):
            motivo = f"Chiudi prima l'esercizio {anno - 1}"
        elif anno + 1 in chiusi:
            motivo = f"L'esercizio {anno + 1} è già chiuso"
        return {"chiusi": chiusi, "motivo": motivo}

    @r.get("/chiusura/{anno}")
    async def anteprima(anno: int, t: dict = Depends(tenant)):
        cid = t["cid"]
        p = await ctx(cid)
        st = await stato(cid, anno)
        anni = sorted(set(await db.coa_entries.distinct("anno", {"company_id": cid})) | {date.today().year - 1}, reverse=True)
        if anno in st["chiusi"]:
            regs = await db.coa_entries.find({"company_id": cid, "origine": {"$in": ["chiusura", "apertura"]}, "ref_id": {"$regex": f"^(CH|AP)-{anno}-"}},
                                             {"_id": 0}).sort([("data", 1), ("numero", 1)]).to_list(20)
            ris = next((e for e in regs if e["descrizione"].startswith("Rilevazione")), None)
            r_val = 0.0
            if ris:
                u = [x for x in ris["righe"] if x["conto"] == p["utile_esercizio"]]
                r_val = r2(sum(x["avere"] - x["dare"] for x in u))
            return {"anno": anno, "chiuso": True, "anni": anni, "scritture": regs, "risultato": r_val, **st}
        sal, accs = await saldi(cid, anno)
        return {"anno": anno, "chiuso": False, "anni": anni, **piano(anno, sal, accs, p), **st}

    @r.post("/chiusura/{anno}")
    async def chiudi(anno: int, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        st = await stato(cid, anno)
        if st["motivo"]:
            raise HTTPException(400, st["motivo"])
        p = await ctx(cid)
        sal, accs = await saldi(cid, anno)
        pl = piano(anno, sal, accs, p)
        if not pl["scritture"]:
            raise HTTPException(400, f"Nessun saldo da chiudere nell'esercizio {anno}")
        by = t["user"].get("name") or t["user"]["email"]
        done = []
        try:
            for s in pl["scritture"]:
                e = await _insert(db, cid, p, s["data"], s["causale"], s["descrizione"], s["righe"], s["origine"], s["ref"], {"documento": f"Esercizio {anno}"}, by=by)
                if e:
                    done.append(e["id"])
        except ValueError as e:
            await db.coa_entries.delete_many({"company_id": cid, "id": {"$in": done}})
            raise HTTPException(400, str(e))
        await db.companies.update_one({"id": cid}, {"$addToSet": {"coge_chiusi": anno}})
        return {"ok": True, "registrazioni": len(done), "risultato": pl["risultato"]}

    @r.delete("/chiusura/{anno}")
    async def riapri(anno: int, t: dict = Depends(tenant_accounting)):
        cid = t["cid"]
        chiusi = await anni_chiusi(db, cid)
        if anno not in chiusi:
            raise HTTPException(400, f"L'esercizio {anno} non è chiuso")
        if anno + 1 in chiusi:
            raise HTTPException(400, f"Annulla prima la chiusura dell'esercizio {anno + 1}")
        await db.coa_entries.delete_many({"company_id": cid, "origine": {"$in": ["chiusura", "apertura"]}, "ref_id": {"$regex": f"^(CH|AP)-{anno}-"}})
        await db.companies.update_one({"id": cid}, {"$pull": {"coge_chiusi": anno}})
        return {"ok": True}

    return r

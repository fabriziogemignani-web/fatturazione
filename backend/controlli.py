from collections import defaultdict

from fastapi import APIRouter, Depends

import contabilita as coge


def _r2(x) -> float:
    return round(float(x or 0) + 1e-9, 2)


def build_router(db, tenant_accounting, hooks):
    r = APIRouter(prefix="/api/controlli")

    @r.get("/coerenza")
    async def coerenza(t: dict = Depends(tenant_accounting)):
        cid, comp = t["cid"], t["company"]
        out = []

        def add(area, gravita, msg, link=None):
            out.append({"area": area, "gravita": gravita, "messaggio": msg, "link": link})

        coge_on = coge.attiva(comp)
        entries = await db.coa_entries.find({"company_id": cid}, {"_id": 0, "id": 1, "anno": 1, "numero": 1, "data": 1, "righe": 1, "totale": 1,
                                                                   "origine": 1, "ref_id": 1}).to_list(200000)
        if coge_on:
            conti = set(await db.coa_accounts.distinct("codice", {"company_id": cid, "livello": 3}))
            visti, massimi = defaultdict(list), defaultdict(int)
            for e in entries:
                d, a = _r2(sum(x["dare"] for x in e["righe"])), _r2(sum(x["avere"] for x in e["righe"]))
                rif = f"Registrazione n. {e['numero']}/{e['anno']} del {e['data']}"
                if d != a:
                    add("Prima nota", "errore", f"{rif}: non quadra (Dare {d:.2f} € · Avere {a:.2f} €)", "/contabilita/prima-nota")
                if _r2(e.get("totale")) != d:
                    add("Prima nota", "errore", f"{rif}: il totale salvato ({_r2(e.get('totale')):.2f} €) non corrisponde alla somma del Dare ({d:.2f} €)", "/contabilita/prima-nota")
                mancanti = sorted({x["conto"] for x in e["righe"]} - conti)
                if mancanti:
                    add("Prima nota", "errore", f"{rif}: usa conti non presenti nel piano dei conti ({', '.join(mancanti)})", "/contabilita/prima-nota")
                visti[(e["anno"], e["numero"])].append(e["id"])
                massimi[e["anno"]] = max(massimi[e["anno"]], int(e["numero"]))
            for (anno, num), ids in sorted(visti.items()):
                if len(ids) > 1:
                    add("Prima nota", "errore", f"Il numero di registrazione {num}/{anno} è usato {len(ids)} volte", "/contabilita/prima-nota")
            for anno, mx in massimi.items():
                c = await db.counters.find_one({"key": f"coge_{cid}_{anno}"}, {"_id": 0, "v": 1})
                if (c or {}).get("v", 0) < mx:
                    add("Prima nota", "errore", f"Il contatore delle registrazioni {anno} ({(c or {}).get('v', 0)}) è inferiore all'ultimo numero usato ({mx}): i prossimi numeri sarebbero doppi")

        invs = await db.invoices.find({"company_id": cid}, {"_id": 0, "id": 1, "anno": 1, "numero": 1, "sezionale": 1, "numero_display": 1, "status": 1,
                                                            "tipo_documento": 1, "autofattura": 1}).to_list(100000)
        serie = defaultdict(list)
        for i in invs:
            serie[(i.get("sezionale") or "", i["anno"])].append(int(i["numero"]))
        for (sez, anno), nums in sorted(serie.items()):
            nome = f"{'Note di credito' if sez else 'Fatture'} {anno}"
            dup = sorted({n for n in nums if nums.count(n) > 1})
            if dup:
                add("Fatture emesse", "errore", f"{nome}: numeri doppi {', '.join(map(str, dup[:10]))}", "/registro")
            buchi = sorted(set(range(min(nums), max(nums) + 1)) - set(nums))
            if buchi:
                add("Fatture emesse", "avviso", f"{nome}: numeri mancanti nella sequenza {', '.join(map(str, buchi[:10]))}{'…' if len(buchi) > 10 else ''}", "/registro")
        if coge_on:
            reg = {(e["origine"], e.get("ref_id")) for e in entries}
            for i in invs:
                if i["status"] in coge.AUTO_STATI and not i.get("autofattura") and ("vendita", i["id"]) not in reg:
                    add("Fatture emesse", "avviso", f"Fattura {i['numero_display']} consegnata ma non registrata in prima nota", f"/fatture/{i['id']}")

        inv_ids = {i["id"] for i in invs} | set(await db.partite_aperte.distinct("id", {"company_id": cid}))
        entry_ids = {e["id"] for e in entries}
        pas_ids = set(await db.passive_invoices.distinct("id", {"company_id": cid})) | inv_ids
        for coll, ids, area in ((db.payments, inv_ids, "Incassi clienti"), (db.passive_payments, pas_ids, "Pagamenti fornitori")):
            async for p in coll.find({"company_id": cid}, {"_id": 0, "id": 1, "invoice_id": 1, "importo": 1, "data": 1, "numero_display": 1, "coge_entry_id": 1}):
                rif = f"Movimento del {p.get('data')} di {_r2(p.get('importo')):.2f} € (documento {p.get('numero_display') or '?'})"
                if p.get("invoice_id") not in ids:
                    add(area, "errore", f"{rif}: il documento collegato non esiste più")
                if p.get("coge_entry_id") and p["coge_entry_id"] not in entry_ids:
                    add(area, "errore", f"{rif}: la registrazione di prima nota collegata non esiste più")

        party_nome = {}
        for (fn, area, link, segno) in ((hooks["ledger"], "Scadenzario clienti", "/scadenzario", 1), (hooks["ledger_passive"], "Scadenzario fornitori", "/scadenzario-fornitori", -1)):
            docs, crediti, _, _ = await fn(cid)
            aperto = defaultdict(float)
            for d in docs:
                c = d.get("cliente")
                party_nome[d["party_id"]] = (c.get("denominazione") if isinstance(c, dict) else c) or ""
                if d["residuo"] < -0.01:
                    add(area, "errore", f"Documento {d['numero_display']} ({party_nome[d['party_id']]}): incassato/pagato più del dovuto di {-d['residuo']:.2f} €", link)
                aperto[d["party_id"]] += d["residuo"]
            for c in crediti:
                aperto[c.get("party_id")] -= c.get("residuo") or 0
            if not coge_on:
                continue
            p = coge.params_of(comp)
            conto = p["clienti" if segno == 1 else "fornitori"]
            saldo = defaultdict(float)
            for e in entries:
                for x in e["righe"]:
                    if x["conto"] == conto and x.get("party_id"):
                        saldo[x["party_id"]] += segno * (x["dare"] - x["avere"])
            for pid in sorted(set(aperto) | set(saldo), key=lambda k: party_nome.get(k) or ""):
                if pid and abs(_r2(aperto[pid]) - _r2(saldo[pid])) > 0.01:
                    add(area, "avviso", f"{party_nome.get(pid) or pid}: residuo da scadenzario {_r2(aperto[pid]):.2f} € diverso dal saldo contabile {_r2(saldo[pid]):.2f} €", link)

        prot = defaultdict(list)
        async for d in db.passive_invoices.find({"company_id": cid, "protocollo": {"$type": "number"}}, {"_id": 0, "anno_registrazione": 1, "protocollo": 1}):
            prot[(d.get("anno_registrazione"), d["protocollo"])].append(1)
        for (anno, n), v in sorted(prot.items(), key=lambda kv: (kv[0][0] or 0, kv[0][1])):
            if len(v) > 1:
                add("Fatture ricevute", "errore", f"Protocollo IVA {n}/{anno} assegnato a {len(v)} fatture", "/passive")

        err = sum(1 for x in out if x["gravita"] == "errore")
        return {"problemi": out, "errori": err, "avvisi": len(out) - err, "contabilita": coge_on,
                "controlli": ["Quadratura Dare/Avere e totali delle registrazioni", "Conti esistenti nel piano dei conti", "Numerazioni doppie o mancanti",
                              "Contatori dei progressivi", "Incassi e pagamenti collegati a documenti esistenti", "Documenti incassati o pagati oltre il dovuto",
                              "Residui dello scadenzario confrontati con i saldi contabili di clienti e fornitori", "Fatture consegnate non registrate", "Protocolli IVA acquisti doppi"]}

    return r

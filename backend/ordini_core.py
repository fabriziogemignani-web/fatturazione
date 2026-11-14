STATI_APERTI = ["aperto", "parziale"]


def stato_righe(lines: list) -> str:
    if all((x.get("evasa") or 0) >= x["quantita"] - 1e-9 for x in lines):
        return "evaso"
    return "parziale" if any((x.get("evasa") or 0) > 0 for x in lines) else "aperto"


async def aggiorna_impegni(db, cid: str, aids) -> None:
    for aid in {a for a in aids if a}:
        rows = await db.orders.aggregate([
            {"$match": {"company_id": cid, "status": {"$in": STATI_APERTI}, "lines.article_id": aid}}, {"$unwind": "$lines"},
            {"$match": {"lines.article_id": aid}},
            {"$group": {"_id": "$tipo", "q": {"$sum": {"$max": [0, {"$subtract": ["$lines.quantita", {"$ifNull": ["$lines.evasa", 0]}]}]}}}}]).to_list(5)
        q = {r["_id"]: round(r["q"], 4) for r in rows}
        a = await db.articles.find_one({"id": aid, "company_id": cid}, {"_id": 0, "giacenza": 1}) or {}
        imp, ordn = q.get("cliente", 0), q.get("fornitore", 0)
        await db.articles.update_one({"id": aid, "company_id": cid}, {"$set": {"impegnato": imp, "ordinato": ordn, "disponibilita": round((a.get("giacenza") or 0) - imp + ordn, 4)}})


async def storna(db, cid: str, doc_id: str) -> None:
    o = await db.orders.find_one({"company_id": cid, "evasioni.doc_id": doc_id, "evasioni.annullata": {"$ne": True}}, {"_id": 0})
    if not o:
        return
    ev = next(e for e in o["evasioni"] if e["doc_id"] == doc_id and not e.get("annullata"))
    q = {r["line_id"]: r["quantita"] for r in ev["righe"]}
    lines = [{**x, "evasa": round(max((x.get("evasa") or 0) - q.get(x["id"], 0), 0), 4)} for x in o["lines"]]
    evs = [{**e, "annullata": True} if e is ev else e for e in o["evasioni"]]
    st = o["status"] if o["status"] == "chiuso" else stato_righe(lines)
    await db.orders.update_one({"id": o["id"], "company_id": cid}, {"$set": {"lines": lines, "evasioni": evs, "status": st}})
    await aggiorna_impegni(db, cid, [x.get("article_id") for x in lines])

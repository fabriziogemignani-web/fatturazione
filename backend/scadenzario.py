from collections import defaultdict
from datetime import date, timedelta


def _r2(v: float) -> float:
    return round(v + 0.0, 2)


def rate_of(inv: dict) -> list:
    r = inv.get("rate_mod") or inv.get("rate") or [{"scadenza": inv.get("scadenza") or inv["data"], "importo": inv.get("netto", inv["totale"])}]
    return sorted(r, key=lambda x: x["scadenza"])


def _netto(i: dict) -> float:
    return i.get("netto", i["totale"])


def build_ledger(invs: list, pays: list, today: str):
    fatt = [i for i in invs if i.get("tipo_documento") != "TD04"]
    ncs = sorted((i for i in invs if i.get("tipo_documento") == "TD04"), key=lambda x: (x["data"], x["numero"]))
    fids = {i["id"] for i in fatt}
    paid, comp, nc_used, auto = defaultdict(float), defaultdict(float), defaultdict(float), defaultdict(float)
    for p in pays:
        if p.get("nc_id"):
            comp[p["invoice_id"]] += p["importo"]
            nc_used[p["nc_id"]] += p["importo"]
        else:
            paid[p["invoice_id"]] += p["importo"]
    netto = {i["id"]: _netto(i) for i in fatt}
    for nc in ncs:
        fid = nc.get("fattura_collegata_id")
        if fid in fids:
            a = max(0.0, min(_netto(nc) - nc_used[nc["id"]], netto[fid] - paid[fid] - comp[fid] - auto[fid]))
            auto[fid] += a
            nc_used[nc["id"]] += a
    docs = []
    for i in fatt:
        cov = paid[i["id"]] + comp[i["id"]] + auto[i["id"]]
        left, rows, rate = cov, [], rate_of(i)
        for n, r in enumerate(rate, 1):
            p = min(r["importo"], max(left, 0.0))
            left -= p
            res = _r2(r["importo"] - p)
            rows.append({"n": n, "di": len(rate), "scadenza": r["scadenza"], "importo": _r2(r["importo"]), "pagato": _r2(p), "residuo": res,
                         "stato": "pagata" if res <= 0.005 else ("parziale" if p > 0.005 else "aperta"),
                         "scaduta": res > 0.005 and r["scadenza"] < today,
                         "giorni_ritardo": (date.fromisoformat(today) - date.fromisoformat(r["scadenza"])).days if res > 0.005 and r["scadenza"] < today else 0})
        docs.append({"id": i["id"], "numero_display": i["numero_display"], "data": i["data"], "party_id": i["party_id"],
                     "cliente": (i.get("cliente") or {}).get("denominazione", ""), "netto": _r2(netto[i["id"]]),
                     "incassato": _r2(paid[i["id"]]), "compensato": _r2(comp[i["id"]] + auto[i["id"]]),
                     "compensato_auto": _r2(auto[i["id"]]), "residuo": _r2(max(netto[i["id"]] - cov, 0)), "rate": rows})
    crediti = []
    for nc in ncs:
        res = _r2(_netto(nc) - nc_used[nc["id"]])
        if res > 0.005:
            crediti.append({"id": nc["id"], "numero_display": nc["numero_display"], "data": nc["data"], "party_id": nc["party_id"],
                            "cliente": (nc.get("cliente") or {}).get("denominazione", ""), "netto": _r2(_netto(nc)), "residuo": res})
    return docs, crediti


def per_cliente(docs: list, crediti: list, today: str) -> list:
    lim = (date.fromisoformat(today) + timedelta(days=30)).isoformat()
    g = {}

    def row(pid, name):
        return g.setdefault(pid, {"party_id": pid, "cliente": name, "aperto": 0.0, "scaduto": 0.0, "entro_30": 0.0, "oltre_30": 0.0,
                                  "rate_aperte": 0, "rate_scadute": 0, "prossima": None, "crediti": 0.0})
    for d in docs:
        for r in d["rate"]:
            if r["residuo"] <= 0.005:
                continue
            c = row(d["party_id"], d["cliente"])
            c["aperto"] += r["residuo"]
            c["rate_aperte"] += 1
            if r["scaduta"]:
                c["scaduto"] += r["residuo"]
                c["rate_scadute"] += 1
            else:
                c["entro_30" if r["scadenza"] <= lim else "oltre_30"] += r["residuo"]
                if not c["prossima"] or r["scadenza"] < c["prossima"]:
                    c["prossima"] = r["scadenza"]
    for n in crediti:
        row(n["party_id"], n["cliente"])["crediti"] += n["residuo"]
    out = [{**c, **{k: _r2(c[k]) for k in ("aperto", "scaduto", "entro_30", "oltre_30", "crediti")}} for c in g.values()]
    return sorted(out, key=lambda c: (-c["scaduto"], -c["aperto"]))

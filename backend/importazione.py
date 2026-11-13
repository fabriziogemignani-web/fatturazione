import uuid
from datetime import date, datetime, timezone
from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from pydantic import ValidationError

import contabilita as coge
from magazzino import recompute_article

PARTY_COLS = ["denominazione", "partita_iva", "codice_fiscale", "codice_destinatario", "pec", "email", "telefono", "indirizzo", "cap", "comune", "provincia", "nazione"]
PAG_COLS = ["pagamento_modalita", "pagamento_rate", "pagamento_giorni", "pagamento_fine_mese"]
FORN_COLS = ["detraibilita_iva", "iban", "persona", "nome", "cognome", "data_nascita", "comune_nascita", "provincia_nascita", "soggetto_ritenuta",
             "ritenuta_codice_tributo", "ritenuta_tipo", "ritenuta_aliquota", "ritenuta_base", "ritenuta_causale", "cassa_tipo", "cassa_aliquota", "cassa_ritenuta"]
CONV = {"pagamento_rate": "int", "pagamento_giorni": "int", "pagamento_fine_mese": "bool", "detraibilita_iva": "num", "data_nascita": "data", "soggetto_ritenuta": "bool",
        "ritenuta_aliquota": "num", "ritenuta_base": "num", "cassa_aliquota": "num", "cassa_ritenuta": "bool"}
SHEETS = {
    "Clienti": PARTY_COLS + PAG_COLS,
    "Fornitori": PARTY_COLS + PAG_COLS + FORN_COLS,
    "Articoli": ["codice", "descrizione", "unita_misura", "prezzo", "aliquota", "natura", "gestione_magazzino", "scorta_minima", "scorta_riordino", "fornitore_abituale"],
    "Listini": ["piva_o_cf_cliente", "codice_articolo", "prezzo", "sconto"],
    "Giacenze": ["codice_articolo", "data", "quantita", "costo_unitario"],
    "SaldiContabili": ["data", "conto", "piva_o_cf_cliente_fornitore", "dare", "avere"],
    "PartiteAperte": ["tipo", "piva_o_cf", "numero", "data", "scadenza", "importo"],
}
OBBLIGATORI = {"Clienti": ["denominazione", "indirizzo", "cap", "comune"], "Fornitori": ["denominazione", "indirizzo", "cap", "comune"], "Articoli": ["codice", "descrizione"],
               "Listini": ["piva_o_cf_cliente", "codice_articolo", "prezzo"], "Giacenze": ["codice_articolo", "data", "quantita", "costo_unitario"],
               "SaldiContabili": ["data", "conto"], "PartiteAperte": ["tipo", "piva_o_cf", "numero", "data", "scadenza", "importo"]}
ISTRUZIONI = [
    "Compila i fogli e ricarica il file da Impostazioni > Importazione di massa. Le colonne con * sono obbligatorie.",
    "Clienti e fornitori gia presenti (stessa P.IVA o codice fiscale) e articoli gia presenti (stesso codice) vengono AGGIORNATI con i dati del foglio.",
    "Date nel formato GG/MM/AAAA o come data Excel. Numeri con la virgola o il punto. gestione_magazzino: SI oppure NO. Sconto: 10 oppure 10+5.",
    "Listini: un rigo per cliente e articolo. Giacenze: carico di inventario iniziale al costo unitario indicato.",
    "Pagamento predefinito: pagamento_modalita MP05 bonifico, MP12 Ri.Ba., MP01 contanti, MP02 assegno, MP08 carta; pagamento_rate numero di rate (1-12); pagamento_giorni giorni tra le rate; pagamento_fine_mese SI o NO.",
    "Fornitori: persona GIURIDICA o FISICA (per le persone fisiche nome e cognome obbligatori, la ragione sociale diventa Cognome Nome); soggetto_ritenuta e cassa_ritenuta SI o NO; ritenuta_codice_tributo es. 1040; ritenuta_tipo RT01-RT06; cassa_tipo TC01-TC22.",
    "SaldiContabili: una sola registrazione di apertura con tutte le righe; il totale dare deve essere uguale al totale avere. Conto = codice del sottoconto del piano dei conti.",
    "PartiteAperte: fatture aperte prima dell'avvio del programma (tipo cliente o fornitore); entrano nello scadenzario e si incassano/pagano come le altre.",
    "Prima della scrittura nel database viene mostrata un'anteprima con gli errori: nulla viene salvato finche non confermi.",
]


def _now():
    return datetime.now(timezone.utc).isoformat()


def _s(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _num(v, campo):
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(".", "").replace(",", ".") if "," in str(v) else str(v))
    except ValueError:
        raise ValueError(f"{campo}: numero non valido")


def _data(v, campo):
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = _s(v)
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"{campo}: data non valida (usa GG/MM/AAAA)")


def _verr(e: ValidationError) -> str:
    x = e.errors()[0]
    campo = getattr((x.get("ctx") or {}).get("error"), "field", None)
    return f"{'.'.join(str(p) for p in x['loc']) or campo or 'riga'}: {x['msg'].removeprefix('Value error, ')}"


def build(db, tenant_admin, deps) -> APIRouter:
    r = APIRouter(prefix="/api/importazione")
    PartyIn, ArticleIn, norm_sconto = deps["PartyIn"], deps["ArticleIn"], deps["norm_sconto"]

    @r.get("/modello")
    async def modello(t: dict = Depends(tenant_admin)):
        cid = t["cid"]
        wb = Workbook()
        ws = wb.active
        ws.title = "Istruzioni"
        ws["A1"] = f"Modello di importazione - {t['company']['denominazione']}"
        ws["A1"].font = Font(bold=True, size=14)
        for i, txt in enumerate(ISTRUZIONI, start=3):
            ws.cell(i, 1, txt)
        ws.column_dimensions["A"].width = 150
        parties = await db.parties.find({"company_id": cid}, {"_id": 0}).sort("denominazione", 1).to_list(20000)
        arts = await db.articles.find({"company_id": cid}, {"_id": 0}).sort("codice", 1).to_list(20000)
        def _out(p, c):
            v = p.get(c, "")
            if CONV.get(c) == "bool":
                return "SI" if v else "NO"
            return v.upper() if c == "persona" and v else v
        pre = {"Clienti": [[_out(p, c) for c in SHEETS["Clienti"]] for p in parties if p["tipo"] == "cliente"],
               "Fornitori": [[_out(p, c) for c in SHEETS["Fornitori"]] for p in parties if p["tipo"] == "fornitore"],
               "Articoli": [[a["codice"], a["descrizione"], a.get("unita_misura") or "", a.get("prezzo") or 0, a.get("aliquota"), a.get("natura") or "",
                             "SI" if a.get("gestione_magazzino") else "NO", a.get("scorta_minima") or 0, a.get("scorta_riordino") or 0, a.get("fornitore_abituale") or ""] for a in arts]}
        amap = {a["id"]: a["codice"] for a in arts}
        pre["Listini"] = [[p.get("partita_iva") or p.get("codice_fiscale"), amap.get(x["article_id"], ""), x["prezzo"], x.get("sconto") or ""]
                          for p in parties if p["tipo"] == "cliente" for x in p.get("listino") or [] if x["article_id"] in amap]
        head_fill = PatternFill("solid", fgColor="0F172A")
        for name, cols in SHEETS.items():
            s = wb.create_sheet(name)
            s.append([c + (" *" if c in OBBLIGATORI[name] else "") for c in cols])
            for c in s[1]:
                c.font = Font(bold=True, color="FFFFFF")
                c.fill = head_fill
            for row in pre.get(name, []):
                s.append(row)
            for i, c in enumerate(cols, start=1):
                s.column_dimensions[s.cell(1, i).column_letter].width = max(14, len(c) + 4)
            s.freeze_panes = "A2"
            if name == "Articoli":
                dv = DataValidation(type="list", formula1='"SI,NO"', allow_blank=True)
                s.add_data_validation(dv)
                dv.add("G2:G5000")
            if name == "PartiteAperte":
                dv = DataValidation(type="list", formula1='"cliente,fornitore"', allow_blank=True)
                s.add_data_validation(dv)
                dv.add("A2:A5000")
        buf = BytesIO()
        wb.save(buf)
        return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": 'attachment; filename="modello_importazione.xlsx"'})

    def _rows(wb, name):
        if name not in wb.sheetnames:
            return []
        ws = wb[name]
        head = [_s(c.value).replace(" *", "").strip() for c in ws[1]]
        out = []
        for n, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if all(v in (None, "") for v in row):
                continue
            out.append((n, {h: row[i] if i < len(row) else None for i, h in enumerate(head) if h}))
        return out

    @r.post("/anteprima")
    async def anteprima(file: UploadFile = File(...), t: dict = Depends(tenant_admin)):
        cid = t["cid"]
        raw = await file.read()
        if len(raw) > 10 * 1024 * 1024:
            raise HTTPException(400, "File troppo grande (massimo 10 MB)")
        try:
            wb = load_workbook(BytesIO(raw), data_only=True, read_only=True)
        except Exception:
            raise HTTPException(400, "Il file non è un Excel valido (.xlsx)")
        parties = await db.parties.find({"company_id": cid}, {"_id": 0, "id": 1, "tipo": 1, "partita_iva": 1, "codice_fiscale": 1, "denominazione": 1}).to_list(20000)
        pkey = {(p["tipo"], k): p for p in parties for k in (p.get("partita_iva"), p.get("codice_fiscale")) if k}
        acods = set(await db.articles.distinct("codice", {"company_id": cid}))
        ris, ok = {}, {}

        def add(name, n, fn):
            x = ris.setdefault(name, {"nuovi": 0, "aggiornati": 0, "righe": 0, "errori": []})
            try:
                rec, nuovo = fn()
                ok.setdefault(name, []).append(rec)
                x["righe"] += 1
                x["nuovi" if nuovo else "aggiornati"] += 1
            except ValidationError as e:
                x["errori"].append({"riga": n, "errore": _verr(e)})
            except ValueError as e:
                x["errori"].append({"riga": n, "errore": str(e)})

        file_keys = set()
        for name, tipo in (("Clienti", "cliente"), ("Fornitori", "fornitore")):
            for n, row in _rows(wb, name):
                def f(row=row, tipo=tipo):
                    vals = {c: _s(row.get(c)) for c in SHEETS[name] if _s(row.get(c))}
                    for c, kind in CONV.items():
                        if c in vals:
                            raw = row.get(c)
                            vals[c] = (_s(raw).upper() in ("SI", "SÌ", "S", "X", "1", "TRUE") if kind == "bool" else int(_num(raw, c)) if kind == "int"
                                       else _num(raw, c) if kind == "num" else _data(raw, c))
                    if "persona" in vals:
                        vals["persona"] = vals["persona"].lower()
                    if "pagamento_modalita" in vals:
                        vals["pagamento_modalita"] = vals["pagamento_modalita"].upper()
                    for c in OBBLIGATORI[name]:
                        if not vals.get(c) and not (c == "denominazione" and vals.get("persona") == "fisica"):
                            raise ValueError(f"{c}: obbligatorio")
                    if not (vals.get("partita_iva") or vals.get("codice_fiscale")):
                        raise ValueError("Indica partita IVA o codice fiscale")
                    m = PartyIn(tipo=tipo, **vals)
                    vals = {k: getattr(m, k) for k in set(vals) | ({"denominazione", "nome", "cognome", "data_nascita", "comune_nascita", "provincia_nascita"} if "persona" in vals else {"denominazione"})}
                    keys = [vals.get("partita_iva"), vals.get("codice_fiscale")]
                    file_keys.update((tipo, k) for k in keys if k)
                    cur = next((pkey[(tipo, k)] for k in keys if k and (tipo, k) in pkey), None)
                    return {"tipo": tipo, "vals": vals, "id": cur["id"] if cur else None}, cur is None
                add(name, n, f)
        file_arts = set()
        for n, row in _rows(wb, "Articoli"):
            def f(row=row):
                vals = {c: row.get(c) for c in SHEETS["Articoli"] if row.get(c) not in (None, "")}
                for c in ("codice", "descrizione", "unita_misura", "natura", "fornitore_abituale"):
                    if c in vals:
                        vals[c] = _s(vals[c])
                for c in ("prezzo", "aliquota", "scorta_minima", "scorta_riordino"):
                    if c in vals:
                        vals[c] = _num(vals[c], c)
                if "gestione_magazzino" in vals:
                    vals["gestione_magazzino"] = _s(vals["gestione_magazzino"]).upper() in ("SI", "SÌ", "S", "X", "1", "TRUE")
                for c in OBBLIGATORI["Articoli"]:
                    if not vals.get(c):
                        raise ValueError(f"{c}: obbligatorio")
                ArticleIn(**vals)
                file_arts.add(vals["codice"])
                return {"vals": vals}, vals["codice"] not in acods
            add("Articoli", n, f)
        for n, row in _rows(wb, "Listini"):
            def f(row=row):
                k, cod = _s(row.get("piva_o_cf_cliente")), _s(row.get("codice_articolo"))
                if ("cliente", k) not in pkey and ("cliente", k) not in file_keys:
                    raise ValueError(f"Cliente {k} non trovato")
                if cod not in acods and cod not in file_arts:
                    raise ValueError(f"Articolo {cod} non trovato")
                prezzo = _num(row.get("prezzo"), "prezzo")
                if prezzo is None or prezzo < 0:
                    raise ValueError("prezzo: obbligatorio e non negativo")
                return {"cliente": k, "codice": cod, "prezzo": prezzo, "sconto": norm_sconto(_s(row.get("sconto")))}, True
            add("Listini", n, f)
        for n, row in _rows(wb, "Giacenze"):
            def f(row=row):
                cod = _s(row.get("codice_articolo"))
                if cod not in acods and cod not in file_arts:
                    raise ValueError(f"Articolo {cod} non trovato")
                q, cu = _num(row.get("quantita"), "quantita"), _num(row.get("costo_unitario"), "costo_unitario")
                if not q or q <= 0 or cu is None or cu < 0:
                    raise ValueError("quantita maggiore di zero e costo_unitario non negativo obbligatori")
                d = _data(row.get("data"), "data")
                if d > date.today().isoformat():
                    raise ValueError("data: non può essere futura")
                return {"codice": cod, "data": d, "quantita": q, "costo_unitario": cu}, True
            add("Giacenze", n, f)
        await coge.ensure_seed(db, cid)
        conti = {a["codice"]: a for a in await db.coa_accounts.find({"company_id": cid, "livello": 3}, {"_id": 0, "codice": 1, "tipo": 1}).to_list(5000)}
        for n, row in _rows(wb, "SaldiContabili"):
            def f(row=row):
                c = _s(row.get("conto"))
                if c not in conti:
                    raise ValueError(f"Conto {c} inesistente o non è un sottoconto")
                dare, avere = _num(row.get("dare"), "dare") or 0, _num(row.get("avere"), "avere") or 0
                if (dare > 0) == (avere > 0) or dare < 0 or avere < 0:
                    raise ValueError("Indica un importo positivo in dare oppure in avere")
                k = _s(row.get("piva_o_cf_cliente_fornitore"))
                if k and not any((tp, k) in pkey or (tp, k) in file_keys for tp in ("cliente", "fornitore")):
                    raise ValueError(f"Cliente/fornitore {k} non trovato")
                return {"data": _data(row.get("data"), "data"), "conto": c, "party": k, "dare": round(dare, 2), "avere": round(avere, 2)}, True
            add("SaldiContabili", n, f)
        if ok.get("SaldiContabili"):
            rs = ok["SaldiContabili"]
            diff = round(sum(x["dare"] for x in rs) - sum(x["avere"] for x in rs), 2)
            if diff:
                ris["SaldiContabili"]["errori"].append({"riga": "-", "errore": f"Dare e avere non quadrano: differenza {diff:.2f} €"})
            if len({x["data"] for x in rs}) > 1:
                ris["SaldiContabili"]["errori"].append({"riga": "-", "errore": "Tutte le righe devono avere la stessa data di apertura"})
        for n, row in _rows(wb, "PartiteAperte"):
            def f(row=row):
                tipo, k = _s(row.get("tipo")).lower(), _s(row.get("piva_o_cf"))
                if tipo not in ("cliente", "fornitore"):
                    raise ValueError("tipo: cliente oppure fornitore")
                if (tipo, k) not in pkey and (tipo, k) not in file_keys:
                    raise ValueError(f"{tipo.capitalize()} {k} non trovato")
                imp = _num(row.get("importo"), "importo")
                if not imp or imp <= 0:
                    raise ValueError("importo: maggiore di zero")
                d, sc = _data(row.get("data"), "data"), _data(row.get("scadenza"), "scadenza")
                if sc < d:
                    raise ValueError("scadenza: non può precedere la data")
                return {"tipo": tipo, "chiave": k, "numero": _s(row.get("numero"))[:30], "data": d, "scadenza": sc, "importo": round(imp, 2)}, True
            add("PartiteAperte", n, f)
        bid = str(uuid.uuid4())
        await db.import_batches.delete_many({"company_id": cid, "stato": "anteprima"})
        await db.import_batches.insert_one({"id": bid, "company_id": cid, "stato": "anteprima", "dati": ok, "riepilogo": ris, "file": file.filename,
                                            "created_by": t["user"]["email"], "created_at": _now()})
        bloccanti = [k for k in ("SaldiContabili",) if any(e["riga"] == "-" for e in ris.get(k, {}).get("errori", []))]
        return {"id": bid, "riepilogo": ris, "bloccanti": bloccanti}

    @r.post("/{bid}/conferma")
    async def conferma(bid: str, t: dict = Depends(tenant_admin)):
        cid = t["cid"]
        b = await db.import_batches.find_one_and_update({"id": bid, "company_id": cid, "stato": "anteprima"}, {"$set": {"stato": "in_corso"}})
        if not b:
            raise HTTPException(404, "Anteprima non trovata o già importata: ricarica il file")
        if any(e["riga"] == "-" for e in b["riepilogo"].get("SaldiContabili", {}).get("errori", [])):
            await db.import_batches.update_one({"id": bid}, {"$set": {"stato": "anteprima"}})
            raise HTTPException(400, "Correggi i saldi contabili (dare e avere non quadrano) e ricarica il file")
        d, out = b["dati"], {}

        async def _iban_predefinito(pid, iban, prev):
            bf = [{"nome": x.get("nome") or "", "iban": x["iban"], "predefinita": x["iban"] == iban} for x in prev.get("banche_fornitore") or [] if x.get("iban")]
            if not bf and prev.get("iban") and prev["iban"] != iban:
                bf = [{"nome": "", "iban": prev["iban"], "predefinita": False}]
            if not any(x["iban"] == iban for x in bf):
                bf.insert(0, {"nome": "", "iban": iban, "predefinita": True})
            await db.parties.update_one({"id": pid, "company_id": cid}, {"$set": {"banche_fornitore": bf}})
        for name in ("Clienti", "Fornitori"):
            for x in d.get(name, []):
                cur = await db.parties.find_one({"company_id": cid, "tipo": x["tipo"], "$or": [{k: x["vals"][k]} for k in ("partita_iva", "codice_fiscale") if x["vals"].get(k)]}, {"_id": 0, "id": 1, "iban": 1, "banche_fornitore": 1})
                if cur:
                    await db.parties.update_one({"id": cur["id"]}, {"$set": x["vals"]})
                    if x["tipo"] == "fornitore" and x["vals"].get("iban"):
                        await _iban_predefinito(cur["id"], x["vals"]["iban"], cur)
                else:
                    await db.parties.insert_one({"id": str(uuid.uuid4()), **PartyIn(tipo=x["tipo"], **x["vals"]).model_dump(), "company_id": cid, "created_at": _now()})
            out[name] = len(d.get(name, []))
        for x in d.get("Articoli", []):
            cur = await db.articles.find_one({"company_id": cid, "codice": x["vals"]["codice"]}, {"_id": 0, "id": 1})
            if cur:
                await db.articles.update_one({"id": cur["id"]}, {"$set": x["vals"]})
            else:
                await db.articles.insert_one({"id": str(uuid.uuid4()), **ArticleIn(**x["vals"]).model_dump(), "company_id": cid, "giacenza": 0, "costo_medio": 0, "created_at": _now()})
        out["Articoli"] = len(d.get("Articoli", []))
        arts = {a["codice"]: a for a in await db.articles.find({"company_id": cid}, {"_id": 0, "id": 1, "codice": 1, "descrizione": 1, "unita_misura": 1}).to_list(20000)}

        async def party(tipi, k):
            return await db.parties.find_one({"company_id": cid, "tipo": {"$in": tipi}, "$or": [{"partita_iva": k}, {"codice_fiscale": k}]}, {"_id": 0})
        for x in d.get("Listini", []):
            p, a = await party(["cliente"], x["cliente"]), arts[x["codice"]]
            lst = [y for y in p.get("listino") or [] if y["article_id"] != a["id"]] + [{"article_id": a["id"], "prezzo": x["prezzo"], "sconto": x["sconto"]}]
            await db.parties.update_one({"id": p["id"]}, {"$set": {"listino": lst}})
        out["Listini"] = len(d.get("Listini", []))
        toccati = set()
        for x in d.get("Giacenze", []):
            a = arts[x["codice"]]
            await db.articles.update_one({"id": a["id"]}, {"$set": {"gestione_magazzino": True}})
            await db.stock_moves.insert_one({"id": str(uuid.uuid4()), "company_id": cid, "article_id": a["id"], "tipo": "carico", "data": x["data"], "quantita": x["quantita"],
                                             "costo_unitario": x["costo_unitario"], "causale": "Altro", "documento": "Inventario iniziale", "note": "Importazione di massa",
                                             "codice": a["codice"], "descrizione": a["descrizione"], "unita_misura": a.get("unita_misura") or "",
                                             "created_at": _now(), "created_by": t["user"]["email"]})
            toccati.add(a["id"])
        for aid in toccati:
            await recompute_article(db, cid, aid)
        out["Giacenze"] = len(d.get("Giacenze", []))
        if d.get("SaldiContabili"):
            await coge.ensure_seed(db, cid)
            p = coge.params_of(await coge._company(db, cid))
            righe = []
            for x in d["SaldiContabili"]:
                pt = await party(["cliente", "fornitore"], x["party"]) if x["party"] else None
                righe.append({"conto": x["conto"], "dare": x["dare"], "avere": x["avere"], **({"party_id": pt["id"], "party_nome": pt["denominazione"]} if pt else {})})
            try:
                await coge._insert(db, cid, p, d["SaldiContabili"][0]["data"], "AP", "Saldi di apertura da importazione", righe, "apertura", ref_id=bid, by=t["user"]["email"])
            except ValueError as e:
                await db.import_batches.update_one({"id": bid}, {"$set": {"stato": "errore", "errore": str(e), "esito": out}})
                raise HTTPException(400, f"Saldi contabili non registrati: {e}. Le altre schede sono state importate")
            out["SaldiContabili"] = len(d["SaldiContabili"])
        for x in d.get("PartiteAperte", []):
            p = await party([x["tipo"]], x["chiave"])
            await db.partite_aperte.insert_one({"id": str(uuid.uuid4()), "company_id": cid, "tipo": x["tipo"], "party_id": p["id"], "numero": 0,
                                                "numero_display": x["numero"], "data": x["data"], "scadenza": x["scadenza"], "totale": x["importo"], "netto": x["importo"],
                                                "rate": [{"scadenza": x["scadenza"], "importo": x["importo"]}], "tipo_documento": "TD01", "status": "storico",
                                                "stato_reg": "registrata", ("cliente" if x["tipo"] == "cliente" else "fornitore"): {"denominazione": p["denominazione"]},
                                                "origine": "importazione", "import_id": bid, "created_at": _now()})
        out["PartiteAperte"] = len(d.get("PartiteAperte", []))
        await db.import_batches.update_one({"id": bid}, {"$set": {"stato": "importato", "esito": out, "imported_at": _now()}, "$unset": {"dati": ""}})
        return {"esito": out}

    @r.get("/storico")
    async def storico(t: dict = Depends(tenant_admin)):
        return await db.import_batches.find({"company_id": t["cid"], "stato": {"$ne": "anteprima"}}, {"_id": 0, "dati": 0}).sort("created_at", -1).to_list(50)

    return r

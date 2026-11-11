# Iteration 47: Importazione di massa (Excel model download, preview with errors, confirm writes DB, scadenzario partite aperte, tenant isolation).
# Run with: REACT_APP_BACKEND_URL=... pytest tests/test_iteration47_importazione.py -n 0
import io
import os
import subprocess
from datetime import date, timedelta

import pytest
import requests
from openpyxl import load_workbook

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
PA, PB = "01234567897", "12345678903"
TODAY = date.today()
U = {k: (f"test-user-t47-{k}", f"test_session_t47_{k}") for k in ("admin", "op")}
ROLE = {"admin": "admin", "op": "operatore"}
S = {}
CLI_PIVA, FOR_PIVA, CLI2_CF = "02345670481", "03456780482", "RSSMRA80A01H501U"
COLLS = ["invoices", "parties", "articles", "stock_moves", "ddts", "payments", "passive_payments", "passive_invoices", "coa_entries", "coa_accounts",
         "coa_causali", "coa_iva", "audit", "sdi_events", "partite_aperte", "import_batches"]


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


def sess(k="admin", cid="A"):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {U[k][1]}"
    if cid and S.get(cid):
        s.headers["X-Company-Id"] = S[cid]
    return s


def clean():
    ids = "[" + ",".join(f'"{u}"' for u, _ in U.values()) + "]"
    colls = "[" + ",".join(f'"{c}"' for c in COLLS) + "]"
    mongo(f'db.companies.find({{partita_iva:{{$in:["{PA}","{PB}"]}}, denominazione:/^TEST_T47/}}).forEach(c=>{{{colls}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:{ids}}}}}); db.user_sessions.deleteMany({{user_id:{{$in:{ids}}}}});')


def mk_company(name, piva):
    r = sess("admin", None).post(f"{API}/companies", json={"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01",
                                                          "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    for k, (uid, tok) in U.items():
        mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.{uid}@example.com", name:"TEST_{k}", picture:"", role:"{ROLE[k]}", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
              f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    S["A"] = mk_company("TEST_T47 Alfa Srl", PA)
    S["B"] = mk_company("TEST_T47 Beta Srl", PB)
    mongo(f'db.users.updateMany({{user_id:"{U["op"][0]}"}}, {{$set:{{company_ids:["{S["A"]}"]}}}});')
    # existing client + article in A (to check prefill + update)
    s = sess()
    r = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": "TEST_T47 Cliente Old", "partita_iva": CLI_PIVA, "codice_fiscale": CLI_PIVA,
                                       "codice_destinatario": "ABC1234", "indirizzo": "Via Vecchia 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT",
                                       "email": "old@example.com"})
    assert r.status_code == 200, r.text
    S["cli"] = r.json()["id"]
    r = s.post(f"{API}/articles", json={"codice": "T47-A1", "descrizione": "TEST articolo vecchio", "unita_misura": "PZ", "prezzo": 10, "aliquota": 22})
    assert r.status_code == 200, r.text
    S["art"] = r.json()["id"]
    # seed chart of accounts (triggers ensure_seed)
    assert s.get(f"{API}/contabilita/conti").status_code == 200
    yield
    clean()


def model_wb():
    r = sess().get(f"{API}/importazione/modello")
    assert r.status_code == 200, r.text
    return load_workbook(io.BytesIO(r.content))


def upload(wb, k="admin", cid="A", name="imp.xlsx"):
    b = io.BytesIO(); wb.save(b)
    return sess(k, cid).post(f"{API}/importazione/anteprima", files={"file": (name, b.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})


def errs(res, sheet):
    return res["riepilogo"].get(sheet, {}).get("errori", [])


def counts():
    cid = S["A"]
    return mongo(f'print([db.parties.countDocuments({{company_id:"{cid}"}}), db.articles.countDocuments({{company_id:"{cid}"}}), db.stock_moves.countDocuments({{company_id:"{cid}"}}),'
                 f'db.coa_entries.countDocuments({{company_id:"{cid}"}}), db.partite_aperte.countDocuments({{company_id:"{cid}"}})].join(","))')


# --- Access control ---
def test_non_admin_forbidden():
    assert sess("op").get(f"{API}/importazione/modello").status_code == 403
    assert sess("op").post(f"{API}/importazione/anteprima", files={"file": ("x.xlsx", b"x")}).status_code == 403
    assert sess("op").get(f"{API}/importazione/storico").status_code == 403


# --- Model download ---
def test_modello_structure_and_prefill():
    wb = model_wb()
    assert wb.sheetnames == ["Istruzioni", "Clienti", "Fornitori", "Articoli", "Listini", "Giacenze", "SaldiContabili", "PartiteAperte"]
    h = [c.value for c in wb["Clienti"][1]]
    assert "denominazione *" in h and "partita_iva" in h and "indirizzo *" in h
    assert [c.value for c in wb["Articoli"][1]][:2] == ["codice *", "descrizione *"]
    assert wb["Clienti"].cell(2, 2).value == CLI_PIVA
    assert wb["Articoli"].cell(2, 1).value == "T47-A1"
    dvs = {s: [d.formula1 for d in wb[s].data_validations.dataValidation] for s in ("Articoli", "PartiteAperte")}
    assert '"SI,NO"' in dvs["Articoli"] and '"cliente,fornitore"' in dvs["PartiteAperte"]


# --- Preview validations, nothing written ---
def test_preview_errors_and_no_write():
    before = counts()
    wb = model_wb()
    c = wb["Clienti"]
    c.append(["TEST_T47 Nuovo Cliente", "", CLI2_CF, "", "", "", "", "Via Nuova 2", "00100", "Roma", "RM", "IT"])
    c.append(["TEST_T47 Senza PIVA", "", "", "", "", "", "", "Via 3", "00100", "Roma", "RM", "IT"])  # no piva/cf
    c.append(["TEST_T47 Senza Indirizzo", "09999999999", "", "", "", "", "", "", "00100", "Roma", "RM", "IT"])  # missing mandatory
    wb["Fornitori"].append(["TEST_T47 Fornitore", FOR_PIVA, FOR_PIVA, "", "", "", "", "Via F 1", "10100", "Torino", "TO", "IT", 50])
    a = wb["Articoli"]
    a.append(["T47-A2", "TEST articolo nuovo", "KG", "12,50", 22, "", "SI", 5, 10, ""])
    a.append(["T47-A3", "TEST prezzo errato", "PZ", "abc", 22, "", "NO", "", "", ""])
    l = wb["Listini"]
    l.append([CLI_PIVA, "T47-A2", 9.5, "10+5"])
    l.append([CLI_PIVA, "NOPE", 1, ""])  # unknown article
    l.append(["00000000000", "T47-A1", 1, ""])  # unknown client
    l.append([CLI_PIVA, "T47-A1", 1, "abc"])  # bad sconto
    g = wb["Giacenze"]
    g.append(["T47-A2", (TODAY - timedelta(days=1)).strftime("%d/%m/%Y"), 10, 4.5])
    g.append(["T47-A2", (TODAY + timedelta(days=5)).strftime("%d/%m/%Y"), 10, 4.5])  # future
    g.append(["T47-A2", "32/13/2024", 10, 4.5])  # bad date
    sc = wb["SaldiContabili"]
    sc.append(["01/01/2025", "02.01.002", CLI_PIVA, 100, ""])
    sc.append(["01/01/2025", "01.01.001", "", "", 100])
    sc.append(["01/01/2025", "01.01.001", "", 10, 10])  # both
    sc.append(["01/01/2025", "99.99.999", "", 10, ""])  # unknown conto
    p = wb["PartiteAperte"]
    p.append(["cliente", CLI_PIVA, "OLD-1", "01/12/2024", "31/01/2025", 244])
    p.append(["fornitore", FOR_PIVA, "F-9", "01/12/2024", "28/02/2025", 122])
    p.append(["boh", CLI_PIVA, "X", "01/12/2024", "31/01/2025", 1])
    p.append(["cliente", CLI_PIVA, "Y", "01/12/2024", "01/11/2024", 1])  # scadenza < data
    r = upload(wb)
    assert r.status_code == 200, r.text
    d = r.json()
    rp = d["riepilogo"]
    print(rp)
    assert rp["Clienti"]["righe"] == 2 and rp["Clienti"]["nuovi"] == 1 and rp["Clienti"]["aggiornati"] == 1
    ce = {e["riga"] for e in errs(d, "Clienti")}
    assert ce == {4, 5}
    assert rp["Fornitori"]["nuovi"] == 1
    assert rp["Articoli"]["nuovi"] == 1 and rp["Articoli"]["aggiornati"] == 1 and [e["riga"] for e in errs(d, "Articoli")] == [4]
    assert rp["Listini"]["righe"] == 1 and len(errs(d, "Listini")) == 3
    assert rp["Giacenze"]["righe"] == 1 and {e["riga"] for e in errs(d, "Giacenze")} == {3, 4}
    assert rp["SaldiContabili"]["righe"] == 2 and {e["riga"] for e in errs(d, "SaldiContabili")} == {4, 5}
    assert d["bloccanti"] == []
    assert rp["PartiteAperte"]["righe"] == 2 and {e["riga"] for e in errs(d, "PartiteAperte")} == {4, 5}
    assert counts() == before
    S["bid"] = d["id"]


def test_preview_unbalanced_blocks_confirm():
    wb = model_wb()
    sc = wb["SaldiContabili"]
    sc.append(["01/01/2025", "02.01.002", "", 100, ""])
    sc.append(["02/01/2025", "01.01.001", "", "", 90])
    r = upload(wb)
    d = r.json()
    msgs = [e["errore"] for e in errs(d, "SaldiContabili") if e["riga"] == "-"]
    assert len(msgs) == 2, msgs
    assert d["bloccanti"] == ["SaldiContabili"]
    c = sess().post(f"{API}/importazione/{d['id']}/conferma")
    assert c.status_code == 400, c.text


def test_non_xlsx_400():
    r = sess().post(f"{API}/importazione/anteprima", files={"file": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 400 and "Excel" in r.json()["detail"]


def test_tenant_isolation_and_confirm():
    # re-run the valid preview (last preview replaced previous one), then try confirm from company B
    test_preview_errors_and_no_write()
    bid = S["bid"]
    r = sess("admin", "B").post(f"{API}/importazione/{bid}/conferma")
    assert r.status_code == 404
    r = sess().post(f"{API}/importazione/{bid}/conferma")
    assert r.status_code == 200, r.text
    e = r.json()["esito"]
    print(e)
    assert e == {"Clienti": 2, "Fornitori": 1, "Articoli": 2, "Listini": 1, "Giacenze": 1, "SaldiContabili": 2, "PartiteAperte": 2}
    assert sess().post(f"{API}/importazione/{bid}/conferma").status_code == 404


def test_confirm_effects_parties_articles():
    s = sess()
    parties = s.get(f"{API}/parties").json()
    old = next(p for p in parties if p["id"] == S["cli"])
    assert old["denominazione"] == "TEST_T47 Cliente Old" and old["email"] == "old@example.com"  # prefilled values kept
    lst = old.get("listino") or []
    arts = {a["codice"]: a for a in s.get(f"{API}/articles").json()}
    a2 = arts["T47-A2"]
    assert any(x["article_id"] == a2["id"] and x["prezzo"] == 9.5 and x["sconto"] == "10+5" for x in lst), lst
    assert any(p.get("codice_fiscale") == CLI2_CF and p["tipo"] == "cliente" for p in parties)
    forn = next(p for p in parties if p.get("partita_iva") == FOR_PIVA and p["tipo"] == "fornitore")
    assert forn["detraibilita_iva"] == 50
    assert a2["prezzo"] == 12.5 and a2["gestione_magazzino"] is True and a2["giacenza"] == 10 and abs(a2["costo_medio"] - 4.5) < 0.001
    S["forn"] = forn["id"]


def test_confirm_effects_coge_and_scadenzario():
    cid = S["A"]
    out = mongo(f'const e=db.coa_entries.find({{company_id:"{cid}", origine:"apertura"}}).toArray(); print(e.length+"|"+(e[0]||{{}}).causale+"|"+JSON.stringify((e[0]||{{}}).righe||[]))')
    n, caus, righe = out.split("|", 2)
    assert n == "1" and caus == "AP", out
    assert S["cli"] in righe
    s = sess()
    sc = s.get(f"{API}/scadenzario").json()
    r = next(x for x in sc["rate"] if x["numero_display"] == "OLD-1")
    assert r["residuo"] == 244 and r["party_id"] == S["cli"]
    p = s.post(f"{API}/invoices/{r['invoice_id']}/pagamenti", json={"data": TODAY.isoformat(), "importo": 100, "metodo": "bonifico"})
    assert p.status_code == 200, p.text
    r2 = next(x for x in s.get(f"{API}/scadenzario").json()["rate"] if x["numero_display"] == "OLD-1")
    assert r2["residuo"] == 144
    over = s.post(f"{API}/invoices/{r['invoice_id']}/pagamenti", json={"data": TODAY.isoformat(), "importo": 500, "metodo": "bonifico"})
    assert over.status_code == 400
    sp = s.get(f"{API}/scadenzario-passivo").json()
    rp = next(x for x in sp["rate"] if x["numero_display"] == "F-9")
    assert rp["residuo"] == 122
    p = s.post(f"{API}/passive/{rp['invoice_id']}/pagamenti", json={"data": TODAY.isoformat(), "importo": 122, "metodo": "bonifico"})
    assert p.status_code == 200, p.text
    rp2 = next((x for x in s.get(f"{API}/scadenzario-passivo").json()["rate"] if x["numero_display"] == "F-9"), None)
    assert rp2 is None or rp2["residuo"] == 0
    S["pa_cli"], S["pa_for"] = r["invoice_id"], rp["invoice_id"]


def test_get_payments_of_partita():
    # PaymentsPanel uses GET /{kind}/{id}/pagamenti
    s = sess()
    r1 = s.get(f"{API}/invoices/{S['pa_cli']}/pagamenti")
    r2 = s.get(f"{API}/passive/{S['pa_for']}/pagamenti")
    assert r1.status_code == 200 and r2.status_code == 200, (r1.status_code, r1.text[:100], r2.status_code, r2.text[:100])


def test_storico():
    st = sess().get(f"{API}/importazione/storico").json()
    assert any(b["id"] == S["bid"] and b["stato"] == "importato" for b in st)
    assert all("dati" not in b for b in st)
    assert sess("admin", "B").get(f"{API}/importazione/storico").json() == []


def test_unseeded_conto_accepted_when_coa_empty():
    # Company B has no chart of accounts seeded -> invalid conto is not flagged at preview
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active; ws.title = "SaldiContabili"
    ws.append(["data *", "conto *", "piva_o_cf_cliente_fornitore", "dare", "avere"])
    ws.append(["01/01/2025", "99.99.999", "", 50, ""])
    ws.append(["01/01/2025", "88.88.888", "", "", 50])
    d = upload(wb, cid="B").json()
    print(d)
    c = sess("admin", "B").post(f"{API}/importazione/{d['id']}/conferma")
    print("confirm unseeded:", c.status_code, c.text[:300])
    assert len(errs(d, "SaldiContabili")) == 2, "invalid conti not flagged at preview when chart of accounts not seeded"


def test_delete_company_cleanup():
    cid = S["B"]
    mongo(f'db.partite_aperte.insertOne({{id:"t47-x", company_id:"{cid}", tipo:"cliente"}})')
    r = sess("admin", None).delete(f"{API}/companies/{cid}")
    assert r.status_code == 200, r.text
    out = mongo(f'print(db.partite_aperte.countDocuments({{company_id:"{cid}"}})+","+db.import_batches.countDocuments({{company_id:"{cid}"}}))')
    assert out == "0,0"

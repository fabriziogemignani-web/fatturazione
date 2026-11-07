# Iteration 29: Regole di abbinamento (CRUD, prova, auto-apply on import/auto, inattive, annulla, salva_regola da riconcilia)
# and Previsione di cassa (/api/banca/previsione: saldo, voci, scaduti, serie, clamp giorni, moduli).
# Run with: pytest test_iteration29_regole_previsione.py -n 0
import os
import random
import sys
from datetime import date, timedelta

import pytest
import requests

from test_iteration7_pa_scartate_registro import API, mongo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import banca as bk  # noqa: E402

RUN = str(random.randint(100000, 999999))
TOK, UID = f"test_session_t29_admin_{RUN}", f"test-user-t29-admin-{RUN}"
CTOK, CUID = f"test_session_t29_cont_{RUN}", f"test-user-t29-cont-{RUN}"
OTOK, OUID = f"test_session_t29_oper_{RUN}", f"test-user-t29-oper-{RUN}"
PIVA = "86" + RUN + "291"
FIX = open(os.path.join(os.path.dirname(__file__), "fixtures", "sample_fattura.xml")).read()
TODAY = date.today()
D = lambda n: (TODAY + timedelta(days=n)).isoformat()  # noqa: E731
CAT = "Spese e commissioni bancarie"
ST = {}


def sess(tok):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def user(uid, tok, role, cids):
    mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.t29.{uid}@example.com", name:"TEST_T29 {role}", picture:"", role:"{role}", status:"approved", company_ids:{cids}, created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')


def clean():
    ids = f'["{UID}","{CUID}","{OUID}"]'
    mongo(f'db.companies.find({{partita_iva:"{PIVA}"}}).forEach(c=>{{["invoices","passive_invoices","parties","counters","payments","passive_payments","bank_tx","bank_accounts","bank_rules","corrispettivi"].forEach(k=>db[k].deleteMany({{company_id:c.id}})); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:{ids}}}}}); db.user_sessions.deleteMany({{user_id:{{$in:{ids}}}}});')


def csv_file(rows):
    lines = ["Data contabile;Data valuta;Descrizione operazione;Dare;Avere"]
    for d, desc, imp in rows:
        it = date.fromisoformat(d).strftime("%d/%m/%Y")
        v = f"{abs(imp):.2f}".replace(".", ",")
        lines.append(f"{it};{it};{desc};{v if imp < 0 else ''};{v if imp > 0 else ''}")
    return "\n".join(lines).encode("cp1252")


def imp(rows, tok=None):
    return sess(tok or CTOK).post(f"{API}/banca/conti/{ST['aid']}/import", files={"file": (f"m{random.random()}.csv", csv_file(rows), "text/csv")})


def tx_by(desc):
    rows = sess(TOK).get(f"{API}/banca/movimenti", params={"stato": "tutti"}).json()["movimenti"]
    return next(m for m in rows if m["descrizione"] == desc)


def rule(**kw):
    return {"nome": "Spese", "contiene": "commissioni, canone conto", "segno": "uscita", "categoria": CAT, "note": "", "attiva": True} | kw


def fc(**params):
    r = sess(OTOK).get(f"{API}/banca/previsione", params=params)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    user(UID, TOK, "admin", "[]")
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    r = s.post(f"{API}/companies", json={"denominazione": f"TEST_T29 Regole {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                         "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    user(CUID, CTOK, "contabile", f'["{ST["cid"]}"]')
    user(OUID, OTOK, "operatore", f'["{ST["cid"]}"]')
    s = sess(TOK)
    p = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": "TEST_T29 Rossi Impianti Srl", "partita_iva": "09876543217", "codice_fiscale": "",
                                       "codice_destinatario": "ABC1234", "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"})
    assert p.status_code == 200, p.text
    pid = p.json()["id"]

    def inv(data, price, **kw):
        r = s.post(f"{API}/invoices", json={"tipo_documento": "TD01", "data": data, "party_id": pid, "modalita_pagamento": "MP05",
                                           "lines": [{"descrizione": "servizio", "quantita": 1, "prezzo_unitario": price, "aliquota": 22}], **kw})
        assert r.status_code == 200, r.text
        assert s.post(f"{API}/invoices/{r.json()['id']}/send").status_code == 200
        return r.json()["id"]
    ST["A"] = inv(D(-60), 100, scadenza=D(-10))                       # 122 overdue
    ST["B"] = inv(D(0), 200, scadenza=D(20))                          # 244
    ST["C"] = inv(D(0), 500, rate=[{"scadenza": D(30), "importo": 300}, {"scadenza": D(120), "importo": 310}])  # 610 in 2 rate
    xml = FIX.replace("<IdCodice>01234567890</IdCodice>", f"<IdCodice>{PIVA}</IdCodice>").replace("<Numero>5674/2026</Numero>", f"<Numero>T29-{RUN}</Numero>") \
             .replace("<Data>2026-10-30</Data>", f"<Data>{D(-1)}</Data>").replace("<DataScadenzaPagamento>2026-11-29</DataScadenzaPagamento>",
                                                                              f"<DataScadenzaPagamento>{D(40)}</DataScadenzaPagamento>")
    up = s.post(f"{API}/passive/upload", files=[("files", ("p1.xml", xml, "text/xml"))])
    assert up.status_code == 200 and all(x["ok"] for x in up.json()), up.text
    yield
    clean()


# Previsione di cassa
class TestForecast:
    def test_01_no_accounts(self):
        d = fc()
        assert d["conti"] == 0 and d["saldo_iniziale"] == 0 and d["giorni"] == 90 and len(d["serie"]) == 91

    def test_02_forecast_90(self):
        a = sess(CTOK).post(f"{API}/banca/conti", json={"nome": "TEST_T29 Conto"})
        assert a.status_code == 200
        ST["aid"] = a.json()["id"]
        mongo(f'db.bank_accounts.updateOne({{id:"{ST["aid"]}"}}, {{$set:{{saldo:1000}}}})')
        d = fc(giorni=90)
        assert d["saldo_iniziale"] == 1000 and d["conti"] == 1
        v = d["voci"]
        assert [(x["data"], x["importo"], x["scaduta"]) for x in v] == [(D(0), 122, True), (D(20), 244, False), (D(30), 300, False), (D(40), -574.93, False)], v
        assert v[0]["scadenza"] == D(-10) and v[0]["invoice_id"] == ST["A"] and "(rata 1/2)" in v[2]["label"] and v[3]["tipo"] == "pagamento"
        assert d["entrate"] == 666 and d["uscite"] == 574.93 and d["saldo_finale"] == 1091.07
        assert d["minimo"] == {"data": D(40), "saldo": 1091.07}, d["minimo"]
        assert d["scaduti"] == {"incassi": 122, "pagamenti": 0}
        s = d["serie"]
        assert s[0] == {"data": D(0), "entrate": 122, "uscite": 0, "saldo": 1122} and s[20]["saldo"] == 1366 and s[-1]["data"] == D(90)

    def test_03_no_scaduti(self):
        d = fc(giorni=90, scaduti="false")
        assert all(not x["scaduta"] for x in d["voci"]) and d["entrate"] == 544 and d["saldo_finale"] == 969.07
        assert d["minimo"]["saldo"] == 969.07 and d["scaduti"] == {"incassi": 0, "pagamenti": 0}

    def test_04_clamp_and_long(self):
        assert len(fc(giorni=1)["serie"]) == 8
        assert fc(giorni=1000)["giorni"] == 365
        d = fc(giorni=180)
        assert any(x["importo"] == 310 and x["data"] == D(120) for x in d["voci"])

    def test_05_modules_passive_off(self):
        mods = {"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": False, "corrispettivi": True}
        assert sess(TOK).put(f"{API}/companies/{ST['cid']}/moduli", json=mods).status_code == 200
        try:
            d = sess(TOK).get(f"{API}/banca/previsione").json()
            assert d["uscite"] == 0 and all(x["importo"] > 0 for x in d["voci"])
        finally:
            sess(TOK).put(f"{API}/companies/{ST['cid']}/moduli", json={**mods, "fatture_passive": True})


# Regole di abbinamento
class TestRules:
    def test_10_roles(self):
        o = sess(OTOK)
        assert o.get(f"{API}/banca/regole").status_code == 403
        assert o.post(f"{API}/banca/regole", json=rule()).status_code == 403
        assert o.post(f"{API}/banca/regole/prova", json=rule()).status_code == 403
        d = sess(CTOK).get(f"{API}/banca/regole").json()
        assert d["regole"] == [] and CAT in d["categorie"]

    def test_11_validation(self):
        s = sess(CTOK)
        assert s.post(f"{API}/banca/regole", json=rule(categoria="Pizza")).status_code == 422
        assert s.post(f"{API}/banca/regole", json=rule(importo_min=10, importo_max=5)).status_code == 422
        assert s.post(f"{API}/banca/regole", json=rule(importo_min=-1)).status_code == 422
        assert s.post(f"{API}/banca/regole", json=rule(contiene="x")).status_code == 422
        assert s.post(f"{API}/banca/regole", json=rule(nome="")).status_code == 422
        assert s.post(f"{API}/banca/regole", json=rule(segno="boh")).status_code == 422

    def test_12_import_without_rules(self):
        r = imp([(D(-3), "COMMISSIONI TENUTA CONTO", -5.5), (D(-3), "CANONE MENSILE CONTO", -10), (D(-2), "COMMISSIONI RIMBORSO", 3),
                 (D(-2), "COMMISSIONI BONIFICO ESTERO", -150), (D(-1), "POLIZZA RCA", -300)])
        assert r.status_code == 200 and r.json()["nuovi"] == 5 and r.json()["auto"] == 0, r.text

    def test_13_create_and_prova(self):
        s = sess(CTOK)
        p = s.post(f"{API}/banca/regole/prova", json=rule(importo_max=100))
        assert p.status_code == 200, p.text
        d = p.json()
        assert d["n"] == 2 and {e["descrizione"] for e in d["esempi"]} == {"COMMISSIONI TENUTA CONTO", "CANONE MENSILE CONTO"}, d
        assert set(d["esempi"][0]) == {"id", "data", "importo", "descrizione"}
        assert s.post(f"{API}/banca/regole/prova", json=rule(segno="entrambi", importo_max=None)).json()["n"] == 4
        assert s.post(f"{API}/banca/regole/prova", json=rule(contiene="TENUTA commissioni")).json()["n"] == 1  # all words, any order, case-insens.
        r = s.post(f"{API}/banca/regole", json=rule(importo_max=100))
        assert r.status_code == 200, r.text
        x = r.json()
        assert x["applicata"] == 0 and x["attiva"] and "_id" not in x and x["importo_max"] == 100
        ST["rid"] = x["id"]
        r2 = s.post(f"{API}/banca/regole", json=rule(nome="Assicurazione", contiene="polizza", categoria="Altro", attiva=False, note="RCA auto"))
        assert r2.status_code == 200
        ST["rid2"] = r2.json()["id"]
        assert [g["id"] for g in s.get(f"{API}/banca/regole").json()["regole"]] == [ST["rid"], ST["rid2"]]

    def test_14_auto_applies_rules(self):
        r = sess(CTOK).post(f"{API}/banca/auto")
        assert r.status_code == 200 and r.json()["riconciliati"] == 2, r.text
        t = tx_by("COMMISSIONI TENUTA CONTO")
        m = t["match"]
        assert t["stato"] == "riconciliato" and m["tipo"] == "altro" and m["auto"] is True and m["rule_id"] == ST["rid"] and m["rule_nome"] == "Spese", m
        assert m["label"].startswith(CAT), m
        assert tx_by("CANONE MENSILE CONTO")["stato"] == "riconciliato"
        for d in ("COMMISSIONI RIMBORSO", "COMMISSIONI BONIFICO ESTERO", "POLIZZA RCA"):
            assert tx_by(d)["stato"] == "da_riconciliare", d
        rr = {g["id"]: g for g in sess(TOK).get(f"{API}/banca/regole").json()["regole"]}
        assert rr[ST["rid"]]["applicata"] == 2 and rr[ST["rid2"]]["applicata"] == 0

    def test_15_annulla_and_reapply(self):
        tid = tx_by("CANONE MENSILE CONTO")["id"]
        a = sess(CTOK).post(f"{API}/banca/movimenti/{tid}/annulla")
        assert a.status_code == 200 and tx_by("CANONE MENSILE CONTO")["stato"] == "da_riconciliare"
        # prova only counts da_riconciliare
        assert sess(CTOK).post(f"{API}/banca/regole/prova", json=rule(importo_max=100)).json()["n"] == 1

    def test_16_toggle_inactive_rule(self):
        s = sess(CTOK)
        r = s.put(f"{API}/banca/regole/{ST['rid2']}", json=rule(nome="Assicurazione", contiene="polizza", categoria="Altro", attiva=True, note="RCA auto"))
        assert r.status_code == 200 and r.json()["attiva"] is True and r.json()["applicata"] == 0
        assert s.post(f"{API}/banca/auto").json()["riconciliati"] == 2  # canone + polizza
        m = tx_by("POLIZZA RCA")["match"]
        assert m["label"] == "Altro · RCA auto" and m["rule_nome"] == "Assicurazione"

    def test_17_invoice_match_beats_rule(self):
        # passive invoice 574.93 "DEMO ENERGIA" + word commissioni -> invoice match wins
        s = sess(CTOK)
        s.put(f"{API}/banca/regole/{ST['rid']}", json=rule(importo_max=None))
        r = imp([(D(0), "PAGAMENTO DEMO ENERGIA TOSCANA COMMISSIONI", -574.93)])
        assert r.status_code == 200 and r.json()["auto"] >= 1, r.text  # also "COMMISSIONI BONIFICO ESTERO" now without max
        m = tx_by("PAGAMENTO DEMO ENERGIA TOSCANA COMMISSIONI")["match"]
        assert m["tipo"] == "pagamento" and "rule_id" not in m, m

    def test_18_import_applies_rule(self):
        r = imp([(D(0), "Addebito canone servizio conto online", -7)])
        assert r.status_code == 200 and r.json()["auto"] >= 1, r.text
        assert tx_by("Addebito canone servizio conto online")["match"]["rule_id"] == ST["rid"]

    def test_19_salva_regola_from_riconcilia(self):
        imp([(D(-1), "IMPOSTA DI BOLLO E/C", -2), (D(-1), "BONIFICO GIROCONTO", 50)])
        tid = tx_by("IMPOSTA DI BOLLO E/C")["id"]
        r = sess(CTOK).post(f"{API}/banca/movimenti/{tid}/riconcilia", json={"tipo": "altro", "categoria": CAT, "note": "bollo", "salva_regola": "Bollo"})
        assert r.status_code == 200 and r.json().get("regola_creata") is True, r.text
        g = next(x for x in sess(CTOK).get(f"{API}/banca/regole").json()["regole"] if x["nome"] == "Bollo")
        assert g["segno"] == "uscita" and g["categoria"] == CAT and g["contiene"] == "Bollo"
        ST["rid3"] = g["id"]
        tid2 = tx_by("BONIFICO GIROCONTO")["id"]
        r = sess(CTOK).post(f"{API}/banca/movimenti/{tid2}/riconcilia", json={"tipo": "altro", "categoria": "Giroconto tra conti", "salva_regola": "giroconto"})
        assert r.status_code == 200 and r.json()["regola_creata"]
        g = next(x for x in sess(CTOK).get(f"{API}/banca/regole").json()["regole"] if x["nome"] == "giroconto")
        assert g["segno"] == "entrata"
        r = imp([(D(0), "IMPOSTA BOLLO TRIMESTRE", -2)])
        assert tx_by("IMPOSTA BOLLO TRIMESTRE")["match"]["rule_id"] == ST["rid3"]

    def test_20_salva_regola_too_short(self):
        imp([(D(0), "ADDEBITO X", -1)])
        tid = tx_by("ADDEBITO X")["id"]
        r = sess(CTOK).post(f"{API}/banca/movimenti/{tid}/riconcilia", json={"tipo": "altro", "categoria": "Altro", "salva_regola": "X"})
        ST["short_status"] = r.status_code
        ST["short_state"] = tx_by("ADDEBITO X")["stato"]
        assert r.status_code in (400, 422), f"status {r.status_code}, movement state {ST['short_state']}"

    def test_21_put_delete_404(self):
        s = sess(CTOK)
        assert s.put(f"{API}/banca/regole/nope", json=rule()).status_code == 404
        assert s.delete(f"{API}/banca/regole/nope").status_code == 404
        assert s.delete(f"{API}/banca/regole/{ST['rid2']}").status_code == 200
        assert ST["rid2"] not in [x["id"] for x in s.get(f"{API}/banca/regole").json()["regole"]]


# unit: rule_matches
class TestUnit:
    def test_rule_matches_controparte_and_alts(self):
        r = {"segno": "entrambi", "contiene": "rossi, verdi spa", "attiva": True}
        assert bk.rule_matches(r, {"importo": 5, "descrizione": "BONIFICO", "controparte": "Mario ROSSI"})
        assert bk.rule_matches(r, {"importo": -5, "descrizione": "spa verdi", "controparte": ""})
        assert not bk.rule_matches(r, {"importo": -5, "descrizione": "verdi", "controparte": ""})
        assert not bk.rule_matches(r | {"attiva": False}, {"importo": 5, "descrizione": "rossi"})
        assert bk.rule_matches(r | {"importo_min": 5, "importo_max": 5}, {"importo": -5, "descrizione": "rossi"})

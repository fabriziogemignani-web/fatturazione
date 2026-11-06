# Iteration 27: Banca e riconciliazione - conti, import CSV/CBI, auto-match (incasso/pagamento/iva/corrispettivi),
# riconciliazione manuale (split, errori), annulla/ignora, delete pagamento -> reset, ruoli, config PSD2, gating modulo.
# Run with: pytest test_iteration27_banca.py -n 0
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
TOK, UID = f"test_session_t27_admin_{RUN}", f"test-user-t27-admin-{RUN}"
CTOK, CUID = f"test_session_t27_cont_{RUN}", f"test-user-t27-cont-{RUN}"
OTOK, OUID = f"test_session_t27_oper_{RUN}", f"test-user-t27-oper-{RUN}"
PIVA = "87" + RUN + "271"
FIX = open(os.path.join(os.path.dirname(__file__), "fixtures", "sample_fattura.xml")).read()
ST = {}


def sess(tok, cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    if cid or ST.get("cid"):
        s.headers["X-Company-Id"] = cid or ST["cid"]
    return s


def user(uid, tok, role, cids):
    mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.t27.{uid}@example.com", name:"TEST_T27 {role}", picture:"", role:"{role}", status:"approved", company_ids:{cids}, created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')


def clean():
    ids = f'["{UID}","{CUID}","{OUID}"]'
    mongo(f'db.companies.find({{partita_iva:"{PIVA}"}}).forEach(c=>{{["invoices","passive_invoices","parties","counters","payments","passive_payments","bank_tx","bank_accounts","corrispettivi"].forEach(k=>db[k].deleteMany({{company_id:c.id}})); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:{ids}}}}}); db.user_sessions.deleteMany({{user_id:{{$in:{ids}}}}});')


def it(d):
    return date.fromisoformat(d).strftime("%d/%m/%Y")


def csv_file(rows):
    lines = ["Estratto conto TEST_T27", "Conto 123", "", "Data contabile;Data valuta;Descrizione operazione;Dare;Avere"]
    for d, desc, imp in rows:
        v = f"{abs(imp):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        lines.append(f"{it(d)};{it(d)};{desc};{v if imp < 0 else ''};{v if imp > 0 else ''}")
    return "\n".join(lines).encode("cp1252")


def imp(aid, content, name="mov.csv", tok=None):
    return sess(tok or TOK).post(f"{API}/banca/conti/{aid}/import", files={"file": (name, content, "text/csv")})


def movs(stato="tutti"):
    return sess(TOK).get(f"{API}/banca/movimenti", params={"stato": stato}).json()


def tx_by(desc):
    return next(m for m in movs()["movimenti"] if m["descrizione"].startswith(desc))


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    user(UID, TOK, "admin", "[]")
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    r = s.post(f"{API}/companies", json={"denominazione": f"TEST_T27 Banca {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                         "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    user(CUID, CTOK, "contabile", f'["{ST["cid"]}"]')
    user(OUID, OTOK, "operatore", f'["{ST["cid"]}"]')
    s = sess(TOK)
    p = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": "TEST_T27 Verdi Costruzioni Srl", "partita_iva": "01234567890", "codice_fiscale": "",
                                       "codice_destinatario": "ABC1234", "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"})
    assert p.status_code == 200, p.text
    pid = p.json()["id"]

    def inv(data, price):
        r = s.post(f"{API}/invoices", json={"tipo_documento": "TD01", "data": data, "party_id": pid, "modalita_pagamento": "MP05",
                                           "lines": [{"descrizione": "TEST_T27 servizio", "quantita": 1, "prezzo_unitario": price, "aliquota": 22}]})
        assert r.status_code == 200, r.text
        assert s.post(f"{API}/invoices/{r.json()['id']}/send").status_code == 200
        return r.json()["id"]
    ST["A"] = inv("2026-10-01", 100)     # 122
    ST["B"] = inv("2026-10-02", 200)     # 244
    ST["C"] = inv("2026-10-03", 50)      # 61
    ST["D"] = inv("2026-10-03", 50)      # 61 (ambiguous with C)
    ST["E"] = inv("2026-10-04", 1000)    # 1220
    xml = FIX.replace("<IdCodice>01234567890</IdCodice>", f"<IdCodice>{PIVA}</IdCodice>").replace("<Numero>5674/2026</Numero>", "<Numero>TEST27-1</Numero>") \
             .replace("<Data>2026-10-30</Data>", "<Data>2026-10-01</Data>")
    up = s.post(f"{API}/passive/upload", files=[("files", ("p1.xml", xml, "text/xml"))])
    assert up.status_code == 200 and all(x["ok"] for x in up.json()), up.text
    ST["P"] = mongo(f'print(db.passive_invoices.findOne({{company_id:"{ST["cid"]}"}}).id)')
    assert s.post(f"{API}/corrispettivi/sync").status_code == 200
    yield
    clean()


class TestFlow:
    def test_01_create_account_roles(self):
        assert sess(OTOK).post(f"{API}/banca/conti", json={"nome": "X"}).status_code == 403
        r = sess(CTOK).post(f"{API}/banca/conti", json={"nome": "TEST_T27 Conto BPM", "iban": "it60 x054 2811 1010 0000 0123 456", "banca": "BPM"})
        assert r.status_code == 200, r.text
        a = r.json()
        assert a["fonte"] == "file" and a["iban"] == "IT60X0542811101000000123456" and a["saldo"] is None
        ST["aid"] = a["id"]
        assert sess(TOK).post(f"{API}/banca/conti", json={"nome": ""}).status_code == 422

    def test_02_import_csv_auto(self):
        content = csv_file([
            ("2026-10-05", "BONIFICO DA VERDI COSTRUZIONI SALDO FATT. 1/2026", 122),
            ("2026-10-06", "BONIFICO VERDI COSTRUZIONI", 61),
            ("2026-10-07", "PAGAMENTO DEMO ENERGIA TOSCANA", -574.93),
            ("2026-10-08", "COMMISSIONI TENUTA CONTO", -5.5),
            ("2026-10-09", "BONIFICO CLIENTE XYZ", 1500),
            ("2026-09-01", "BONIFICO VECCHIO", 10),
            ("2026-10-10", "BONIFICO DA IGNORARE", 1234.56),
        ])
        ST["csv"] = content
        assert imp(ST["aid"], content, tok=OTOK).status_code == 403
        r = imp(ST["aid"], content, tok=CTOK)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["nuovi"] == 7 and d["duplicati"] == 0 and d["formato"] == "CSV", d
        assert d["auto"] == 2, d

    def test_03_reimport_duplicates(self):
        d = imp(ST["aid"], ST["csv"]).json()
        assert d["nuovi"] == 0 and d["duplicati"] == 7, d

    def test_04_bad_file(self):
        r = imp(ST["aid"], b"hello world\nfoo bar\n", "x.txt")
        assert r.status_code == 400 and "File non leggibile" in r.json()["detail"], r.text

    def test_05_auto_incasso_payment(self):
        tx = tx_by("BONIFICO DA VERDI")
        assert tx["stato"] == "riconciliato" and tx["match"]["auto"] is True and tx["match"]["tipo"] == "incasso"
        pg = sess(TOK).get(f"{API}/invoices/{ST['A']}/pagamenti").json()["pagamenti"]
        assert len(pg) == 1 and pg[0]["importo"] == 122 and pg[0]["note"].startswith("Banca: ") and pg[0]["data"] == "2026-10-05", pg

    def test_06_auto_pagamento_passive(self):
        tx = tx_by("PAGAMENTO DEMO")
        assert tx["stato"] == "riconciliato" and tx["match"]["tipo"] == "pagamento", tx
        pg = sess(TOK).get(f"{API}/passive/{ST['P']}/pagamenti").json()["pagamenti"]
        assert len(pg) == 1 and pg[0]["importo"] == 574.93

    def test_07_ambiguous_proposta(self):
        tx = next(m for m in movs("da_riconciliare")["movimenti"] if m["descrizione"] == "BONIFICO VERDI COSTRUZIONI")
        assert tx["proposta"] and tx["proposta"]["score"] >= 50 and tx["proposta"]["ref_id"] in (ST["C"], ST["D"]), tx
        c = sess(CTOK).get(f"{API}/banca/movimenti/{tx['id']}/candidati").json()
        assert len([p for p in c["proposte"] if p["tipo"] == "incasso"]) >= 2
        assert {f["id"] for f in c["fatture"]} == {ST["B"], ST["C"], ST["D"], ST["E"]}
        assert "Altro" in c["categorie"]

    def test_08_conti_stats(self):
        a = next(x for x in sess(OTOK).get(f"{API}/banca/conti").json() if x["id"] == ST["aid"])
        assert a["movimenti"] == 7 and a["da_riconciliare"] == 5, a
        assert sess(OTOK).get(f"{API}/banca/movimenti").status_code == 200

    def test_09_operatore_forbidden(self):
        tid = tx_by("COMMISSIONI")["id"]
        o = sess(OTOK)
        assert o.get(f"{API}/banca/movimenti/{tid}/candidati").status_code == 403
        assert o.post(f"{API}/banca/movimenti/{tid}/riconcilia", json={"tipo": "altro", "categoria": "Altro"}).status_code == 403
        assert o.post(f"{API}/banca/movimenti/{tid}/ignora").status_code == 403
        assert o.post(f"{API}/banca/movimenti/{tid}/annulla").status_code == 403
        assert o.post(f"{API}/banca/auto").status_code == 403

    def test_10_errors(self):
        s = sess(CTOK)
        com = tx_by("COMMISSIONI")["id"]
        r = s.post(f"{API}/banca/movimenti/{com}/riconcilia", json={"tipo": "incasso", "ref_ids": [ST["B"]]})
        assert r.status_code == 400 and "entrata" in r.json()["detail"]
        r = s.post(f"{API}/banca/movimenti/{com}/riconcilia", json={"tipo": "altro", "categoria": "Pizza"})
        assert r.status_code == 400, r.text
        old = tx_by("BONIFICO VECCHIO")["id"]
        r = s.post(f"{API}/banca/movimenti/{old}/riconcilia", json={"tipo": "incasso", "ref_ids": [ST["B"]]})
        assert r.status_code == 400 and "precede" in r.json()["detail"], r.text
        r = s.post(f"{API}/banca/movimenti/{old}/riconcilia", json={"tipo": "corrispettivi", "ref_ids": ["2026-08-31"]})
        assert r.status_code == 400
        r = s.post(f"{API}/banca/movimenti/{com}/riconcilia", json={"tipo": "iva", "ref_ids": ["2026-m-10"]})
        assert r.status_code == 400
        r = s.post(f"{API}/banca/movimenti/{old}/riconcilia", json={"tipo": "incasso", "ref_ids": [ST["A"]]})
        assert r.status_code == 400 and "saldata" in r.json()["detail"]

    def test_11_altro_ok(self):
        com = tx_by("COMMISSIONI")["id"]
        r = sess(CTOK).post(f"{API}/banca/movimenti/{com}/riconcilia", json={"tipo": "altro", "categoria": "Spese e commissioni bancarie", "note": "TEST"})
        assert r.status_code == 200 and r.json()["match"]["label"] == "Spese e commissioni bancarie · TEST", r.text
        assert sess(CTOK).post(f"{API}/banca/movimenti/{com}/riconcilia", json={"tipo": "altro", "categoria": "Altro"}).status_code == 400

    def test_12_split(self):
        tid = tx_by("BONIFICO CLIENTE XYZ")["id"]
        r = sess(CTOK).post(f"{API}/banca/movimenti/{tid}/riconcilia", json={"tipo": "incasso", "ref_ids": [ST["E"], ST["B"]]})
        assert r.status_code == 200, r.text
        m = r.json()["match"]
        assert [x["importo"] for x in m["righe"]] == [1220, 244] and m["non_abbinato"] == 36, m
        ST["split"] = tid
        ST["split_pids"] = m["payment_ids"]
        assert sess(TOK).get(f"{API}/invoices/{ST['B']}/pagamenti").json()["pagamenti"][0]["importo"] == 244

    def test_13_delete_payment_resets_tx(self):
        r = sess(CTOK).delete(f"{API}/pagamenti/{ST['split_pids'][1]}")
        assert r.status_code == 200
        tx = tx_by("BONIFICO CLIENTE XYZ")
        assert tx["stato"] == "da_riconciliare" and tx["match"] is None

    def test_14_split_partial_delete_leaves_no_orphans(self):
        # after deleting 1 of 2 split payments the movement is free again: the other payment should not survive
        pg = sess(TOK).get(f"{API}/invoices/{ST['E']}/pagamenti").json()["pagamenti"]
        assert pg == [], f"Orphan payment left on invoice E while movement is da_riconciliare: {pg}"

    def test_14b_split_again_delete_first(self):
        tid = tx_by("BONIFICO CLIENTE XYZ")["id"]
        r = sess(CTOK).post(f"{API}/banca/movimenti/{tid}/riconcilia", json={"tipo": "incasso", "ref_ids": [ST["E"], ST["B"]]})
        assert r.status_code == 200, r.text
        pids = r.json()["match"]["payment_ids"]
        assert len(pids) == 2 and len(sess(TOK).get(f"{API}/invoices/{ST['E']}/pagamenti").json()["pagamenti"]) == 1
        assert sess(CTOK).delete(f"{API}/pagamenti/{pids[0]}").status_code == 200
        assert sess(TOK).get(f"{API}/invoices/{ST['E']}/pagamenti").json()["pagamenti"] == []
        assert sess(TOK).get(f"{API}/invoices/{ST['B']}/pagamenti").json()["pagamenti"] == []
        tx = tx_by("BONIFICO CLIENTE XYZ")
        assert tx["stato"] == "da_riconciliare" and tx["match"] is None
        assert sess(CTOK).delete(f"{API}/pagamenti/{pids[1]}").status_code == 404

    def test_14c_ref_ids_only_paid(self):
        r = imp(ST["aid"], csv_file([("2026-10-20", "BONIFICO RIF BREAK", 1220)]), "b.csv")
        assert r.status_code == 200 and r.json()["auto"] == 0, r.text
        tid = tx_by("BONIFICO RIF BREAK")["id"]
        r = sess(CTOK).post(f"{API}/banca/movimenti/{tid}/riconcilia", json={"tipo": "incasso", "ref_ids": [ST["E"], ST["B"]]})
        assert r.status_code == 200, r.text
        m = r.json()["match"]
        assert m["ref_ids"] == [ST["E"]] and len(m["payment_ids"]) == 1 and m["non_abbinato"] == 0, m
        assert sess(CTOK).post(f"{API}/banca/movimenti/{tid}/annulla").status_code == 200
        assert sess(TOK).get(f"{API}/invoices/{ST['E']}/pagamenti").json()["pagamenti"] == []

    def test_15_annulla(self):
        tx = tx_by("BONIFICO DA VERDI")
        r = sess(CTOK).post(f"{API}/banca/movimenti/{tx['id']}/annulla")
        assert r.status_code == 200 and r.json()["stato"] == "da_riconciliare"
        assert sess(TOK).get(f"{API}/invoices/{ST['A']}/pagamenti").json()["pagamenti"] == []
        assert sess(CTOK).post(f"{API}/banca/movimenti/{tx['id']}/annulla").status_code == 400
        r = sess(CTOK).post(f"{API}/banca/auto")
        assert r.status_code == 200 and r.json()["riconciliati"] >= 1, r.text
        assert tx_by("BONIFICO DA VERDI")["stato"] == "riconciliato"

    def test_16_ignora(self):
        tid = tx_by("BONIFICO DA IGNORARE")["id"]
        r = sess(CTOK).post(f"{API}/banca/movimenti/{tid}/ignora")
        assert r.status_code == 200 and r.json()["stato"] == "ignorato"
        assert sess(CTOK).post(f"{API}/banca/movimenti/{tid}/ignora").status_code == 400
        assert movs("ignorato")["conteggi"]["ignorato"] == 1
        assert sess(CTOK).post(f"{API}/banca/movimenti/{tid}/annulla").status_code == 200

    def test_17_corrispettivi(self):
        rows = mongo(f'db.corrispettivi.aggregate([{{$match:{{company_id:"{ST["cid"]}"}}}},{{$group:{{_id:"$data",t:{{$sum:"$totale"}}}}}},{{$sort:{{_id:1}}}}]).forEach(x=>print(x._id+"|"+x.t))').split("\n")
        rows = [(r.split("|")[0], round(float(r.split("|")[1]), 2)) for r in rows if "|" in r]
        assert rows, "no corrispettivi"
        d, tot = rows[len(rows) // 2]
        md = (date.fromisoformat(d) + timedelta(days=2)).isoformat()
        r = imp(ST["aid"], csv_file([(md, "VERSAMENTO CONTANTI NEGOZIO", tot)]), "c.csv")
        assert r.status_code == 200, r.text
        tx = tx_by("VERSAMENTO CONTANTI")
        if tx["stato"] == "da_riconciliare":
            c = sess(CTOK).get(f"{API}/banca/movimenti/{tx['id']}/candidati").json()["proposte"]
            assert any(p["tipo"] == "corrispettivi" and p["ref_id"] == d for p in c), c
            r = sess(CTOK).post(f"{API}/banca/movimenti/{tx['id']}/riconcilia", json={"tipo": "corrispettivi", "ref_ids": [d]})
            assert r.status_code == 200, r.text
        tx = tx_by("VERSAMENTO CONTANTI")
        assert tx["stato"] == "riconciliato" and tx["match"]["tipo"] == "corrispettivi" and tx["match"]["ref_ids"] == [d], tx

    def test_18_iva(self):
        liq = sess(TOK).get(f"{API}/liquidazione-iva", params={"anno": 2026, "periodicita": "mensile"}).json()
        p = next(x for x in liq["periodi"] if x["periodo"] == 10)
        assert p["da_versare"] > 0, p
        r = imp(ST["aid"], csv_file([("2026-11-05", "DELEGA F24 AGENZIA ENTRATE", -p["da_versare"])]), "f.csv")
        assert r.status_code == 200, r.text
        tx = tx_by("DELEGA F24")
        if tx["stato"] == "da_riconciliare":
            r = sess(CTOK).post(f"{API}/banca/movimenti/{tx['id']}/riconcilia", json={"tipo": "iva", "ref_ids": ["2026-m-10"]})
            assert r.status_code == 200, r.text
        tx = tx_by("DELEGA F24")
        assert tx["stato"] == "riconciliato" and tx["match"]["ref_ids"] == ["2026-m-10"], tx

    def test_19_cbi(self):
        a = sess(TOK).post(f"{API}/banca/conti", json={"nome": "TEST_T27 Conto CBI"}).json()
        ST["aid2"] = a["id"]

        def rec(t, body):
            return (" " + t + body).ljust(120)[:120]
        r62 = list(" 62" + " " * 117)
        r62[13:19], r62[19:25], r62[25], r62[26:41], r62[41:43] = "151026", "151026", "C", "000000000012200", "48"
        r62[86:120] = "BONIFICO DA VERDI COSTR".ljust(34)
        r62b = list(" 62" + " " * 117)
        r62b[13:19], r62b[19:25], r62b[25], r62b[26:41] = "161026", "161026", "D", "000000000000250"
        r62b[86:120] = "COMMISSIONE".ljust(34)
        r63 = list(" 63" + " " * 117)
        r63[13:60] = "BONIFICO SEPA EXTRA TESTO".ljust(47)
        r64 = list(" 64" + " " * 117)
        r64[13:19], r64[19], r64[20:35] = "311026", "C", "000000000987654"
        txt = "\n".join([rec("RH", "TEST"), rec("61", ""), "".join(r62), "".join(r62b), "".join(r63), "".join(r64), rec("EF", "")])
        r = imp(ST["aid2"], txt.encode(), "e.cbi")
        assert r.status_code == 200, r.text
        assert r.json()["nuovi"] == 2 and r.json()["formato"] == "CBI", r.json()
        acc = next(x for x in sess(TOK).get(f"{API}/banca/conti").json() if x["id"] == ST["aid2"])
        assert acc["saldo"] == 9876.54 and acc["saldo_at"] == "2026-10-31", acc
        m = [x for x in movs()["movimenti"] if x["account_id"] == ST["aid2"]]
        com = next(x for x in m if x["importo"] < 0)
        assert com["importo"] == -2.5 and "EXTRA TESTO" in com["descrizione"], com
        assert imp(ST["aid2"], txt.encode(), "e.cbi").json()["duplicati"] == 2

    def test_20_delete_accounts(self):
        assert sess(CTOK).delete(f"{API}/banca/conti/{ST['aid2']}").status_code == 403
        r = sess(TOK).delete(f"{API}/banca/conti/{ST['aid']}")
        assert r.status_code == 400 and "riconciliat" in r.json()["detail"]
        tx = [x for x in movs()["movimenti"] if x["account_id"] == ST["aid2"] and x["stato"] == "riconciliato"]
        for x in tx:
            sess(TOK).post(f"{API}/banca/movimenti/{x['id']}/annulla")
        assert sess(TOK).delete(f"{API}/banca/conti/{ST['aid2']}").status_code == 200
        assert all(x["account_id"] != ST["aid2"] for x in movs()["movimenti"])


    def test_21_delete_passive_payment_resets(self):
        pg = sess(TOK).get(f"{API}/passive/{ST['P']}/pagamenti").json()["pagamenti"]
        assert len(pg) == 1
        assert sess(CTOK).delete(f"{API}/passive-pagamenti/{pg[0]['id']}").status_code == 200
        tx = tx_by("PAGAMENTO DEMO")
        assert tx["stato"] == "da_riconciliare" and tx["match"] is None, tx


class TestConfig:
    def test_usa_sdi(self):
        mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}},{{$set:{{"sdi.provider":"acube","sdi.email":"x@example.com"}}}})')
        c = sess(OTOK).get(f"{API}/banca/config").json()
        assert c["usa_sdi"] is True and c["configurato"] is True and c["has_password"] is False
        mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}},{{$unset:{{sdi:""}}}})')

    def test_put_config(self):
        body = {"ambiente": "sandbox", "email": "Fake.T27@Example.com", "password": "FakePass-t27", "auto": True}
        assert sess(CTOK).put(f"{API}/banca/config", json=body).status_code == 403
        assert sess(TOK).put(f"{API}/banca/config", json={**body, "password": None, "email": "new@example.com"}).status_code == 400
        r = sess(TOK).put(f"{API}/banca/config", json=body)
        assert r.status_code == 200 and r.json()["has_password"] and r.json()["email"] == "fake.t27@example.com" and r.json()["usa_sdi"] is False
        assert "FakePass-t27" not in r.text and "password_enc" not in r.text
        for path in ("/banca/config", "/company", "/banca/riepilogo"):
            g = sess(TOK).get(f"{API}{path}")
            assert g.status_code == 200 and "FakePass" not in g.text and "password_enc" not in g.text, path
        # keep password when omitted
        r = sess(TOK).put(f"{API}/banca/config", json={**body, "password": None, "auto": False})
        assert r.status_code == 200 and r.json()["has_password"] and r.json()["auto"] is False
        enc = mongo(f'print(db.companies.findOne({{id:"{ST["cid"]}"}}).banca.password_enc)')
        assert enc and "FakePass" not in enc

    def test_get_config_reflects_own_credentials(self):
        # GET must report has_password/configurato=true after own credentials are saved (UI enables Collega/Sincronizza on it)
        c = sess(TOK).get(f"{API}/banca/config").json()
        assert c["has_password"] is True and c["configurato"] is True and c["usa_sdi"] is False, c
        r = sess(TOK).get(f"{API}/banca/riepilogo").json()
        cfg = r.get("config") or {}
        assert cfg.get("has_password") is True and cfg.get("configurato") is True, r

    def test_put_clears_last_sync_error_and_remove_own(self):
        mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}},{{$set:{{"banca.last_sync_error":"boom"}}}})')
        assert sess(TOK).get(f"{API}/banca/config").json()["last_sync_error"] == "boom"
        r = sess(TOK).put(f"{API}/banca/config", json={"ambiente": "sandbox", "email": "fake.t27@example.com", "password": None, "auto": True})
        assert r.status_code == 200 and r.json()["last_sync_error"] is None and r.json()["has_password"], r.text
        assert sess(TOK).get(f"{API}/banca/config").json()["last_sync_error"] is None
        # empty email -> own credentials removed, fall back to SDI A-Cube
        mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}},{{$set:{{"sdi.provider":"acube","sdi.email":"x@example.com"}}}})')
        r = sess(TOK).put(f"{API}/banca/config", json={"ambiente": "sandbox", "email": "", "password": None, "auto": True})
        assert r.status_code == 200, r.text
        c = sess(TOK).get(f"{API}/banca/config").json()
        assert c["has_password"] is False and c["usa_sdi"] is True and c["configurato"] is True and c["email"] == "", c
        assert mongo(f'print(db.companies.findOne({{id:"{ST["cid"]}"}}).banca.password_enc || "none")').strip() == "none"
        mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}},{{$unset:{{sdi:""}}}})')
        c = sess(TOK).get(f"{API}/banca/config").json()
        assert c["configurato"] is False, c
        # restore own creds for psd2 tests
        r = sess(TOK).put(f"{API}/banca/config", json={"ambiente": "sandbox", "email": "fake.t27@example.com", "password": "FakePass-t27", "auto": True})
        assert r.status_code == 200 and r.json()["has_password"]

    def test_psd2_fake(self):
        assert sess(CTOK).post(f"{API}/banca/psd2/connect").status_code == 403
        r = sess(TOK).post(f"{API}/banca/psd2/connect", headers={"Origin": "https://x.example"})
        assert r.status_code == 400 and "A-Cube" in r.json()["detail"], r.text
        r = sess(CTOK).post(f"{API}/banca/psd2/sync")
        assert r.status_code == 400 and "A-Cube" in r.json()["detail"], r.text
        c = sess(TOK).get(f"{API}/banca/config").json()
        assert c["last_sync_error"]

    def test_riepilogo(self):
        d = sess(OTOK).get(f"{API}/banca/riepilogo").json()
        assert len(d["conti"]) == 1 and "saldo_totale" in d

    def test_module_gating(self):
        cid = ST["cid"]
        mods = {"fatturazione": False, "archivio": True, "fatture_attive": True, "fatture_passive": True, "corrispettivi": True}
        assert sess(TOK).put(f"{API}/companies/{cid}/moduli", json=mods).status_code == 200
        try:
            assert sess(TOK).get(f"{API}/banca/conti").status_code == 403
            assert sess(TOK).get(f"{API}/banca/movimenti").status_code == 403
        finally:
            sess(TOK).put(f"{API}/companies/{cid}/moduli", json={**mods, "fatturazione": True})
        assert sess(TOK).get(f"{API}/banca/conti").status_code == 200


# unit: parser / scoring edge cases
class TestUnit:
    def test_csv_importo_column(self):
        p = bk.parse_csv("Data;Descrizione;Importo\n01/10/2026;A;-1.234,56\n02/10/2026;B;+10,00\n")
        assert [m["importo"] for m in p["movimenti"]] == [-1234.56, 10.0]

    def test_score_number_substring(self):
        # invoice 1/2026 must not get the "number" bonus from a description that references invoice 11/2026
        d = {"numero_display": "1/2026", "residuo": 122.0, "cliente": "Rossi Spa", "data": "2026-10-01"}
        tx = {"descrizione": "BONIFICO SALDO FATTURA 11/2026", "importo": 122.0, "data": "2026-10-10"}
        sc, hit = bk.score_doc(tx, d)
        assert sc < 80 and hit is False, (sc, hit)

    def test_score_n_word_end(self):
        d = {"numero_display": "3/2026", "residuo": 50.0, "cliente": "Bianchi Spa", "data": "2026-10-01"}
        tx = {"descrizione": "BONIFICO BIANCHI CAUSALE EUROPEAN 3 RATE", "importo": 50.0, "data": "2026-10-10"}
        sc, hit = bk.score_doc(tx, d)
        assert sc == 80 and hit is True, (sc, hit)

    def test_score_number_exact_and_prefixes(self):
        d = {"numero_display": "1/2026", "residuo": 122.0, "cliente": "Rossi Spa", "data": "2026-10-01"}
        for desc in ("SALDO FATT. 1/2026", "FT 1", "FATTURA N. 1", "NR 001 ROSSI", "rif 1/2026"):
            sc, _ = bk.score_doc({"descrizione": desc, "importo": 122.0, "data": "2026-10-10"}, d)
            assert sc >= 90, (desc, sc)
        for desc in ("FATTURA 11/2026", "FT 21", "21/2026", "PAGAMENTO 1/20260", "CAMPAIGN 1"):
            sc, _ = bk.score_doc({"descrizione": desc, "importo": 122.0, "data": "2026-10-10"}, d)
            assert sc == 55, (desc, sc)

    def test_safe_auto_requires_name(self):
        d = {"id": "x", "numero_display": "1/2026", "residuo": 122.0, "cliente": "Rossi Spa", "data": "2026-10-01"}
        tx = {"descrizione": "BONIFICO SALDO FATT 1/2026", "importo": 122.0, "data": "2026-10-10"}
        c = bk.candidates(tx, [d], [], [], [])
        assert c[0]["score"] == 90 and c[0]["nome"] is False and bk.safe_auto(c) is None, c
        tx["descrizione"] += " ROSSI"
        c = bk.candidates(tx, [d], [], [], [])
        assert c[0]["nome"] is True and bk.safe_auto(c)["ref_id"] == "x", c

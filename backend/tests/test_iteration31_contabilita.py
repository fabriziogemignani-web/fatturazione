# Iteration 31: Contabilità generale - seed piano/causali/IVA/parametri, CRUD conti/causali/IVA, parametri,
# auto-registrazione vendite (FV/NV), acquisti (FA, contropartita fornitore), banca (IN/PG/MB), manuali, rigenera,
# report (giornale, mastrino, bilancio), gating modulo.
# Run with: pytest test_iteration31_contabilita.py -n 0
import os
import random
from datetime import date, timedelta

import pytest
import requests

from test_iteration7_pa_scartate_registro import API, mongo

RUN = str(random.randint(100000, 999999))
TOK, UID = f"test_session_t31_admin_{RUN}", f"test-user-t31-admin-{RUN}"
OTOK, OUID = f"test_session_t31_oper_{RUN}", f"test-user-t31-oper-{RUN}"
PIVA = "86" + RUN + "311"
FIX = open(os.path.join(os.path.dirname(__file__), "fixtures", "sample_fattura.xml")).read()
TODAY = date.today()
D1 = (TODAY - timedelta(days=5)).isoformat()
ST = {}
ALL = {"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True, "corrispettivi": True, "contabilita": True}


def sess(tok=TOK):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def user(uid, tok, role, cids):
    mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.t31.{uid}@example.com", name:"TEST_T31 {role}", picture:"", role:"{role}", status:"approved", company_ids:{cids}, created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')


def clean():
    ids = f'["{UID}","{OUID}"]'
    mongo(f'db.companies.find({{partita_iva:"{PIVA}"}}).forEach(c=>{{["invoices","passive_invoices","parties","articles","counters","payments","passive_payments","bank_tx","bank_accounts","corrispettivi","coa_accounts","coa_causali","coa_iva","coa_entries"].forEach(k=>db[k].deleteMany({{company_id:c.id}})); db.counters.deleteMany({{key:{{$regex:"^coge_"+c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:{ids}}}}}); db.user_sessions.deleteMany({{user_id:{{$in:{ids}}}}});')


def entries(**params):
    return sess().get(f"{API}/contabilita/registrazioni", params=params).json()


def entry_for(origine, ref):
    return next((e for e in entries(origine=origine)["registrazioni"] if e["ref_id"] == ref), None)


def side(e, conto):
    rows = [r for r in e["righe"] if r["conto"] == conto]
    return round(sum(r["dare"] for r in rows), 2), round(sum(r["avere"] for r in rows), 2)


def balanced(e):
    return round(sum(r["dare"] for r in e["righe"]), 2) == round(sum(r["avere"] for r in e["righe"]), 2)


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    user(UID, TOK, "admin", "[]")
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    r = s.post(f"{API}/companies", json={"denominazione": f"TEST_T31 Coge {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                         "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    user(OUID, OTOK, "operatore", f'["{ST["cid"]}"]')
    yield
    clean()


def make_inv(pid, lines, tipo="TD01", **kw):
    s = sess()
    r = s.post(f"{API}/invoices", json={"tipo_documento": tipo, "data": D1, "party_id": pid, "modalita_pagamento": "MP05", "lines": lines, **kw})
    assert r.status_code == 200, r.text
    iid = r.json()["id"]
    assert s.post(f"{API}/invoices/{iid}/send").status_code == 200
    rr = s.post(f"{API}/invoices/{iid}/refresh")
    assert rr.status_code == 200, rr.text
    return iid


class TestSeed:
    def test_01_conti_seeded(self):
        d = sess().get(f"{API}/contabilita/conti").json()
        c = d["conti"]
        assert 140 <= len(c) <= 220, len(c)
        assert {x["livello"] for x in c} == {1, 2, 3}
        codes = {x["codice"] for x in c}
        assert {"05", "05.01", "05.01.001", "13.03.001", "20.01.001"} <= codes

    def test_02_causali_iva_parametri(self):
        cau = {x["codice"] for x in sess().get(f"{API}/contabilita/causali").json()}
        assert {"FV", "NV", "FA", "NA", "IN", "PG", "VC", "VI", "MB", "GC", "GE"} <= cau
        iva = {x["codice"] for x in sess().get(f"{API}/contabilita/codici-iva").json()}
        assert {"22", "10", "5", "4", "N1", "N4", "N6.1", "N7"} <= iva
        p = sess().get(f"{API}/contabilita/parametri").json()["parametri"]
        assert p["clienti"] == "05.01.001" and p["contropartita_vendite"] == "unica" and p["contropartita_acquisti"] == "unica"


class TestCrud:
    def test_01_add_conto_rules(self):
        s = sess()
        assert s.post(f"{API}/contabilita/conti", json={"codice": "20.77.001", "descrizione": "TEST_x"}).status_code == 400  # parent missing
        assert s.post(f"{API}/contabilita/conti", json={"codice": "20.01.001", "descrizione": "TEST_dup"}).status_code == 400
        assert s.post(f"{API}/contabilita/conti", json={"codice": "2001", "descrizione": "TEST_bad"}).status_code == 422
        r = s.post(f"{API}/contabilita/conti", json={"codice": "20.01.050", "descrizione": "TEST_Ricavi consulenza"})
        assert r.status_code == 200, r.text
        assert r.json()["livello"] == 3 and r.json()["tipo"] == "ricavo"
        ST["conto_art"] = r.json()["id"]
        r = s.post(f"{API}/contabilita/conti", json={"codice": "30.07.050", "descrizione": "TEST_Costi energia forn"})
        assert r.status_code == 200 and r.json()["tipo"] == "costo"
        r = s.put(f"{API}/contabilita/conti/{ST['conto_art']}", json={"descrizione": "TEST_Ricavi consulenze"})
        assert r.status_code == 200 and r.json()["descrizione"] == "TEST_Ricavi consulenze"

    def test_02_delete_conto_rules(self):
        s = sess()
        c = {x["codice"]: x["id"] for x in s.get(f"{API}/contabilita/conti").json()["conti"]}
        assert s.delete(f"{API}/contabilita/conti/{c['05.01']}").status_code == 400  # children
        assert s.delete(f"{API}/contabilita/conti/{c['05.01.001']}").status_code == 400  # parametri
        r = s.post(f"{API}/contabilita/conti", json={"codice": "20.01.099", "descrizione": "TEST_del"})
        assert s.delete(f"{API}/contabilita/conti/{r.json()['id']}").status_code == 200
        assert "20.01.099" not in {x["codice"] for x in s.get(f"{API}/contabilita/conti").json()["conti"]}

    def test_03_causali_iva_crud(self):
        s = sess()
        r = s.post(f"{API}/contabilita/causali", json={"codice": "TST", "descrizione": "TEST_causale", "conto_dare": "05.01.001"})
        assert r.status_code == 200, r.text
        cid_ = r.json()["id"]
        assert s.post(f"{API}/contabilita/causali", json={"codice": "TST", "descrizione": "dup"}).status_code == 400
        assert s.post(f"{API}/contabilita/causali", json={"codice": "TS2", "descrizione": "x", "conto_dare": "05.01"}).status_code == 400
        assert s.put(f"{API}/contabilita/causali/{cid_}", json={"codice": "TST", "descrizione": "TEST_caus2"}).status_code == 200
        assert s.delete(f"{API}/contabilita/causali/{cid_}").status_code == 200
        fv = next(x for x in s.get(f"{API}/contabilita/causali").json() if x["codice"] == "FV")
        assert s.delete(f"{API}/contabilita/causali/{fv['id']}").status_code == 400
        r = s.post(f"{API}/contabilita/codici-iva", json={"codice": "22IND", "descrizione": "TEST_iva", "aliquota": 22, "detraibilita": 40})
        assert r.status_code == 200, r.text
        assert s.delete(f"{API}/contabilita/codici-iva/{r.json()['id']}").status_code == 200
        i22 = next(x for x in s.get(f"{API}/contabilita/codici-iva").json() if x["codice"] == "22")
        assert s.delete(f"{API}/contabilita/codici-iva/{i22['id']}").status_code == 400

    def test_04_parametri_validation(self):
        s = sess()
        p = s.get(f"{API}/contabilita/parametri").json()["parametri"]
        conti = {k: p[k] for k in p if k not in ("contropartita_vendite", "contropartita_acquisti", "aliquota_rc", "categorie")}
        bad = {**conti, "clienti": "05.01"}
        assert s.put(f"{API}/contabilita/parametri", json={"conti": bad, "categorie": p["categorie"]}).status_code == 400
        assert s.put(f"{API}/contabilita/parametri", json={"conti": conti, "categorie": p["categorie"], "contropartita_vendite": "xx"}).status_code == 422
        r = s.put(f"{API}/contabilita/parametri", json={"conti": conti, "categorie": p["categorie"], "contropartita_vendite": "articolo",
                                                       "contropartita_acquisti": "fornitore"})
        assert r.status_code == 200, r.text
        g = s.get(f"{API}/contabilita/parametri").json()["parametri"]
        assert g["contropartita_vendite"] == "articolo" and g["contropartita_acquisti"] == "fornitore"

    def test_05_operatore_forbidden(self):
        assert sess(OTOK).post(f"{API}/contabilita/conti", json={"codice": "20.01.098", "descrizione": "x"}).status_code == 403


class TestVendite:
    def test_01_article_and_invoice(self):
        s = sess()
        assert s.post(f"{API}/articles", json={"codice": "TART", "descrizione": "TEST_art", "unita_misura": "pz", "prezzo": 1, "aliquota": 22,
                                               "conto_ricavo": "05.01"}).status_code == 400
        a = s.post(f"{API}/articles", json={"codice": "TART", "descrizione": "TEST_art", "unita_misura": "pz", "prezzo": 1, "aliquota": 22, "conto_ricavo": "20.01.050"})
        assert a.status_code == 200, a.text
        assert a.json()["conto_ricavo"] == "20.01.050"
        ST["art"] = a.json()["id"]
        p = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": "TEST_T31 Cliente Srl", "partita_iva": "01234567890", "codice_fiscale": "",
                                           "codice_destinatario": "ABC1234", "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"})
        assert p.status_code == 200, p.text
        ST["cli"] = p.json()["id"]
        ST["inv"] = make_inv(ST["cli"], [{"descrizione": "TEST art", "quantita": 2, "prezzo_unitario": 100, "aliquota": 22, "article_id": ST["art"]},
                                         {"descrizione": "TEST libero", "quantita": 1, "prezzo_unitario": 50, "aliquota": 22}])
        inv = s.get(f"{API}/invoices/{ST['inv']}").json()
        assert inv["status"] == "consegnata", inv["status"]
        e = entry_for("vendita", ST["inv"])
        assert e, "FV entry not created"
        assert e["causale"] == "FV" and balanced(e)
        assert side(e, "05.01.001") == (305.0, 0.0)
        assert side(e, "20.01.050") == (0.0, 200.0)
        assert side(e, "20.01.001") == (0.0, 50.0)
        assert side(e, "13.03.001") == (0.0, 55.0)

    def test_02_idempotent(self):
        s = sess()
        s.post(f"{API}/invoices/{ST['inv']}/refresh")
        r = s.post(f"{API}/contabilita/rigenera", json={})
        assert r.status_code == 200, r.text
        assert len([e for e in entries(origine="vendita")["registrazioni"] if e["ref_id"] == ST["inv"]]) == 1

    def test_03_ritenuta_invoice(self):
        iid = make_inv(ST["cli"], [{"descrizione": "TEST prof", "quantita": 1, "prezzo_unitario": 1000, "aliquota": 22}],
                       ritenuta={"tipo": "RT01", "aliquota": 20, "causale": "A"})
        e = entry_for("vendita", iid)
        assert e and balanced(e), e
        assert side(e, "05.02.003") == (200.0, 0.0)
        assert side(e, "05.01.001") == (1020.0, 0.0)

    def test_04_credit_note(self):
        inv = sess().get(f"{API}/invoices/{ST['inv']}").json()
        iid = make_inv(ST["cli"], [{"descrizione": "TEST storno", "quantita": 1, "prezzo_unitario": 50, "aliquota": 22}], tipo="TD04",
                       fattura_collegata_id=ST["inv"], fatture_collegate=[{"numero": inv["numero_display"], "data": inv["data"]}])
        e = entry_for("vendita", iid)
        assert e and e["causale"] == "NV" and balanced(e), e
        assert side(e, "05.01.001") == (0.0, 61.0)
        assert side(e, "13.03.001") == (11.0, 0.0)


class TestAcquisti:
    def test_01_supplier_and_import(self):
        s = sess()
        f = s.post(f"{API}/parties", json={"tipo": "fornitore", "denominazione": "TEST_T31 DEMO Energia", "partita_iva": "02345670481", "codice_fiscale": "",
                                           "indirizzo": "Via Y 1", "cap": "50100", "comune": "Firenze", "provincia": "FI", "nazione": "IT", "conto_costo": "30.07.050"})
        assert f.status_code == 200, f.text
        assert f.json()["conto_costo"] == "30.07.050"
        ST["forn"] = f.json()["id"]
        xml = FIX.replace("<IdCodice>01234567890</IdCodice>", f"<IdCodice>{PIVA}</IdCodice>").replace("<Numero>5674/2026</Numero>", "<Numero>TEST31-1</Numero>") \
                 .replace("<Data>2026-10-30</Data>", f"<Data>{D1}</Data>")
        up = s.post(f"{API}/passive/upload", files=[("files", ("p1.xml", xml, "text/xml"))])
        assert up.status_code == 200 and all(x["ok"] for x in up.json()), up.text
        ST["pas"] = mongo(f'print(db.passive_invoices.findOne({{company_id:"{ST["cid"]}"}}).id)')
        e = entry_for("acquisto", ST["pas"])
        assert e and e["causale"] == "FA" and balanced(e), e
        assert side(e, "30.07.050") == (471.25, 0.0)
        assert side(e, "05.02.002") == (103.68, 0.0)
        assert side(e, "13.02.001") == (0.0, 574.93)


class TestBanca:
    def test_01_bank_reconcile(self):
        s = sess()
        a = s.post(f"{API}/banca/conti", json={"nome": "TEST_T31 Conto", "iban": "", "banca": "X"})
        assert a.status_code == 200, a.text
        ST["bank"] = a.json()["id"]
        d = TODAY.strftime("%d/%m/%Y")
        csv = "\n".join(["Data contabile;Data valuta;Descrizione operazione;Dare;Avere",
                         f"{d};{d};TEST INCASSO CLIENTE;;305,00", f"{d};{d};TEST PAGAMENTO ENERGIA;574,93;", f"{d};{d};TEST COMMISSIONI;3,50;"]).encode("cp1252")
        r = s.post(f"{API}/banca/conti/{ST['bank']}/import", files={"file": ("m.csv", csv, "text/csv")})
        assert r.status_code == 200, r.text
        movs = s.get(f"{API}/banca/movimenti", params={"stato": "tutti"}).json()["movimenti"]
        tx = {m["descrizione"]: m for m in movs}
        for desc, body in (("TEST INCASSO CLIENTE", {"tipo": "incasso", "ref_ids": [ST["inv"]]}),
                           ("TEST PAGAMENTO ENERGIA", {"tipo": "pagamento", "ref_ids": [ST["pas"]]}),
                           ("TEST COMMISSIONI", {"tipo": "altro", "categoria": "Spese e commissioni bancarie"})):
            m = tx[desc]
            if m["stato"] != "riconciliato":
                rr = s.post(f"{API}/banca/movimenti/{m['id']}/riconcilia", json=body)
                assert rr.status_code == 200, rr.text
            ST[desc] = m["id"]
        e = entry_for("banca", ST["TEST INCASSO CLIENTE"])
        assert e and e["causale"] == "IN" and side(e, "06.01.001") == (305.0, 0.0) and side(e, "05.01.001") == (0.0, 244.0) and side(e, "13.05.009") == (0.0, 61.0), e  # NC reduced residual: 61 to transitorio
        e = entry_for("banca", ST["TEST PAGAMENTO ENERGIA"])
        assert e and e["causale"] == "PG" and side(e, "13.02.001") == (574.93, 0.0), e
        e = entry_for("banca", ST["TEST COMMISSIONI"])
        assert e and e["causale"] == "MB" and side(e, "30.07.011") == (3.5, 0.0), e

    def test_02_annulla(self):
        s = sess()
        assert s.post(f"{API}/banca/movimenti/{ST['TEST COMMISSIONI']}/annulla").status_code == 200
        assert entry_for("banca", ST["TEST COMMISSIONI"]) is None


class TestManuali:
    def test_01_manual_entry(self):
        s = sess()
        bad = {"data": TODAY.isoformat(), "causale": "GE", "descrizione": "TEST_man", "righe": [{"conto": "06.02.001", "dare": 100}, {"conto": "06.01.001", "avere": 90}]}
        assert s.post(f"{API}/contabilita/registrazioni", json=bad).status_code == 400
        bad2 = {**bad, "righe": [{"conto": "06.02", "dare": 100}, {"conto": "06.01.001", "avere": 100}]}
        assert s.post(f"{API}/contabilita/registrazioni", json=bad2).status_code == 400
        ok = {**bad, "righe": [{"conto": "06.02.001", "dare": 100}, {"conto": "06.01.001", "avere": 100}]}
        r = s.post(f"{API}/contabilita/registrazioni", json=ok)
        assert r.status_code == 200, r.text
        ST["man"] = r.json()["id"]
        ok["descrizione"] = "TEST_man2"
        ok["righe"][0]["dare"] = ok["righe"][1]["avere"] = 120
        r = s.put(f"{API}/contabilita/registrazioni/{ST['man']}", json=ok)
        assert r.status_code == 200 and r.json()["totale"] == 120
        e = next(x for x in entries(origine="manuale")["registrazioni"] if x["id"] == ST["man"])
        assert e["descrizione"] == "TEST_man2"

    def test_02_auto_not_editable(self):
        s = sess()
        e = entry_for("vendita", ST["inv"])
        assert s.delete(f"{API}/contabilita/registrazioni/{e['id']}").status_code == 400
        assert s.put(f"{API}/contabilita/registrazioni/{e['id']}", json={"data": e["data"], "causale": "GE", "descrizione": "x",
                                                                          "righe": [{"conto": "06.02.001", "dare": 1}, {"conto": "06.01.001", "avere": 1}]}).status_code == 400

    def test_03_delete_manual(self):
        s = sess()
        assert s.delete(f"{API}/contabilita/registrazioni/{ST['man']}").status_code == 200
        assert not any(x["id"] == ST["man"] for x in entries()["registrazioni"])


class TestReport:
    def test_01_giornale(self):
        d = entries()
        assert d["dare"] == d["avere"] and d["dare"] > 0
        q = entries(q="TEST31-1")["registrazioni"]
        assert {x["origine"] for x in q} <= {"acquisto", "banca"} and any(x["origine"] == "acquisto" for x in q)
        assert entries(dal="2000-01-01", al="2000-12-31")["registrazioni"] == []

    def test_02_mastrino(self):
        r = sess().get(f"{API}/contabilita/mastrino", params={"conto": "05.01"})
        assert r.status_code == 200, r.text
        m = r.json()
        assert m["movimenti"] and m["saldo_finale"] == round(m["saldo_iniziale"] + m["dare"] - m["avere"], 2)
        assert m["movimenti"][-1]["saldo"] == m["saldo_finale"]
        assert any(p["id"] == ST["cli"] for p in m["parties"])
        mp = sess().get(f"{API}/contabilita/mastrino", params={"conto": "05.01", "party_id": ST["cli"]}).json()
        assert all(x["party_nome"] for x in mp["movimenti"])
        m2 = sess().get(f"{API}/contabilita/mastrino", params={"conto": "05.01", "dal": TODAY.isoformat()}).json()
        assert m2["saldo_iniziale"] != 0 and m2["saldo_finale"] == m["saldo_finale"]
        assert sess().get(f"{API}/contabilita/mastrino", params={"conto": "99"}).status_code == 404

    def test_03_bilancio(self):
        b = sess().get(f"{API}/contabilita/bilancio").json()
        assert b["dare"] == b["avere"]
        assert b["risultato"] == round(b["ricavi"] - b["costi"], 2)
        assert round(b["attivita"] - b["passivita"], 2) == b["risultato"]
        lv = {x["livello"] for x in b["righe"]}
        assert lv == {1, 2, 3}


class TestPassiveDelete:
    def test_01_delete_passive_removes_entry(self):
        s = sess()
        # first unreconcile payment
        s.post(f"{API}/banca/movimenti/{ST['TEST PAGAMENTO ENERGIA']}/annulla")
        assert entry_for("banca", ST["TEST PAGAMENTO ENERGIA"]) is None
        r = s.delete(f"{API}/passive/{ST['pas']}")
        assert r.status_code == 200, r.text
        assert entry_for("acquisto", ST["pas"]) is None

    def test_02_rigenera(self):
        s = sess()
        e = entry_for("vendita", ST["inv"])
        mongo(f'db.coa_entries.deleteOne({{id:"{e["id"]}"}})')
        r = s.post(f"{API}/contabilita/rigenera", json={})
        assert r.status_code == 200, r.text
        assert r.json()["vendite"] == 1, r.json()
        assert entry_for("vendita", ST["inv"]) is not None


class TestGating:
    def test_01_module_off(self):
        s = sess()
        r = s.put(f"{API}/companies/{ST['cid']}/moduli", json={**ALL, "contabilita": False})
        assert r.status_code == 200, r.text
        assert s.get(f"{API}/contabilita/conti").status_code == 403
        assert s.get(f"{API}/contabilita/bilancio").status_code == 403
        r = s.put(f"{API}/companies/{ST['cid']}/moduli", json=ALL)
        assert r.status_code == 200
        assert s.get(f"{API}/contabilita/conti").status_code == 200

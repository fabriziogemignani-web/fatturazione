# Iteration 32: Liquidazione IVA contabile (giroconto LI) + Chiusura/Apertura esercizio (lock anno, annulla chiusura),
# bilancio con/senza chiusure, mastrino continuità, blocchi su fatture passive / banca per anno chiuso.
# Run with: pytest test_iteration32_chiusure.py -n 0
import random

import pytest
import requests

from test_iteration7_pa_scartate_registro import API, mongo

RUN = str(random.randint(100000, 999999))
TOK, UID = f"test_session_t32_admin_{RUN}", f"test-user-t32-admin-{RUN}"
OTOK, OUID = f"test_session_t32_oper_{RUN}", f"test-user-t32-oper-{RUN}"
PIVA = "87" + RUN + "321"
ST = {}


def sess(tok=TOK):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def user(uid, tok, role, cids):
    mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.t32.{uid}@example.com", name:"TEST_T32 {role}", picture:"", role:"{role}", status:"approved", company_ids:{cids}, created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')


def clean():
    ids = f'["{UID}","{OUID}"]'
    mongo(f'db.companies.find({{partita_iva:"{PIVA}"}}).forEach(c=>{{["invoices","passive_invoices","parties","articles","counters","payments","passive_payments","bank_tx","bank_accounts","corrispettivi","coa_accounts","coa_causali","coa_iva","coa_entries"].forEach(k=>db[k].deleteMany({{company_id:c.id}})); db.counters.deleteMany({{key:{{$regex:"^coge_"+c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:{ids}}}}}); db.user_sessions.deleteMany({{user_id:{{$in:{ids}}}}});')


def side(e, conto):
    rows = [r for r in e["righe"] if r["conto"] == conto]
    return round(sum(r["dare"] for r in rows), 2), round(sum(r["avere"] for r in rows), 2)


def man(data, righe, desc="TEST_man"):
    return sess().post(f"{API}/contabilita/registrazioni", json={"data": data, "causale": "GE", "descrizione": desc, "righe": righe})


def entries(**p):
    return sess().get(f"{API}/contabilita/registrazioni", params=p).json()["registrazioni"]


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    user(UID, TOK, "admin", "[]")
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    r = s.post(f"{API}/companies", json={"denominazione": f"TEST_T32 Chiusure {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                         "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    user(OUID, OTOK, "operatore", f'["{ST["cid"]}"]')
    yield
    clean()


class TestSetup:
    def test_01_parties_and_entries(self):
        s = sess()
        base = {"codice_fiscale": "", "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"}
        c = s.post(f"{API}/parties", json={**base, "tipo": "cliente", "denominazione": "TEST_T32 Cliente", "partita_iva": "01234567890", "codice_destinatario": "ABC1234"})
        f = s.post(f"{API}/parties", json={**base, "tipo": "fornitore", "denominazione": "TEST_T32 Fornitore", "partita_iva": "02345670481"})
        assert c.status_code == 200 and f.status_code == 200, (c.text, f.text)
        ST["cli"], ST["forn"] = c.json()["id"], f.json()["id"]
        r1 = man("2025-01-15", [{"conto": "05.01.001", "dare": 1220, "party_id": ST["cli"]}, {"conto": "20.01.001", "avere": 1000}, {"conto": "13.03.001", "avere": 220}])
        r2 = man("2025-02-10", [{"conto": "30.06.001", "dare": 500}, {"conto": "05.02.002", "dare": 110}, {"conto": "13.02.001", "avere": 610, "party_id": ST["forn"]}])
        r3 = man("2025-03-05", [{"conto": "06.01.001", "dare": 1000}, {"conto": "10.01.001", "avere": 1000}])
        for r in (r1, r2, r3):
            assert r.status_code == 200, r.text
        ST["m1"], ST["m3"] = r1.json()["id"], r3.json()["id"]


class TestLiquidazioni:
    def test_01_mensile(self):
        d = sess().get(f"{API}/contabilita/liquidazioni", params={"anno": 2025, "periodicita": "mensile"}).json()
        p = {x["periodo"]: x for x in d["periodi"]}
        assert len(p) == 12 and d["chiuso"] is False
        assert (p[1]["iva_vendite"], p[1]["iva_acquisti"], p[1]["saldo"], p[1]["interessi"]) == (220.0, 0.0, 220.0, 0.0)
        assert (p[2]["iva_acquisti"], p[2]["saldo"]) == (110.0, -110.0)
        assert p[2]["al"] == "2025-02-28" and p[12]["al"] == "2025-12-31"

    def test_02_trimestrale_interessi(self):
        d = sess().get(f"{API}/contabilita/liquidazioni", params={"anno": 2025, "periodicita": "trimestrale"}).json()
        q1 = d["periodi"][0]
        assert len(d["periodi"]) == 4
        assert (q1["iva_vendite"], q1["iva_acquisti"], q1["saldo"], q1["interessi"], q1["registrazione"]) == (220.0, 110.0, 110.0, 1.1, None)

    def test_03_registra_q1(self):
        s = sess()
        r = s.post(f"{API}/contabilita/liquidazioni", json={"anno": 2025, "periodicita": "trimestrale", "periodo": 1})
        assert r.status_code == 200, r.text
        e = r.json()
        ST["li"] = e["id"]
        assert e["data"] == "2025-03-31" and e["causale"] == "LI" and e["origine"] == "liquidazione"
        assert side(e, "13.03.001") == (220.0, 0.0) and side(e, "05.02.002") == (0.0, 110.0)
        assert side(e, "05.02.001") == (0.0, 111.1) and side(e, "40.02.003") == (1.1, 0.0)
        q1 = s.get(f"{API}/contabilita/liquidazioni", params={"anno": 2025, "periodicita": "trimestrale"}).json()["periodi"][0]
        assert q1["registrazione"]["id"] == ST["li"] and q1["iva_vendite"] == 220.0  # LI excluded from computation

    def test_04_rejections(self):
        s = sess()
        assert s.post(f"{API}/contabilita/liquidazioni", json={"anno": 2025, "periodicita": "trimestrale", "periodo": 1}).status_code == 400  # duplicate
        r = s.post(f"{API}/contabilita/liquidazioni", json={"anno": 2025, "periodicita": "mensile", "periodo": 2})
        assert r.status_code == 400 and "periodicità" in r.json()["detail"], r.text
        assert s.post(f"{API}/contabilita/liquidazioni", json={"anno": 2025, "periodicita": "trimestrale", "periodo": 3}).status_code == 400  # empty
        assert s.post(f"{API}/contabilita/liquidazioni", json={"anno": 2025, "periodicita": "trimestrale", "periodo": 5}).status_code == 400
        assert s.post(f"{API}/contabilita/liquidazioni", json={"anno": 2025, "periodicita": "x", "periodo": 1}).status_code == 422
        assert sess(OTOK).post(f"{API}/contabilita/liquidazioni", json={"anno": 2025, "periodicita": "trimestrale", "periodo": 2}).status_code == 403
        m = s.get(f"{API}/contabilita/liquidazioni", params={"anno": 2025, "periodicita": "mensile"}).json()["periodi"]
        assert all(x["bloccato"] for x in m[:3]) and not m[3]["bloccato"]

    def test_05_li_not_editable_via_registrazioni(self):
        s = sess()
        assert s.delete(f"{API}/contabilita/registrazioni/{ST['li']}").status_code == 400
        assert s.put(f"{API}/contabilita/registrazioni/{ST['li']}", json={"data": "2025-03-31", "causale": "GE", "descrizione": "x",
                                                                          "righe": [{"conto": "06.02.001", "dare": 1}, {"conto": "06.01.001", "avere": 1}]}).status_code == 400

    def test_06_annulla_and_reregister(self):
        s = sess()
        assert s.delete(f"{API}/contabilita/liquidazioni/{ST['li']}").status_code == 200
        assert s.delete(f"{API}/contabilita/liquidazioni/{ST['li']}").status_code == 404
        assert not any(e["id"] == ST["li"] for e in entries(origine="liquidazione"))
        r = s.post(f"{API}/contabilita/liquidazioni", json={"anno": 2025, "periodicita": "trimestrale", "periodo": 1})
        assert r.status_code == 200
        ST["li"] = r.json()["id"]


class TestChiusura:
    def test_01_current_year_blocked(self):
        s = sess()
        d = s.get(f"{API}/contabilita/chiusura/2026").json()
        assert d["motivo"] and "non è ancora terminato" in d["motivo"]
        assert s.post(f"{API}/contabilita/chiusura/2026").status_code == 400

    def test_02_previous_year_not_closed(self):
        s = sess()
        r = man("2024-12-01", [{"conto": "06.02.001", "dare": 5}, {"conto": "06.01.001", "avere": 5}])
        assert r.status_code == 200
        d = s.get(f"{API}/contabilita/chiusura/2025").json()
        assert d["motivo"] and "2024" in d["motivo"], d["motivo"]
        assert s.post(f"{API}/contabilita/chiusura/2025").status_code == 400
        assert s.delete(f"{API}/contabilita/registrazioni/{r.json()['id']}").status_code == 200

    def test_03_preview(self):
        d = sess().get(f"{API}/contabilita/chiusura/2025").json()
        assert d["chiuso"] is False and d["motivo"] is None and d["risultato"] == 498.9, d
        sc = d["scritture"]
        assert len(sc) == 6 and [x["causale"] for x in sc] == ["CH"] * 4 + ["AP"] * 2
        assert all(x["data"] == "2025-12-31" for x in sc[:4]) and all(x["data"] == "2026-01-01" for x in sc[4:])
        for x in sc:
            assert round(sum(r["dare"] for r in x["righe"]), 2) == round(sum(r["avere"] for r in x["righe"]), 2), x
        assert side(sc[0], "60.01.003") == (0.0, 498.9) and side(sc[0], "20.01.001") == (1000.0, 0.0)
        assert side(sc[1], "10.03.002") == (0.0, 498.9) and "utile" in sc[1]["descrizione"]
        assert side(sc[2], "60.01.002") == (2108.9, 0.0) and side(sc[3], "60.01.002") == (0.0, 2108.9)
        assert side(sc[4], "60.01.001") == (0.0, 2108.9) and side(sc[5], "60.01.001") == (2108.9, 0.0)
        cli = [r for r in sc[4]["righe"] if r["conto"] == "05.01.001"]
        assert cli and cli[0]["party_id"] == ST["cli"] and cli[0]["dare"] == 1220
        forn = [r for r in sc[5]["righe"] if r["conto"] == "13.02.001"]
        assert forn and forn[0]["party_id"] == ST["forn"] and forn[0]["avere"] == 610
        assert 2025 in d["anni"]

    def test_04_operatore_forbidden(self):
        assert sess(OTOK).post(f"{API}/contabilita/chiusura/2025").status_code == 403

    def test_05_close(self):
        s = sess()
        r = s.post(f"{API}/contabilita/chiusura/2025")
        assert r.status_code == 200, r.text
        assert r.json()["registrazioni"] == 6 and r.json()["risultato"] == 498.9
        d = s.get(f"{API}/contabilita/chiusura/2025").json()
        assert d["chiuso"] is True and d["risultato"] == 498.9 and len(d["scritture"]) == 6 and d["motivo"] == "Esercizio già chiuso"
        assert s.post(f"{API}/contabilita/chiusura/2025").status_code == 400
        assert len(entries(origine="chiusura")) == 4 and len(entries(origine="apertura")) == 2
        assert all(e["anno"] == 2026 for e in entries(origine="apertura"))

    def test_06_lock_manual(self):
        s = sess()
        assert man("2025-06-01", [{"conto": "06.02.001", "dare": 5}, {"conto": "06.01.001", "avere": 5}]).status_code == 400
        body = {"data": "2025-03-05", "causale": "GE", "descrizione": "x", "righe": [{"conto": "06.01.001", "dare": 1000}, {"conto": "10.01.001", "avere": 1000}]}
        assert s.put(f"{API}/contabilita/registrazioni/{ST['m3']}", json=body).status_code == 400
        assert s.delete(f"{API}/contabilita/registrazioni/{ST['m3']}").status_code == 400
        r = man("2026-02-01", [{"conto": "06.02.001", "dare": 5}, {"conto": "06.01.001", "avere": 5}])
        assert r.status_code == 200
        assert s.delete(f"{API}/contabilita/registrazioni/{r.json()['id']}").status_code == 200
        # chiusura/apertura entries not deletable via registrazioni
        ap = entries(origine="apertura")[0]
        assert s.delete(f"{API}/contabilita/registrazioni/{ap['id']}").status_code == 400

    def test_07_lock_liquidazione(self):
        s = sess()
        d = s.get(f"{API}/contabilita/liquidazioni", params={"anno": 2025, "periodicita": "trimestrale"}).json()
        assert d["chiuso"] is True
        assert s.delete(f"{API}/contabilita/liquidazioni/{ST['li']}").status_code == 400
        man_ok = s.post(f"{API}/contabilita/liquidazioni", json={"anno": 2025, "periodicita": "mensile", "periodo": 6})
        assert man_ok.status_code == 400

    def test_08_passive_delete_blocked(self):
        cid = ST["cid"]
        pid = f"test-pas-t32-{RUN}"
        mongo(f'db.passive_invoices.insertOne({{id:"{pid}", company_id:"{cid}", numero:"TEST32", fornitore:{{denominazione:"TEST_T32 F"}}, data:"2025-05-01", tipo_documento:"TD01", totale:10, imponibile:10, iva:0}});'
              f'db.coa_entries.insertOne({{id:"test-coa-pas-{RUN}", company_id:"{cid}", anno:2025, numero:999, data:"2025-05-01", causale:"FA", descrizione:"TEST", origine:"acquisto", ref_id:"{pid}", righe:[], totale:0}});')
        r = sess().delete(f"{API}/passive/{pid}")
        mongo(f'db.passive_invoices.deleteOne({{id:"{pid}"}})')  # synthetic doc is incomplete: remove before ledger-based endpoints run
        assert r.status_code == 400 and "chiuso" in r.json()["detail"], r.text

    def test_09_bank_auto_silent_and_unreconcile_blocked(self):
        s = sess()
        a = s.post(f"{API}/banca/conti", json={"nome": "TEST_T32 Conto", "iban": "", "banca": "X"})
        assert a.status_code == 200, a.text
        csv = "\n".join(["Data contabile;Data valuta;Descrizione operazione;Dare;Avere", "10/06/2025;10/06/2025;TEST32 COMMISSIONI;3,50;"]).encode("cp1252")
        assert s.post(f"{API}/banca/conti/{a.json()['id']}/import", files={"file": ("m.csv", csv, "text/csv")}).status_code == 200
        m = next(x for x in s.get(f"{API}/banca/movimenti", params={"stato": "tutti"}).json()["movimenti"] if x["descrizione"] == "TEST32 COMMISSIONI")
        rr = s.post(f"{API}/banca/movimenti/{m['id']}/riconcilia", json={"tipo": "altro", "categoria": "Spese e commissioni bancarie"})
        assert rr.status_code == 200, rr.text  # silent failure on ledger
        assert not any(e["ref_id"] == m["id"] for e in entries(origine="banca"))
        mongo(f'db.coa_entries.insertOne({{id:"test-coa-bank-{RUN}", company_id:"{ST["cid"]}", anno:2025, numero:998, data:"2025-06-10", causale:"MB", descrizione:"TEST", origine:"banca", ref_id:"{m["id"]}", righe:[], totale:0}});')
        r = s.post(f"{API}/banca/movimenti/{m['id']}/annulla")
        assert r.status_code == 400, r.text
        mongo(f'db.coa_entries.deleteMany({{id:{{$in:["test-coa-bank-{RUN}","test-coa-pas-{RUN}"]}}}})')
        assert s.post(f"{API}/banca/movimenti/{m['id']}/annulla").status_code == 200

    def test_10_bilancio(self):
        s = sess()
        b = s.get(f"{API}/contabilita/bilancio", params={"dal": "2025-01-01", "al": "2025-12-31"}).json()
        assert b["risultato"] == 498.9 and b["attivita"] == 2108.9 and b["dare"] == b["avere"]
        bc = s.get(f"{API}/contabilita/bilancio", params={"dal": "2025-01-01", "al": "2025-12-31", "chiusura": True}).json()
        assert bc["risultato"] == 0 and bc["attivita"] == 0, bc
        b6 = s.get(f"{API}/contabilita/bilancio", params={"dal": "2026-01-01", "al": "2026-12-31"}).json()
        assert b6["attivita"] == 2108.9 and b6["passivita"] == 2108.9 and b6["risultato"] == 0

    def test_11_bilancio_all_years_not_doubled(self):
        b = sess().get(f"{API}/contabilita/bilancio").json()
        assert b["attivita"] == 2108.9, f"unfiltered bilancio double counts opening entries: attivita={b['attivita']}"

    def test_12_mastrino_continuity(self):
        s = sess()
        m = s.get(f"{API}/contabilita/mastrino", params={"conto": "06.01.001"}).json()
        assert m["saldo_finale"] == 1000
        m6 = s.get(f"{API}/contabilita/mastrino", params={"conto": "06.01.001", "dal": "2026-01-01"}).json()
        assert m6["saldo_iniziale"] == 0 and m6["saldo_finale"] == 1000
        mc = s.get(f"{API}/contabilita/mastrino", params={"conto": "05.01.001", "party_id": ST["cli"], "dal": "2026-01-01"}).json()
        assert mc["saldo_finale"] == 1220

    def test_13_annulla_blocked_if_next_closed(self):
        cid = ST["cid"]
        mongo(f'db.companies.updateOne({{id:"{cid}"}}, {{$addToSet:{{coge_chiusi:2026}}}})')
        r = sess().delete(f"{API}/contabilita/chiusura/2025")
        mongo(f'db.companies.updateOne({{id:"{cid}"}}, {{$pull:{{coge_chiusi:2026}}}})')
        assert r.status_code == 400 and "2026" in r.json()["detail"]

    def test_14_annulla(self):
        s = sess()
        assert sess(OTOK).delete(f"{API}/contabilita/chiusura/2025").status_code == 403
        r = s.delete(f"{API}/contabilita/chiusura/2025")
        assert r.status_code == 200
        assert not entries(origine="chiusura") and not entries(origine="apertura")
        assert s.get(f"{API}/contabilita/chiusura/2025").json()["chiuso"] is False
        assert s.delete(f"{API}/contabilita/chiusura/2025").status_code == 400
        r = man("2025-06-01", [{"conto": "06.02.001", "dare": 5}, {"conto": "06.01.001", "avere": 5}])
        assert r.status_code == 200
        assert s.delete(f"{API}/contabilita/registrazioni/{r.json()['id']}").status_code == 200

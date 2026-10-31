# Iteration 15: Corrispettivi giornalieri (cassetto fiscale SIMULATO): sync, list/filter, delete+resync, riepilogo,
# integration into Liquidazione IVA (iva_corrispettivi added to iva_debito), roles and company isolation.
# Run with: pytest test_iteration15_corrispettivi.py -n 0
import random
from datetime import date, timedelta
import pytest
import requests
from test_iteration7_pa_scartate_registro import API, mongo

RUN = str(random.randint(100000, 999999))
TOK, UID = f"test_session_t15_admin_{RUN}", f"test-user-t15-admin-{RUN}"
OTOK, OUID = f"test_session_t15_oper_{RUN}", f"test-user-t15-oper-{RUN}"
CTOK, CUID = f"test_session_t15_cont_{RUN}", f"test-user-t15-cont-{RUN}"
PIVA1, PIVA2 = "15" + RUN + "001", "15" + RUN + "002"
TODAY = date.today()


def clean_all():
    mongo('db.companies.find({denominazione:/^TEST_T15/}).forEach(c=>{["invoices","parties","payments","passive_invoices","passive_payments","corrispettivi"].forEach(k=>db[k].deleteMany({company_id:c.id}));'
          'db.counters.deleteMany({key:{$regex:c.id}}); db.companies.deleteOne({id:c.id});});'
          'db.users.deleteMany({user_id:/^test-user-t15-/}); db.user_sessions.deleteMany({session_token:/^test_session_t15_/});')


def comp(name, piva):
    return {"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01", "iban": "IT60X0542811101000000123456",
            "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"}


def user(uid, tok, role, cids):
    mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.{uid}@example.com", name:"TEST_T15 {role}", picture:"", role:"{role}", status:"approved", company_ids:{cids}, created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+7*864e5), created_at:new Date().toISOString()}});')


def sess(tok):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    return s


def expected_days(start, end_excl):
    out, d = [], start
    while d < end_excl:
        if d.weekday() != 6:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


@pytest.fixture(scope="module")
def ctx():
    clean_all()
    user(UID, TOK, "admin", "[]")
    s = sess(TOK)
    cid = s.post(f"{API}/companies", json=comp("TEST_T15 Negozio Srl", PIVA1)).json()["id"]
    cid2 = s.post(f"{API}/companies", json=comp("TEST_T15 Altro Srl", PIVA2)).json()["id"]
    user(OUID, OTOK, "operatore", f'["{cid}"]')
    user(CUID, CTOK, "contabile", f'["{cid}"]')
    yield {"s": s, "o": sess(OTOK), "c": sess(CTOK), "h": {"X-Company-Id": cid}, "h2": {"X-Company-Id": cid2}, "cid": cid}
    clean_all()


class TestSync:
    def test_01_operatore_forbidden(self, ctx):
        r = ctx["o"].post(f"{API}/corrispettivi/sync", headers=ctx["h"])
        assert r.status_code == 403, r.text
        r = requests.post(f"{API}/corrispettivi/sync", headers=ctx["h"])
        assert r.status_code == 401

    def test_02_first_sync(self, ctx):
        r = ctx["s"].post(f"{API}/corrispettivi/sync", headers=ctx["h"])
        assert r.status_code == 200, r.text
        d = r.json()
        exp = expected_days(TODAY - timedelta(days=30), TODAY)
        assert d["ricevuti"] == len(exp), d
        assert d["dal"] == (TODAY - timedelta(days=30)).isoformat() and d["al"] == (TODAY - timedelta(days=1)).isoformat()
        docs = ctx["s"].get(f"{API}/corrispettivi", params={"anno": TODAY.year}, headers=ctx["h"]).json()
        assert [x["data"] for x in docs["rows"]] == [e for e in exp if e.startswith(str(TODAY.year))]

    def test_03_second_sync_no_duplicates(self, ctx):
        r = ctx["s"].post(f"{API}/corrispettivi/sync", headers=ctx["h"])
        assert r.status_code == 200 and r.json()["ricevuti"] == 0, r.text
        n = int(mongo(f'print(db.corrispettivi.countDocuments({{company_id:"{ctx["cid"]}"}}))'))
        assert n == len(expected_days(TODAY - timedelta(days=30), TODAY))

    def test_04_contabile_can_sync(self, ctx):
        r = ctx["c"].post(f"{API}/corrispettivi/sync", headers=ctx["h"])
        assert r.status_code == 200 and r.json()["ricevuti"] == 0

    def test_05_record_structure(self, ctx):
        d = ctx["s"].get(f"{API}/corrispettivi", params={"anno": TODAY.year}, headers=ctx["h"]).json()
        assert "_id" not in str(d)
        assert d["azienda"]["partita_iva"] == PIVA1 and TODAY.year in d["anni"]
        for x in d["rows"]:
            assert date.fromisoformat(x["data"]).weekday() != 6
            assert x["matricola"] == f"99MEX{PIVA1[-6:]}" and x["origine"] == "cassetto_simulato"
            assert 8 <= x["n_documenti"] <= 90 and isinstance(x["id"], str)
            assert x["riepilogo"], x
            aliq = [r["aliquota"] for r in x["riepilogo"]]
            assert set(aliq) <= {22.0, 10.0, 4.0} and 22.0 in aliq
            for r in x["riepilogo"]:
                lordo = r["imponibile"] + r["imposta"]
                assert abs(round(lordo / (1 + r["aliquota"] / 100), 2) - r["imponibile"]) <= 0.01, r
            assert abs(sum(r["imponibile"] + r["imposta"] for r in x["riepilogo"]) - x["totale"]) < 0.011
        # totals
        tot = {t["codice"]: t for t in d["totali"]}
        assert [t["codice"] for t in d["totali"]][0] == "22%"
        for code, t in tot.items():
            al = t["aliquota"]
            assert t["imposta"] == round(sum(r["imposta"] for x in d["rows"] for r in x["riepilogo"] if r["aliquota"] == al), 2)
            assert t["documenti"] == sum(1 for x in d["rows"] for r in x["riepilogo"] if r["aliquota"] == al)
        assert d["imposta"] == round(sum(t["imposta"] for t in d["totali"]), 2)
        assert d["totale"] == round(sum(x["totale"] for x in d["rows"]), 2)
        assert abs(d["imponibile"] + d["imposta"] - d["totale"]) < 0.05

    def test_06_company_isolation(self, ctx):
        d = ctx["s"].get(f"{API}/corrispettivi", headers=ctx["h2"]).json()
        assert d["rows"] == [] and d["imposta"] == 0
        r = ctx["o"].get(f"{API}/corrispettivi", headers=ctx["h2"])
        assert r.status_code == 404
        # sync on company 2 generates different (seeded by company) values
        r = ctx["s"].post(f"{API}/corrispettivi/sync", headers=ctx["h2"])
        assert r.status_code == 200 and r.json()["ricevuti"] > 0
        a = ctx["s"].get(f"{API}/corrispettivi", headers=ctx["h"]).json()
        b = ctx["s"].get(f"{API}/corrispettivi", headers=ctx["h2"]).json()
        assert a["totale"] != b["totale"] and b["rows"][0]["matricola"].endswith(PIVA2[-6:])
        assert not {x["id"] for x in a["rows"]} & {x["id"] for x in b["rows"]}

    def test_07_operatore_can_read(self, ctx):
        r = ctx["o"].get(f"{API}/corrispettivi", headers=ctx["h"])
        assert r.status_code == 200 and len(r.json()["rows"]) > 0
        assert ctx["o"].get(f"{API}/corrispettivi/riepilogo", headers=ctx["h"]).status_code == 200


class TestFilterDelete:
    def test_08_date_filter(self, ctx):
        s, h = ctx["s"], ctx["h"]
        full = s.get(f"{API}/corrispettivi", headers=h).json()["rows"]
        dal, al = full[2]["data"], full[6]["data"]
        d = s.get(f"{API}/corrispettivi", params={"anno": TODAY.year, "dal": dal, "al": al}, headers=h).json()
        assert [x["data"] for x in d["rows"]] == [x["data"] for x in full[2:7]]
        assert d["totale"] == round(sum(x["totale"] for x in full[2:7]), 2)
        r = s.get(f"{API}/corrispettivi", params={"anno": TODAY.year, "dal": "bad", "al": "2026-13"}, headers=h)
        assert r.status_code == 200 and len(r.json()["rows"]) == len(full)
        d = s.get(f"{API}/corrispettivi", params={"anno": TODAY.year - 1}, headers=h).json()
        assert d["anno"] == TODAY.year - 1

    def test_09_delete_roles_and_404(self, ctx):
        s, h = ctx["s"], ctx["h"]
        rows = s.get(f"{API}/corrispettivi", headers=h).json()["rows"]
        assert ctx["o"].delete(f"{API}/corrispettivi/{rows[0]['id']}", headers=h).status_code == 403
        assert s.delete(f"{API}/corrispettivi/{rows[0]['id']}", headers=ctx["h2"]).status_code == 404  # wrong company
        assert s.delete(f"{API}/corrispettivi/nonexistent", headers=h).status_code == 404

    def test_10_delete_middle_not_readded(self, ctx):
        s, h = ctx["s"], ctx["h"]
        rows = s.get(f"{API}/corrispettivi", headers=h).json()["rows"]
        mid = rows[3]
        r = ctx["c"].delete(f"{API}/corrispettivi/{mid['id']}", headers=h)
        assert r.status_code == 200 and r.json()["ok"] is True
        after = s.get(f"{API}/corrispettivi", headers=h).json()["rows"]
        assert mid["data"] not in [x["data"] for x in after] and len(after) == len(rows) - 1
        assert s.post(f"{API}/corrispettivi/sync", headers=h).json()["ricevuti"] == 0
        assert mid["data"] not in [x["data"] for x in s.get(f"{API}/corrispettivi", headers=h).json()["rows"]]

    def test_11_delete_last_readded(self, ctx):
        s, h = ctx["s"], ctx["h"]
        rows = s.get(f"{API}/corrispettivi", headers=h).json()["rows"]
        last = rows[-1]
        assert s.delete(f"{API}/corrispettivi/{last['id']}", headers=h).status_code == 200
        r = s.post(f"{API}/corrispettivi/sync", headers=h).json()
        assert r["ricevuti"] == 1 and r["dal"] == (date.fromisoformat(rows[-2]["data"]) + timedelta(days=1)).isoformat(), r
        new = s.get(f"{API}/corrispettivi", headers=h).json()["rows"]
        assert new[-1]["data"] == last["data"] and new[-1]["totale"] == last["totale"]  # deterministic demo
        assert new[-1]["id"] != last["id"]


class TestRiepilogo:
    def test_12_riepilogo(self, ctx):
        s, h = ctx["s"], ctx["h"]
        r = s.get(f"{API}/corrispettivi/riepilogo", headers=h)
        assert r.status_code == 200, r.text
        d = r.json()
        rows = s.get(f"{API}/corrispettivi", params={"anno": TODAY.year}, headers=h).json()["rows"]
        assert d["anno"] == TODAY.year
        assert d["ultimo"]["data"] == rows[-1]["data"] and d["ultimo"]["totale"] == rows[-1]["totale"]
        assert set(d["ultimo"]) == {"data", "totale", "n_documenti"}
        mese = TODAY.isoformat()[:7]
        assert d["mese"] == round(sum(x["totale"] for x in rows if x["data"].startswith(mese)), 2)
        assert d["totale_anno"] == round(sum(x["totale"] for x in rows), 2)
        assert len(d["mesi"]) == 12 and [m["mese"] for m in d["mesi"]] == list(range(1, 13))
        assert round(sum(m["totale"] for m in d["mesi"]), 2) == d["totale_anno"]
        since = (TODAY - timedelta(days=30)).isoformat()
        assert [g["data"] for g in d["giorni"]] == [x["data"] for x in rows if x["data"] >= since]

    def test_13_riepilogo_empty(self, ctx):
        mongo(f'db.corrispettivi.deleteMany({{company_id:"{ctx["h2"]["X-Company-Id"]}"}})')
        d = ctx["s"].get(f"{API}/corrispettivi/riepilogo", headers=ctx["h2"]).json()
        assert d["ultimo"] is None and d["mese"] == 0 and d["totale_anno"] == 0 and d["giorni"] == [] and len(d["mesi"]) == 12


class TestLiquidazione:
    def test_14_mensile(self, ctx):
        s, h = ctx["s"], ctx["h"]
        rows = s.get(f"{API}/corrispettivi", params={"anno": TODAY.year}, headers=h).json()["rows"]
        d = s.get(f"{API}/liquidazione-iva", params={"anno": TODAY.year, "periodicita": "mensile"}, headers=h).json()
        for p in d["periodi"]:
            mine = [x for x in rows if int(x["data"][5:7]) == p["periodo"]]
            exp = round(sum(r["imposta"] for x in mine for r in x["riepilogo"]), 2)
            assert p["iva_corrispettivi"] == exp, (p["periodo"], p["iva_corrispettivi"], exp)
            assert p["documenti_corrispettivi"] == len(mine)
            assert p["iva_debito"] == exp  # no invoices in test company
        assert d["totale_versare"] > 0

    def test_15_trimestrale(self, ctx):
        s, h = ctx["s"], ctx["h"]
        rows = s.get(f"{API}/corrispettivi", params={"anno": TODAY.year}, headers=h).json()["rows"]
        d = s.get(f"{API}/liquidazione-iva", params={"anno": TODAY.year, "periodicita": "trimestrale"}, headers=h).json()
        assert len(d["periodi"]) == 4
        for p in d["periodi"]:
            mine = [x for x in rows if (int(x["data"][5:7]) - 1) // 3 + 1 == p["periodo"]]
            exp = round(sum(r["imposta"] for x in mine for r in x["riepilogo"]), 2)
            assert p["iva_corrispettivi"] == exp and p["documenti_corrispettivi"] == len(mine)
            assert p["iva_debito"] == exp

    def test_16_corr_plus_invoice(self, ctx):
        """insert a fake sent invoice in the current month directly in DB: debito = vendite + corrispettivi"""
        s, h, cid = ctx["s"], ctx["h"], ctx["cid"]
        m = TODAY.month
        mongo(f'db.invoices.insertOne({{id:"t15-inv-{RUN}", company_id:"{cid}", status:"consegnata", anno:{TODAY.year}, data:"{TODAY.isoformat()}", tipo_documento:"TD01",'
              f' numero:1, numero_display:"1", cliente:{{denominazione:"TEST_T15 C"}}, riepilogo:[{{aliquota:22, natura:null, imponibile:100, imposta:22}}], totale:122, split_payment:false}})')
        d = s.get(f"{API}/liquidazione-iva", params={"anno": TODAY.year}, headers=h).json()
        p = d["periodi"][m - 1]
        assert p["iva_debito"] == round(22 + p["iva_corrispettivi"], 2), p

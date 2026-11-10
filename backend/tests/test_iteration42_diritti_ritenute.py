# Iteration 42: per-user editing rights (diritti) - /auth/me, /users list, PUT /users/{id}/diritti, enforcement on
# PUT /company (dati vs banche), contabilita tables, articles/magazzino, comunicazioni testi; plus ritenute d'acconto
# (supplier soggetto_ritenuta -> passive invoice ritenuta, proportional on payments, /ritenute/mese, da-versare, versato -> coge entry).
# Run with: pytest tests/test_iteration42_diritti_ritenute.py -n 0
import os
import subprocess
from datetime import date

import pytest
import requests

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
FIX = open(os.path.join(os.path.dirname(__file__), "fixtures", "sample_fattura.xml")).read()
PA = "88123456421"
U = {k: (f"test-user-t42-{k}", f"test_session_t42_{k}") for k in ("admin", "op", "co", "opban", "opdati", "optab", "conotesti")}
ROLE = {"admin": "admin", "op": "operatore", "co": "contabile", "opban": "operatore", "opdati": "operatore", "optab": "operatore", "conotesti": "contabile"}
S = {}
today = date.today()
PM = date(today.year - (today.month == 1), 12 if today.month == 1 else today.month - 1, 1)
YM = PM.isoformat()[:7]


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


def sess(k, cid=True):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {U[k][1]}"
    if cid and S.get("cid"):
        s.headers["X-Company-Id"] = S["cid"]
    return s


def clean():
    ids = "[" + ",".join(f'"{u}"' for u, _ in U.values()) + "]"
    mongo(f'db.companies.find({{partita_iva:"{PA}"}}).forEach(c=>{{["invoices","passive_invoices","parties","payments","passive_payments","coa_entries","coa_accounts","coa_causali","coa_iva","articles","stock_moves","f24_versamenti","sdi_events","audit","com_log"].forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:{ids}}}}}); db.user_sessions.deleteMany({{user_id:{{$in:{ids}}}}});')


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    for k, (uid, tok) in U.items():
        mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.{uid}@example.com", name:"TEST_{k}", picture:"", role:"{ROLE[k]}", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
              f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess("admin").post(f"{API}/companies", json={"denominazione": "TEST_T42 Srl", "partita_iva": PA, "codice_fiscale": PA, "regime_fiscale": "RF01",
                                                     "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT",
                                                     "banche": [{"nome": "Banca A", "iban": "IT60X0542811101000000123456", "predefinita": True}]})
    assert r.status_code == 200, r.text
    S["cid"] = r.json()["id"]
    mongo(f'db.users.updateMany({{user_id:{{$in:["{U["op"][0]}","{U["co"][0]}","{U["opban"][0]}","{U["opdati"][0]}","{U["optab"][0]}","{U["conotesti"][0]}"]}}}}, {{$set:{{company_ids:["{S["cid"]}"]}}}});')
    yield
    clean()


def put_dir(k, **on):
    body = {d: on.get(d, False) for d in ("dati_azienda", "banche", "tabelle_contabili", "articoli_magazzino", "testi_comunicazioni")}
    r = sess("admin", False).put(f"{API}/users/{U[k][0]}/diritti", json=body)
    assert r.status_code == 200, r.text
    assert r.json() == body


def me(k):
    r = sess(k, False).get(f"{API}/auth/me")
    assert r.status_code == 200
    return r.json()["diritti"]


def company_body(**kw):
    c = sess("admin").get(f"{API}/company").json()
    keep = ("denominazione", "partita_iva", "codice_fiscale", "regime_fiscale", "indirizzo", "cap", "comune", "provincia", "nazione", "iban", "banche",
            "email", "pec", "telefono", "periodicita_iva")
    return {**{k: c.get(k) for k in keep if c.get(k) is not None}, **kw}


# --- Defaults and admin endpoint
class TestDirittiDefaults:
    def test_defaults(self):
        assert me("admin") == {k: True for k in me("admin")}
        assert me("op") == {"dati_azienda": False, "banche": False, "tabelle_contabili": False, "articoli_magazzino": True, "testi_comunicazioni": False}
        assert me("co") == {"dati_azienda": False, "banche": False, "tabelle_contabili": True, "articoli_magazzino": True, "testi_comunicazioni": True}

    def test_list_users_has_diritti(self):
        r = sess("admin", False).get(f"{API}/users")
        u = next(x for x in r.json() if x["user_id"] == U["op"][0])
        assert u["diritti"]["articoli_magazzino"] is True and u["diritti"]["banche"] is False

    def test_put_diritti_non_admin_forbidden(self):
        r = sess("co", False).put(f"{API}/users/{U['op'][0]}/diritti", json={"banche": True})
        assert r.status_code == 403

    def test_put_diritti_real_admin(self):
        s = requests.Session()
        assert s.post(f"{API}/auth/login", json={"email": "fabrizio.gemignani@gmail.com", "password": "Fe-Admin-2aOBey8irzL8"}).status_code == 200
        r = s.put(f"{API}/users/{U['opban'][0]}/diritti", json={"banche": True})
        assert r.status_code == 200
        assert me("opban")["banche"] is True and me("opban")["articoli_magazzino"] is False


# --- PUT /company enforcement
class TestCompanyRights:
    def test_no_right_403(self):
        r = sess("op").put(f"{API}/company", json=company_body(denominazione="TEST_X"))
        assert r.status_code == 403 and "diritto" in r.text

    def test_only_banche(self):
        put_dir("opban", banche=True)
        body = company_body(denominazione="TEST_HACK", banche=[{"nome": "Banca B", "iban": "IT09X0306909606100000063333", "predefinita": True}])
        r = sess("opban").put(f"{API}/company", json=body)
        assert r.status_code == 200, r.text
        c = sess("admin").get(f"{API}/company").json()
        assert c["denominazione"] == "TEST_T42 Srl"
        assert [b["nome"] for b in c["banche"]] == ["Banca B"]

    def test_only_dati(self):
        put_dir("opdati", dati_azienda=True)
        body = company_body(denominazione="TEST_T42 Dati Srl", banche=[])
        r = sess("opdati").put(f"{API}/company", json=body)
        assert r.status_code == 200, r.text
        c = sess("admin").get(f"{API}/company").json()
        assert c["denominazione"] == "TEST_T42 Dati Srl"
        assert [b["nome"] for b in c["banche"]] == ["Banca B"]

    def test_admin_full(self):
        r = sess("admin").put(f"{API}/company", json=company_body(denominazione="TEST_T42 Srl", banche=[{"nome": "Banca C", "iban": "IT60X0542811101000000123456", "predefinita": True}]))
        assert r.status_code == 200
        c = r.json()
        assert c["denominazione"] == "TEST_T42 Srl" and c["banche"][0]["nome"] == "Banca C"


# --- Contabilita tables
class TestTabelle:
    def test_operatore_without_right(self):
        r = sess("op").post(f"{API}/contabilita/causali", json={"codice": "T42A", "descrizione": "TEST"})
        assert r.status_code == 403 and "Non hai il diritto" in r.text
        assert sess("op").get(f"{API}/contabilita/conti").status_code == 200

    def test_contabile_revoked(self):
        put_dir("conotesti", articoli_magazzino=True)
        r = sess("conotesti").post(f"{API}/contabilita/causali", json={"codice": "T42B", "descrizione": "TEST"})
        assert r.status_code == 403
        r = sess("conotesti").put(f"{API}/contabilita/parametri", json={"conti": {}})
        assert r.status_code == 403

    def test_operatore_with_right(self):
        put_dir("optab", tabelle_contabili=True, testi_comunicazioni=True)
        s = sess("optab")
        r = s.post(f"{API}/contabilita/causali", json={"codice": "T42C", "descrizione": "TEST_causale"})
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        assert s.put(f"{API}/contabilita/causali/{cid}", json={"codice": "T42C", "descrizione": "TEST_mod"}).status_code == 200
        assert s.delete(f"{API}/contabilita/causali/{cid}").status_code == 200
        r = s.post(f"{API}/contabilita/codici-iva", json={"codice": "T42", "descrizione": "TEST", "aliquota": 22})
        assert r.status_code == 200, r.text
        r = s.post(f"{API}/contabilita/registrazioni", json={"data": today.isoformat(), "causale": "GE", "descrizione": "x", "righe": []})
        assert r.status_code == 403 and "Admin o Contabile" in r.text


# --- Articles / magazzino
class TestArticoli:
    def test_without_right(self):
        s = sess("opban")
        assert s.get(f"{API}/articles").status_code == 200
        r = s.post(f"{API}/articles", json={"codice": "T42", "descrizione": "TEST"})
        assert r.status_code == 403 and "articoli" in r.text
        r = s.post(f"{API}/magazzino/movimenti", json={"article_id": "x", "tipo": "carico", "data": today.isoformat(), "quantita": 1, "causale": "x"})
        assert r.status_code == 403

    def test_default_operatore(self):
        r = sess("op").post(f"{API}/articles", json={"codice": "T42OP", "descrizione": "TEST_art", "gestione_magazzino": True})
        assert r.status_code == 200, r.text


# --- Comunicazioni testi
class TestComunicazioni:
    def cfg(self, k="admin"):
        return sess(k).get(f"{API}/comunicazioni/config").json()["config"]

    def test_neither_403(self):
        c = self.cfg()
        assert sess("op").put(f"{API}/comunicazioni/config", json=c).status_code == 403

    def test_operatore_testi_only(self):
        c = self.cfg()
        c["testi"]["cortesia"]["oggetto"] = "TEST_T42 oggetto"
        c["ora"] = 15 if c["ora"] != 15 else 16
        r = sess("optab").put(f"{API}/comunicazioni/config", json=c)
        assert r.status_code == 200, r.text
        n = self.cfg()
        assert n["testi"]["cortesia"]["oggetto"] == "TEST_T42 oggetto"
        assert n["ora"] != c["ora"]

    def test_contabile_without_testi(self):
        c = self.cfg()
        c["testi"]["cortesia"]["oggetto"] = "TEST_T42 HACK"
        c["ora"] = 9
        r = sess("conotesti").put(f"{API}/comunicazioni/config", json=c)
        assert r.status_code == 200, r.text
        n = self.cfg()
        assert n["testi"]["cortesia"]["oggetto"] == "TEST_T42 oggetto" and n["ora"] == 9


# --- Ritenute d'acconto
class TestRitenute:
    def test_flow(self):
        s = sess("admin")
        f = s.post(f"{API}/parties", json={"tipo": "fornitore", "denominazione": "TEST_T42 Studio Legale", "partita_iva": "02345670481", "codice_fiscale": "",
                                           "indirizzo": "Via Y 1", "cap": "50100", "comune": "Firenze", "provincia": "FI", "nazione": "IT",
                                           "soggetto_ritenuta": True, "ritenuta_tipo": "RT01", "ritenuta_aliquota": 20, "ritenuta_base": 100, "ritenuta_causale": "A"})
        assert f.status_code == 200, f.text
        assert f.json()["soggetto_ritenuta"] is True
        d1 = PM.replace(day=5).isoformat()
        xml = FIX.replace("<IdCodice>01234567890</IdCodice>", f"<IdCodice>{PA}</IdCodice>").replace("<Numero>5674/2026</Numero>", "<Numero>TEST42-1</Numero>") \
            .replace("<Data>2026-10-30</Data>", f"<Data>{d1}</Data>")
        up = s.post(f"{API}/passive/upload", files=[("files", ("p.xml", xml, "text/xml"))])
        assert up.status_code == 200 and up.json()[0]["ok"], up.text
        pid = up.json()[0]["documenti"][0]["id"]
        d = s.get(f"{API}/passive/{pid}").json()
        assert d["ritenuta_importo"] == 94.25 and d["netto"] == round(574.93 - 94.25, 2)
        S["pid"] = pid
        p = s.post(f"{API}/passive/{pid}/pagamenti", json={"data": PM.replace(day=20).isoformat(), "importo": 240.34})
        assert p.status_code == 200, p.text
        m = s.get(f"{API}/ritenute/mese", params={"mese": YM}).json()
        assert m["totale"] == round(94.25 * 240.34 / 480.68, 2), m
        assert m["provvisorio"] is False and m["codice"] == "1040"
        assert m["fornitori"][0]["fornitore"] == "TEST_T42 Studio Legale" or len(m["fornitori"]) == 1
        p2 = s.post(f"{API}/passive/{pid}/pagamenti", json={"data": PM.replace(day=25).isoformat(), "importo": 240.34})
        assert p2.status_code == 200, p2.text
        m = s.get(f"{API}/ritenute/mese", params={"mese": YM}).json()
        S["tot_full"] = m["totale"]
        dv = s.get(f"{API}/ritenute/da-versare").json()
        assert any(x["mese"] == YM for x in dv["mesi"])
        assert s.get(f"{API}/ritenute/{YM}/f24").status_code == 200
        assert sess("op").post(f"{API}/ritenute/{YM}/versato", json={"data": today.isoformat()}).status_code == 403
        v = s.post(f"{API}/ritenute/{YM}/versato", json={"data": today.isoformat()})
        assert v.status_code == 200, v.text
        assert v.json()["versato"]["importo"] == m["totale"]
        e = mongo(f'printjson(db.coa_entries.findOne({{company_id:"{S["cid"]}", origine:"ritenute", ref_id:"RIT-{YM}"}}, {{_id:0, righe:1}}))')
        assert "dare" in e and "avere" in e, e
        dv = s.get(f"{API}/ritenute/da-versare").json()
        assert not any(x["mese"] == YM for x in dv["mesi"])
        assert s.delete(f"{API}/scadenze-fiscali/versato/RIT-{YM}").status_code == 200
        assert mongo(f'print(db.coa_entries.countDocuments({{company_id:"{S["cid"]}", origine:"ritenute"}}))') == "0"

    def test_full_payment_equals_ritenuta(self):
        # two 50% payments must sum to the full ritenuta (94.25), not lose a cent to per-payment rounding
        assert S.get("tot_full") == 94.25, S.get("tot_full")

    def test_bad_month(self):
        assert sess("admin").get(f"{API}/ritenute/mese", params={"mese": "2026-13"}).status_code == 422

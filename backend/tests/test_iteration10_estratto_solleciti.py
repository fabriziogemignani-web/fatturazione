# Iteration 10: estratto conto cliente PDF + solleciti di pagamento (preview, real send to delivered@resend.dev ONLY,
# role checks, 400 no email / no overdue, 429 rate limit, company isolation).
# Run with: pytest test_iteration10_estratto_solleciti.py -n 0   (needs pypdf: pip install pypdf)
import io
import random
from datetime import date, timedelta
import pytest
import requests
from pypdf import PdfReader
from test_iteration7_pa_scartate_registro import API, mongo, party, inv

SAFE_TO = "delivered@resend.dev"
RUN = str(random.randint(100000, 999999))
TOK, UID = f"test_session_t10_admin_{RUN}", f"test-user-t10-admin-{RUN}"
CTOK, CUID = f"test_session_t10_cont_{RUN}", f"test-user-t10-cont-{RUN}"
OTOK, OUID = f"test_session_t10_oper_{RUN}", f"test-user-t10-oper-{RUN}"
PIVA, PIVA2 = "88" + RUN + "001", "88" + RUN + "002"
IBAN = "IT60X0542811101000000123456"
TODAY = date.today()
D0 = (TODAY - timedelta(days=60)).isoformat()
R1 = (TODAY - timedelta(days=45)).isoformat()
R2 = (TODAY - timedelta(days=15)).isoformat()
R3 = (TODAY + timedelta(days=15)).isoformat()


def clean_all():
    mongo('db.companies.find({denominazione:/^TEST_T10/}).forEach(c=>{["invoices","parties","payments","solleciti"].forEach(k=>db[k].deleteMany({company_id:c.id}));'
          'db.counters.deleteMany({key:{$regex:c.id}}); db.companies.deleteOne({id:c.id});});'
          'db.users.deleteMany({user_id:/^test-user-t10-/}); db.user_sessions.deleteMany({session_token:/^test_session_t10_/});')


def comp(name, piva):
    return {"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01", "iban": IBAN,
            "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"}


def user(uid, tok, role, cids):
    mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.{uid}@example.com", name:"TEST_T10 {role}", picture:"", role:"{role}", status:"approved", company_ids:{cids}, created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+7*864e5), created_at:new Date().toISOString()}});')


def sess(tok):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    return s


def sent(s, h, body):
    r = s.post(f"{API}/invoices", json=body, headers=h)
    assert r.status_code == 200, r.text
    iid = r.json()["id"]
    assert s.post(f"{API}/invoices/{iid}/send", headers=h).status_code == 200
    r = s.post(f"{API}/invoices/{iid}/refresh", headers=h)
    assert r.json()["status"] == "consegnata", r.text
    return r.json()


def seed(s, tag="TEST_T10"):
    """Company + clients: A (email safe, 3 rate, partial payment, linked NC, free NC partly compensated), B (no email, overdue),
    C (pec only = safe, nothing overdue). Returns dict."""
    r = s.post(f"{API}/companies", json=comp(f"{tag} Srl", PIVA))
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    cid2 = s.post(f"{API}/companies", json=comp(f"{tag} Altra Srl", PIVA2)).json()["id"]
    h = {"X-Company-Id": cid}
    A = s.post(f"{API}/parties", json=party(f"{tag} Cliente A", piva="0" + RUN + "0011", email=SAFE_TO), headers=h).json()["id"]
    B = s.post(f"{API}/parties", json=party(f"{tag} Cliente B", piva="0" + RUN + "0012"), headers=h).json()["id"]
    C = s.post(f"{API}/parties", json=party(f"{tag} Cliente C", piva="0" + RUN + "0013", pec=SAFE_TO), headers=h).json()["id"]
    X = s.post(f"{API}/parties", json=party(f"{tag} Cliente X", piva="0" + RUN + "0014", email=SAFE_TO), headers={"X-Company-Id": cid2}).json()["id"]
    i1 = sent(s, h, inv(A, data=D0, rate=[{"scadenza": R1, "importo": 400}, {"scadenza": R2, "importo": 400}, {"scadenza": R3, "importo": 420}]))
    p = s.post(f"{API}/invoices/{i1['id']}/pagamenti", json={"data": TODAY.isoformat(), "importo": 300, "metodo": "bonifico", "note": "TEST acconto"}, headers=h)
    assert p.status_code == 200, p.text
    nc1 = sent(s, h, inv(A, tipo_documento="TD04", price=50, fattura_collegata_id=i1["id"]))  # 61 auto
    nc2 = sent(s, h, inv(A, tipo_documento="TD04", price=100))  # 122 free credit
    cp = s.post(f"{API}/invoices/{i1['id']}/pagamenti", json={"data": TODAY.isoformat(), "importo": 22, "metodo": "compensazione", "nc_id": nc2["id"]}, headers=h)
    assert cp.status_code == 200, cp.text
    iB = sent(s, h, inv(B, data=D0, scadenza=R2))
    iC = sent(s, h, inv(C, scadenza=R3))
    return {"cid": cid, "cid2": cid2, "h": h, "A": A, "B": B, "C": C, "X": X, "i1": i1, "nc1": nc1, "nc2": nc2, "iB": iB, "iC": iC}


@pytest.fixture(scope="module")
def ctx():
    clean_all()
    user(UID, TOK, "admin", "[]")
    s = sess(TOK)
    d = seed(s)
    user(CUID, CTOK, "contabile", f'["{d["cid"]}"]')
    user(OUID, OTOK, "operatore", f'["{d["cid"]}"]')
    yield {"s": s, "c": sess(CTOK), "o": sess(OTOK), **d}
    clean_all()


def pdf_text(content):
    return "\n".join(pg.extract_text() for pg in PdfReader(io.BytesIO(content)).pages)


class TestEstratto:
    def test_01_pdf_admin(self, ctx):
        r = ctx["s"].get(f"{API}/clienti/{ctx['A']}/estratto-conto.pdf", headers=ctx["h"])
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/pdf")
        assert r.content[:4] == b"%PDF"
        assert "Estratto_conto_TEST_T10_Cliente_A" in r.headers.get("content-disposition", "")
        t = pdf_text(r.content)
        print(t)
        for s in ("Movimenti", "Partite aperte", f"Fattura {ctx['i1']['numero_display']}", f"Nota di credito {ctx['nc1']['numero_display']}",
                  f"storno fatt. {ctx['i1']['numero_display']}", f"Nota di credito {ctx['nc2']['numero_display']}", "Incasso Bonifico", "TEST acconto",
                  f"Compensazione NC {ctx['nc2']['numero_display']}", "Scaduta da 45 gg", "Scaduta da 15 gg", "A scadere", "Totale da incassare",
                  "di cui scaduto", "Crediti da note di credito non compensati", "Saldo a vostro debito", IBAN, "TEST_T10 Cliente A"):
            assert s in t, f"missing {s!r}"

    def test_02_pdf_amounts(self, ctx):
        # 1220 - 300 paid - 61 auto NC - 22 comp = 837 residuo. rate: R1 400 paid fully(383 cov), wait -> cov=383: R1 res 17, R2 400, R3 420
        t = pdf_text(ctx["s"].get(f"{API}/clienti/{ctx['A']}/estratto-conto.pdf", headers=ctx["h"]).content)
        assert "837,00 €" in t  # totale da incassare
        assert "417,00 €" in t  # scaduto 17 + 400
        assert "- 100,00 €" in t  # credit 122-22
        assert "737,00 €" in t  # saldo 1220-61-122-300

    def test_03_pdf_operatore_and_contabile(self, ctx):
        for k in ("o", "c"):
            r = ctx[k].get(f"{API}/clienti/{ctx['A']}/estratto-conto.pdf", headers=ctx["h"])
            assert r.status_code == 200 and r.content[:4] == b"%PDF", (k, r.status_code)

    def test_04_pdf_other_company_404(self, ctx):
        r = ctx["s"].get(f"{API}/clienti/{ctx['X']}/estratto-conto.pdf", headers=ctx["h"])
        assert r.status_code == 404
        r = ctx["s"].get(f"{API}/clienti/does-not-exist/estratto-conto.pdf", headers=ctx["h"])
        assert r.status_code == 404
        r = ctx["o"].get(f"{API}/clienti/{ctx['X']}/estratto-conto.pdf", headers={"X-Company-Id": ctx["cid2"]})
        assert r.status_code == 404

    def test_05_pdf_no_movements(self, ctx):
        pid = ctx["s"].post(f"{API}/parties", json=party("TEST_T10 Vuoto", piva="0" + RUN + "0019"), headers=ctx["h"]).json()["id"]
        r = ctx["s"].get(f"{API}/clienti/{pid}/estratto-conto.pdf", headers=ctx["h"])
        assert r.status_code == 200 and "Nessun movimento" in pdf_text(r.content)


class TestSollecitoPreview:
    def test_06_preview_A(self, ctx):
        r = ctx["s"].get(f"{API}/clienti/{ctx['A']}/sollecito", headers=ctx["h"])
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["to"] == SAFE_TO
        assert d["subject"] == "Sollecito di pagamento - TEST_T10 Srl"
        assert d["scaduto"] == 417.0 and d["rate"] == 2
        assert d["storico"] == []
        for s in ("Totale scaduto", IBAN, "17,00", "400,00", "417,00", "45 gg", "15 gg", ctx["i1"]["numero_display"]):
            assert s in d["html"], s

    def test_07_preview_pec_fallback_and_none(self, ctx):
        d = ctx["s"].get(f"{API}/clienti/{ctx['C']}/sollecito", headers=ctx["h"]).json()
        assert d["to"] == SAFE_TO and d["rate"] == 0 and d["scaduto"] == 0
        d = ctx["o"].get(f"{API}/clienti/{ctx['B']}/sollecito", headers=ctx["h"]).json()
        assert d["to"] == "" and d["rate"] == 1 and d["scaduto"] == 1220.0

    def test_08_preview_other_company_404(self, ctx):
        assert ctx["s"].get(f"{API}/clienti/{ctx['X']}/sollecito", headers=ctx["h"]).status_code == 404


class TestSollecitoSend:
    def test_09_operatore_403(self, ctx):
        r = ctx["o"].post(f"{API}/clienti/{ctx['A']}/sollecito", headers=ctx["h"])
        assert r.status_code == 403, r.text

    def test_10_no_email_400(self, ctx):
        r = ctx["s"].post(f"{API}/clienti/{ctx['B']}/sollecito", headers=ctx["h"])
        assert r.status_code == 400 and "email" in r.json()["detail"].lower(), r.text

    def test_11_no_overdue_400(self, ctx):
        r = ctx["c"].post(f"{API}/clienti/{ctx['C']}/sollecito", headers=ctx["h"])
        assert r.status_code == 400 and "scadute" in r.json()["detail"], r.text

    def test_12_other_company_404(self, ctx):
        assert ctx["s"].post(f"{API}/clienti/{ctx['X']}/sollecito", headers=ctx["h"]).status_code == 404

    def test_13_real_send(self, ctx):
        assert mongo(f'print(db.parties.findOne({{id:"{ctx["A"]}"}}).email)') == SAFE_TO  # safety
        r = ctx["s"].post(f"{API}/clienti/{ctx['A']}/sollecito", headers=ctx["h"])
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["to"] == SAFE_TO and d["importo_scaduto"] == 417.0 and d["rate"] == 2 and "_id" not in d
        print("email_id", d.get("email_id"))
        cnt = mongo(f'print(db.solleciti.countDocuments({{party_id:"{ctx["A"]}", company_id:"{ctx["cid"]}"}}))')
        assert cnt == "1"
        st = ctx["s"].get(f"{API}/clienti/{ctx['A']}/sollecito", headers=ctx["h"]).json()["storico"]
        assert len(st) == 1 and st[0]["importo_scaduto"] == 417.0 and "_id" not in st[0]

    def test_14_rate_limit_429(self, ctx):
        # insert 2 fake records (no real email) -> 3 in 24h -> next send must be 429
        mongo(f'[1,2].forEach(i=>db.solleciti.insertOne({{id:"fake-t10-"+i, company_id:"{ctx["cid"]}", party_id:"{ctx["A"]}", to:"{SAFE_TO}", importo_scaduto:1, rate:1, created_at:new Date().toISOString()}}));')
        r = ctx["s"].post(f"{API}/clienti/{ctx['A']}/sollecito", headers=ctx["h"])
        assert r.status_code == 429, r.text
        assert len(ctx["s"].get(f"{API}/clienti/{ctx['A']}/sollecito", headers=ctx["h"]).json()["storico"]) == 3

# Iteration 43: Conservazione documenti (internal 10-year archive + manual A-Cube preservation).
# Covers candidati, archivia (roles, duplicates, annual-only-past-years), file/allegati download, PDFs, verifica + tampering,
# config GET/PUT (admin only, password encrypted / never returned, usa_sdi rule), invia/aggiorna without config, tenant isolation, menu off.
# Run with: REACT_APP_BACKEND_URL=... pytest tests/test_iteration43_conservazione.py -n 0
import base64
import io
import json
import os
import subprocess
from datetime import date

import pytest
import requests
from pypdf import PdfReader

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
FIX = open(os.path.join(os.path.dirname(__file__), "fixtures", "sample_fattura.xml")).read()
PA, PB = "01234567897", "12345678903"
Y = date.today().year
PY = Y - 1
U = {k: (f"test-user-t43-{k}", f"test_session_t43_{k}") for k in ("admin", "co", "op")}
ROLE = {"admin": "admin", "co": "contabile", "op": "operatore"}
S = {}


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


def sess(k, cid="A"):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {U[k][1]}"
    if cid and S.get(cid):
        s.headers["X-Company-Id"] = S[cid]
    return s


def clean():
    ids = "[" + ",".join(f'"{u}"' for u, _ in U.values()) + "]"
    mongo(f'db.companies.find({{partita_iva:{{$in:["{PA}","{PB}"]}}, denominazione:/^TEST_T43/}}).forEach(c=>{{["invoices","passive_invoices","parties","payments","passive_payments","coa_entries","coa_accounts","coa_causali","coa_iva","f24_versamenti","corrispettivi","sdi_events","audit","cons_docs"].forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:{ids}}}}}); db.user_sessions.deleteMany({{user_id:{{$in:{ids}}}}});')


def mk_company(name, piva):
    r = sess("admin", None).post(f"{API}/companies", json={"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01",
                                                          "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT",
                                                          "banche": [{"nome": "Banca A", "iban": "IT60X0542811101000000123456", "predefinita": True}]})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def do_setup():
    clean()
    for k, (uid, tok) in U.items():
        mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.{uid}@example.com", name:"TEST_{k}", picture:"", role:"{ROLE[k]}", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
              f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    S["A"] = mk_company("TEST_T43 Alfa Srl", PA)
    S["B"] = mk_company("TEST_T43 Beta Srl", PB)
    mongo(f'db.users.updateMany({{user_id:{{$in:["{U["co"][0]}","{U["op"][0]}"]}}}}, {{$set:{{company_ids:["{S["A"]}"]}}}});')
    s = sess("admin")
    p = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": "TEST_T43 Cliente Spa", "partita_iva": "02345670481", "codice_fiscale": "02345670481",
                                       "codice_destinatario": "ABC1234", "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"})
    assert p.status_code == 200, p.text
    S["party"] = p.json()["id"]
    inv = []
    for d in (f"{PY}-03-10", f"{PY}-06-15"):
        r = s.post(f"{API}/invoices", json={"data": d, "party_id": S["party"], "lines": [{"descrizione": "TEST consulenza", "quantita": 1, "prezzo_unitario": 1000, "aliquota": 22}]})
        assert r.status_code == 200, r.text
        inv.append(r.json()["id"])
    r = s.post(f"{API}/invoices/{inv[0]}/send")
    assert r.status_code == 200, r.text
    S["inv_sent"], S["inv_draft"] = inv
    xml = FIX.replace("<IdCodice>01234567890</IdCodice>", f"<IdCodice>{PA}</IdCodice>").replace("<Numero>5674/2026</Numero>", "<Numero>TEST43-1</Numero>") \
        .replace("<Data>2026-10-30</Data>", f"<Data>{PY}-05-05</Data>")
    up = s.post(f"{API}/passive/upload", files=[("files", ("p.xml", xml, "text/xml"))])
    assert up.status_code == 200, up.text
    S["pas"] = up.json()[0]["documenti"][0]["id"]
    mongo(f'db.f24_versamenti.insertOne({{company_id:"{S["A"]}", key:"IVA-{PY}-05", codice:"6005", importo:1234.56, data:"{PY}-06-16", by:"TEST", created_at:new Date().toISOString()}});'
          f'db.f24_versamenti.insertOne({{company_id:"{S["A"]}", key:"RIT-{PY}-04", codice:"1040", importo:200, data:"{PY}-05-16", by:"TEST", created_at:new Date().toISOString()}});'
          f'db.corrispettivi.insertOne({{id:"test-t43-corr-1", company_id:"{S["A"]}", data:"{PY}-04-04", anno:{PY}, matricola:"99MEXTEST", n_documenti:12, tipo_documento:"COR", riepilogo:[{{aliquota:22, natura:null, imponibile:100, imposta:22}}], totale:122, origine:"test", created_at:new Date().toISOString()}});')


@pytest.fixture(scope="module", autouse=True)
def setup():
    do_setup()
    yield
    clean()


def cand(tipo, anno=PY, k="admin"):
    r = sess(k).get(f"{API}/conservazione/candidati", params={"tipo": tipo, "anno": anno})
    assert r.status_code == 200, r.text
    return r.json()["items"]


def archivia(tipo, rif, anno=PY, k="admin"):
    return sess(k).post(f"{API}/conservazione/archivia", json={"tipo": tipo, "anno": anno, "rif": rif})


def docs(tipo=None, k="admin", cid="A"):
    r = sess(k, cid).get(f"{API}/conservazione", params={"anno": PY, **({"tipo": tipo} if tipo else {})})
    assert r.status_code == 200, r.text
    return r.json()


class TestCandidati:
    def test_emesse_only_sent(self):
        it = cand("fattura_emessa")
        assert [i["rif"] for i in it] == [S["inv_sent"]]
        assert it[0]["archiviato"] is False and it[0]["importo"] == 1220

    def test_ricevute(self):
        assert [i["rif"] for i in cand("fattura_ricevuta")] == [S["pas"]]
        assert cand("fattura_ricevuta", Y) == []

    def test_f24(self):
        assert sorted(i["rif"] for i in cand("f24")) == [f"IVA-{PY}-05", f"RIT-{PY}-04"]

    def test_annual(self):
        it = cand("registro_iva_vendite")
        assert it == [{"rif": str(PY), "label": f"Registro IVA vendite {PY}", "data": f"{PY}-12-31", "importo": None, "nota": None, "archiviato": False}]
        assert cand("libro_giornale", Y)[0]["nota"] == "Disponibile a fine anno"

    def test_bad_tipo(self):
        assert sess("admin").get(f"{API}/conservazione/candidati", params={"tipo": "xxx", "anno": PY}).status_code == 422


class TestArchivia:
    def test_operatore_403(self):
        assert archivia("fattura_emessa", [S["inv_sent"]], k="op").status_code == 403

    def test_annual_current_year_400(self):
        r = archivia("registro_iva_vendite", [str(Y)], anno=Y)
        assert r.status_code == 400 and "anno concluso" in r.json()["detail"]
        assert archivia("registro_iva_vendite", ["1999"]).status_code == 400

    def test_draft_error(self):
        r = archivia("fattura_emessa", [S["inv_draft"]])
        assert r.status_code == 200 and r.json()["archiviati"] == 0 and len(r.json()["errori"]) == 1

    def test_emessa(self):
        r = archivia("fattura_emessa", [S["inv_sent"], S["inv_sent"]], k="co")
        assert r.status_code == 200 and r.json() == {"archiviati": 1, "gia_presenti": 0, "errori": []}
        assert archivia("fattura_emessa", [S["inv_sent"]]).json()["gia_presenti"] == 1
        d = docs("fattura_emessa")["documenti"]
        assert len(d) == 1
        d = d[0]
        S["doc_em"] = d["id"]
        assert d["conserva_fino"] == f"{PY + 10}-12-31" and d["mime"] == "application/xml" and d["conservatore"] is True
        assert "content_b64" not in d and "content_b64" not in d["allegati"][0]
        assert d["allegati"][0]["file_name"] == "ricevute_sdi.json"
        assert cand("fattura_emessa")[0]["archiviato"] is True
        f = sess("admin").get(f"{API}/conservazione/{d['id']}/file")
        assert f.status_code == 200 and b"FatturaElettronica" in f.content
        import hashlib
        assert hashlib.sha256(f.content).hexdigest() == d["sha256"]
        a = sess("admin").get(f"{API}/conservazione/{d['id']}/file", params={"allegato": 0})
        assert a.status_code == 200 and json.loads(a.content)["stato"] == "inviata"
        assert sess("admin").get(f"{API}/conservazione/{d['id']}/file", params={"allegato": 5}).status_code == 404

    def test_ricevuta(self):
        r = archivia("fattura_ricevuta", [S["pas"]])
        assert r.json()["archiviati"] == 1, r.text
        d = docs("fattura_ricevuta")["documenti"][0]
        S["doc_ric"] = d["id"]
        assert d["allegati"][0]["file_name"] == "dati_ricezione_sdi.json"
        assert b"TEST43-1" in sess("admin").get(f"{API}/conservazione/{d['id']}/file").content

    @pytest.mark.parametrize("tipo,rif,needle", [("registro_iva_vendite", str(PY), "Registro IVA vendite"), ("registro_iva_acquisti", str(PY), "Registro IVA acquisti"),
                                                 ("corrispettivi", str(PY), "Registro corrispettivi"), ("libro_giornale", str(PY), "Libro giornale"),
                                                 ("f24", f"IVA-{PY}-05", None), ("f24", f"RIT-{PY}-04", None)])
    def test_pdfs(self, tipo, rif, needle):
        r = archivia(tipo, [rif])
        assert r.status_code == 200 and r.json()["archiviati"] == 1, r.text
        d = next(x for x in docs(tipo)["documenti"] if x["rif"] == rif)
        f = sess("admin").get(f"{API}/conservazione/{d['id']}/file")
        assert f.status_code == 200 and f.content[:4] == b"%PDF" and f.headers["content-type"] == "application/pdf"
        pdf = PdfReader(io.BytesIO(f.content))
        txt = "".join(p.extract_text() for p in pdf.pages)
        if needle:
            assert needle in txt and "Riepilogo" in txt
            w, h = pdf.pages[0].mediabox.width, pdf.pages[0].mediabox.height
            assert w > h  # landscape
        assert len(txt) > 50

    def test_no_delete(self):
        assert sess("admin").delete(f"{API}/conservazione/{S['doc_em']}").status_code in (404, 405)


class TestVerifica:
    def test_ok_then_tamper(self):
        r = sess("op").post(f"{API}/conservazione/{S['doc_ric']}/verifica")
        assert r.status_code == 200 and r.json()["ok"] is True
        assert docs("fattura_ricevuta")["documenti"][0]["verifica"]["ok"] is True
        mongo(f'db.cons_docs.updateOne({{id:"{S["doc_ric"]}"}}, {{$set:{{content_b64:"{base64.b64encode(b"tampered").decode()}"}}}});')
        assert sess("admin").post(f"{API}/conservazione/{S['doc_ric']}/verifica").json()["ok"] is False
        assert docs("fattura_ricevuta")["documenti"][0]["verifica"]["ok"] is False


class TestConfig:
    def test_default(self):
        r = sess("admin").get(f"{API}/conservazione/config").json()
        assert r["has_password"] is False and r["sdi_acube"] is False and docs()["collegato"] is False

    def test_without_config_400(self):
        for ep in ("invia", "aggiorna"):
            r = sess("admin").post(f"{API}/conservazione/{ep}", json={"ids": [S["doc_em"]]})
            assert r.status_code == 400 and "Configura prima" in r.json()["detail"]
        assert sess("admin").post(f"{API}/conservazione/config/test").status_code == 400

    def test_put_roles_and_validation(self):
        body = {"usa_sdi": False, "ambiente": "sandbox", "email": "TEST_acube@example.com", "password": "Secret123"}
        assert sess("co").put(f"{API}/conservazione/config", json=body).status_code == 403
        assert sess("admin").put(f"{API}/conservazione/config", json={**body, "email": "bad"}).status_code == 422
        assert sess("admin").put(f"{API}/conservazione/config", json={**body, "password": None}).status_code == 422
        assert sess("admin").put(f"{API}/conservazione/config", json={**body, "usa_sdi": True}).status_code == 422
        r = sess("admin").put(f"{API}/conservazione/config", json=body)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["email"] == "test_acube@example.com" and j["has_password"] is True and "password" not in j and "password_enc" not in j
        raw = mongo(f'print(JSON.stringify(db.companies.findOne({{id:"{S["A"]}"}}).conservazione))')
        assert "Secret123" not in raw and "password_enc" in raw
        # keep password when omitted
        r = sess("admin").put(f"{API}/conservazione/config", json={**body, "password": None, "ambiente": "production"})
        assert r.status_code == 200 and r.json()["has_password"] is True and r.json()["ambiente"] == "production"
        d = docs()
        assert d["collegato"] is True and d["ambiente"] == "production"
        assert "Secret123" not in json.dumps(sess("admin").get(f"{API}/conservazione/config").json())


class TestIsolation:
    def test_company_b(self):
        assert docs(cid="B")["documenti"] == []
        assert sess("admin", "B").get(f"{API}/conservazione/{S['doc_em']}/file").status_code == 404
        assert sess("admin", "B").post(f"{API}/conservazione/{S['doc_em']}/verifica").status_code == 404
        assert sess("admin", "B").get(f"{API}/conservazione/{S['doc_em']}/ricevuta").status_code == 404

    def test_ricevuta_not_available(self):
        assert sess("admin").get(f"{API}/conservazione/{S['doc_em']}/ricevuta").status_code == 404

    def test_menu_off_403(self):
        r = sess("admin", None).put(f"{API}/companies/{S['B']}/menu", json={"off": ["conservazione"]})
        assert r.status_code == 200, r.text
        assert sess("admin", "B").get(f"{API}/conservazione", params={"anno": PY}).status_code == 403
        sess("admin", None).put(f"{API}/companies/{S['B']}/menu", json={"off": []})

    def test_module_off_403(self):
        m = {k: True for k in ("fatturazione", "archivio", "fatture_attive", "fatture_passive", "corrispettivi", "contabilita")}
        r = sess("admin", None).put(f"{API}/companies/{S['B']}/moduli", json={**m, "fatturazione": False})
        assert r.status_code == 200, r.text
        assert sess("admin", "B").get(f"{API}/conservazione/candidati", params={"tipo": "f24", "anno": PY}).status_code == 403
        sess("admin", None).put(f"{API}/companies/{S['B']}/moduli", json=m)

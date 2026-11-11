# Iteration 46: DDT signatures (destinatario/conducente/vettore) in-app + temporary public signing link + PDF embedding.
# Run with: REACT_APP_BACKEND_URL=... pytest tests/test_iteration46_ddt_firme.py -n 0
import base64
import io
import os
import subprocess
from datetime import date

import pytest
import requests
from PIL import Image, ImageDraw
from pypdf import PdfReader

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
PA, PB = "01234567897", "12345678903"
TODAY = date.today().isoformat()
U = {k: (f"test-user-t46-{k}", f"test_session_t46_{k}") for k in ("admin", "op")}
ROLE = {"admin": "admin", "op": "operatore"}
S = {}


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


def sess(k="admin", cid="A"):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {U[k][1]}"
    if cid and S.get(cid):
        s.headers["X-Company-Id"] = S[cid]
    return s


def png(color="black", fmt="PNG"):
    im = Image.new("RGB" if fmt == "JPEG" else "RGBA", (400, 150), (255, 255, 255, 0) if fmt == "PNG" else "white")
    ImageDraw.Draw(im).line([(10, 100), (100, 30), (200, 120), (380, 40)], fill=color, width=4)
    b = io.BytesIO(); im.save(b, fmt)
    return f"data:image/{fmt.lower()};base64," + base64.b64encode(b.getvalue()).decode()


def clean():
    ids = "[" + ",".join(f'"{u}"' for u, _ in U.values()) + "]"
    mongo(f'db.companies.find({{partita_iva:{{$in:["{PA}","{PB}"]}}, denominazione:/^TEST_T46/}}).forEach(c=>{{["invoices","parties","articles","stock_moves","ddts","payments","coa_entries","coa_accounts","coa_causali","coa_iva","audit","sdi_events"].forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:{ids}}}}}); db.user_sessions.deleteMany({{user_id:{{$in:{ids}}}}});')


def mk_company(name, piva):
    r = sess("admin", None).post(f"{API}/companies", json={"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01",
                                                          "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT",
                                                          "banche": [{"nome": "Banca A", "iban": "IT60X0542811101000000123456", "predefinita": True}]})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def ddt_body():
    return {"data": TODAY, "party_id": S["cli"], "causale": "Vendita", "porto": "assegnato", "trasporto_a_cura": "vettore",
            "vettore": {"denominazione": "TEST Vettore Express", "partita_iva": "11111111111", "indirizzo": "Via Corriere 9"},
            "colli": 2, "peso_kg": 5, "aspetto_beni": "Scatole", "prezzi_in_stampa": True,
            "lines": [{"descrizione": "TEST riga firma", "quantita": 3, "unita_misura": "PZ", "prezzo_unitario": 12.34, "aliquota": 22}]}


def new_ddt(confirm=True):
    s = sess()
    r = s.post(f"{API}/ddt", json=ddt_body()); assert r.status_code == 200, r.text
    did = r.json()["id"]
    if confirm:
        r = s.post(f"{API}/ddt/{did}/conferma", json={"forza": True}); assert r.status_code == 200, r.text
    return did


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    for k, (uid, tok) in U.items():
        mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.{uid}@example.com", name:"TEST_{k}", picture:"", role:"{ROLE[k]}", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
              f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    S["A"] = mk_company("TEST_T46 Alfa Srl", PA)
    S["B"] = mk_company("TEST_T46 Beta Srl", PB)
    mongo(f'db.users.updateMany({{user_id:"{U["op"][0]}"}}, {{$set:{{company_ids:["{S["A"]}"]}}}});')
    r = sess().post(f"{API}/parties", json={"tipo": "cliente", "denominazione": "TEST_T46 Cliente Spa", "partita_iva": "02345670481", "codice_fiscale": "02345670481",
                                           "codice_destinatario": "ABC1234", "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"})
    assert r.status_code == 200, r.text
    S["cli"] = r.json()["id"]
    yield
    clean()


class TestFirme:
    def test_bozza_not_signable(self):
        did = new_ddt(confirm=False)
        s = sess()
        assert s.post(f"{API}/ddt/{did}/firme", json={"ruolo": "destinatario", "nome": "Mario Rossi", "immagine": png()}).status_code == 400
        assert s.post(f"{API}/ddt/{did}/link-firma").status_code == 400

    def test_sign_in_app(self):
        S["d"] = did = new_ddt()
        s = sess()
        r = s.post(f"{API}/ddt/{did}/firme", json={"ruolo": "destinatario", "nome": "  Mario Rossi ", "immagine": png()})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["nome"] == "Mario Rossi" and j["by"] == "TEST_admin" and "png_b64" not in j and len(j["sha256"]) == 64
        d = s.get(f"{API}/ddt/{did}").json()
        assert d["firme"]["destinatario"]["nome"] == "Mario Rossi"
        assert base64.b64decode(d["firme"]["destinatario"]["png_b64"]).startswith(b"\x89PNG")
        # duplicate
        assert s.post(f"{API}/ddt/{did}/firme", json={"ruolo": "destinatario", "nome": "Altro", "immagine": png()}).status_code == 400

    def test_validation(self):
        s, did = sess(), S["d"]
        jpg = png(fmt="JPEG")
        assert s.post(f"{API}/ddt/{did}/firme", json={"ruolo": "conducente", "nome": "Gino", "immagine": jpg}).status_code == 422
        assert s.post(f"{API}/ddt/{did}/firme", json={"ruolo": "conducente", "nome": "Gino", "immagine": "data:image/png;base64," + "@!#$" * 40}).status_code == 422
        assert s.post(f"{API}/ddt/{did}/firme", json={"ruolo": "conducente", "nome": "Gino", "immagine": "data:image/png;base64,AAAA"}).status_code == 422
        assert s.post(f"{API}/ddt/{did}/firme", json={"ruolo": "cliente", "nome": "Gino", "immagine": png()}).status_code == 422
        assert s.post(f"{API}/ddt/{did}/firme", json={"ruolo": "conducente", "nome": "G", "immagine": png()}).status_code == 422
        # nothing persisted
        assert not (sess().get(f"{API}/ddt/{did}").json()["firme"].get("conducente"))

    def test_tenant_isolation(self):
        sb = sess("admin", "B")
        did = S["d"]
        assert sb.post(f"{API}/ddt/{did}/firme", json={"ruolo": "vettore", "nome": "Hacker", "immagine": png()}).status_code == 404
        assert sb.post(f"{API}/ddt/{did}/link-firma").status_code == 404
        assert sb.delete(f"{API}/ddt/{did}/firme/destinatario").status_code == 404
        assert sb.get(f"{API}/ddt/{did}/pdf").status_code == 404

    def test_remove_roles(self):
        did = S["d"]
        op = sess("op")
        r = op.post(f"{API}/ddt/{did}/firme", json={"ruolo": "vettore", "nome": "Op Vettore", "immagine": png()})
        assert r.status_code == 200, r.text
        assert op.delete(f"{API}/ddt/{did}/firme/vettore").status_code == 403
        r = sess().delete(f"{API}/ddt/{did}/firme/vettore"); assert r.status_code == 200
        assert sess().get(f"{API}/ddt/{did}").json()["firme"]["vettore"] is None
        r = sess().post(f"{API}/ddt/{did}/firme", json={"ruolo": "vettore", "nome": "Luca Vettore", "immagine": png("blue")})
        assert r.status_code == 200, r.text

    def test_list_hides_firme(self):
        lst = sess().get(f"{API}/ddt").json()
        x = next(x for x in lst if x["id"] == S["d"])
        assert "firme" not in x and "firma_link" not in x

    def test_public_link_flow(self):
        did, s = S["d"], sess()
        r = s.post(f"{API}/ddt/{did}/link-firma"); assert r.status_code == 200, r.text
        tok = r.json()["token"]; assert len(tok) > 30 and r.json()["expires_at"]
        pub = requests.get(f"{API}/public/ddt-firma/{tok}")
        assert pub.status_code == 200, pub.text
        j = pub.json()
        assert j["azienda"] == "TEST_T46 Alfa Srl" and j["cliente"] == "TEST_T46 Cliente Spa" and j["numero_display"]
        assert j["lines"] == [{"descrizione": "TEST riga firma", "quantita": 3, "unita_misura": "PZ"}]
        assert j["firme"]["destinatario"]["nome"] == "Mario Rossi" and j["firme"]["conducente"] is None
        raw = pub.text
        assert "png_b64" not in raw and "12.34" not in raw and "prezzo" not in raw and "hash" not in raw
        r = requests.post(f"{API}/public/ddt-firma/{tok}", json={"ruolo": "conducente", "nome": "Gianni Autista", "immagine": png("red")})
        assert r.status_code == 200, r.text
        assert r.json()["by"] == "link di firma" and "png_b64" not in r.json()
        assert requests.post(f"{API}/public/ddt-firma/{tok}", json={"ruolo": "conducente", "nome": "Again", "immagine": png()}).status_code == 400
        assert requests.get(f"{API}/public/ddt-firma/{tok}").json()["firme"]["conducente"]["nome"] == "Gianni Autista"
        # new link replaces old
        tok2 = s.post(f"{API}/ddt/{did}/link-firma").json()["token"]
        assert requests.get(f"{API}/public/ddt-firma/{tok}").status_code == 404
        assert requests.post(f"{API}/public/ddt-firma/{tok}", json={"ruolo": "vettore", "nome": "Xx", "immagine": png()}).status_code == 404
        assert requests.get(f"{API}/public/ddt-firma/{tok2}").status_code == 200
        assert requests.get(f"{API}/public/ddt-firma/badtoken123").status_code == 404
        S["tok2"] = tok2

    def test_pdf_signatures(self):
        r = sess().get(f"{API}/ddt/{S['d']}/pdf")
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/pdf")
        rd = PdfReader(io.BytesIO(r.content))
        txt = "\n".join(p.extract_text() for p in rd.pages)
        for k in ("FIRMA CONDUCENTE", "FIRMA VETTORE", "FIRMA DESTINATARIO", "Mario Rossi", "Gianni Autista", "Luca Vettore"):
            assert k in txt, k
        assert sum(len(p.images) for p in rd.pages) >= 3  # distinct PNGs per role (reportlab dedupes identical images)

    def test_expired_token(self):
        did = new_ddt()
        tok = sess().post(f"{API}/ddt/{did}/link-firma").json()["token"]
        assert requests.get(f"{API}/public/ddt-firma/{tok}").status_code == 200
        mongo(f'db.ddts.updateOne({{id:"{did}"}}, {{$set:{{"firma_link.expires_at":"2000-01-01T00:00:00+00:00"}}}})')
        assert requests.get(f"{API}/public/ddt-firma/{tok}").status_code == 404
        assert requests.post(f"{API}/public/ddt-firma/{tok}", json={"ruolo": "vettore", "nome": "Xx", "immagine": png()}).status_code == 404

    def test_annullato(self):
        did = new_ddt()
        s = sess()
        tok = s.post(f"{API}/ddt/{did}/link-firma").json()["token"]
        r = s.post(f"{API}/ddt/{did}/annulla"); assert r.status_code == 200, r.text
        assert requests.get(f"{API}/public/ddt-firma/{tok}").status_code == 404
        assert requests.post(f"{API}/public/ddt-firma/{tok}", json={"ruolo": "vettore", "nome": "Xx", "immagine": png()}).status_code == 404
        assert s.post(f"{API}/ddt/{did}/firme", json={"ruolo": "vettore", "nome": "Xx", "immagine": png()}).status_code == 400
        assert s.post(f"{API}/ddt/{did}/link-firma").status_code == 400

    def test_fatturato_signable(self):
        did = new_ddt()
        s = sess()
        r = s.post(f"{API}/ddt/{did}/fattura")
        assert r.status_code == 200, r.text
        assert s.get(f"{API}/ddt/{did}").json()["status"] == "fatturato"
        r = s.post(f"{API}/ddt/{did}/firme", json={"ruolo": "destinatario", "nome": "Post Fattura", "immagine": png()})
        assert r.status_code == 200, r.text
        tok = s.post(f"{API}/ddt/{did}/link-firma").json()["token"]
        assert requests.get(f"{API}/public/ddt-firma/{tok}").status_code == 200

    def test_unauth(self):
        assert requests.post(f"{API}/ddt/{S['d']}/firme", json={"ruolo": "vettore", "nome": "Xx", "immagine": png()}).status_code == 401
        assert requests.post(f"{API}/ddt/{S['d']}/link-firma").status_code == 401

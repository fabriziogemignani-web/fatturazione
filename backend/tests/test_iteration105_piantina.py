# Iteration 105: Porto turistico - piantina interattiva (upload/info/immagine/delete, disponi, pos per posto, isolation, mappa pos, planning regression)
# Run: cd /app/backend && set -a && . ./.env && . ../frontend/.env && set +a && pytest tests/test_iteration105_piantina.py -v -n 0
import os
import sys
from datetime import date, timedelta

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

UID, TOK = "test-user-t105-admin", "test_session_t105_admin"
ST = {}
TODAY = date.today()
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 200
WEBP = b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"\x00" * 200
MARINA = "/tmp/pt/marina.png"


def s(cid=None):
    x = requests.Session()
    x.headers["Authorization"] = f"Bearer {TOK}"
    x.headers["X-Requested-With"] = "invoix"
    if cid or ST.get("cid"):
        x.headers["X-Company-Id"] = cid or ST["cid"]
    return x


def clean():
    mongo('db.companies.find({denominazione:/^TEST_T105/}).forEach(c=>{["parties","invoices","porto_config","porto_pontili","porto_posti","porto_barche","porto_contratti","porto_transiti","porto_piantina","payments","scadenze"].forEach(k=>db[k].deleteMany({company_id:c.id}));'
          'db.counters.deleteMany({key:{$regex:c.id}}); db.users.updateMany({}, {$pull:{company_ids:c.id}}); db.companies.deleteOne({id:c.id});});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def company(name, piva):
    r = s(cid="x").post(f"{API}/companies", headers={"X-Company-Id": None}, json={"denominazione": name, "partita_iva": piva, "codice_fiscale": piva,
                        "regime_fiscale": "RF01", "indirizzo": "Via Roma 1", "cap": "57100", "comune": "Livorno", "provincia": "LI", "nazione": "IT"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t105@example.com", name:"TEST_T105 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    ST["cid"] = company("TEST_T105 Marina Srl", "10510510510")
    ST["cid2"] = company("TEST_T105 Altro Srl", "10510510511")
    ST["pont"] = s().post(f"{API}/porto/pontili", json={"nome": "TEST_A", "ordine": 1}).json()["id"]
    s().post(f"{API}/porto/posti/serie", json={"pontile_id": ST["pont"], "prefisso": "A", "da": 1, "a": 5, "lunghezza_max": 12})
    ST["posti"] = {p["codice"]: p["id"] for p in s().get(f"{API}/porto/posti").json()}
    yield
    if not os.environ.get("KEEP_T105"):
        clean()


def up(data, name="x.png", cid=None):
    return s(cid).post(f"{API}/porto/piantina", files={"file": (name, data, "application/octet-stream")})


class TestUpload:
    def test_info_empty(self):
        assert s().get(f"{API}/porto/piantina/info").json() == {"presente": False}
        assert s().get(f"{API}/porto/piantina/immagine").status_code == 404

    def test_reject_formats(self):
        assert up(b"GIF89a" + b"\x00" * 50, "a.gif").status_code == 415
        assert up(b"%PDF-1.4 hello", "a.png").status_code == 415
        assert up(b"", "a.png").status_code == 415

    def test_too_large(self):
        r = up(b"\x89PNG" + b"\x00" * (5 * 1024 * 1024), "big.png")
        assert r.status_code == 413, r.text

    def test_csrf(self):
        r = s().post(f"{API}/porto/piantina", headers={"X-Requested-With": None}, files={"file": ("x.png", PNG)})
        assert r.status_code == 403

    def test_jpg_webp_accepted(self):
        r = up(JPG, "a.jpg")
        assert r.status_code == 200 and r.json()["mime"] == "image/jpeg"
        r = up(WEBP, "a.webp")
        assert r.status_code == 200 and r.json()["mime"] == "image/webp"

    def test_png_upload_info_image(self):
        raw = open(MARINA, "rb").read() if os.path.exists(MARINA) else PNG
        r = up(raw, "marina del fezzano.png")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["mime"] == "image/png" and d["dimensione"] == len(raw) and d["presente"] is True and "data" not in d and "company_id" not in d
        i = s().get(f"{API}/porto/piantina/info").json()
        assert i["presente"] is True and i["mime"] == "image/png" and i["nome"] == "marina del fezzano.png" and i["dimensione"] == len(raw)
        img = s().get(f"{API}/porto/piantina/immagine")
        assert img.status_code == 200 and img.headers["content-type"].startswith("image/png") and img.content == raw

    def test_isolation(self):
        o = s(ST["cid2"])
        assert o.get(f"{API}/porto/piantina/info").json() == {"presente": False}
        assert o.get(f"{API}/porto/piantina/immagine").status_code == 404


class TestPosizioni:
    def test_disponi_line(self):
        ids = [ST["posti"][c] for c in ("A1", "A2", "A3", "A4", "A5")]
        r = s().post(f"{API}/porto/piantina/disponi", json={"posto_ids": ids, "x1": 0.1, "y1": 0.2, "x2": 0.5, "y2": 0.6})
        assert r.status_code == 200 and r.json() == {"posizionati": 5}
        m = s().get(f"{API}/porto/mappa").json()
        pos = {p["codice"]: p["pos"] for pt in m["pontili"] for p in pt["posti"]}
        assert pos["A1"] == {"x": 0.1, "y": 0.2} and pos["A5"] == {"x": 0.5, "y": 0.6}
        assert abs(pos["A3"]["x"] - 0.3) < 1e-6 and abs(pos["A3"]["y"] - 0.4) < 1e-6

    def test_disponi_reversed_and_single(self):
        ids = [ST["posti"]["A2"], ST["posti"]["A1"]]
        assert s().post(f"{API}/porto/piantina/disponi", json={"posto_ids": ids, "x1": 0.0, "y1": 0.0, "x2": 1.0, "y2": 1.0}).status_code == 200
        pos = {p["codice"]: p.get("pos") for p in s().get(f"{API}/porto/posti").json()}
        assert pos["A2"] == {"x": 0.0, "y": 0.0} and pos["A1"] == {"x": 1.0, "y": 1.0}
        r = s().post(f"{API}/porto/piantina/disponi", json={"posto_ids": [ST["posti"]["A1"]], "x1": 0.2, "y1": 0.2, "x2": 0.4, "y2": 0.4})
        assert r.json() == {"posizionati": 1}
        pos = {p["codice"]: p.get("pos") for p in s().get(f"{API}/porto/posti").json()}
        assert pos["A1"] == {"x": 0.3, "y": 0.3}

    def test_disponi_errors(self):
        assert s().post(f"{API}/porto/piantina/disponi", json={"posto_ids": ["nope"], "x1": 0, "y1": 0, "x2": 1, "y2": 1}).status_code == 404
        assert s().post(f"{API}/porto/piantina/disponi", json={"posto_ids": [], "x1": 0, "y1": 0, "x2": 1, "y2": 1}).status_code == 422
        assert s().post(f"{API}/porto/piantina/disponi", json={"posto_ids": [ST["posti"]["A1"]], "x1": 0, "y1": 0, "x2": 1.5, "y2": 1}).status_code == 422
        assert s(ST["cid2"]).post(f"{API}/porto/piantina/disponi", json={"posto_ids": [ST["posti"]["A1"]], "x1": 0, "y1": 0, "x2": 1, "y2": 1}).status_code == 404

    def test_set_pos(self):
        pid = ST["posti"]["A4"]
        r = s().put(f"{API}/porto/posti/{pid}/pos", json={"x": 0.77, "y": 0.11})
        assert r.status_code == 200 and r.json() == {"x": 0.77, "y": 0.11}
        assert next(p for p in s().get(f"{API}/porto/posti").json() if p["id"] == pid)["pos"] == {"x": 0.77, "y": 0.11}
        assert s().put(f"{API}/porto/posti/{pid}/pos", json={"x": 1.2, "y": 0.1}).status_code == 422
        assert s().put(f"{API}/porto/posti/{pid}/pos", json={"x": -0.1, "y": 0.1}).status_code == 422
        assert s().put(f"{API}/porto/posti/nope/pos", json={"x": 0.1, "y": 0.1}).status_code == 404
        assert s(ST["cid2"]).put(f"{API}/porto/posti/{pid}/pos", json={"x": 0.1, "y": 0.1}).status_code == 404

    def test_del_pos(self):
        pid = ST["posti"]["A4"]
        assert s(ST["cid2"]).delete(f"{API}/porto/posti/{pid}/pos").status_code == 404
        assert s().delete(f"{API}/porto/posti/{pid}/pos").status_code == 200
        assert "pos" not in next(p for p in s().get(f"{API}/porto/posti").json() if p["id"] == pid)
        assert s().delete(f"{API}/porto/posti/nope/pos").status_code == 404

    def test_planning_regression(self):
        r = s().get(f"{API}/porto/planning", params={"da": TODAY.isoformat(), "giorni": 14})
        assert r.status_code == 200 and len(r.json()["posti"]) == 5

    def test_posto_update_keeps_pos(self):
        pid = ST["posti"]["A5"]
        before = next(p for p in s().get(f"{API}/porto/posti").json() if p["id"] == pid)
        r = s().put(f"{API}/porto/posti/{pid}", json={"pontile_id": ST["pont"], "codice": "A5", "lunghezza_max": 13, "larghezza_max": 0, "tipo": "mare", "fuori_servizio": False, "note": ""})
        assert r.status_code == 200, r.text
        after = next(p for p in s().get(f"{API}/porto/posti").json() if p["id"] == pid)
        assert after.get("pos") == before.get("pos"), "editing a posto should not wipe its map position"

    def test_delete_piantina_clears(self):
        assert s(ST["cid2"]).delete(f"{API}/porto/piantina").status_code == 200
        assert s().get(f"{API}/porto/piantina/info").json()["presente"] is True  # other company delete no effect
        assert s().delete(f"{API}/porto/piantina").status_code == 200
        assert s().get(f"{API}/porto/piantina/info").json() == {"presente": False}
        assert s().get(f"{API}/porto/piantina/immagine").status_code == 404
        assert all("pos" not in p for p in s().get(f"{API}/porto/posti").json())

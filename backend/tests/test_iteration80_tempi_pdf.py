# Iteration 80: Produzione - scheda di lavoro PDF, tempi effettivi per fase, consuntivo std vs effettivo.
# Run: pytest tests/test_iteration80_tempi_pdf.py -v -n 0   (T80_KEEP=1 keeps data for UI)
import json
import os
import random
import sys
from datetime import date, timedelta

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

RUN = os.environ.get("T80_RUN") or str(random.randint(100000, 999999))
TOK, UID = "test_session_t80_admin", "test-user-t80-admin"
D = lambda n: (date.today() + timedelta(days=n)).isoformat()  # noqa: E731
ST = {}
P = f"{API}/produzione"


def sess(cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    c = cid or ST.get("cid")
    if c:
        s.headers["X-Company-Id"] = c
    return s


def clean():
    mongo('db.companies.find({denominazione:/^TEST_T80/}).forEach(c=>{db.getCollectionNames().forEach(k=>{if(k!=="companies") db[k].deleteMany({company_id:c.id})});'
          'db.users.updateMany({}, {$pull:{company_ids:c.id}}); db.companies.deleteOne({id:c.id});});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def company(name, piva):
    r = sess("x").post(f"{API}/companies", json={"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01",
                                                 "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def art(codice):
    r = sess().post(f"{API}/articles", json={"codice": codice, "descrizione": f"TEST_T80 {codice}", "unita_misura": "PZ", "prezzo": 10, "aliquota": 22, "gestione_magazzino": True})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def carico(aid, q, c):
    r = sess().post(f"{API}/magazzino/movimenti", json={"article_id": aid, "tipo": "carico", "data": D(-10), "quantita": q, "costo_unitario": c, "causale": "Acquisto"})
    assert r.status_code == 200, r.text


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t80.admin@example.com", name:"TEST_T80 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    ST["cid"] = company(f"TEST_T80 Produzione {RUN} Srl", "80" + RUN + "801")
    ST["cid2"] = company(f"TEST_T80 Altra {RUN} Srl", "80" + RUN + "802")
    ST["RM1"], ST["RM2"], ST["SL"] = art("TEST_RM1"), art("TEST_RM2"), art("TEST_SL")
    carico(ST["RM1"], 100, 2)
    carico(ST["RM2"], 50, 5)
    s = sess()
    ST["C1"] = s.post(f"{P}/centri", json={"codice": "C1", "descrizione": "TEST Taglio", "costo_orario": 60}).json()["id"]
    ST["C2"] = s.post(f"{P}/centri", json={"codice": "C2", "descrizione": "TEST Montaggio", "costo_orario": 30}).json()["id"]
    d = s.post(f"{P}/distinte", json={"article_id": ST["SL"], "lotto": 10, "componenti": [{"article_id": ST["RM1"], "quantita": 2}, {"article_id": ST["RM2"], "quantita": 1}],
                                      "fasi": [{"descrizione": "Taglio <&> lamiera", "centro_id": ST["C1"], "setup_min": 30, "minuti_pezzo": 6},
                                               {"descrizione": "Montaggio", "centro_id": ST["C2"], "setup_min": 0, "minuti_pezzo": 3}]})
    assert d.status_code == 200, d.text
    o = s.post(f"{P}/ordini", json={"article_id": ST["SL"], "quantita": 10, "data": D(0), "note": "TEST_T80 note <b>"})
    assert o.status_code == 200, o.text
    ST["OP"] = o.json()["id"]
    yield
    if os.environ.get("T80_KEEP"):
        print("\nKEEP", RUN, json.dumps({k: v for k, v in ST.items() if isinstance(v, str)}))
    else:
        clean()


def tempi(idx):
    return f"{P}/ordini/{ST['OP']}/fasi/{idx}/tempi"


class TestTempiPdf:
    # Consuntivo on pianificato order (no tempi) - standard values
    def test_01_consuntivo_initial(self):
        rows = {o["id"]: o for o in sess().get(f"{P}/ordini").json()}
        c = rows[ST["OP"]]["consuntivo"]
        # base 10; std mat 9*10=90; std lav (30+60)/60*60 + (0+30)/60*30 = 90+15 = 105
        assert c["base"] == 10 and c["std_materiali"] == 90 and c["std_lavorazioni"] == 105, c
        assert c["eff_materiali"] == 90 and c["eff_lavorazioni"] == 0 and c["fasi_mancanti"] == 2, c
        assert c["std_totale"] == 195 and c["eff_totale"] == 90 and c["scostamento"] == -105, c
        assert c["scostamento_pct"] == round(-105 / 195 * 100, 1)

    # PDF scheda di lavoro
    def test_02_pdf(self):
        r = sess().get(f"{P}/ordini/{ST['OP']}/pdf")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/pdf") and r.content[:4] == b"%PDF" and len(r.content) > 1500
        assert "Scheda_lavoro_OP_" in r.headers.get("content-disposition", "")
        assert sess().get(f"{P}/ordini/nonexistent/pdf").status_code == 404
        assert sess(ST["cid2"]).get(f"{P}/ordini/{ST['OP']}/pdf").status_code == 404

    def test_03_pdf_text(self):
        pytest.importorskip("pypdf")
        from io import BytesIO
        from pypdf import PdfReader
        txt = "".join(p.extract_text() for p in PdfReader(BytesIO(sess().get(f"{P}/ordini/{ST['OP']}/pdf").content)).pages)
        for s in ("SCHEDA DI LAVORO", "Componenti da prelevare", "Fasi da eseguire", "TEST_RM1", "TEST_RM2", "Taglio <&> lamiera", "Montaggio"):
            assert s in txt, (s, txt[:800])

    # Tempi on pianificato -> 400
    def test_04_tempi_pianificato(self):
        r = sess().post(tempi(0), json={"data": D(0), "minuti": 10})
        assert r.status_code == 400, r.text
        assert sess().post(f"{P}/ordini/{ST['OP']}/stato/lanciato").json()["status"] == "lanciato"

    # Validation: invalid idx, future date, minuti <=0
    def test_05_tempi_validation(self):
        s = sess()
        assert s.post(tempi(5), json={"data": D(0), "minuti": 10}).status_code == 404
        assert s.post(tempi(-1), json={"data": D(0), "minuti": 10}).status_code == 404
        assert s.post(tempi(0), json={"data": D(1), "minuti": 10}).status_code in (400, 422)
        assert s.post(tempi(0), json={"data": D(0), "minuti": 0}).status_code == 422
        assert s.post(tempi(0), json={"data": "bad", "minuti": 5}).status_code == 422
        assert sess(ST["cid2"]).post(tempi(0), json={"data": D(0), "minuti": 5}).status_code == 404

    # Add multiple regs -> sum + consuntivo
    def test_06_tempi_add(self):
        s = sess()
        r1 = s.post(tempi(0), json={"data": D(0), "minuti": 60, "operatore": "TEST_Mario", "note": "a"})
        assert r1.status_code == 200, r1.text
        r2 = s.post(tempi(0), json={"data": D(-1), "minuti": 45.5, "operatore": "TEST_Luigi"})
        assert r2.status_code == 200, r2.text
        o = r2.json()
        f = o["fasi"][0]
        assert len(f["tempi"]) == 2 and f["minuti_effettivi"] == 105.5 and f["tempi"][0]["operatore"] == "TEST_Mario"
        ST["T1"], ST["T2"] = f["tempi"][0]["id"], f["tempi"][1]["id"]
        c = o["consuntivo"]
        assert c["eff_lavorazioni"] == round(105.5 / 60 * 60, 2) and c["fasi_mancanti"] == 1 and c["minuti_effettivi"] == 105.5, c
        # persisted
        g = {x["id"]: x for x in s.get(f"{P}/ordini").json()}[ST["OP"]]
        assert g["fasi"][0]["minuti_effettivi"] == 105.5 and "_id" not in g

    # Delete -> recompute ; unknown tid no-op
    def test_07_tempi_del(self):
        s = sess()
        r = s.delete(f"{tempi(0)}/{ST['T1']}")
        assert r.status_code == 200, r.text
        f = r.json()["fasi"][0]
        assert len(f["tempi"]) == 1 and f["minuti_effettivi"] == 45.5
        r = s.delete(f"{tempi(0)}/nope")
        print("delete unknown tid ->", r.status_code)
        assert r.status_code in (200, 404)

    # Versamento -> base=prodotta, eff_materiali from versamenti
    def test_08_consuntivo_after_versa(self):
        s = sess()
        s.post(tempi(1), json={"data": D(0), "minuti": 20})
        r = s.post(f"{P}/ordini/{ST['OP']}/versa", json={"data": D(0), "quantita": 4})
        assert r.status_code == 200, r.text
        o = r.json()
        c = o.get("consuntivo") or {x["id"]: x for x in s.get(f"{P}/ordini").json()}[ST["OP"]]["consuntivo"]
        v_mat = sum(v["costo_materiali"] for v in o["versamenti"] if not v.get("annullato"))
        assert c["base"] == 4 and c["eff_materiali"] == round(v_mat, 2) and c["std_materiali"] == 36, c
        # std lav (30+24)/60*60 + 12/60*30 = 54+6 = 60 ; eff lav 45.5 + 20/60*30=10 -> 55.5
        assert c["std_lavorazioni"] == 60 and c["eff_lavorazioni"] == 55.5 and c["fasi_mancanti"] == 0, c
        assert c["scostamento"] == round(c["eff_totale"] - c["std_totale"], 2)

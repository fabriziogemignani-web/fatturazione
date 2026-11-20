# Iteration 116: passive upload stores ritenuta_xml (XML) next to ritenuta_importo (anagrafica), list exposes both;
# GET /ritenute/da-versare drives the dashboard F24 banner (past deadline -> giorni<0), F24 PDF, versato removes month.
# Run: pytest tests/test_iteration116_ritxml_f24_avviso.py -v -n 0 -s   (T116_KEEP=1 keeps data for UI tests)
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import test_iteration114_ritenuta_anagrafica_bollo as b  # noqa: E402
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

b.RUN = os.environ.get("T116_RUN", b.RUN)
b.TOK, b.UID = f"test_session_t116_admin_{b.RUN}", f"test-user-t116-admin-{b.RUN}"
b.PIVA = "13" + b.RUN + "116"
b.DATA = "2026-09-02"
ST = b.ST
MESE = "2026-09"
sess, upload, pdoc, mk_sup, piva, xml, reg_body = b.sess, b.upload, b.pdoc, b.mk_sup, b.piva, b.xml, b.reg_body


@pytest.fixture(scope="module", autouse=True)
def setup():
    b.clean()
    mongo(f'db.users.insertOne({{user_id:"{b.UID}", email:"test.user.t116.admin.{b.RUN}@example.com", name:"TEST_T116 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{b.UID}", session_token:"{b.TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": "TEST_T116 Srl", "partita_iva": b.PIVA, "codice_fiscale": b.PIVA, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    assert sess().put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                                   "corrispettivi": True, "contabilita": True}).status_code == 200
    sess().get(f"{API}/contabilita/conti")
    yield
    if os.environ.get("T116_KEEP"):
        print("\nKEEP", b.RUN, ST["cid"], b.TOK, json.dumps(ST))
    else:
        b.clean()


def listed(i):
    r = sess().get(f"{API}/passive")
    assert r.status_code == 200, r.text
    return next(x for x in r.json() if x["id"] == i)


class TestRitenutaXml:
    def test_xml_diff_stored(self):
        pi = piva()
        mk_sup("TEST_T116 XML diff", pi, cassa_tipo="TC01", cassa_aliquota=4, cassa_ritenuta=False)
        d = upload(xml(pi, ((22.0, None, 1040.0, 228.8),), rit=("RT01", 104.0, 10.0), den="TEST_T116 XML diff"))
        ST["diff"] = d["id"]
        x = listed(d["id"])
        print("diff:", x.get("ritenuta_xml"), x.get("ritenuta_importo"))
        assert x["ritenuta_xml"] == 104 and x["ritenuta_importo"] == 200

    def test_no_xml_ritenuta_zero(self):
        pi = piva()
        mk_sup("TEST_T116 No XML rit", pi, cassa_tipo="TC01", cassa_aliquota=4, cassa_ritenuta=False)
        d = upload(xml(pi, ((22.0, None, 1040.0, 228.8),), den="TEST_T116 No XML rit"))
        ST["noxml"] = d["id"]
        x = listed(d["id"])
        assert x["ritenuta_xml"] == 0 and x["ritenuta_importo"] == 200

    def test_equal_values(self):
        pi = piva()
        mk_sup("TEST_T116 Uguale", pi, cassa_tipo="TC01", cassa_aliquota=4, cassa_ritenuta=False)
        d = upload(xml(pi, ((22.0, None, 1040.0, 228.8),), rit=("RT01", 200.0, 20.0), den="TEST_T116 Uguale"))
        ST["eq"] = d["id"]
        x = listed(d["id"])
        assert x["ritenuta_xml"] == 200 and x["ritenuta_importo"] == 200

    def test_forfettario(self):
        pi = piva()
        mk_sup("TEST_T116 Forf", pi, soggetto_ritenuta=False, regime_percipiente="forfettario")
        d = upload(xml(pi, ((0.0, "N2.2", 1040.0, 0.0),), rit=("RT01", 208.0, 20.0), den="TEST_T116 Forf"))
        ST["forf"] = d["id"]
        x = listed(d["id"])
        assert x["ritenuta_xml"] == 208 and not x.get("ritenuta_importo")

    def test_non_soggetto_absent(self):
        pi = piva()
        mk_sup("TEST_T116 Normale", pi, soggetto_ritenuta=False)
        d = upload(xml(pi, ((22.0, None, 1000.0, 220.0),), den="TEST_T116 Normale"))
        ST["norm"] = d["id"]
        assert "ritenuta_xml" not in listed(d["id"])

    def test_riallinea_keeps_xml(self):
        r = sess().post(f"{API}/ritenute/riallinea")
        assert r.status_code == 200, r.text
        assert listed(ST["diff"])["ritenuta_xml"] == 104


class TestF24Avviso:
    def test_empty_before_payment(self):
        r = sess().get(f"{API}/ritenute/da-versare")
        assert r.status_code == 200 and r.json()["mesi"] == [], r.text

    def test_register_and_pay(self):
        i = ST["noxml"]
        d = pdoc(i)
        r = sess().post(f"{API}/passive/{i}/registrazione", json=reg_body(d))
        assert r.status_code == 200, r.text
        x = pdoc(i)
        assert x["stato_reg"] == "registrata" and x["ritenuta_importo"] == 200, x
        r = sess().post(f"{API}/passive/{i}/pagamenti", json={"data": "2026-09-10", "importo": x["netto"], "metodo": "bonifico"})
        assert r.status_code == 200, r.text

    def test_da_versare_past_deadline(self):
        j = sess().get(f"{API}/ritenute/da-versare").json()
        m = next(m for m in j["mesi"] if m["mese"] == MESE)
        print("da-versare:", m)
        assert m["importo"] == 200 and m["scadenza"] == "2026-10-16" and m["giorni"] < 0 and m["provvisorio"] is False

    def test_f24_pdf(self):
        r = sess().get(f"{API}/ritenute/{MESE}/f24")
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/pdf") and r.content[:4] == b"%PDF"

    def test_f24_bad_month(self):
        assert sess().get(f"{API}/ritenute/2026-13/f24").status_code in (404, 422)
        assert sess().get(f"{API}/ritenute/2025-01/f24").status_code == 400

    def test_versato_removes(self):
        if os.environ.get("T116_KEEP"):
            pytest.skip("kept for UI")
        r = sess().post(f"{API}/ritenute/{MESE}/versato", json={"data": "2026-10-15"})
        assert r.status_code == 200, r.text
        assert r.json()["versato"]["importo"] == 200
        assert not [m for m in sess().get(f"{API}/ritenute/da-versare").json()["mesi"] if m["mese"] == MESE]

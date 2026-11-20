# Iteration 115: RegistraPassivaDialog anteprima returns ritenuta_proposta from supplier anagrafica (privata / INPS / XML override / forfettario),
# proposal not suppressed when body has ritenuta values, registration saves ritenuta + netto.
# Run: pytest tests/test_iteration115_regpas_proposta_ritenuta.py -v -n 0   (T115_KEEP=1 keeps data for UI tests)
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import test_iteration114_ritenuta_anagrafica_bollo as b  # noqa: E402
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402

b.RUN = os.environ.get("T115_RUN", b.RUN)
b.TOK, b.UID = f"test_session_t115_admin_{b.RUN}", f"test-user-t115-admin-{b.RUN}"
b.PIVA = "12" + b.RUN + "115"
ST = b.ST
sess, upload, pdoc, mk_sup, piva, xml, reg_body, amt, entries = b.sess, b.upload, b.pdoc, b.mk_sup, b.piva, b.xml, b.reg_body, b.amt, b.entries


@pytest.fixture(scope="module", autouse=True)
def setup():
    b.clean()
    mongo(f'db.users.insertOne({{user_id:"{b.UID}", email:"test.user.t115.admin.{b.RUN}@example.com", name:"TEST_T115 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{b.UID}", session_token:"{b.TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": "TEST_T115 Srl", "partita_iva": b.PIVA, "codice_fiscale": b.PIVA, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    assert sess().put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                                   "corrispettivi": True, "contabilita": True}).status_code == 200
    sess().get(f"{API}/contabilita/conti")
    ST["p"] = sess().get(f"{API}/contabilita/parametri").json()["parametri"]
    yield
    if os.environ.get("T115_KEEP"):
        print("\nKEEP", b.RUN, ST["cid"], b.TOK, json.dumps({k: v for k, v in ST.items() if k != "p"}))
    else:
        b.clean()


def edit_party(pid, **kw):
    s = sess()
    cur = json.loads(mongo(f'print(JSON.stringify(db.parties.findOne({{id:"{pid}"}},{{_id:0}})))'))
    body = cur | kw
    r = s.put(f"{API}/parties/{pid}", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def anteprima(pid, **kw):
    d = pdoc(pid)
    r = sess().post(f"{API}/passive/{pid}/registrazione/anteprima", json=reg_body(d) | kw)
    assert r.status_code == 200, r.text
    return r.json()


def _party_id(pi):
    return json.loads(mongo(f'print(JSON.stringify(db.parties.findOne({{company_id:"{ST["cid"]}", partita_iva:"{pi}"}},{{_id:0,id:1}})))'))["id"]


class TestProposta:
    def test_privata_after_edit(self):
        pi = piva()
        sid = mk_sup("TEST_T115 Ing privata", pi, soggetto_ritenuta=False)
        d = upload(xml(pi, ((22.0, None, 1040.0, 228.8),), den="TEST_T115 Ing privata"))
        x = pdoc(d["id"])
        assert not x.get("ritenuta_importo"), x.get("ritenuta_importo")
        edit_party(sid, soggetto_ritenuta=True, ritenuta_aliquota=20, ritenuta_base=100, cassa_tipo="TC01", cassa_aliquota=4, cassa_ritenuta=False, ritenuta_tipo="RT01", ritenuta_causale="A")
        ST["inv_priv"], ST["sid_priv"] = d["id"], sid
        a = anteprima(d["id"])
        rp = a["ritenuta_proposta"]
        print("proposta privata:", rp)
        assert rp == {"aliquota": 20.0, "imponibile": 1000.0, "importo": 200.0, "cassa": 40.0, "cassa_in_base": False, "regime": "ordinario"}, rp

    def test_proposta_not_suppressed_with_body_values(self):
        p = ST["p"]
        a = anteprima(ST["inv_priv"], ritenuta_aliquota=20, ritenuta_imponibile=1000)
        assert a["ritenuta_proposta"] and a["ritenuta_proposta"]["importo"] == 200
        assert a["ritenuta_importo"] == 200 and round(a["netto"], 2) == round(1268.8 - 200, 2)
        assert amt(a["righe"], p["ritenute_operate"], "avere") == 200
        assert amt(a["righe"], p["fornitori"], "avere") == round(1268.8 - 200, 2), a["righe"]
        # body with different values: proposal still returned, anteprima uses body values
        a2 = anteprima(ST["inv_priv"], ritenuta_aliquota=10, ritenuta_imponibile=500)
        assert a2["ritenuta_proposta"]["importo"] == 200 and a2["ritenuta_importo"] == 50

    def test_registra_saves(self):
        p = ST["p"]
        d = pdoc(ST["inv_priv"])
        r = sess().post(f"{API}/passive/{ST['inv_priv']}/registrazione", json=reg_body(d) | {"ritenuta_aliquota": 20, "ritenuta_imponibile": 1000})
        assert r.status_code == 200, r.text
        x = pdoc(ST["inv_priv"])
        assert x["stato_reg"] == "registrata" and x["ritenuta_importo"] == 200 and x["ritenuta_imponibile"] == 1000 and round(x["netto"], 2) == 1068.8
        e = entries(ST["inv_priv"])
        assert len(e) == 1 and amt(e[0]["righe"], p["ritenute_operate"], "avere") == 200 and amt(e[0]["righe"], p["fornitori"], "avere") == 1068.8

    def test_inps_rivalsa(self):
        pi = piva()
        sid = mk_sup("TEST_T115 Prof INPS", pi, soggetto_ritenuta=False)
        d = upload(xml(pi, ((22.0, None, 1040.0, 228.8),), den="TEST_T115 Prof INPS"))
        edit_party(sid, soggetto_ritenuta=True, ritenuta_aliquota=20, ritenuta_base=100, cassa_tipo="TC22", cassa_aliquota=4, cassa_ritenuta=True, ritenuta_tipo="RT01", ritenuta_causale="A")
        ST["inv_inps"] = d["id"]
        rp = anteprima(d["id"])["ritenuta_proposta"]
        print("proposta INPS:", rp)
        assert rp["aliquota"] == 20 and rp["imponibile"] == 1040 and rp["importo"] == 208 and rp["cassa"] == 40 and rp["cassa_in_base"] is True

    def test_xml_diff_override(self):
        pi = piva()
        mk_sup("TEST_T115 XML diff", pi, cassa_tipo="TC01", cassa_aliquota=4, cassa_ritenuta=False)
        d = upload(xml(pi, ((22.0, None, 1040.0, 228.8),), rit=("RT01", 104.0, 10.0), den="TEST_T115 XML diff"))
        ST["inv_xml"] = d["id"]
        rp = anteprima(d["id"])["ritenuta_proposta"]
        print("proposta XML diff:", rp, "doc rit:", pdoc(d["id"]).get("ritenuta_importo"))
        assert rp["aliquota"] == 20 and rp["imponibile"] == 1000 and rp["importo"] == 200

    def test_forfettario(self):
        pi = piva()
        mk_sup("TEST_T115 Forfettario", pi, soggetto_ritenuta=False, regime_percipiente="forfettario")
        d = upload(xml(pi, ((0.0, "N2.2", 1040.0, 0.0),), rit=("RT01", 208.0, 20.0), den="TEST_T115 Forfettario"))
        ST["inv_forf"] = d["id"]
        rp = anteprima(d["id"])["ritenuta_proposta"]
        print("proposta forf:", rp)
        assert rp is not None and rp["aliquota"] == 0 and rp["importo"] == 0 and rp["regime"] == "forfettario"

    def test_manual_ritenuta_no_proposal(self):
        pi = piva()
        mk_sup("TEST_T115 Manuale", pi)
        d = upload(xml(pi, ((22.0, None, 1000.0, 220.0),), den="TEST_T115 Manuale"))
        assert sess().put(f"{API}/passive/{d['id']}/ritenuta", json={"aliquota": 10, "imponibile": 1000}).status_code == 200
        assert anteprima(d["id"])["ritenuta_proposta"] is None

    def test_non_soggetto_no_proposal(self):
        pi = piva()
        mk_sup("TEST_T115 Normale", pi, soggetto_ritenuta=False)
        d = upload(xml(pi, ((22.0, None, 1000.0, 220.0),), den="TEST_T115 Normale"))
        assert anteprima(d["id"])["ritenuta_proposta"] is None

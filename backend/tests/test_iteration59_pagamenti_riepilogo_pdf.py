# Iteration 59: Pagamenti fornitori - dashboard riepilogo (10 days window, overdue, manca_iban, isolation, 403 module/menu off)
# and distinta PDF (content, headers, 404 other company). Run: pytest tests/test_iteration59_pagamenti_riepilogo_pdf.py -v -n 0
# UI fixtures: T57_RUN=123456 python tests/test_iteration59_pagamenti_riepilogo_pdf.py setup|clean (same T57_RUN for both)
import io
import json
import sys
from datetime import date, timedelta

import pytest
from pypdf import PdfReader

import test_iteration57_pagamenti_fornitori as t57
from test_iteration57_pagamenti_fornitori import ST, API, mongo, sess, post_dist, IBAN1, IBAN_A

RUN = t57.RUN
T = date.today()
d = lambda n: (T + timedelta(days=n)).isoformat()  # noqa: E731
TOK_CO, UID_CO = f"test_session_t59_co_{RUN}", f"test-user-t59-co-{RUN}"


def pa(pid, party, num, scad, imp, nome):
    mongo(f'db.partite_aperte.insertOne({{id:"{pid}", company_id:"{ST["cid"]}", tipo:"fornitore", party_id:"{party}", numero:0, numero_display:"{num}",'
          f'data:"{d(-60)}", scadenza:"{scad}", totale:{imp}, netto:{imp}, rate:[{{scadenza:"{scad}", importo:{imp}}}], tipo_documento:"TD01", status:"storico",'
          f'stato_reg:"registrata", fornitore:{{denominazione:"{nome}"}}, created_at:new Date().toISOString()}})')


def setup_all():
    t57.setup_data()
    # overdue (A, -5) and in-window without IBAN (B, +3)
    ST["OV"], ST["NB"] = f"t59ov-{RUN}", f"t59nb-{RUN}"
    pa(ST["OV"], ST["forn_a"], "TEST_T59 OV-1", d(-5), 50, "TEST_T57 Fornitore A SpA")
    pa(ST["NB"], ST["forn_b"], "TEST_T59 NB-1", d(3), 20, "TEST_T57 Fornitore B Srl")
    mongo(f'db.users.insertOne({{user_id:"{UID_CO}", email:"test.user.t59.co.{RUN}@example.com", name:"TEST_T59 contabile", picture:"", role:"contabile", status:"approved",'
          f'company_ids:["{ST["cid"]}"], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID_CO}", session_token:"{TOK_CO}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    mongo(f'db.users.updateOne({{email:"fabrizio.gemignani@gmail.com"}}, {{$addToSet:{{company_ids:"{ST["cid"]}"}}}})')
    return {**ST, "tok": t57.TOK, "tok_op": t57.TOK_OP, "tok_co": TOK_CO}


def clean_all():
    t57.clean()
    mongo(f'db.users.deleteMany({{user_id:"{UID_CO}"}}); db.user_sessions.deleteMany({{user_id:"{UID_CO}"}});')


@pytest.fixture(scope="module", autouse=True)
def setup():
    setup_all()
    yield
    clean_all()


def riep(tok=t57.TOK, cid=None):
    return sess(tok, cid).get(f"{API}/pagamenti-fornitori/riepilogo")


# Riepilogo dashboard
class TestRiepilogo:
    def test_01_window(self):
        r = riep()
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["dal"] == T.isoformat() and j["al"] == d(10)
        keys = [x["key"] for x in j["in_scadenza"]]
        assert keys == [f"{ST['NB']}:1", f"{ST['A1']}:1", f"{ST['PA']}:1"], keys
        assert j["in_scadenza_totale"] == 420
        assert j["scadute_n"] == 1 and j["scadute_totale"] == 50
        x = {x["key"]: x for x in j["in_scadenza"]}
        assert x[f"{ST['NB']}:1"]["manca_iban"] is True and x[f"{ST['A1']}:1"]["manca_iban"] is False
        a1 = x[f"{ST['A1']}:1"]
        assert a1["numero_display"] and a1["scadenza"] == d(5) and a1["residuo"] == 300 and a1["fornitore"] == "TEST_T57 Fornitore A SpA"
        assert a1["rate_totali"] == 2 and a1["rata_n"] == 1
        assert "iban" not in a1

    def test_02_roles(self):
        assert riep(TOK_CO).status_code == 200
        assert riep(t57.TOK_OP).status_code == 200

    def test_03_isolation(self):
        j = riep(cid=ST["cid2"]).json()
        assert j["in_scadenza"] == [] and j["in_scadenza_totale"] == 0 and j["scadute_n"] == 0

    def test_04_module_menu_off(self):
        u = f"{API}/companies/{ST['cid']}/moduli"
        on = {"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True, "corrispettivi": True, "contabilita": True}
        sess().put(u, json={**on, "fatture_passive": False})
        try:
            assert riep().status_code == 403
        finally:
            sess().put(u, json=on)
        m = f"{API}/companies/{ST['cid']}/menu"
        assert sess().put(m, json={"off": ["pagamenti-fornitori"]}).status_code == 200
        try:
            assert riep().status_code == 403
        finally:
            sess().put(m, json={"off": []})
        assert riep().status_code == 200


# Distinta PDF
class TestPdf:
    def test_01_pdf_content(self):
        assert t57.put_banche(uno="AB12CD34").status_code == 200
        mongo(f'db.companies.updateOne({{id:"{ST["cid"]}", "banche.iban":"{IBAN1}"}}, {{$set:{{"banche.$.abi":"05428", "banche.$.cab":"11101"}}}})')
        r = post_dist([(f"{ST['A1']}:1", 300), (f"{ST['PA']}:1", 100)])
        assert r.status_code == 200, r.text
        ST["DP"] = r.json()["id"]
        p = sess().get(f"{API}/pagamenti-fornitori/distinte/{ST['DP']}/pdf")
        assert p.status_code == 200, p.text
        assert p.headers["content-type"].startswith("application/pdf") and p.content[:4] == b"%PDF"
        assert "inline" in p.headers.get("content-disposition", "") and "Distinta_bonifici_" in p.headers["content-disposition"]
        txt = "\n".join(pg.extract_text() for pg in PdfReader(io.BytesIO(p.content)).pages)
        ST["pdf_txt"] = txt
        for s in ("TEST_T57 Pagamenti", "DISTINTA DI BONIFICI", IBAN1, "ABI 05428", "CAB 11101", "CUC AB12CD34", "TEST Banca Uno",
                  "Disposizioni di bonifico", "TEST_T57 Fornitore A SpA", IBAN_A, "Saldo fatt.", "Totale 1 bonifici", "Dettaglio fatture pagate",
                  "TEST_T57 PA-1", "rata 1/2", "Timbro e firma", "400,00"):
            assert s in txt, (s, txt[:1500])

    def test_02_pdf_other_company(self):
        assert sess(cid=ST["cid2"]).get(f"{API}/pagamenti-fornitori/distinte/{ST['DP']}/pdf").status_code == 404
        assert sess().get(f"{API}/pagamenti-fornitori/distinte/nope/pdf").status_code == 404

    def test_03_riepilogo_after_payment(self):
        j = riep().json()
        assert [x["key"] for x in j["in_scadenza"]] == [f"{ST['NB']}:1"] and j["in_scadenza_totale"] == 20

    def test_04_annulla(self):
        assert sess().delete(f"{API}/pagamenti-fornitori/distinte/{ST['DP']}").status_code == 200
        assert riep().json()["in_scadenza_totale"] == 420


if __name__ == "__main__":
    if sys.argv[1] == "setup":
        print(json.dumps(setup_all()))
    else:
        clean_all()

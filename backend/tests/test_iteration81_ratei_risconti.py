# Iteration 81: Ratei e risconti - party flag, reg-veloce with rateo (acquisto/vendita), manual creation, quota by days, proposta,
# contabilizzazione simulata/definitiva (+storno 1/1), annulla, quick edit/delete blocks, prima nota blocks, bilancio/mastrino solo_definitive,
# chiusura blocked by provisional entries, registra passiva with rateo, delete reg-veloce doc with rateo.
# Run: pytest tests/test_iteration81_ratei_risconti.py -v -n 0   (T81_KEEP=1 keeps data; `python tests/<file> clean`)
import json
import os
import random
import sys

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402
from test_iteration13_reverse_charge import rc_xml  # noqa: E402

RUN = os.environ.get("T81_RUN") or str(random.randint(100000, 999999))
TOK, UID = "test_session_t81_admin", "test-user-t81-admin"
PIVA = "81" + RUN + "811"
ST = {}
COLLS = ["invoices", "passive_invoices", "parties", "articles", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "partite_aperte", "ratei_risconti", "coa_chiusure", "counters"]


def sess():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{denominazione:/^TEST_T81/}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def rr_entries(rid=None):
    q = {"company_id": ST["cid"], "origine": "ratei"}
    if rid:
        q["ref_id"] = {"$regex": "^" + rid}
    return json.loads(mongo(f'print(JSON.stringify(db.coa_entries.find({json.dumps(q)},{{_id:0}}).toArray()))') or "[]")


def side(e, conto):
    rows = [r for r in e["righe"] if r["conto"] == conto]
    return round(sum(r.get("dare") or 0 for r in rows), 2), round(sum(r.get("avere") or 0 for r in rows), 2)


def party(tipo, name, piva, **kw):
    r = sess().post(f"{API}/parties", json={"tipo": tipo, "denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "codice_destinatario": "ABC1234",
                                           "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT", **kw})
    assert r.status_code == 200, r.text
    return r.json()


def rv(**kw):
    b = {"tipo": "acquisto", "party_id": ST["F"], "numero": f"T81-{random.randint(1000, 99999)}", "data_documento": "2025-10-01", "data_registrazione": "2025-10-01",
         "scadenza": "", "righe": [{"aliquota": 22, "totale": 1464}]}
    return sess().post(f"{API}/reg-veloce", json=b | kw)


def lista(anno):
    r = sess().get(f"{API}/contabilita/ratei", params={"anno": anno})
    assert r.status_code == 200, r.text
    return {x["id"]: x for x in r.json()}


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t81.admin@example.com", name:"TEST_T81 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": f"TEST_T81 Ratei {RUN} Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    sess().put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                            "corrispettivi": True, "contabilita": True})
    sess().get(f"{API}/contabilita/conti")
    yield
    if os.environ.get("T81_KEEP"):
        print("\nKEEP", RUN, ST["cid"])
    else:
        clean()


# Party flag
class TestParty:
    def test_01_flag_fornitore_cliente(self):
        f = party("fornitore", "TEST_T81 Fornitore Affitti", "01234567890", ratei_risconti=True)
        assert f["ratei_risconti"] is True
        ST["F"] = f["id"]
        c = party("cliente", "TEST_T81 Cliente Canoni", "02345670481", ratei_risconti=True)
        assert c["ratei_risconti"] is True
        ST["C"] = c["id"]
        n = party("fornitore", "TEST_T81 Fornitore Normale", "09876543217")
        assert n.get("ratei_risconti") is False
        r = sess().put(f"{API}/parties/{n['id']}", json={**{k: v for k, v in n.items() if k not in ("id", "company_id", "created_at")}, "ratei_risconti": True})
        assert r.status_code == 200, r.text
        assert r.json()["ratei_risconti"] is True
        g = [p for p in sess().get(f"{API}/parties", params={"tipo": "fornitore"}).json() if p["id"] == n["id"]][0]
        assert g["ratei_risconti"] is True


# Proposta tipo
class TestProposta:
    @pytest.mark.parametrize("dr,dal,al,exp", [("2025-10-01", "2025-10-01", "2026-09-30", "risconto"), ("2026-02-10", "2025-11-01", "2026-01-31", "rateo"),
                                                ("2025-03-01", "2025-03-01", "2025-06-30", None)])
    def test_02_proposta(self, dr, dal, al, exp):
        r = sess().get(f"{API}/contabilita/ratei/proposta", params={"data_registrazione": dr, "competenza_dal": dal, "competenza_al": al})
        assert r.status_code == 200 and r.json()["tipo"] == exp


# Reg veloce + manual creation
class TestCreazione:
    def test_03_acquisto_risconto(self):
        r = rv(rateo={"competenza_dal": "2025-10-01", "competenza_al": "2026-09-30", "tipo": "risconto", "note": "TEST affitto"})
        assert r.status_code == 200, r.text
        ST["DOC_AR"] = r.json()["id"]
        rows = [x for x in lista(2025).values() if x["doc_id"] == ST["DOC_AR"]]
        assert len(rows) == 1
        x = rows[0]
        ST["AR"] = x["id"]
        assert x["origine"] == "acquisto" and x["tipo"] == "risconto" and x["nome_tipo"] == "Risconto attivo"
        assert x["importo"] == 1200 and len(x["righe"]) == 1
        ST["COSTO"] = x["righe"][0]["conto"]
        assert x["quota"]["giorni"] == 273 and x["quota"]["giorni_totali"] == 365 and x["quota"]["importo"] == 897.53
        assert x["stato"] == "da_contabilizzare" and x["anni"] == [2025]
        assert lista(2026)[ST["AR"]]["stato"] == "non_dovuto"

    def test_04_acquisto_rateo(self):
        r = rv(data_documento="2026-02-10", data_registrazione="2026-02-10", righe=[{"aliquota": 22, "totale": 1220}],
               rateo={"competenza_dal": "2025-11-01", "competenza_al": "2026-01-31", "tipo": "rateo"})
        assert r.status_code == 200, r.text
        ST["DOC_AP"] = r.json()["id"]
        x = [v for v in lista(2025).values() if v["doc_id"] == ST["DOC_AP"]][0]
        ST["AP"] = x["id"]
        assert x["nome_tipo"] == "Rateo passivo" and x["quota"]["giorni"] == 61 and x["quota"]["giorni_totali"] == 92
        assert x["quota"]["importo"] == round(1000 * 61 / 92, 2)

    def test_05_vendita_risconto(self):
        r = rv(tipo="vendita", party_id=ST["C"], data_documento="2025-12-01", data_registrazione="2025-12-01", righe=[{"aliquota": 22, "totale": 732}],
               rateo={"competenza_dal": "2025-12-01", "competenza_al": "2026-05-31", "tipo": "risconto"})
        assert r.status_code == 200, r.text
        ST["DOC_VR"] = r.json()["id"]
        x = [v for v in lista(2025).values() if v["doc_id"] == ST["DOC_VR"]][0]
        ST["VR"] = x["id"]
        ST["RICAVO"] = x["righe"][0]["conto"]
        assert x["nome_tipo"] == "Risconto passivo" and x["importo"] == 600
        assert x["quota"]["giorni"] == 151 and x["quota"]["importo"] == round(600 * 151 / 182, 2)

    def test_06_manual_vendita_rateo(self):
        b = {"origine": "vendita", "party_id": ST["C"], "documento": "TEST_T81-M1", "data_documento": "2026-01-15", "data_registrazione": "2026-01-15",
             "competenza_dal": "2025-07-01", "competenza_al": "2025-12-31", "tipo": "rateo", "righe": [{"conto": ST["RICAVO"], "importo": 500}]}
        r = sess().post(f"{API}/contabilita/ratei", json=b)
        assert r.status_code == 200, r.text
        ST["VP"] = r.json()["id"]
        x = lista(2025)[ST["VP"]]
        assert x["nome_tipo"] == "Rateo attivo" and x["quota"]["importo"] == 500
        bad = sess().post(f"{API}/contabilita/ratei", json=b | {"righe": [{"conto": ST["COSTO"], "importo": 100}]})
        assert bad.status_code == 422, bad.text
        bad = sess().post(f"{API}/contabilita/ratei", json=b | {"party_id": ST["F"]})
        assert bad.status_code == 422, bad.text
        bad = sess().post(f"{API}/contabilita/ratei", json=b | {"competenza_al": "2025-06-01"})
        assert bad.status_code == 422, bad.text


# Contabilizzazione
class TestContabilizza:
    def test_07_simulazione(self):
        r = sess().post(f"{API}/contabilita/ratei/contabilizza", json={"anno": 2025, "definitiva": False})
        assert r.status_code == 200, r.text
        assert r.json()["contabilizzati"] == 4 and not r.json()["errori"]
        es = rr_entries()
        assert len(es) == 8
        assert all(e["provvisoria"] is True and e["causale"] == "RR" for e in es)
        assert sorted({e["data"] for e in es}) == ["2025-12-31", "2026-01-01"]
        L = lista(2025)
        assert all(L[k]["stato"] == "simulata" for k in ("AR", "AP", "VR", "VP") for k in [ST[k]])

    @pytest.mark.parametrize("key,dare,avere,imp", [("AR", "07.01.002", "COSTO", 897.53), ("AP", "COSTO", "14.01.001", 663.04),
                                                   ("VR", "RICAVO", "14.01.002", 497.8), ("VP", "07.01.001", "RICAVO", 500)])
    def test_08_sides(self, key, dare, avere, imp):
        dare, avere = ST.get(dare, dare), ST.get(avere, avere)
        es = {e["data"]: e for e in rr_entries(ST[key])}
        c, s = es["2025-12-31"], es["2026-01-01"]
        assert side(c, dare) == (imp, 0) and side(c, avere) == (0, imp), c["righe"]
        assert side(s, dare) == (0, imp) and side(s, avere) == (imp, 0), s["righe"]

    def test_09_rerun_replaces(self):
        r = sess().post(f"{API}/contabilita/ratei/contabilizza", json={"anno": 2025, "definitiva": False})
        assert r.status_code == 200 and r.json()["contabilizzati"] == 4
        assert len(rr_entries()) == 8

    def test_10_prima_nota_blocks(self):
        e = rr_entries(ST["AR"])[0]
        L = sess().get(f"{API}/contabilita/registrazioni", params={"origine": "ratei"}).json()["registrazioni"]
        x = [v for v in L if v["id"] == e["id"]][0]
        assert x["eliminabile"] is False and x["provvisoria"] is True
        assert sess().delete(f"{API}/contabilita/registrazioni/{e['id']}").status_code == 400
        body = {"data": e["data"], "causale": "RR", "descrizione": "x", "righe": [{"conto": r["conto"], "dare": r["dare"], "avere": r["avere"]} for r in e["righe"]]}
        r = sess().put(f"{API}/contabilita/registrazioni/{e['id']}", json=body)
        assert r.status_code == 400, r.text

    def test_11_bilancio_solo_definitive(self):
        a = sess().get(f"{API}/contabilita/bilancio", params={"dal": "2025-01-01", "al": "2025-12-31"}).json()
        b = sess().get(f"{API}/contabilita/bilancio", params={"dal": "2025-01-01", "al": "2025-12-31", "solo_definitive": "true"}).json()
        assert a["provvisorie"] == 4 and b["provvisorie"] == 0
        ga = {x["codice"]: x for x in a["righe"]}
        gb = {x["codice"]: x for x in b["righe"]}
        assert ga["07.01.002"]["saldo"] == 897.53 and "07.01.002" not in gb
        m1 = sess().get(f"{API}/contabilita/mastrino", params={"conto": "07.01.002"}).json()
        m2 = sess().get(f"{API}/contabilita/mastrino", params={"conto": "07.01.002", "solo_definitive": "true"}).json()
        assert len(m1["movimenti"]) == 2 and len(m2["movimenti"]) == 0

    def test_12_chiusura_blocked(self):
        r = sess().get(f"{API}/contabilita/chiusura/2025")
        assert r.status_code == 200, r.text
        assert "simulazione" in (r.json().get("motivo") or ""), r.json().get("motivo")

    def test_13_edit_removes_simulated(self):
        r = sess().put(f"{API}/contabilita/ratei/{ST['VP']}", params={"anno": 2025},
                       json={"competenza_dal": "2025-10-01", "competenza_al": "2025-12-31", "tipo": "rateo", "note": "TEST edit"})
        assert r.status_code == 200, r.text
        assert r.json()["stato"] == "da_contabilizzare" and r.json()["note"] == "TEST edit"
        assert rr_entries(ST["VP"]) == []
        assert len(rr_entries()) == 6

    def test_14_definitiva_ids(self):
        r = sess().post(f"{API}/contabilita/ratei/contabilizza", json={"anno": 2025, "definitiva": True, "ids": [ST["AR"]]})
        assert r.status_code == 200 and r.json()["contabilizzati"] == 1
        es = rr_entries(ST["AR"])
        assert len(es) == 2 and all(e["provvisoria"] is False for e in es)
        assert lista(2025)[ST["AR"]]["stato"] == "definitiva"
        # simulation of all must not touch the definitive one
        sess().post(f"{API}/contabilita/ratei/contabilizza", json={"anno": 2025, "definitiva": False})
        assert {e["id"] for e in rr_entries(ST["AR"])} == {e["id"] for e in es}

    def test_15_blocks_on_definitiva(self):
        r = sess().put(f"{API}/contabilita/ratei/{ST['AR']}", params={"anno": 2025},
                       json={"competenza_dal": "2025-10-01", "competenza_al": "2026-06-30", "tipo": "risconto"})
        assert r.status_code == 400, r.text
        assert sess().delete(f"{API}/contabilita/ratei/{ST['AR']}").status_code == 400
        assert sess().delete(f"{API}/reg-veloce/acquisto/{ST['DOC_AR']}").status_code == 400

    def test_16_annulla_and_delete_doc(self):
        r = sess().post(f"{API}/contabilita/ratei/annulla", json={"anno": 2025, "ids": [ST["AR"]]})
        assert r.status_code == 200 and r.json()["annullati"] == 1
        assert rr_entries(ST["AR"]) == []
        r = sess().delete(f"{API}/reg-veloce/acquisto/{ST['DOC_AR']}")
        assert r.status_code == 200, r.text
        assert ST["AR"] not in lista(2025)

    def test_17_annulla_all(self):
        r = sess().post(f"{API}/contabilita/ratei/annulla", json={"anno": 2025})
        assert r.status_code == 200, r.text
        assert rr_entries() == []
        assert sess().get(f"{API}/contabilita/bilancio").json()["provvisorie"] == 0

    def test_18_delete_manual(self):
        assert sess().delete(f"{API}/contabilita/ratei/{ST['VP']}").status_code == 200
        assert ST["VP"] not in lista(2025)


# Registra fattura passiva (SDI) with rateo
class TestRegistraPassiva:
    def test_19_registra_with_rateo(self):
        x = rc_xml(f"T81-{RUN}", data="2025-09-01", rc=()).decode().replace("<IdCodice>01234567890</IdCodice>", f"<IdCodice>{PIVA}</IdCodice>")
        x = x.replace("<IdCodice>02345670481</IdCodice>", "<IdCodice>01234567890</IdCodice>")  # cedente = flagged fornitore
        r = sess().post(f"{API}/passive/upload", files=[("files", ("t81.xml", x.encode(), "application/octet-stream"))])
        assert r.status_code == 200, r.text
        pid = r.json()[0]["documenti"][0]["id"]
        ST["PID"] = pid
        d = sess().get(f"{API}/passive/{pid}").json()
        body = {"data_registrazione": "2025-09-05", "numero": d["numero"], "data": d["data"],
                "riepilogo": [{k: y.get(k) for k in ("aliquota", "natura", "imponibile", "imposta")} | {"conto": ""} for y in d["riepilogo"]]}
        a = sess().post(f"{API}/passive/{pid}/registrazione/anteprima", json=body)
        assert a.status_code == 200, a.text
        assert a.json()["ratei_risconti"] is True and a.json()["rateo_esistente"] is None
        r = sess().post(f"{API}/passive/{pid}/registrazione", json=body | {"rateo": {"competenza_dal": "2025-09-01", "competenza_al": "2026-08-31", "tipo": "risconto"}})
        assert r.status_code == 200, r.text
        rows = [v for v in lista(2025).values() if v["doc_id"] == pid]
        assert len(rows) == 1 and rows[0]["importo"] == round(sum(y["imponibile"] for y in d["riepilogo"]), 2)
        assert rows[0]["quota"]["giorni"] == 243
        a = sess().post(f"{API}/passive/{pid}/registrazione/anteprima", json=body)
        assert a.json()["rateo_esistente"]["tipo"] == "risconto"

    def test_20_unregister_leaves_rateo(self):
        # observational: un-registering a passive invoice (PATCH stato_reg) - does the rateo survive as orphan?
        r = sess().patch(f"{API}/passive/{ST['PID']}", json={"stato_reg": "da_registrare"})
        assert r.status_code == 200, r.text
        rows = [v for v in lista(2025).values() if v["doc_id"] == ST["PID"]]
        print("RATEO_AFTER_UNREGISTER", len(rows))
        assert len(rows) == 0, "rateo remains after passive invoice un-registration (orphan)"


if __name__ == "__main__" and sys.argv[-1] == "clean":
    clean()

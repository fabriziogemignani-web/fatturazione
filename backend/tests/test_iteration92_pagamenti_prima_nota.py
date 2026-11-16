# Iteration 92: payments on bank / card / cash accounts -> prima nota (origine 'pagamento'), conti-pagamento endpoint, 'carta' parameter,
# block payments before passive invoice registration (manual, distinta, saldaconto), delete sync payment <-> prima nota entry, incassi IN.
# Run: pytest tests/test_iteration92_pagamenti_prima_nota.py -v -n 0
import json
import os
import random
import sys
from datetime import date, timedelta

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo, party, inv  # noqa: E402
import test_iteration89_rigenera_passive as t89  # noqa: E402

RUN = str(random.randint(100000, 999999))
TOK, UID = "test_session_t92_admin", "test-user-t92-admin"
PIVA = "92" + RUN + "921"
ST = {}
COLLS = ["invoices", "passive_invoices", "parties", "articles", "payments", "passive_payments", "coa_accounts", "coa_causali", "coa_iva", "coa_entries",
         "sdi_events", "audit", "partite_aperte", "f24_versamenti", "pag_distinte", "ratei_risconti", "counters", "bank_tx", "bank_accounts"]
T = date.today()
D = lambda n: (T - timedelta(days=n)).isoformat()  # noqa: E731
IBAN = "IT60X0542811101000000123456"


def sess():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    if ST.get("cid"):
        s.headers["X-Company-Id"] = ST["cid"]
    return s


def clean():
    mongo(f'db.companies.find({{denominazione:/^TEST_T92/}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def upload(x):
    r = sess().post(f"{API}/passive/upload", files=[("files", (f"t92_{RUN}_{random.randint(1, 10**6)}.xml", x, "application/octet-stream"))])
    assert r.status_code == 200, r.text
    j = r.json()[0]
    assert j["ok"], j
    return j["documenti"][0]["id"]


def pxml(num, data, ced, imp=1000.0, td="TD01"):
    return t89.xml(num, data, ced, imp).replace(t89.PIVA.encode(), PIVA.encode()).replace(b"TEST_T89", b"TEST_T92").replace(b"<TipoDocumento>TD01", f"<TipoDocumento>{td}".encode())


def registra(pid, dr):
    r = sess().patch(f"{API}/passive/{pid}", json={"stato_reg": "registrata", "data_registrazione": dr})
    assert r.status_code == 200 and r.json()["stato_reg"] == "registrata", r.text


def entry(eid):
    return json.loads(mongo(f'print(JSON.stringify(db.coa_entries.findOne({{id:"{eid}", company_id:"{ST["cid"]}"}},{{_id:0}})))') or "null")


def side(e, conto):
    rows = [r for r in e["righe"] if r["conto"] == conto]
    return round(sum(r.get("dare") or 0 for r in rows), 2), round(sum(r.get("avere") or 0 for r in rows), 2)


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t92.admin@example.com", name:"TEST_T92 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": "TEST_T92 Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    ST["cid"] = r.json()["id"]
    sess().put(f"{API}/companies/{ST['cid']}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                            "corrispettivi": True, "contabilita": True})
    mongo(f'db.companies.updateOne({{id:"{ST["cid"]}"}}, {{$set:{{banche:[{{nome:"TEST_T92 Banca", iban:"{IBAN}", predefinita:true}}]}}}})')
    sess().get(f"{API}/contabilita/conti")
    yield
    if os.environ.get("T92_KEEP"):
        print("\nKEEP", RUN, ST["cid"], TOK)
    else:
        clean()


class TestPagamenti:
    def test_01_conti_pagamento(self):
        r = sess().get(f"{API}/contabilita/conti-pagamento")
        assert r.status_code == 200, r.text
        j = r.json()
        codes = {o["conto"]: o for o in j["conti"]}
        assert {"06.01.001", "06.02.001", "06.03.001"} <= set(codes), codes
        assert codes["06.02.001"]["tipo"] == "cassa" and codes["06.03.001"]["tipo"] == "carta" and codes["06.01.001"]["tipo"] == "banca"
        assert all({"conto", "label", "descrizione", "tipo"} <= set(o) for o in j["conti"])
        dft = j["default"]
        assert set(dft) == {"bonifico", "contanti", "carta", "assegno", "riba", "rid", "altro"}, dft
        assert dft["contanti"] == "06.02.001" and dft["carta"] == "06.03.001"
        assert all(dft[k] == "06.01.001" for k in ("bonifico", "assegno", "riba", "rid", "altro")), dft
        assert codes["06.01.001"]["label"].startswith("Banca TEST_T92")

    def test_02_parametri_carta(self):
        s = sess()
        pr = s.get(f"{API}/contabilita/parametri").json()
        ruoli = dict(pr["ruoli"])
        assert "carta" in ruoli and "Carta di credito" in ruoli["carta"], ruoli
        p = pr["parametri"]
        assert p["carta"] == "06.03.001"
        body = {"conti": {k: p[k] for k, _ in pr["ruoli"]}, "contropartita_vendite": p["contropartita_vendite"],
                "contropartita_acquisti": p["contropartita_acquisti"], "aliquota_rc": p["aliquota_rc"], "categorie": p["categorie"]}
        rr = s.put(f"{API}/contabilita/parametri", json=body)
        assert rr.status_code == 200, rr.text
        assert rr.json()["parametri"]["carta"] == "06.03.001"
        body["conti"]["carta"] = "06.01.001"
        rr = s.put(f"{API}/contabilita/parametri", json=body)
        assert rr.status_code == 200 and rr.json()["parametri"]["carta"] == "06.01.001", rr.text
        assert s.get(f"{API}/contabilita/parametri").json()["parametri"]["carta"] == "06.01.001"
        body["conti"]["carta"] = "06.03.001"
        assert s.put(f"{API}/contabilita/parametri", json=body).status_code == 200

    def test_03_unregistered_blocked(self):
        ST["A"] = upload(pxml("A-1", D(30), "01111111111"))
        r = sess().post(f"{API}/passive/{ST['A']}/pagamenti", json={"data": D(5), "importo": 100, "metodo": "bonifico"})
        assert r.status_code == 400 and "non è ancora registrata" in r.text, r.text

    def test_04_before_registration_blocked(self):
        registra(ST["A"], D(10))
        r = sess().post(f"{API}/passive/{ST['A']}/pagamenti", json={"data": D(15), "importo": 100, "metodo": "bonifico"})
        assert r.status_code == 400 and "registrazione" in r.text, r.text

    def test_05_bonifico_default(self):
        s = sess()
        r = s.post(f"{API}/passive/{ST['A']}/pagamenti", json={"data": D(5), "importo": 100, "metodo": "bonifico"})
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["conto"] == "06.01.001" and p.get("coge_entry_id") and p["coge_rif"].startswith("prima nota n."), p
        e = entry(p["coge_entry_id"])
        assert e["origine"] == "pagamento" and e["ref_id"] == p["id"] and e["causale"] == "PG", e
        assert side(e, "13.02.001") == (100, 0) and side(e, "06.01.001") == (0, 100)
        assert next(x for x in e["righe"] if x["conto"] == "13.02.001").get("party_id")
        lst = s.get(f"{API}/contabilita/registrazioni", params={"origine": "pagamento"}).json()
        rows = lst if isinstance(lst, list) else lst.get("rows") or lst.get("registrazioni") or lst.get("items") or []
        assert any(x["id"] == e["id"] for x in rows), str(lst)[:400]
        ST["pay_bon"] = p

    def test_06_carta_contanti(self):
        s = sess()
        r = s.post(f"{API}/passive/{ST['A']}/pagamenti", json={"data": D(5), "importo": 50, "metodo": "carta"})
        assert r.status_code == 200 and r.json()["conto"] == "06.03.001", r.text
        assert side(entry(r.json()["coge_entry_id"]), "06.03.001") == (0, 50)
        ST["pay_carta"] = r.json()
        r = s.post(f"{API}/passive/{ST['A']}/pagamenti", json={"data": D(5), "importo": 20, "metodo": "contanti"})
        assert r.status_code == 200 and r.json()["conto"] == "06.02.001", r.text
        assert side(entry(r.json()["coge_entry_id"]), "06.02.001") == (0, 20)
        # explicit conto override
        r = s.post(f"{API}/passive/{ST['A']}/pagamenti", json={"data": D(5), "importo": 10, "metodo": "bonifico", "conto": "06.03.001"})
        assert r.status_code == 200 and r.json()["conto"] == "06.03.001", r.text

    def test_07_invalid_conto(self):
        r = sess().post(f"{API}/passive/{ST['A']}/pagamenti", json={"data": D(5), "importo": 10, "metodo": "bonifico", "conto": "30.06.001"})
        assert r.status_code == 400 and "conto" in r.text, r.text
        pays = sess().get(f"{API}/passive/{ST['A']}/pagamenti").json()["pagamenti"]
        assert len(pays) == 4, pays

    def test_08_delete_payment_removes_entry(self):
        p = ST["pay_bon"]
        r = sess().delete(f"{API}/passive-pagamenti/{p['id']}")
        assert r.status_code == 200, r.text
        assert entry(p["coge_entry_id"]) is None

    def test_09_delete_entry_removes_payment(self):
        p = ST["pay_carta"]
        r = sess().delete(f"{API}/contabilita/registrazioni/{p['coge_entry_id']}")
        assert r.status_code == 200, r.text
        pays = sess().get(f"{API}/passive/{ST['A']}/pagamenti").json()["pagamenti"]
        assert all(x["id"] != p["id"] for x in pays), pays

    def test_10_compensazione_no_entry(self):
        nc = upload(pxml("NC-1", D(25), "01111111111", imp=100.0, td="TD04"))
        registra(nc, D(10))
        r = sess().post(f"{API}/passive/{ST['A']}/pagamenti", json={"data": D(5), "importo": 30, "metodo": "compensazione", "nc_id": nc})
        assert r.status_code == 200, r.text
        assert not r.json().get("coge_entry_id") and not r.json().get("conto"), r.json()
        n = mongo(f'print(db.coa_entries.countDocuments({{company_id:"{ST["cid"]}", origine:"pagamento", ref_id:"{r.json()["id"]}"}}))')
        assert n == "0"

    def test_11_incasso_attivo(self):
        s = sess()
        pid = s.post(f"{API}/parties", json=party("TEST_T92 Cliente", piva="01234567892", cf="01234567892"))
        assert pid.status_code == 200, pid.text
        pid = pid.json()["id"]
        r = s.post(f"{API}/invoices", json=inv(pid, data=D(20)))
        assert r.status_code == 200, r.text
        iid = r.json()["id"]
        assert s.post(f"{API}/invoices/{iid}/send").status_code == 200
        assert s.post(f"{API}/invoices/{iid}/refresh").json()["status"] == "consegnata"
        r = s.post(f"{API}/invoices/{iid}/pagamenti", json={"data": D(3), "importo": 200, "metodo": "bonifico"})
        assert r.status_code == 200, r.text
        p = r.json()
        e = entry(p["coge_entry_id"])
        assert e["causale"] == "IN" and side(e, "06.01.001") == (200, 0) and side(e, "05.01.001") == (0, 200), e
        r = s.post(f"{API}/invoices/{iid}/pagamenti", json={"data": D(3), "importo": 96, "metodo": "contanti", "ritenuta_subita": 4})
        assert r.status_code == 200, r.text
        e2 = entry(r.json()["coge_entry_id"])
        assert side(e2, "06.02.001") == (96, 0) and side(e2, "05.02.003") == (4, 0) and side(e2, "05.01.001") == (0, 100), e2
        r = s.delete(f"{API}/pagamenti/{p['id']}")
        assert r.status_code == 200, r.text
        assert entry(p["coge_entry_id"]) is None
        ST["iid"] = iid

    def test_12_distinta_rejects_unregistered(self):
        s = sess()
        B = upload(pxml("B-1", D(30), "02222222222"))
        ST["B"] = B
        sc = s.get(f"{API}/pagamenti-fornitori/scadenze").json()
        key = next(x["key"] for x in sc if x["invoice_id"] == B)
        r = s.post(f"{API}/pagamenti-fornitori/distinte", json={"banca_iban": IBAN, "data": D(2), "voci": [{"key": key, "importo": 100, "iban": IBAN}]})
        assert r.status_code == 400 and "non è ancora registrata" in r.text, r.text

    def test_13_saldaconto_rejects_unregistered(self):
        s = sess()
        party_id = s.get(f"{API}/passive/{ST['B']}").json()["party_id"]
        body = {"data": D(2), "causale": "PG", "descrizione": "TEST_T92 pagamento manuale",
                "righe": [{"conto": "13.02.001", "dare": 100, "party_id": party_id}, {"conto": "06.01.001", "avere": 100}],
                "saldaconto": [{"invoice_id": ST["B"], "importo": 100, "passivo": True}]}
        r = s.post(f"{API}/contabilita/registrazioni", json=body)
        assert r.status_code == 400 and "non è ancora registrata" in r.text, r.text
        # registered but date before registration
        registra(ST["B"], D(5))
        body["data"] = D(8)
        r = s.post(f"{API}/contabilita/registrazioni", json=body)
        assert r.status_code == 400 and "precedere la registrazione" in r.text, r.text
        body["data"] = D(2)
        r = s.post(f"{API}/contabilita/registrazioni", json=body)
        assert r.status_code == 200, r.text
        pays = s.get(f"{API}/passive/{ST['B']}/pagamenti").json()["pagamenti"]
        assert any(x.get("coge_entry_id") == r.json()["id"] for x in pays)


class TestEdge:
    # Editing an auto 'pagamento' entry from prima nota (no saldaconto in body) must not silently drop the linked payment
    def test_14_edit_auto_entry_keeps_payment(self):
        s = sess()
        r = s.post(f"{API}/passive/{ST['A']}/pagamenti", json={"data": D(4), "importo": 15, "metodo": "bonifico"})
        assert r.status_code == 200, r.text
        p = r.json()
        e = entry(p["coge_entry_id"])
        body = {"data": e["data"], "causale": e["causale"], "descrizione": e["descrizione"] + " mod",
                "righe": [{k: x.get(k) for k in ("conto", "dare", "avere", "party_id")} for x in e["righe"]]}
        r = s.put(f"{API}/contabilita/registrazioni/{e['id']}", json=body)
        print("PUT", r.status_code, r.text[:200])
        pays = s.get(f"{API}/passive/{ST['A']}/pagamenti").json()["pagamenti"]
        assert r.status_code == 400 or any(x.get("coge_entry_id") == e["id"] for x in pays), f"payment lost after edit: {r.status_code}"

    # Un-registering a passive invoice that already has prima-nota payments should be blocked (payment would precede registration)
    def test_15_unregister_with_payments(self):
        r = sess().patch(f"{API}/passive/{ST['A']}", json={"stato_reg": "da_registrare"})
        print("UNREG", r.status_code, r.text[:200])
        assert r.status_code == 400, r.text

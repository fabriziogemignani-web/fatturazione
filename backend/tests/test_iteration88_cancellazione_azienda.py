# Iteration 88: company data deletion (parziale / totale) + gzip backup. Only touches TEST_T88 companies created here.
# Run: pytest tests/test_iteration88_cancellazione_azienda.py -v -n 0   (T88_KEEP=1 keeps companies for UI tests)
import gzip
import json
import os
import random
import sys

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo, TODAY  # noqa: E402

RUN = str(random.randint(100000, 999999))
TOK, UID = "test_session_t88_admin", "test-user-t88-admin"
TOK_OP, UID_OP = "test_session_t88_op", "test-user-t88-op"
ST = {}
MOV = ["passive_invoices", "payments", "passive_payments", "ddts", "bem", "orders", "ordini_produzione", "stock_moves", "coa_entries",
       "corrispettivi", "partite_aperte", "riba_distinte", "riba_effetti", "pag_distinte", "f24_versamenti", "ratei_risconti", "bank_tx", "solleciti",
       "arch_invoices", "import_batches", "export_log", "com_log"]
KEEP = ["distinte", "centri_lavoro", "coa_accounts", "coa_causali", "coa_iva", "bank_accounts"]
ANAG = ["intenti", "arch_anagrafiche"]
ALL = MOV + KEEP + ANAG + ["invoices", "parties", "articles", "cons_docs", "bank_rules"]


def sess(tok=TOK, cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    if cid:
        s.headers["X-Company-Id"] = cid
    return s


def count(coll, cid):
    return int(mongo(f'print(db.{coll}.countDocuments({{company_id:"{cid}"}}))') or 0)


def clean():
    mongo(f'db.companies.find({{denominazione:/^TEST_T88/}}).forEach(c=>{{{json.dumps(ALL)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:["{UID}","{UID_OP}"]}}}}); db.user_sessions.deleteMany({{user_id:{{$in:["{UID}","{UID_OP}"]}}}});')


def mk_company(tag, piva):
    r = sess().post(f"{API}/companies", json={"denominazione": f"TEST_T88 {tag} {RUN} Srl", "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    sess().put(f"{API}/companies/{cid}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                      "corrispettivi": True, "contabilita": True})
    return cid, r.json()["denominazione"]


def seed(cid):
    s = sess(cid=cid)
    r = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": f"TEST_T88 Cliente {cid[:6]}", "partita_iva": "01234567890", "codice_fiscale": "01234567890",
                                       "codice_destinatario": "ABC1234", "indirizzo": "Via A 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    for _ in range(2):
        r = s.post(f"{API}/invoices", json={"tipo_documento": "TD01", "data": TODAY, "party_id": pid, "modalita_pagamento": "MP05",
                                            "lines": [{"descrizione": "Servizio", "quantita": 1, "prezzo_unitario": 100, "aliquota": 22}]})
        assert r.status_code == 200, r.text
    docs = ",".join(f'db.{c}.insertOne({{id:"t88-{c}-{cid}", company_id:"{cid}", note:"TEST_T88"}})' for c in MOV + KEEP + ANAG + ["cons_docs", "bank_rules"])
    mongo(docs + f';db.articles.insertOne({{id:"t88-art-{cid}", company_id:"{cid}", codice:"TEST_T88A", descrizione:"TEST_T88 art", giacenza:15, impegnato:3, ordinato:4, disponibilita:16}});'
          f'db.companies.updateOne({{id:"{cid}"}},{{$set:{{coge_chiusi:[2024], smtp:{{host:"x", password_enc:"SECRET_SMTP"}}, ftp_backup:{{host:"ftp", password_enc:"SECRET_FTP"}}, conservazione:{{email:"c@x.it", password_enc:"SECRET_CONS"}}}}}})')
    return pid


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t88.admin@example.com", name:"TEST_T88 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    ST["a"], ST["a_name"] = mk_company("Alfa", "88" + RUN + "881")
    ST["b"], ST["b_name"] = mk_company("Beta", "88" + RUN + "882")
    ST["c"], ST["c_name"] = mk_company("Gamma", "88" + RUN + "883")
    for k in ("a", "b", "c"):
        ST["pid_" + k] = seed(ST[k])
    mongo(f'db.users.insertOne({{user_id:"{UID_OP}", email:"test.user.t88.op@example.com", name:"TEST_T88 op", picture:"", role:"operatore", status:"approved", company_ids:["{ST["a"]}","{ST["c"]}"], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID_OP}", session_token:"{TOK_OP}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    yield
    if not os.environ.get("T88_KEEP"):
        clean()


# --- backup
def test_backup_non_admin_403():
    assert sess(TOK_OP, ST["a"]).get(f"{API}/azienda/backup").status_code == 403
    assert sess(TOK_OP, ST["a"]).post(f"{API}/azienda/cancella", json={"modo": "parziale", "conferma": ST["a_name"]}).status_code == 403


def test_backup_content():
    r = sess(cid=ST["a"]).get(f"{API}/azienda/backup")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/gzip")
    assert ".json.gz" in r.headers.get("content-disposition", "")
    d = json.loads(gzip.decompress(r.content))
    assert d["azienda"]["id"] == ST["a"]
    for c in ["invoices", "parties", "articles", "coa_entries", "distinte"]:
        assert c in d["dati"], c
        assert all(x["company_id"] == ST["a"] for x in d["dati"][c])
    assert len(d["dati"]["invoices"]) == 2
    ST["backup_raw"] = r.content.decode("latin1")


def test_backup_no_smtp_secret():
    d = json.loads(gzip.decompress(sess(cid=ST["a"]).get(f"{API}/azienda/backup").content))
    assert "password_enc" not in (d["azienda"].get("smtp") or {})


def test_backup_no_other_encrypted_secrets():
    raw = gzip.decompress(sess(cid=ST["a"]).get(f"{API}/azienda/backup").content).decode()
    leaked = [s for s in ("SECRET_FTP", "SECRET_CONS", "SECRET_SMTP") if s in raw]
    assert not leaked, f"encrypted secrets in backup: {leaked}"


# --- parziale
def test_wrong_conferma_400():
    r = sess(cid=ST["a"]).post(f"{API}/azienda/cancella", json={"modo": "parziale", "conferma": "sbagliato"})
    assert r.status_code == 400
    assert count("invoices", ST["a"]) == 2


def test_invalid_modo_422():
    assert sess(cid=ST["a"]).post(f"{API}/azienda/cancella", json={"modo": "x", "conferma": ST["a_name"]}).status_code == 422


def test_parziale_without_anagrafiche():
    a = ST["a"]
    r = sess(cid=a).post(f"{API}/azienda/cancella", json={"modo": "parziale", "anagrafiche": False, "conferma": "  " + ST["a_name"].upper() + " "})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["modo"] == "parziale" and j["cancellati"]["invoices"] == 2
    for c in MOV + ["invoices"]:
        assert count(c, a) == 0, c
    for c in KEEP + ANAG + ["parties", "articles"]:
        assert count(c, a) >= 1, c
    art = json.loads(mongo(f'print(JSON.stringify(db.articles.findOne({{id:"t88-art-{a}"}},{{_id:0}})))'))
    assert art["giacenza"] == 0 and art["impegnato"] == 0 and art["ordinato"] == 0 and art["disponibilita"] == 0
    assert art["codice"] == "TEST_T88A"
    comp = json.loads(mongo(f'print(JSON.stringify(db.companies.findOne({{id:"{a}"}},{{_id:0}})))'))
    assert "coge_chiusi" not in comp and comp["denominazione"] == ST["a_name"]
    # other companies untouched
    assert count("invoices", ST["b"]) == 2 and count("coa_entries", ST["b"]) == 1


def test_parziale_numbering_restarts():
    r = sess(cid=ST["a"]).post(f"{API}/invoices", json={"tipo_documento": "TD01", "data": TODAY, "party_id": ST["pid_a"], "modalita_pagamento": "MP05",
                                                       "lines": [{"descrizione": "Servizio", "quantita": 1, "prezzo_unitario": 100, "aliquota": 22}]})
    assert r.status_code == 200, r.text
    assert r.json()["numero"] == 1


def test_parziale_with_anagrafiche():
    c = ST["c"]
    r = sess(cid=c).post(f"{API}/azienda/cancella", json={"modo": "parziale", "anagrafiche": True, "conferma": ST["c_name"].lower()})
    assert r.status_code == 200, r.text
    for k in ANAG + ["parties", "invoices"] + MOV:
        assert count(k, c) == 0, k
    for k in KEEP + ["articles"]:
        assert count(k, c) >= 1, k
    assert count("parties", ST["b"]) == 1


def test_users_unchanged_after_parziale():
    u = json.loads(mongo(f'print(JSON.stringify(db.users.findOne({{user_id:"{UID_OP}"}},{{_id:0,company_ids:1}})))'))
    assert ST["a"] in u["company_ids"] and ST["c"] in u["company_ids"]


# --- totale
def test_totale_wrong_conferma():
    assert sess(cid=ST["c"]).post(f"{API}/azienda/cancella", json={"modo": "totale", "conferma": ST["b_name"]}).status_code == 400


def test_totale():
    c = ST["c"]
    r = sess(cid=c).post(f"{API}/azienda/cancella", json={"modo": "totale", "conferma": ST["c_name"]})
    assert r.status_code == 200, r.text
    assert r.json()["modo"] == "totale"
    for k in ALL:
        assert count(k, c) == 0, k
    assert mongo(f'print(db.companies.countDocuments({{id:"{c}"}}))') == "0"
    u = json.loads(mongo(f'print(JSON.stringify(db.users.findOne({{user_id:"{UID_OP}"}},{{_id:0,company_ids:1}})))'))
    assert c not in u["company_ids"] and ST["a"] in u["company_ids"]
    assert sess(TOK_OP, c).get(f"{API}/company").status_code == 404
    # other companies intact
    assert count("invoices", ST["b"]) == 2 and count("articles", ST["b"]) == 1 and count("distinte", ST["b"]) == 1
    assert mongo(f'print(db.companies.countDocuments({{id:"{ST["b"]}"}}))') == "1"

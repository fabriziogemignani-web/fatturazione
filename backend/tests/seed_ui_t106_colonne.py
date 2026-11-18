# Iteration 106 UI seed: TEST_T106 company with clients, invoices (incl. TD04), passive XMLs, prima nota (rigenera).
# Usage: python seed_ui_t106_colonne.py setup | clean
import json
import os
import sys
from datetime import date

import requests

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402
import test_iteration101_ai_registrazione_consulente as t101  # noqa: E402

TOK, UID = "test_session_t106_admin", "test-user-t106-admin"
PIVA = "10106106101"
Y = date.today().year
COLLS = t101.COLLS


def sess(cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    s.headers["X-Requested-With"] = "invoix"
    if cid:
        s.headers["X-Company-Id"] = cid
    return s


def clean():
    mongo(f'db.companies.find({{denominazione:/^TEST_T106/}}).forEach(c=>{{{json.dumps(COLLS)}.forEach(k=>db[k].deleteMany({{company_id:c.id}}));'
          f'db.counters.deleteMany({{key:{{$regex:c.id}}}}); db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


def setup():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t106.admin@example.com", name:"TEST_T106 admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+864e5*3), created_at:new Date().toISOString()}});')
    r = sess().post(f"{API}/companies", json={"denominazione": "TEST_T106 Colonne Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                              "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    s = sess(cid)
    print("moduli", s.put(f"{API}/companies/{cid}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True,
                                                                  "corrispettivi": True, "contabilita": True}).status_code)
    pids = {}
    for n in ["TEST_T106 Alfa Spa", "TEST_T106 Beta Srl", "TEST_T106 Gamma Snc"]:
        r = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": n, "partita_iva": "01234567897", "codice_fiscale": "01234567897",
                                           "codice_destinatario": "ABC1234", "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"})
        print("party", n, r.status_code, r.text[:150])
        pids[n] = r.json()["id"]
    invs = [("TEST_T106 Alfa Spa", f"{Y}-01-05", 1000, "TD01"), ("TEST_T106 Beta Srl", f"{Y}-01-08", 90, "TD01"),
            ("TEST_T106 Gamma Snc", f"{Y}-01-12", 5000, "TD01"), ("TEST_T106 Beta Srl", f"{Y}-01-20", 250, "TD01"),
            ("TEST_T106 Alfa Spa", f"{Y}-01-25", 2000, "TD04")]
    for n, d, p, td in invs:
        r = s.post(f"{API}/invoices", json={"tipo_documento": td, "data": d, "party_id": pids[n], "modalita_pagamento": "MP05",
                                            "lines": [{"descrizione": "Servizio TEST", "quantita": 1, "prezzo_unitario": p, "aliquota": 22}]})
        print("inv", n, td, r.status_code, r.text[:120] if r.status_code != 200 else r.json().get("numero_display"))
    # passive
    t101.ST["cid"] = cid
    t101.TOK = TOK
    t101.PIVA = PIVA
    def up(x):
        r = s.post(f"{API}/passive/upload", files=[("files", (f"t106_{os.urandom(3).hex()}.xml", x, "application/octet-stream"))])
        print("upload", r.status_code, r.text[:200])
    up(t101.xml("EN-1", f"{Y}-01-10", "06655971007", "TEST_T106 Energia SpA", [("Energia", 350.0)]))
    up(t101.xml("CA-3", f"{Y}-01-12", "01234567897", "TEST_T106 Cancelleria Srl", [("Carta", 80.0)]))
    up(t101.xml("ZZ-9", f"{Y}-01-03", "00488410010", "TEST_T106 Telefonia Spa", [("Telefono", 1200.0)]))
    # contabilita
    assert s.get(f"{API}/contabilita/conti").status_code == 200
    pr = s.get(f"{API}/contabilita/parametri").json()
    p = pr["parametri"]
    body = {"conti": {k: p[k] for k, _ in pr["ruoli"]}, "contropartita_vendite": p["contropartita_vendite"],
            "contropartita_acquisti": p["contropartita_acquisti"], "aliquota_rc": 22, "categorie": p["categorie"]}
    print("parametri", s.put(f"{API}/contabilita/parametri", json=body).status_code)
    r = s.post(f"{API}/contabilita/rigenera", json={"ricrea": False})
    print("rigenera", r.status_code, r.text[:300])
    r = s.get(f"{API}/contabilita/registrazioni", params={"dal": f"{Y}-01-01", "al": f"{Y}-12-31"})
    print("regs", r.status_code, len(r.json().get("registrazioni", [])), r.json().get("dare"))
    print("CID", cid)


if __name__ == "__main__":
    setup() if sys.argv[1] == "setup" else clean()

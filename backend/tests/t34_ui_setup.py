# Helper for iteration 34 UI test: `python t34_ui_setup.py setup` prints company id; `python t34_ui_setup.py clean <cid>`
import sys
import requests
import test_iteration34_scadenze_fiscali as T

if sys.argv[1] == "setup":
    T.user(T.UID, T.TOK, "admin", "[]")
    r = T.sess().post(f"{T.API}/companies", json={"denominazione": "TEST_T34 UI Srl", "partita_iva": T.PIVA, "codice_fiscale": T.PIVA, "regime_fiscale": "RF01",
                                                  "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    T.ST["cid"] = cid
    T.inv(cid, "2026-09-10", 220, 1)
    T.inv(cid, "2026-10-10", 1100, 2)
    s = T.sess()
    r = s.post(f"{T.API}/passive/upload", files=[("files", ("rit.xml", T.variant("T34UI-1", ritenuta=94.25, data="2026-09-30"), "application/octet-stream"))])
    pid = r.json()[0]["documenti"][0]["id"]
    netto = s.get(f"{T.API}/passive/{pid}").json()["netto"]
    assert s.post(f"{T.API}/passive/{pid}/pagamenti", json={"data": "2026-10-20", "importo": netto, "metodo": "bonifico"}).status_code == 200
    T.mongo(f'db.users.deleteMany({{user_id:"{T.UID}"}}); db.user_sessions.deleteMany({{user_id:"{T.UID}"}});')
    print(cid)
else:
    T.ST["cid"] = sys.argv[2]
    T.clean()
    print("cleaned")

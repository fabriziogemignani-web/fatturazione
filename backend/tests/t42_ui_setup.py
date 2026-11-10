# Helper for iteration 42 UI test (diritti + ritenute): `python t42_ui_setup.py setup` | `python t42_ui_setup.py clean`
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import test_iteration42_diritti_ritenute as T  # noqa: E402

if sys.argv[1] == "setup":
    T.clean()
    for k, (uid, tok) in T.U.items():
        T.mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.{uid}@example.com", name:"TEST_{k}", picture:"", role:"{T.ROLE[k]}", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
                f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    r = T.sess("admin").post(f"{T.API}/companies", json={"denominazione": "TEST_T42 UI Srl", "partita_iva": T.PA, "codice_fiscale": T.PA, "regime_fiscale": "RF01",
                                                         "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT",
                                                         "banche": [{"nome": "Banca A", "iban": "IT60X0542811101000000123456", "predefinita": True}]})
    assert r.status_code == 200, r.text
    T.S["cid"] = cid = r.json()["id"]
    T.mongo(f'db.users.updateMany({{user_id:{{$in:["{T.U["op"][0]}","{T.U["opban"][0]}","{T.U["optab"][0]}"]}}}}, {{$set:{{company_ids:["{cid}"]}}}});')
    T.put_dir("opban", banche=True)
    T.put_dir("optab", tabelle_contabili=True, testi_comunicazioni=True)
    s = T.sess("admin")
    f = s.post(f"{T.API}/parties", json={"tipo": "fornitore", "denominazione": "TEST_T42 Studio Legale", "partita_iva": "02345670481", "codice_fiscale": "",
                                         "indirizzo": "Via Y 1", "cap": "50100", "comune": "Firenze", "provincia": "FI", "nazione": "IT",
                                         "soggetto_ritenuta": True, "ritenuta_tipo": "RT01", "ritenuta_aliquota": 20, "ritenuta_base": 100, "ritenuta_causale": "A"})
    xml = T.FIX.replace("<IdCodice>01234567890</IdCodice>", f"<IdCodice>{T.PA}</IdCodice>").replace("<Numero>5674/2026</Numero>", "<Numero>TEST42UI-1</Numero>") \
        .replace("<Data>2026-10-30</Data>", f"<Data>{T.PM.replace(day=5).isoformat()}</Data>")
    pid = s.post(f"{T.API}/passive/upload", files=[("files", ("p.xml", xml, "text/xml"))]).json()[0]["documenti"][0]["id"]
    s.post(f"{T.API}/passive/{pid}/pagamenti", json={"data": T.PM.replace(day=20).isoformat(), "importo": 480.68})
    print(json.dumps({"cid": cid, "pid": pid, "forn": f.json()["id"], "ym": T.YM, "tokens": {k: v[1] for k, v in T.U.items()}}))
else:
    T.clean()
    print("cleaned")

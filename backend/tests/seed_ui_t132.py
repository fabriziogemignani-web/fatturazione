# Seeds TEST_T132 UI data (user session, company, suppliers with codice_iva, passive XML invoice). --clean removes it by stored ids.
import json
import sys

import test_iteration132_codici_iva_detraibilita as t

STATE = "/tmp/t132_ui.json"
if len(sys.argv) > 1 and sys.argv[1] == "--clean":
    s = json.load(open(STATE))
    t.ST["cid"], t.UID = s["cid"], s["uid"]
    t.clean()
    print("cleaned", s["cid"])
    sys.exit(0)
t.mongo(f'db.users.insertOne({{user_id:"{t.UID}", email:"test.user.t132ui.{t.RUN}@example.com", name:"TEST_T132 UI", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
        f'db.user_sessions.insertOne({{user_id:"{t.UID}", session_token:"{t.TOK}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
r = t.sess().post(f"{t.API}/companies", json={"denominazione": f"{t.TAG} UI Srl", "partita_iva": t.PIVA, "codice_fiscale": t.PIVA, "regime_fiscale": "RF01",
                                            "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
t.ST["cid"] = r.json()["id"]
json.dump({"cid": t.ST["cid"], "uid": t.UID, "tok": t.TOK}, open(STATE, "w"))
s = t.sess()
f1 = s.post(f"{t.API}/parties", json=t.sup("Auto UI", "02345670481", codice_iva="22D40", aliquota_rc=10)).json()
f2 = s.post(f"{t.API}/parties", json=t.sup("RC10 UI", "00743110157")).json()
up = s.post(f"{t.API}/passive/upload", files=[("files", ("p.xml", t.xml(f"T132UI-{t.RUN}", "02345670481"), "text/xml"))]).json()
print(json.dumps({"cid": t.ST["cid"], "tok": t.TOK, "f1": f1["id"], "f2": f2["id"], "pas": up[0]["documenti"][0]["id"]}))

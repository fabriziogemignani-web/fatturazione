# UI setup for iteration 128 (cespiti + learning). Usage: python tests/ui_setup_t128.py setup | clean <cid>
import json
import sys

sys.path.insert(0, "/app/backend/tests")
import conftest  # noqa: E402,F401  (adds X-Requested-With header)
import test_iteration128_ai_learning_cespiti as t  # noqa: E402

if sys.argv[1] == "setup":
    t.do_setup()
    cid = t.ST["cid"]
    pid = t.upload(t.xml("UI-1", [("Notebook Dell", 900.0)]))
    party = t.q(f'db.passive_invoices.findOne({{id:"{pid}"}},{{_id:0,party_id:1}})')["party_id"]
    t.mongo(f'db.ai_regole_conti.insertOne({{company_id:"{cid}", party_id:"{party}", chiave:"notebook dell", conto:"02.04.002", conto_ia:"30.06.001", corretto:true, descrizione:"Notebook Dell", n:1, updated_at:new Date().toISOString()}})')
    r = t.sess().post(f"{t.API}/cespiti", json={"descrizione": "TEST_PC ufficio", "categoria": "macchine_ufficio", "data_acquisto": "2025-07-01", "costo": 1000, "aliquota": 20})
    print(json.dumps({"cid": cid, "pid": pid, "cespite": r.json()["id"], "tok": t.TOK}))
else:
    t.ST["cids"] = [sys.argv[2]]
    t.clean()
    print("cleaned")

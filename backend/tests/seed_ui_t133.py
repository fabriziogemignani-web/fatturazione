# UI seed for iteration 133 on top of T133_KEEP data: restore model 60/40, upload invoice D of same supplier (model applies), supplier 22D40 exists.
# Usage: python seed_ui_t133.py <cid> <token>
import sys
import requests
import test_iteration133_modelli_prorata as t

cid, tok = sys.argv[1], sys.argv[2]
t.ST["cid"] = cid
t.TOK = tok
t.PIVA = t.mq(f'db.companies.findOne({{id:"{cid}"}},{{_id:0,partita_iva:1}})')["partita_iva"]
s = t.sess()
m = s.get(f"{t.API}/ai/modelli").json()[0]
g = m["righe"][0]
r = s.put(f"{t.API}/ai/modelli/{m['id']}", json={"attivo": True, "righe": [{**g, "conti": [{"conto": "30.06.001", "quota": 60}, {"conto": "30.06.002", "quota": 40}]}]})
print("restore", r.status_code)
pid = t.upload(t.xml("M133-UI", [("Fornitura materiale vario", 500.0)]))
print("UI_INVOICE", pid, "MODEL", m["id"])

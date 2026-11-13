# UI setup for iteration 72: adds 3 fresh maturato Ri.Ba. effects to the kept TEST_T72 company (run after T72_KEEP=1 pytest).
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import test_iteration72_riba_insoluti_blocco_bilancio as t  # noqa: E402

cid = t.mongo('print(db.companies.findOne({denominazione:/^TEST_T72/}).id)')
t.ST["cid"] = cid
pa = t.mongo(f'print(db.parties.findOne({{company_id:"{cid}", denominazione:"TEST_T72 Cliente A Srl"}}).id)')
pb = t.mongo(f'print(db.parties.findOne({{company_id:"{cid}", denominazione:"TEST_T72 Cliente B Srl"}}).id)')
i1 = t.inv(pa, t.d(-44), [(t.d(-12), 122)])
i2 = t.inv(pb, t.d(-44), [(t.d(-8), 122)])
i3 = t.inv(pb, t.d(-44), [(t.d(-25), 122)])
r = t.sess().post(f"{t.API}/riba/distinte", json={"banca_iban": t.IBAN, "data": t.d(-40), "effetti": [f"{i1}:1", f"{i2}:1", f"{i3}:1"]})
print(r.status_code, r.text[:200])
print(json.dumps({"cid": cid, "scaduti": [(x["id"], x["numero_display"], x["scadenza"]) for x in t.sess().get(f"{t.API}/riba/scaduti").json()]}))

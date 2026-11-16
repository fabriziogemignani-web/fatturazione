# UI setup for iteration 87: run after `T87_KEEP=1 pytest tests/test_iteration87_condominio_bonus.py -n 0`; prints ids for Playwright.
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402
import test_iteration87_condominio_bonus as t  # noqa: E402

cid = mongo('const c=db.companies.findOne({denominazione:/^TEST_T87/}); print(c?c.id:"")')
pid = mongo(f'const p=db.parties.findOne({{company_id:"{cid}", condominio:true}}); print(p?p.id:"")')
t.ST["cid"] = cid
mongo(f'db.users.updateOne({{user_id:"{t.UID}"}},{{$addToSet:{{company_ids:"{cid}"}}}})')
a = t.sent(t.inv(pid, price=1000))
b = t.sent(t.inv(pid, price=2000))
r = t.sess().post(f"{API}/invoices", json=t.inv(pid, bonus_edilizio="casa"))
print(json.dumps({"cid": cid, "pid": pid, "pay_iid": a, "inc_iid": b, "bonus_iid": r.json()["id"], "token": t.TOK}))

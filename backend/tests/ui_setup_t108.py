import sys, os
sys.path.insert(0, "/app/backend/tests")
os.environ["T108_KEEP"] = "1"
import test_iteration108_integrita as t
from test_iteration7_pa_scartate_registro import API, party, inv
g = t.setup.__wrapped__()
next(g)
s = t.sess()
pid = s.post(f"{API}/parties", json=party("TEST_T108 UI Cliente", piva="01234567892", cf="01234567892")).json()["id"]
s.post(f"{API}/contabilita/registrazioni", json=t.reg_body(t.D(5)))
iid = s.post(f"{API}/invoices", json=inv(pid, data=t.D(20))).json()["id"]
print("CID", t.ST["cid"], "TOK", t.TOK, "PID", pid, "RUN", t.RUN, "PIVA", t.PIVA, "UID", t.UID, t.UID2)

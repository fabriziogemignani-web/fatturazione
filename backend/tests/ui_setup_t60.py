# UI fixtures for iteration 60 (bollo + bilancio). Usage: T60_RUN=<6 digits> python tests/ui_setup_t60.py setup|clean
import json
import sys

import test_iteration60_bollo_bilancio as t
from test_iteration60_bollo_bilancio import ST, API, sess, inv, ln, T

if sys.argv[1] == "setup":
    t.setup_data()
    a = inv(ST["c_si"], [ln("TEST_UI esente", 100)]).json()
    sess().post(f"{API}/invoices/{a['id']}/send")
    sess().post(f"{API}/invoices/{a['id']}/refresh")
    b = inv(ST["c_no"], [ln("TEST_UI esente B", 90, natura="N4")]).json()
    sess().post(f"{API}/invoices/{b['id']}/send")
    r = sess().post(f"{API}/contabilita/registrazioni", json={"data": T.isoformat(), "causale": "GE", "descrizione": "TEST_UI man",
                                                           "righe": [{"conto": "06.02.001", "dare": 100}, {"conto": "06.01.001", "avere": 100}]}).json()
    print(json.dumps({**ST, "tok": t.TOK, "tok_op": t.TOK_OP, "inv_add": a["id"], "inv_b": b["id"], "rid": r.get("id"), "a_status": sess().get(f"{API}/invoices/{a['id']}").json()["status"]}))
else:
    t.clean()

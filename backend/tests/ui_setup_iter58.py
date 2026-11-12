# UI fixture helper for iteration 58: python tests/ui_setup_iter58.py setup|clean RUN
import json
import random
import sys

sys.argv += [""] * 3
if sys.argv[1] == "clean":
    random.seed(0)
    import test_iteration57_pagamenti_fornitori as m
    r = sys.argv[2]
    m.RUN, m.UID, m.UID_OP = r, f"test-user-t57-admin-{r}", f"test-user-t57-op-{r}"
    m.PIVA, m.PIVA2 = "88" + r + "571", "88" + r + "572"
    m.clean()
    print("cleaned", r)
else:
    import test_iteration57_pagamenti_fornitori as m
    st = m.setup_data()
    rr = m.post_dist([(f"{st['A1']}:1", 300), (f"{st['A1']}:2", 50.5), (f"{st['PA']}:1", 100)])
    assert rr.status_code == 200, rr.text
    st["D1"] = rr.json()["id"]
    st["E1"] = rr.json()["coge_entry_id"]
    print(json.dumps({**st, "RUN": m.RUN, "TOK": m.TOK}))

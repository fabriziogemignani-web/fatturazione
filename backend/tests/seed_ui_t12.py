# Seeds TEST_T12 UI data (registro IVA vendite/acquisti, liquidazione) using test_iteration12_iva.seed. --clean removes all TEST_T12 data
import sys
import json
from test_iteration7_pa_scartate_registro import API
from test_iteration12_iva import clean_all, user, sess, comp, seed, TOK, UID, PIVA_FIX

clean_all()
if "--clean" in sys.argv:
    print("cleaned")
    sys.exit()
user(UID, TOK, "admin", "[]")
s = sess(TOK)
cid = s.post(f"{API}/companies", json=comp("TEST_T12 Iva Srl", PIVA_FIX)).json()["id"]
ids = seed(s, {"X-Company-Id": cid})
print(json.dumps({"TOK": TOK, "CID": cid, **{k: ids[k]["id"] for k in ("F1", "F2", "F3", "F4", "F6", "F7", "F8", "NC1")}, "P": ids["P"]}))

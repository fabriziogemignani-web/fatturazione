# Seeds TEST_T10 UI data (estratto conto + sollecito): admin + operatore sessions, company, clients A/B/C. --clean to remove all TEST_T10 data
import sys
import json
from test_iteration10_estratto_solleciti import clean_all, user, sess, seed, TOK, UID, OTOK, OUID

clean_all()
if "--clean" in sys.argv:
    print("cleaned")
    sys.exit()
user(UID, TOK, "admin", "[]")
d = seed(sess(TOK))
user(OUID, OTOK, "operatore", f'["{d["cid"]}"]')
print(json.dumps({"TOK": TOK, "OTOK": OTOK, "CID": d["cid"], "A": d["A"], "B": d["B"], "C": d["C"]}))

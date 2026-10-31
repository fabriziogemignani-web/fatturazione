# Seeds TEST_T11 UI data (fatture passive): admin + operatore sessions, company (P.IVA 01234567890), 1 active sent invoice,
# passive: fixture XML (1 rata) + overdue 2-rate invoice. --clean removes all TEST_T11 data
import sys
import json
from test_iteration7_pa_scartate_registro import API, party, inv
from test_iteration10_estratto_solleciti import sent
from test_iteration11_passive import clean_all, user, sess, comp, up, variant, XML, TOK, UID, OTOK, OUID, PIVA_FIX, RUN

clean_all()
if "--clean" in sys.argv:
    print("cleaned")
    sys.exit()
user(UID, TOK, "admin", "[]")
s = sess(TOK)
cid = s.post(f"{API}/companies", json=comp("TEST_T11 Fix Srl", PIVA_FIX)).json()["id"]
h = {"X-Company-Id": cid}
user(OUID, OTOK, "operatore", f'["{cid}"]')
cl = s.post(f"{API}/parties", json=party("TEST_T11 Cliente", piva="0" + RUN + "0011"), headers=h).json()["id"]
ai = sent(s, h, inv(cl, data="2026-10-01", scadenza="2026-10-20"))
r1 = up(s, h, ("sample_fattura.xml", XML))[0]["documenti"][0]["id"]
r2 = up(s, h, ("rate.xml", variant("R-1", data="2026-09-01", rate=[("2026-10-01", 300.0), ("2026-12-31", 274.93)])))[0]["documenti"][0]["id"]
print(json.dumps({"TOK": TOK, "OTOK": OTOK, "CID": cid, "P1": r1, "P2": r2, "AI": ai["id"]}))

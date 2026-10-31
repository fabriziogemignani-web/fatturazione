# Seeds TEST_T13 reverse-charge UI data: A (N6.3 1000 + 22%, da_registrare), B (plain, registered Feb), NC (TD04 N6.3 200, registered Feb). --clean removes
import sys
import json
from test_iteration7_pa_scartate_registro import API
from test_iteration12_iva import user, sess, comp
from test_iteration13_reverse_charge import clean_all, rc_xml, up, TOK, UID, PIVA_FIX, RUN

clean_all()
if "--clean" in sys.argv:
    print("cleaned")
    sys.exit()
user(UID, TOK, "admin", "[]")
s = sess(TOK)
cid = s.post(f"{API}/companies", json=comp("TEST_T13 RC Srl", PIVA_FIX)).json()["id"]
h = {"X-Company-Id": cid}
ids = {"A": up(s, h, "a.xml", rc_xml(f"T13UI-{RUN}-A")), "B": up(s, h, "b.xml", rc_xml(f"T13UI-{RUN}-B", rc=())),
       "NC": up(s, h, "nc.xml", rc_xml(f"T13UI-{RUN}-NC", tipo="TD04", rc=(("N6.3", 200.0),), keep22=False))}
s.patch(f"{API}/passive/{ids['B']}", json={"stato_reg": "registrata", "data_registrazione": "2026-02-05"}, headers=h)
s.patch(f"{API}/passive/{ids['NC']}", json={"stato_reg": "registrata", "data_registrazione": "2026-02-20"}, headers=h)
print(json.dumps({"TOK": TOK, "CID": cid, **ids}))

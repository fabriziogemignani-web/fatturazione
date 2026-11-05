# Seed for iteration 26 UI test: TEST_ admin + operatore sessions, company with sent/draft/scartata invoices, passive and local SMTP. Prints cid.
# Usage: python seed_ui_t26.py [clean]
import sys
import requests
import test_iteration26_export_commercialista as T
from test_iteration7_pa_scartate_registro import API, mongo

T.PIVA, T.UID, T.TOK, T.OUID, T.OTOK, T.CUID = "86999999261", "test-user-t26ui-admin", "test_session_t26ui_admin", "test-user-t26ui-op", "test_session_t26ui_op", "test-user-t26ui-none"
T.clean()
if len(sys.argv) > 1:
    sys.exit(0)
gen = T.setup.__wrapped__()
next(gen)
r = requests.put(f"{API}/company/smtp", headers={"Authorization": f"Bearer {T.TOK}", "X-Company-Id": T.ST["cid"]}, json=T.SMTP_OK)
assert r.status_code == 200, r.text
print(T.ST["cid"])

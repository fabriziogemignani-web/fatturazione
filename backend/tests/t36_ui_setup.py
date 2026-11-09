# Helper for iteration 36 UI test (menu on/off + scheda da anagrafica): `python t36_ui_setup.py setup` -> runs t35 setup + creates approved contabile user
import json
import os
import subprocess
import sys
import uuid

import requests

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
here = os.path.dirname(__file__)
out = json.loads(subprocess.run([sys.executable, os.path.join(here, "t35_ui_setup.py"), "setup"], capture_output=True, text=True).stdout.strip().splitlines()[-1])
s = requests.Session()
s.post(f"{API}/auth/login", json={"email": "fabrizio.gemignani@gmail.com", "password": "Fe-Admin-2aOBey8irzL8"})
email = f"test.user.t36ui{uuid.uuid4().hex[:6]}@example.com"
requests.post(f"{API}/auth/register", json={"name": "TEST_T36 UI Contabile", "email": email, "password": "TestPass-123456"})
uid = next(u["user_id"] for u in s.get(f"{API}/users").json() if u["email"] == email)
s.patch(f"{API}/users/{uid}", json={"status": "approved", "role": "contabile", "company_ids": [out["cid"]]})
out.update(uid=uid, email=email)
print(json.dumps(out))

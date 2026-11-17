# Helper for iteration 98 UI test: create / delete TEST_ parties in TEST_SCREEN Srl
import os, sys, json, requests
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
s = requests.Session()
r = s.post(f"{BASE}/auth/login", json={"email": "fabrizio.gemignani@gmail.com", "password": "Fe-Admin-2aOBey8irzL8"})
r.raise_for_status()
cos = s.get(f"{BASE}/companies").json()
cid = [c for c in cos if c.get("denominazione", c.get("ragione_sociale", "")).startswith("TEST_SCREEN")][0]["id"]
s.headers["X-Company-Id"] = cid
def piva(i):
    b = f"0987654{i:03d}"
    s_ = 0
    for k, ch in enumerate(b):
        d = int(ch)
        if k % 2: d *= 2; d = d - 9 if d > 9 else d
        s_ += d
    return b + str((10 - s_ % 10) % 10)
if sys.argv[1] == "create":
    ids = []
    for i, n in enumerate(["Àlfa", "Beta", "Gamma", "Delta", "Epsilon", "Zeta"]):
        p = s.post(f"{BASE}/parties", json={"tipo": "cliente", "denominazione": f"TEST_I98 {n}", "partita_iva": piva(i), "codice_fiscale": piva(i),
                                            "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM"})
        print(p.status_code, p.text[:120]); ids.append(p.json()["id"])
    json.dump({"cid": cid, "ids": ids}, open("/tmp/i98.json", "w"))
else:
    d = json.load(open("/tmp/i98.json"))
    for i in d["ids"]:
        print(i, s.delete(f"{BASE}/parties/{i}").status_code)

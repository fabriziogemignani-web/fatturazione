# Helper for iteration 98: inspect TEST_I98 parties / create TEST fornitore
import os, sys, json, requests
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
s = requests.Session()
s.post(f"{BASE}/auth/login", json={"email": "fabrizio.gemignani@gmail.com", "password": "Fe-Admin-2aOBey8irzL8"}).raise_for_status()
d = json.load(open("/tmp/i98.json"))
s.headers["X-Company-Id"] = d["cid"]
if sys.argv[1] == "forn":
    p = s.post(f"{BASE}/parties", json={"tipo": "fornitore", "denominazione": "TEST_I98 Fornitore", "partita_iva": "09876541005", "codice_fiscale": "09876541005",
                                        "indirizzo": "Via Roma 2", "cap": "00100", "comune": "Roma", "provincia": "RM"})
    print(p.status_code, p.text[:100])
    d["ids"].append(p.json()["id"]); json.dump(d, open("/tmp/i98.json", "w"))
elif sys.argv[1] == "show":
    for p in s.get(f"{BASE}/parties").json():
        if p["denominazione"].startswith("TEST_I98"):
            print(p["denominazione"], "pag=", repr(p.get("pagamento_modalita")), "gest=", repr(p.get("gestione_iva")))
if sys.argv[1] == "cleanup":
    data = s.get(f"{BASE}/contabilita/registrazioni", params={"dal": "2026-01-01", "al": "2026-12-31", "q": "TEST_I98"}).json()
    print(list(data.keys()) if isinstance(data, dict) else type(data)); items = next((v for v in data.values() if isinstance(v, list)), []) if isinstance(data, dict) else data
    for r in items:
        if "TEST_I98" in (r.get("descrizione") or ""):
            print("del reg", r["id"], s.delete(f"{BASE}/contabilita/registrazioni/{r['id']}").status_code)
    for i in d["ids"]:
        print("del party", i, s.delete(f"{BASE}/parties/{i}").status_code)

# UI setup helper for iteration 105 (run after `KEEP_T105=1 pytest tests/test_iteration105_piantina.py -n 0`): adds config, listino, cliente, barche.
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import test_iteration105_piantina as t  # noqa: E402
from test_iteration7_pa_scartate_registro import API, mongo  # noqa: E402
import json, subprocess  # noqa: E402,E401

out = subprocess.run(["mongosh", "--quiet", os.environ["MONGO_URL"] + "/" + os.environ["DB_NAME"], "--eval",
                      'print(db.companies.findOne({denominazione:"TEST_T105 Marina Srl"}).id)'], capture_output=True, text=True).stdout.strip()
t.ST["cid"] = out
s = t.s()
print(s.put(f"{API}/porto/config", json={"alta_da": "06-01", "alta_a": "09-30", "aliquota": 10}).status_code)
print(s.put(f"{API}/porto/listino", json={"fasce": [{"da_m": 0, "a_m": 15, "giorno_alta": 50, "giorno_bassa": 30, "mese_alta": 1000, "mese_bassa": 600, "annuale": 5000}]}).status_code)
p = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": "TEST_T105 Armatore Bianchi", "partita_iva": "01234567897", "codice_fiscale": "01234567897",
                                     "codice_destinatario": "0000000", "indirizzo": "Via Mare 2", "cap": "57100", "comune": "Livorno", "provincia": "LI", "nazione": "IT"})
pid = p.json()["id"]
for n in ("TEST_Gabbiano", "TEST_Delfino"):
    print(s.post(f"{API}/porto/barche", json={"nome": n, "party_id": pid, "lunghezza": 9}).status_code)
print("CID", out)

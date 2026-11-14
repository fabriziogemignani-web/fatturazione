# UI setup for iteration 73: uploads a fresh passive XML (da registrare) into the kept TEST_T73 company (run after T73_KEEP=1 T73_RUN=730073 pytest).
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("T73_RUN", "730073")
import test_iteration73_ritenute_reg_liquidazione as t  # noqa: E402

t.ST["cid"] = t.mongo('print(db.companies.findOne({denominazione:/^TEST_T73/}).id)')
x = t.rc_xml("T73UI-1", data=t.DD, rc=()).decode().replace("<IdCodice>01234567890</IdCodice>", f"<IdCodice>{t.PIVA}</IdCodice>")
r = t.sess().post(f"{t.API}/passive/upload", files=[("files", ("ui.xml", x.encode(), "application/octet-stream"))])
print(r.status_code, r.text[:300])
t.ST["F"] = t.ST["C"] = t.mongo(f'print(db.parties.findOne({{company_id:"{t.ST["cid"]}", tipo:"cliente"}}).id)')
print(t.rv(tipo="vendita", party_id=t.ST["C"], numero="T73UI-V", data_documento="2026-11-02", data_registrazione="2026-11-02", scadenza="2026-11-30",
           righe=[{"aliquota": 22, "totale": 12200}]).status_code)
liq = t.sess().get(f"{t.API}/liquidazione-iva", params={"anno": 2026, "periodicita": "mensile"}).json()
print(json.dumps({"cid": t.ST["cid"], "periodi": [(p["periodo"], p["da_versare"], p["iva_debito"], p["iva_credito"]) for p in liq["periodi"]]}))

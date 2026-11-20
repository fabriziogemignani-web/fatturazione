# Helper (iteration 115 UI): creates extra TEST_ docs in a kept T115 company. Usage: T115_RUN=<run> CID=<cid> python tests/t115_ui_seed.py
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import test_iteration115_regpas_proposta_ritenuta as t  # noqa: E402

t.ST["cid"] = os.environ["CID"]
out = {}
pi = t.piva()
sid = t.mk_sup("TEST_T115 UI privata", pi, soggetto_ritenuta=False)
out["ui_priv"] = t.upload(t.xml(pi, ((22.0, None, 1040.0, 228.8),), den="TEST_T115 UI privata"))["id"]
t.edit_party(sid, soggetto_ritenuta=True, ritenuta_aliquota=20, ritenuta_base=100, cassa_tipo="TC01", cassa_aliquota=4, cassa_ritenuta=False, ritenuta_tipo="RT01", ritenuta_causale="A")
pi = t.piva()
sid = t.mk_sup("TEST_T115 UI xmldiff", pi, soggetto_ritenuta=False)
out["ui_xml"] = t.upload(t.xml(pi, ((22.0, None, 1040.0, 228.8),), rit=("RT01", 104.0, 10.0), den="TEST_T115 UI xmldiff"))["id"]
t.edit_party(sid, soggetto_ritenuta=True, ritenuta_aliquota=20, ritenuta_base=100, cassa_tipo="TC01", cassa_aliquota=4, cassa_ritenuta=False, ritenuta_tipo="RT01", ritenuta_causale="A")
out["ui_xml_doc_rit"] = t.pdoc(out["ui_xml"]).get("ritenuta_importo")
print(json.dumps(out))

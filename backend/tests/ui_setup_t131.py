# UI setup for iteration 131 (ordini proposte). Usage: python tests/ui_setup_t131.py setup | clean <cidA> <cidB>
import json
import sys

sys.path.insert(0, "/app/backend/tests")
import conftest  # noqa: E402,F401
import test_iteration131_ordini_proposte as t  # noqa: E402

if sys.argv[1] == "setup":
    t.do_setup()
    print(json.dumps(t.ST))
else:
    t.ST["cids"] = sys.argv[2:]
    t.clean()
    print("cleaned")

# Helper for iteration 43 UI test (conservazione): `python t43_ui_setup.py setup` | `python t43_ui_setup.py clean`
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import test_iteration43_conservazione as T  # noqa: E402

if sys.argv[1] == "setup":
    T.do_setup()
    print(json.dumps({**T.S, "tokens": {k: v[1] for k, v in T.U.items()}}))
else:
    T.clean()
    print("cleaned")

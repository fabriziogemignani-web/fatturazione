# Iteration 109 UI helper: creates TEST admin + TEST company for invoice editor copy/new buttons. Usage: python ui_setup_t109.py setup|clean RUN
import sys, os
sys.path.insert(0, "/app/backend/tests")
mode, run = sys.argv[1], sys.argv[2]
import random
random.randint = lambda a, b: int(run)  # deterministic RUN so clean() targets the same records
import test_iteration108_integrita as t
if mode == "setup":
    os.environ["T108_KEEP"] = "1"
    g = t.setup.__wrapped__()
    next(g)
    print("CID", t.ST["cid"], "TOK", t.TOK)
else:
    t.clean()
    print("cleaned", t.RUN)

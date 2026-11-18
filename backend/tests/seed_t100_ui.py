# UI seed for iteration 100 (Stampe fiscali): python seed_t100_ui.py create|delete
import sys
import test_iteration100_stampe_fiscali as T

if sys.argv[1] == "delete":
    T.clean()
    print("cleaned")
    sys.exit(0)
gen = T.setup.__wrapped__() if hasattr(T.setup, "__wrapped__") else None
next(gen)  # runs setup (creates TEST_T100 company, admin user/session)
T.test_01_registri_seed()
s = T.sess()
T.ST["p_it"] = T.upload("UIT1", f"{T.Y}-02-05", "01234567897", "IT")
T.ST["p_de"] = T.upload("UDE1", f"{T.Y}-02-06", "123456789", "DE")
for pid in (T.ST["p_it"], T.ST["p_de"]):
    r = s.post(f"{T.API}/passive/{pid}/registrazione", json=T.reg_body(pid, f"{T.Y}-02-10"))
    assert r.status_code == 200, r.text
T.ST["p_un"] = T.upload("UIT2", f"{T.Y}-06-05", "01234567897", "IT")
print(f"TOK={T.TOK}\nCID={T.ST['cid']}\nP_IT={T.ST['p_it']}\nP_DE={T.ST['p_de']}\nP_UN={T.ST['p_un']}\nACQ={T.ST['reg']['ACQ']}\nCEE={T.ST['reg']['CEE']}")

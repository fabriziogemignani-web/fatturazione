# UI setup for iteration 129 (bank conto_coge link + cespiti config card in Dati azienda).
# Usage: python tests/ui_setup_t129.py setup | amm <cid> | clean <cidA> <cidB>
import json
import sys

sys.path.insert(0, "/app/backend/tests")
import conftest  # noqa: E402,F401
import test_iteration128_ai_learning_cespiti as t  # noqa: E402

t.TOK, t.UID = "test_session_t129_admin", "test-user-t129-admin"
t.TOK_OP, t.UID_OP = "test_session_t129_oper", "test-user-t129-oper"
t.sess.__defaults__ = (t.TOK, None)


def iban(bban):
    n = int("".join(str(int(c, 36)) for c in bban + "IT00"))
    return f"IT{98 - n % 97:02d}{bban}"


if sys.argv[1] == "setup":
    t.do_setup()
    cid = t.ST["cid"]
    s = t.sess()
    comp = s.get(f"{t.API}/company").json()
    comp["banche"] = [{"nome": "TEST_Banca Uno", "iban": iban("X0542811101000000123456"), "predefinita": True},
                      {"nome": "TEST_Banca Due", "iban": iban("X0306909606100000063190"), "predefinita": False}]
    r = s.put(f"{t.API}/company", json=comp)
    assert r.status_code == 200, r.text
    # operator: only banche right
    t.mongo(f'db.users.updateOne({{user_id:"{t.UID_OP}"}},{{$set:{{diritti:{{dati_azienda:false, banche:true}}}}}})')
    # company B without contabilita
    r = t.sess(cid="").post(f"{t.API}/companies", json={"denominazione": f"TEST_T129 NoCoge {t.RUN} Srl", "partita_iva": "15" + t.RUN + "129", "codice_fiscale": "15" + t.RUN + "129",
                                                       "regime_fiscale": "RF01", "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    cidb = r.json()["id"]
    sb = t.sess(cid=cidb)
    assert sb.put(f"{t.API}/companies/{cidb}/moduli", json={"fatturazione": True, "archivio": True, "fatture_attive": True, "fatture_passive": True, "corrispettivi": True, "contabilita": False}).status_code == 200
    compb = sb.get(f"{t.API}/company").json()
    compb["banche"] = [{"nome": "TEST_Banca B", "iban": iban("X0542811101000000123456"), "predefinita": True}]
    assert sb.put(f"{t.API}/company", json=compb).status_code == 200
    print(json.dumps({"cid": cid, "cidb": cidb, "tok": t.TOK, "tok_op": t.TOK_OP}))
elif sys.argv[1] == "amm":
    t.ST["cid"] = sys.argv[2]
    s = t.sess()
    r = s.post(f"{t.API}/cespiti", json={"descrizione": "TEST_PC ufficio", "categoria": "macchine_ufficio", "data_acquisto": "2025-07-01", "costo": 1000, "aliquota": 20})
    print(r.status_code, r.text[:200])
    r = s.post(f"{t.API}/cespiti/ammortamenti/2025")
    print(r.status_code, r.text[:200])
else:
    t.ST["cids"] = sys.argv[2:]
    t.clean()
    print("cleaned")

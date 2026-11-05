# Iteration 20: company banks (banche aziendali: IBAN/ABI/CAB/BIC), invoice bank snapshot (banca_id) and FatturaPA DatiPagamento bank tags.
# Run with: pytest test_iteration20_banche.py -n 0
import random
import pytest
import requests
from test_iteration7_pa_scartate_registro import API, mongo, party, inv, strip_ns, TODAY

RUN = str(random.randint(100000, 999999))
TOK, UID = f"test_session_t20_admin_{RUN}", f"test-user-t20-admin-{RUN}"
PIVA = "87" + RUN + "001"
IBAN1 = "IT60X0542811101000000123456"


def it_iban(abi, cab, conto, cin="X"):
    bban = f"{cin}{abi}{cab}{conto}"
    n = int("".join(str(int(c, 36)) for c in bban + "IT00"))
    return f"IT{98 - n % 97:02d}{bban}"


IBAN2 = it_iban("03069", "09606", "100000012345")
IBAN3 = it_iban("02008", "01600", "000100200300")


def comp(banche=None, **kw):
    d = {"denominazione": "TEST_T20 Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
         "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT", **kw}
    if banche is not None:
        d["banche"] = banche
    return d


def clean():
    mongo(f'var c=db.companies.findOne({{partita_iva:"{PIVA}"}}); if(c){{db.invoices.deleteMany({{company_id:c.id}}); db.parties.deleteMany({{company_id:c.id}});'
          f'db.counters.deleteMany({{key:"progressivo_"+c.id}}); db.companies.deleteOne({{id:c.id}});}}'
          f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


@pytest.fixture(scope="module")
def ctx():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t20.{RUN}@example.com", name:"TEST_T20 Admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+7*864e5), created_at:new Date().toISOString()}});')
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    r = s.post(f"{API}/companies", json=comp())
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    s.headers["X-Company-Id"] = cid
    pid = s.post(f"{API}/parties", json=party("TEST_T20 Cliente")).json()["id"]
    yield {"s": s, "cid": cid, "pid": pid}
    clean()


def put(s, banche, **kw):
    return s.put(f"{API}/company", json=comp(banche, **kw))


def locs(r):
    return [(e["loc"], e["msg"]) for e in r.json()["detail"]]


# ---- Company banks validation ----
class TestBanks:
    def test_01_valid_save_normalize_and_derive(self, ctx):
        r = put(ctx["s"], [{"nome": "Banca Popolare", "iban": "it60 x054 2811 1010 0000 0123 456", "bic": "bpmoit22xxx"},
                           {"nome": "Intesa", "iban": IBAN2, "abi": "03069", "cab": "09606"}])
        assert r.status_code == 200, r.text
        b = r.json()["banche"]
        assert b[0]["iban"] == IBAN1 and b[0]["abi"] == "05428" and b[0]["cab"] == "11101" and b[0]["bic"] == "BPMOIT22XXX"
        assert b[0]["predefinita"] is True and b[1]["predefinita"] is False
        assert all(isinstance(x["id"], str) and x["id"] for x in b)
        assert r.json()["iban"] == IBAN1
        g = ctx["s"].get(f"{API}/company").json()
        assert [x["id"] for x in g["banche"]] == [x["id"] for x in b] and g["iban"] == IBAN1

    def test_02_ids_stable_and_default_sync(self, ctx):
        b = ctx["s"].get(f"{API}/company").json()["banche"]
        b[0]["predefinita"], b[1]["predefinita"] = False, True
        r = put(ctx["s"], b)
        assert r.status_code == 200, r.text
        nb = r.json()["banche"]
        assert [x["id"] for x in nb] == [x["id"] for x in b]
        assert nb[1]["predefinita"] and not nb[0]["predefinita"] and r.json()["iban"] == IBAN2

    def test_03_multiple_default_first_kept(self, ctx):
        b = ctx["s"].get(f"{API}/company").json()["banche"]
        for x in b:
            x["predefinita"] = True
        r = put(ctx["s"], b)
        assert [x["predefinita"] for x in r.json()["banche"]] == [True, False] and r.json()["iban"] == IBAN1

    @pytest.mark.parametrize("bank,needle", [
        ({"nome": "X", "iban": "IT60X0542811101000000123457"}, "controllo"),
        ({"nome": "X", "iban": "IT60X05428111010000001234"}, "27"),
        ({"nome": "X", "iban": "ciao"}, "IBAN"),
        ({"nome": "X", "iban": IBAN1, "abi": "12345"}, "ABI"),
        ({"nome": "X", "iban": IBAN1, "cab": "99999"}, "CAB"),
        ({"nome": "X", "iban": IBAN1, "abi": "12"}, "5 cifre"),
        ({"nome": "X", "iban": IBAN1, "bic": "ABC"}, "BIC"),
        ({"nome": "  ", "iban": IBAN1}, "nome"),
    ])
    def test_04_invalid_bank_422(self, ctx, bank, needle):
        r = put(ctx["s"], [bank])
        assert r.status_code == 422, r.text
        msgs = " ".join(m for _, m in locs(r))
        assert needle.lower() in msgs.lower(), locs(r)
        assert [str(x) for x in locs(r)[0][0][:3]] == ["body", "banche", "0"], locs(r)

    def test_05_duplicate_iban(self, ctx):
        r = put(ctx["s"], [{"nome": "A", "iban": IBAN1}, {"nome": "B", "iban": IBAN1.lower()}])
        assert r.status_code == 422 and "già presente" in str(r.json()), r.text

    def test_06_max_20(self, ctx):
        r = put(ctx["s"], [{"nome": f"B{i}", "iban": it_iban("03069", "09606", f"{i:012d}")} for i in range(21)])
        assert r.status_code == 422, r.text

    def test_07_foreign_iban_ok(self, ctx):
        r = put(ctx["s"], [{"nome": "Deutsche", "iban": "DE89370400440532013000", "bic": "COBADEFFXXX"}])
        assert r.status_code == 200, r.text
        assert r.json()["banche"][0]["abi"] == "" and r.json()["iban"] == "DE89370400440532013000"

    def test_08_empty_banche_clears_iban(self, ctx):
        r = put(ctx["s"], [])
        assert r.status_code == 200 and r.json()["iban"] == "" and r.json()["banche"] == []


# ---- Invoice snapshot + XML ----
def pag(xml):
    return [{c.tag: c.text for c in d} | {"_order": [c.tag for c in d]} for d in strip_ns(xml).iter("DettaglioPagamento")]


class TestInvoiceBank:
    def test_10_setup_banks(self, ctx):
        r = put(ctx["s"], [{"nome": "Banca Popolare", "iban": IBAN1, "bic": "BPMOIT22XXX"}, {"nome": "Intesa", "iban": IBAN2}])
        assert r.status_code == 200
        ctx["b"] = r.json()["banche"]

    def test_11_default_bank_snapshot_and_xml(self, ctx):
        r = ctx["s"].post(f"{API}/invoices", json=inv(ctx["pid"]))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["banca"]["id"] == ctx["b"][0]["id"] and d["banca"]["iban"] == IBAN1 and d["banca_id"] == ctx["b"][0]["id"]
        ctx["i1"] = d["id"]
        x = ctx["s"].get(f"{API}/invoices/{d['id']}/xml")
        assert x.status_code == 200
        p = pag(x.text)[0]
        assert p["IstitutoFinanziario"] == "Banca Popolare" and p["IBAN"] == IBAN1 and p["ABI"] == "05428" and p["CAB"] == "11101" and p["BIC"] == "BPMOIT22XXX"
        o = p["_order"]
        assert o.index("ImportoPagamento") < o.index("IstitutoFinanziario") < o.index("IBAN") < o.index("ABI") < o.index("CAB") < o.index("BIC")

    def test_12_chosen_bank_mp12_and_rate(self, ctx):
        body = inv(ctx["pid"], modalita_pagamento="MP12", banca_id=ctx["b"][1]["id"],
                   rate=[{"scadenza": TODAY, "importo": 610}, {"scadenza": TODAY, "importo": 610}])
        r = ctx["s"].post(f"{API}/invoices", json=body)
        assert r.status_code == 200, r.text
        assert r.json()["banca"]["nome"] == "Intesa" and r.json()["banca"]["abi"] == "03069"
        ctx["i2"] = r.json()["id"]
        ps = pag(ctx["s"].get(f"{API}/invoices/{ctx['i2']}/xml").text)
        assert len(ps) == 2 and all(p["IBAN"] == IBAN2 and p["ModalitaPagamento"] == "MP12" and "BIC" not in p for p in ps)

    def test_13_unknown_bank_400(self, ctx):
        r = ctx["s"].post(f"{API}/invoices", json=inv(ctx["pid"], banca_id="nope"))
        assert r.status_code == 400, r.text
        assert "banca_id" in str(r.json()), r.text

    @pytest.mark.parametrize("mod", ["MP01", "MP02", "MP08"])
    def test_14_other_modalita_no_bank(self, ctx, mod):
        r = ctx["s"].post(f"{API}/invoices", json=inv(ctx["pid"], modalita_pagamento=mod, banca_id=ctx["b"][1]["id"]))
        assert r.status_code == 200, r.text
        assert r.json()["banca"] is None and r.json()["banca_id"] is None
        p = pag(ctx["s"].get(f"{API}/invoices/{r.json()['id']}/xml").text)[0]
        assert "IBAN" not in p and "IstitutoFinanziario" not in p
        ctx.setdefault("other", []).append(r.json()["id"])

    def test_15_update_changes_bank(self, ctx):
        r = ctx["s"].put(f"{API}/invoices/{ctx['i1']}", json=inv(ctx["pid"], banca_id=ctx["b"][1]["id"]))
        assert r.status_code == 200, r.text
        assert r.json()["banca"]["iban"] == IBAN2
        g = ctx["s"].get(f"{API}/invoices/{ctx['i1']}").json()
        assert g["banca"]["iban"] == IBAN2 and g["banca_id"] == ctx["b"][1]["id"]
        r = ctx["s"].put(f"{API}/invoices/{ctx['i1']}", json=inv(ctx["pid"], modalita_pagamento="MP01", banca_id=ctx["b"][1]["id"]))
        assert r.json()["banca"] is None
        r = ctx["s"].put(f"{API}/invoices/{ctx['i1']}", json=inv(ctx["pid"], banca_id=ctx["b"][0]["id"]))
        assert r.json()["banca"]["iban"] == IBAN1

    def test_16_snapshot_survives_company_change(self, ctx):
        r = put(ctx["s"], [{"nome": "Unicredit", "iban": IBAN3}])
        assert r.status_code == 200
        g = ctx["s"].get(f"{API}/invoices/{ctx['i2']}").json()
        assert g["banca"]["nome"] == "Intesa" and g["banca"]["iban"] == IBAN2
        p = pag(ctx["s"].get(f"{API}/invoices/{ctx['i2']}/xml").text)[0]
        assert p["IBAN"] == IBAN2 and p["IstitutoFinanziario"] == "Intesa"
        # re-saving draft with the now-deleted bank id -> 400
        r = ctx["s"].put(f"{API}/invoices/{ctx['i1']}", json=inv(ctx["pid"], banca_id=ctx["b"][0]["id"]))
        assert r.status_code == 400 and "banca_id" in str(r.json())

    def test_17_send_then_locked_snapshot(self, ctx):
        r = ctx["s"].post(f"{API}/invoices/{ctx['i2']}/send")
        assert r.status_code == 200, r.text
        assert ctx["s"].get(f"{API}/invoices/{ctx['i2']}").json()["banca"]["iban"] == IBAN2

    def test_18_legacy_iban_only(self, ctx):
        mongo(f'db.companies.updateOne({{id:"{ctx["cid"]}"}}, {{$set:{{banche:[], iban:"{IBAN1}"}}}})')
        r = ctx["s"].post(f"{API}/invoices", json=inv(ctx["pid"]))
        assert r.status_code == 200, r.text
        assert r.json()["banca"]["iban"] == IBAN1
        p = pag(ctx["s"].get(f"{API}/invoices/{r.json()['id']}/xml").text)[0]
        assert p["IBAN"] == IBAN1 and "IstitutoFinanziario" not in p
        # legacy invoice without banca field at all -> XML falls back to company iban
        mongo(f'db.invoices.updateOne({{id:"{r.json()["id"]}"}}, {{$unset:{{banca:"", banca_id:""}}}})')
        p = pag(ctx["s"].get(f"{API}/invoices/{r.json()['id']}/xml").text)[0]
        assert p["IBAN"] == IBAN1

    def test_19_no_banks_no_iban(self, ctx):
        mongo(f'db.companies.updateOne({{id:"{ctx["cid"]}"}}, {{$set:{{banche:[], iban:""}}}})')
        r = ctx["s"].post(f"{API}/invoices", json=inv(ctx["pid"]))
        assert r.status_code == 200, r.text
        assert r.json()["banca"] is None
        p = pag(ctx["s"].get(f"{API}/invoices/{r.json()['id']}/xml").text)[0]
        assert "IBAN" not in p

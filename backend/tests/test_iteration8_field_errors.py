# Iteration 8: field-level error format. Every 422 and business error returns detail=[{loc:["body",field,...],msg(IT),type}]
# Run with: pytest test_iteration8_field_errors.py -n 0
import uuid
import pytest
import requests
from test_iteration7_pa_scartate_registro import API, mongo, party, inv, TODAY

TOK, UID, PIVA, PIVA2 = "test_session_t8_admin", "test-user-t8-admin", "77777777781", "77777777782"
COMP = {"denominazione": "TEST_T8 Srl", "codice_fiscale": "", "regime_fiscale": "RF01", "indirizzo": "Via Roma 1",
        "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"}


def clean():
    for p in (PIVA, PIVA2):
        c = mongo(f'const c=db.companies.findOne({{partita_iva:"{p}"}}); print(c?c.id:"")')
        if c:
            mongo(f'db.invoices.deleteMany({{company_id:"{c}"}}); db.parties.deleteMany({{company_id:"{c}"}}); db.articles.deleteMany({{company_id:"{c}"}});'
                  f'db.counters.deleteMany({{key:"progressivo_{c}"}}); db.companies.deleteMany({{id:"{c}"}});')
    mongo(f'db.users.deleteMany({{$or:[{{user_id:"{UID}"}},{{email:/^test\\.user\\.t8/}}]}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


@pytest.fixture(scope="module")
def ctx():
    clean()
    mongo(f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t8.admin@example.com", name:"TEST_T8 Admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+7*864e5), created_at:new Date().toISOString()}});')
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    r = s.post(f"{API}/companies", json={**COMP, "partita_iva": PIVA})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    s.headers["X-Company-Id"] = cid
    c = {"s": s, "cid": cid}
    c["b2b"] = s.post(f"{API}/parties", json=party("TEST_T8 B2B", codice="ABC1234")).json()["id"]
    c["pa"] = s.post(f"{API}/parties", json=party("TEST_T8 PA", codice="UFAB12", pa=True, piva="80012345678")).json()["id"]
    yield c
    clean()


def errs(r):
    d = r.json()["detail"]
    assert isinstance(d, list), r.text
    for e in d:
        assert set(e) >= {"loc", "msg", "type"} and e["loc"][0] == "body", e
    return {".".join(str(x) for x in e["loc"][1:]): e["msg"] for e in d}


# --- Pydantic 422 translated messages and model-level locs
class TestValidation:
    def test_pa_codice_3_chars(self, ctx):
        r = ctx["s"].post(f"{API}/parties", json=party("TEST_T8 x", codice="ABC", pa=True))
        assert r.status_code == 422
        assert "6 caratteri" in errs(r)["codice_destinatario"]

    def test_b2b_codice_wrong(self, ctx):
        r = ctx["s"].post(f"{API}/parties", json=party("TEST_T8 x", codice="ABC12"))
        assert r.status_code == 422 and "7 caratteri" in errs(r)["codice_destinatario"]

    def test_natura_default_and_intento(self, ctx):
        r = ctx["s"].post(f"{API}/parties", json=party("TEST_T8 x", natura_default="N9"))
        assert errs(r).keys() == {"natura_default"}
        r = ctx["s"].post(f"{API}/parties", json=party("TEST_T8 x", natura_default="N3.5", intento_protocollo="123"))
        assert "intento_protocollo" in errs(r)
        r = ctx["s"].post(f"{API}/parties", json=party("TEST_T8 x", natura_default="N3.5", intento_protocollo="12345678901234567-123456", intento_data=""))
        assert "intento_data" in errs(r)

    def test_party_missing_fields_translated(self, ctx):
        body = party("", codice="ABC1234")
        body.pop("cap")
        r = ctx["s"].post(f"{API}/parties", json=body)
        e = errs(r)
        assert r.status_code == 422 and e["cap"] == "Campo obbligatorio" and e["denominazione"] == "Campo obbligatorio", e

    def test_article_aliquota_natura(self, ctx):
        r = ctx["s"].post(f"{API}/articles", json={"codice": "TEST_T8A", "descrizione": "x", "aliquota": 7})
        assert errs(r).keys() == {"aliquota"}
        r = ctx["s"].post(f"{API}/articles", json={"codice": "TEST_T8A", "descrizione": "x", "aliquota": 0})
        assert errs(r).keys() == {"natura"}

    def test_invoice_line_quantita_zero(self, ctx):
        b = inv(ctx["b2b"])
        b["lines"][0]["quantita"] = 0
        r = ctx["s"].post(f"{API}/invoices", json=b)
        assert r.status_code == 422 and errs(r)["lines.0.quantita"] == "Deve essere maggiore di 0"

    def test_invoice_line_quantita_empty_string(self, ctx):
        b = inv(ctx["b2b"])
        b["lines"][0]["quantita"] = "abc"
        r = ctx["s"].post(f"{API}/invoices", json=b)
        assert errs(r)["lines.0.quantita"] == "Inserisci un numero valido"

    def test_invoice_line_quantita_null(self, ctx):
        b = inv(ctx["b2b"])
        b["lines"][0]["quantita"] = None
        r = ctx["s"].post(f"{API}/invoices", json=b)
        assert r.status_code == 422
        print("null quantita msg:", errs(r))
        assert "lines.0.quantita" in errs(r)

    def test_cassa_locs(self, ctx):
        b = inv(ctx["b2b"], cassa={"tipo": "TC99", "aliquota": 4, "aliquota_iva": 22})
        assert errs(ctx["s"].post(f"{API}/invoices", json=b)).keys() == {"cassa.tipo"}
        b = inv(ctx["b2b"], cassa={"tipo": "TC22", "aliquota": 4, "aliquota_iva": 7})
        assert errs(ctx["s"].post(f"{API}/invoices", json=b)).keys() == {"cassa.aliquota_iva"}
        b = inv(ctx["b2b"], cassa={"tipo": "TC22", "aliquota": 4, "aliquota_iva": 0})
        assert errs(ctx["s"].post(f"{API}/invoices", json=b)).keys() == {"cassa.natura"}
        b = inv(ctx["b2b"], cassa={"tipo": "TC22", "aliquota": 0, "aliquota_iva": 22})
        assert errs(ctx["s"].post(f"{API}/invoices", json=b))["cassa.aliquota"] == "Deve essere maggiore di 0"

    def test_register_short_password(self):
        r = requests.post(f"{API}/auth/register", json={"name": "TEST_T8", "email": f"test.user.t8.{uuid.uuid4().hex[:6]}@example.com", "password": "abc"})
        assert r.status_code == 422 and errs(r)["password"] == "Minimo 8 caratteri"


# --- Business errors with field
class TestBusiness:
    def test_party_missing(self, ctx):
        r = ctx["s"].post(f"{API}/invoices", json=inv(""))
        assert r.status_code == 400 and errs(r) == {"party_id": "Seleziona un cliente"}

    def test_line_natura(self, ctx):
        b = inv(ctx["b2b"])
        b["lines"].append({"descrizione": "Esente", "quantita": 1, "prezzo_unitario": 10, "aliquota": 0})
        assert errs(ctx["s"].post(f"{API}/invoices", json=b)).keys() == {"lines.1.natura"}

    def test_cig_without_rif(self, ctx):
        r = ctx["s"].post(f"{API}/invoices", json=inv(ctx["pa"], cig="ABCDE12345"))
        assert r.status_code == 422 and "rif_documento" in errs(r)

    def test_n35_without_intento(self, ctx):
        b = inv(ctx["b2b"])
        b["lines"][0].update(aliquota=0, natura="N3.5")
        assert "party_id" in errs(ctx["s"].post(f"{API}/invoices", json=b))

    def test_numero_duplicate_progressive_and_date(self, ctx):
        s = ctx["s"]
        r = s.post(f"{API}/invoices", json=inv(ctx["b2b"]))
        assert r.status_code == 200, r.text
        n = r.json()["numero"]
        r = s.post(f"{API}/invoices", json=inv(ctx["b2b"], numero=n))
        assert r.status_code == 400 and "già usato" in errs(r)["numero"]
        r = s.post(f"{API}/invoices", json=inv(ctx["b2b"], numero=n + 5))
        assert "progressiva" in errs(r)["numero"]
        r = s.post(f"{API}/invoices", json=inv(ctx["b2b"], data=f"{TODAY[:4]}-01-01"))
        e = errs(r)
        if "data" in e:
            assert "Data non coerente" in e["data"]
        else:
            assert r.status_code == 200  # first doc of year is on Jan 1 only if no previous data
        iid = s.get(f"{API}/invoices").json()
        first = [i for i in iid if i["numero"] == n][0]["id"]
        r = s.put(f"{API}/invoices/{first}", json=inv(ctx["b2b"], data="2020-01-01", numero=n))
        assert errs(r).keys() == {"data"}

    def test_nc_fattura_collegata(self, ctx):
        r = ctx["s"].post(f"{API}/invoices", json=inv(ctx["b2b"], tipo_documento="TD04", fattura_collegata_id="nope"))
        assert errs(r).keys() == {"fattura_collegata_id"}

    def test_duplicate_article(self, ctx):
        a = {"codice": "TEST_T8DUP", "descrizione": "x", "prezzo": 10, "aliquota": 22}
        assert ctx["s"].post(f"{API}/articles", json=a).status_code == 200
        r = ctx["s"].post(f"{API}/articles", json=a)
        assert r.status_code == 400 and errs(r) == {"codice": "Codice articolo già esistente"}

    def test_duplicate_company(self, ctx):
        r = ctx["s"].post(f"{API}/companies", json={**COMP, "partita_iva": PIVA})
        assert r.status_code == 400 and errs(r).keys() == {"partita_iva"}
        r = ctx["s"].post(f"{API}/companies", json={**COMP, "partita_iva": "123", "cap": "1"})
        assert r.status_code == 422 and errs(r).keys() == {"partita_iva", "cap"}

    def test_duplicate_user_and_register(self, ctx):
        r = ctx["s"].post(f"{API}/users", json={"name": "TEST_T8 Dup", "email": "test.user.t8.admin@example.com", "role": "operatore", "company_ids": []})
        assert r.status_code == 400 and errs(r).keys() == {"email"}
        r = requests.post(f"{API}/auth/register", json={"name": "TEST_T8", "email": "test.user.t8.admin@example.com", "password": "abcdefgh1"})
        assert r.status_code == 400 and errs(r).keys() == {"email"}


# --- Regression: normal saves
class TestRegression:
    def test_saves(self, ctx):
        s = ctx["s"]
        p = s.put(f"{API}/parties/{ctx['b2b']}", json=party("TEST_T8 B2B mod", codice="abc1234"))
        assert p.status_code == 200 and p.json()["codice_destinatario"] == "ABC1234"
        a = s.post(f"{API}/articles", json={"codice": "TEST_T8OK", "descrizione": "ok", "prezzo": 5, "aliquota": 0, "natura": "N2.2"})
        assert a.status_code == 200 and a.json()["natura"] == "N2.2"
        i = s.post(f"{API}/invoices", json=inv(ctx["pa"], rif_documento="ORD-1", cig="ABCDE12345"))
        assert i.status_code == 200 and i.json()["cig"] == "ABCDE12345"
        c = s.put(f"{API}/company", json={**COMP, "partita_iva": PIVA, "denominazione": "TEST_T8 Srl mod"})
        assert c.status_code == 200 and s.get(f"{API}/company").json()["denominazione"] == "TEST_T8 Srl mod"

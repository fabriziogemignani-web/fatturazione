# Iteration 13: Reverse charge (N6.x) on passive invoices -> PATCH registration with aliquota_rc, registro IVA acquisti RC rows/totals,
# liquidazione IVA (iva_rc added both to debito and credito, saldo unchanged). Run with: pytest test_iteration13_reverse_charge.py -n 0
import random
import pytest
from test_iteration7_pa_scartate_registro import API, mongo
from test_iteration11_passive import XML
from test_iteration12_iva import comp, user, sess

RUN = str(random.randint(100000, 999999))
TOK, UID = f"test_session_t13_admin_{RUN}", f"test-user-t13-admin-{RUN}"
PIVA_FIX = "01234567890"


def clean_all():
    mongo('db.companies.find({denominazione:/^TEST_T13/}).forEach(c=>{["invoices","parties","payments","passive_invoices","passive_payments"].forEach(k=>db[k].deleteMany({company_id:c.id}));'
          'db.counters.deleteMany({key:{$regex:c.id}}); db.companies.deleteOne({id:c.id});});'
          'db.users.deleteMany({user_id:/^test-user-t13-/}); db.user_sessions.deleteMany({session_token:/^test_session_t13_/});')


def rc_xml(numero, tipo="TD01", data="2026-01-02", rc=(("N6.3", 1000.0),), keep22=True):
    x = XML.decode().replace("<Numero>5674/2026</Numero>", f"<Numero>{numero}</Numero>")
    x = x.replace("<TipoDocumento>TD01</TipoDocumento>", f"<TipoDocumento>{tipo}</TipoDocumento>").replace("<Data>2026-10-30</Data>", f"<Data>{data}</Data>")
    blocks = "".join(f"<DatiRiepilogo><AliquotaIVA>0.00</AliquotaIVA><Natura>{n}</Natura><ImponibileImporto>{v:.2f}</ImponibileImporto><Imposta>0.00</Imposta>"
                     f"<RiferimentoNormativo>Inversione contabile art.17 c.6 DPR 633/72</RiferimentoNormativo></DatiRiepilogo>" for n, v in rc)
    s, e = x.index("<DatiRiepilogo>"), x.index("</DatiRiepilogo>") + len("</DatiRiepilogo>")
    x = x[:e] + blocks + x[e:] if keep22 else x[:s] + blocks + x[e:]
    tot = (574.93 if keep22 else 0) + sum(v for _, v in rc)
    x = x.replace("574.93", f"{tot:.2f}")
    return x.encode()


def up(s, h, name, xml):
    r = s.post(f"{API}/passive/upload", files=[("files", (name, xml, "application/octet-stream"))], headers=h)
    assert r.status_code == 200, r.text
    return r.json()[0]["documenti"][0]["id"]


@pytest.fixture(scope="module")
def ctx():
    clean_all()
    user(UID, TOK, "admin", "[]")
    s = sess(TOK)
    r = s.post(f"{API}/companies", json=comp("TEST_T13 RC Srl", PIVA_FIX))
    assert r.status_code == 200, r.text
    h = {"X-Company-Id": r.json()["id"]}
    ids = {"A": up(s, h, "a.xml", rc_xml(f"T13-{RUN}-A")),                       # 22% 471.25/103.68 + N6.3 1000
           "B": up(s, h, "b.xml", rc_xml(f"T13-{RUN}-B", rc=())),                # plain 22% only
           "NC": up(s, h, "nc.xml", rc_xml(f"T13-{RUN}-NC", tipo="TD04", rc=(("N6.3", 200.0),), keep22=False)),
           "D": up(s, h, "d.xml", rc_xml(f"T13-{RUN}-D", rc=(("N6.3", 300.0), ("N6.3", 100.0)), keep22=False))}
    # B registered in Feb (baseline)
    r = s.patch(f"{API}/passive/{ids['B']}", json={"stato_reg": "registrata", "data_registrazione": "2026-02-05"}, headers=h)
    assert r.status_code == 200 and r.json().get("reverse_charge") is None, r.text
    yield {"s": s, "h": h, "ids": ids}
    clean_all()


def liq(ctx, per="mensile"):
    r = ctx["s"].get(f"{API}/liquidazione-iva", params={"anno": 2026, "periodicita": per}, headers=ctx["h"])
    assert r.status_code == 200, r.text
    return r.json()


class TestPatchRC:
    def test_01_upload_parsed_natura(self, ctx):
        d = ctx["s"].get(f"{API}/passive/{ctx['ids']['A']}", headers=ctx["h"]).json()
        assert [(x["natura"], x["imponibile"], x["imposta"]) for x in d["riepilogo"]] == [(None, 471.25, 103.68), ("N6.3", 1000.0, 0.0)]
        assert d["stato_reg"] == "da_registrare" and not d.get("reverse_charge")

    def test_02_invalid_aliquota_422(self, ctx):
        s, h, pid = ctx["s"], ctx["h"], ctx["ids"]["A"]
        r = s.patch(f"{API}/passive/{pid}", json={"stato_reg": "registrata", "data_registrazione": "2026-02-10", "aliquota_rc": 7}, headers=h)
        assert r.status_code == 422, r.text
        det = r.json()["detail"]
        assert det[0]["loc"] == ["body", "aliquota_rc"], det
        d = s.get(f"{API}/passive/{pid}", headers=h).json()
        assert d["stato_reg"] == "da_registrare" and d.get("protocollo") is None

    def test_03_aliquota_10_then_deregister_clears(self, ctx):
        s, h, pid = ctx["s"], ctx["h"], ctx["ids"]["A"]
        r = s.patch(f"{API}/passive/{pid}", json={"stato_reg": "registrata", "data_registrazione": "2026-02-10", "aliquota_rc": 10}, headers=h)
        assert r.status_code == 200, r.text
        assert [{k: v for k, v in x.items() if k != "idx"} for x in r.json()["reverse_charge"]] == [{"natura": "N6.3", "imponibile": 1000.0, "aliquota": 10.0, "imposta": 100.0}]
        r = s.patch(f"{API}/passive/{pid}", json={"stato_reg": "da_registrare"}, headers=h)
        assert r.status_code == 200 and r.json()["reverse_charge"] is None and r.json()["protocollo"] is None
        d = s.get(f"{API}/passive/{pid}", headers=h).json()
        assert d.get("reverse_charge") is None

    def test_04_default_22(self, ctx):
        s, h, pid = ctx["s"], ctx["h"], ctx["ids"]["A"]
        r = s.patch(f"{API}/passive/{pid}", json={"stato_reg": "registrata", "data_registrazione": "2026-02-10"}, headers=h)
        assert r.status_code == 200, r.text
        d = s.get(f"{API}/passive/{pid}", headers=h).json()
        assert [{k: v for k, v in x.items() if k != "idx"} for x in d["reverse_charge"]] == [{"natura": "N6.3", "imponibile": 1000.0, "aliquota": 22.0, "imposta": 220.0}]
        assert d["stato_reg"] == "registrata" and d["data_registrazione"] == "2026-02-10"

    def test_05_contestata_clears(self, ctx):
        s, h, pid = ctx["s"], ctx["h"], ctx["ids"]["D"]
        r = s.patch(f"{API}/passive/{pid}", json={"stato_reg": "registrata", "data_registrazione": "2026-05-10", "aliquota_rc": 22}, headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["reverse_charge"] and len(r.json()["reverse_charge"]) == 2
        r = s.patch(f"{API}/passive/{pid}", json={"stato_reg": "contestata"}, headers=h)
        assert r.status_code == 200 and r.json()["reverse_charge"] is None


class TestRegistro:
    def test_06_registro_rc_row_and_totals(self, ctx):
        d = ctx["s"].get(f"{API}/registro-iva-acquisti", params={"anno": 2026}, headers=ctx["h"]).json()
        row = next(x for x in d["rows"] if x["id"] == ctx["ids"]["A"])
        rc = [x for x in row["riepilogo"] if x.get("rc")]
        assert rc == [{"aliquota": 22.0, "natura": "N6.3", "imponibile": 1000.0, "imposta": 220.0, "rc": True}], row["riepilogo"]
        tot = {t["codice"]: t for t in d["totali"]}
        assert "N6.3 RC 22%" in tot and tot["N6.3 RC 22%"]["rc"] is True and tot["N6.3 RC 22%"]["imposta"] == 220.0, d["totali"]
        assert tot["22%"]["rc"] is False and tot["22%"]["documenti"] == 2
        assert d["imposta_rc"] == 220.0
        assert d["imposta"] == round(2 * 103.68 + 220, 2) and d["imponibile"] == round(2 * 471.25 + 1000, 2)
        assert "_id" not in str(d)

    def test_07_td04_negative(self, ctx):
        s, h, pid = ctx["s"], ctx["h"], ctx["ids"]["NC"]
        r = s.patch(f"{API}/passive/{pid}", json={"stato_reg": "registrata", "data_registrazione": "2026-02-20"}, headers=h)
        assert r.status_code == 200 and r.json()["reverse_charge"][0]["imposta"] == 44.0, r.text
        d = s.get(f"{API}/registro-iva-acquisti", params={"anno": 2026}, headers=h).json()
        row = next(x for x in d["rows"] if x["id"] == pid)
        assert row["riepilogo"] == [{"aliquota": 22.0, "natura": "N6.3", "imponibile": -200.0, "imposta": -44.0, "rc": True}] and row["totale"] == -200.0
        assert d["imposta_rc"] == 176.0
        tot = {t["codice"]: t for t in d["totali"]}
        assert tot["N6.3 RC 22%"]["imposta"] == 176.0 and tot["N6.3 RC 22%"]["imponibile"] == 800.0


class TestLiquidazione:
    def test_08_mensile(self, ctx):
        p = liq(ctx)["periodi"]
        feb = p[1]
        assert feb["iva_rc"] == 176.0, feb
        assert feb["iva_debito"] == 176.0 and feb["iva_credito"] == round(2 * 103.68 + 176, 2)
        assert feb["saldo"] == round(-2 * 103.68, 2)  # saldo unchanged vs no-RC
        assert all(x["iva_rc"] == 0 for i, x in enumerate(p) if i != 1)

    def test_09_trimestrale(self, ctx):
        q1 = liq(ctx, "trimestrale")["periodi"][0]
        assert q1["iva_rc"] == 176.0 and q1["iva_debito"] == 176.0 and q1["saldo"] == -207.36 and q1["interessi"] == 0

    def test_10_saldo_unchanged_after_deregister(self, ctx):
        s, h = ctx["s"], ctx["h"]
        before = liq(ctx)
        for k in ("A", "NC"):
            assert s.patch(f"{API}/passive/{ctx['ids'][k]}", json={"stato_reg": "da_registrare"}, headers=h).status_code == 200
        after = liq(ctx)
        assert after["periodi"][1]["iva_rc"] == 0 and after["periodi"][1]["saldo"] == -103.68
        # re-register A at 22 -> diff in saldo only from A's 103.68 ordinary credit
        assert s.patch(f"{API}/passive/{ctx['ids']['A']}", json={"stato_reg": "registrata", "data_registrazione": "2026-02-10"}, headers=h).status_code == 200
        again = liq(ctx)
        assert again["periodi"][1]["iva_rc"] == 220.0 and again["periodi"][1]["saldo"] == -207.36
        assert before["periodi"][1]["saldo"] == again["periodi"][1]["saldo"]


class TestEdge:
    def test_11_duplicate_natura_rows(self, ctx):
        """Two DatiRiepilogo with same N6.3 natura (300 + 100): register must show imposta 66 + 22 = 88."""
        s, h, pid = ctx["s"], ctx["h"], ctx["ids"]["D"]
        assert s.patch(f"{API}/passive/{pid}", json={"stato_reg": "registrata", "data_registrazione": "2026-05-10"}, headers=h).status_code == 200
        d = s.get(f"{API}/registro-iva-acquisti", params={"anno": 2026, "dal": "2026-05-01", "al": "2026-05-31"}, headers=h).json()
        row = d["rows"][0]
        assert [x["imposta"] for x in row["riepilogo"]] == [66.0, 22.0], row["riepilogo"]
        assert d["imposta_rc"] == 88.0

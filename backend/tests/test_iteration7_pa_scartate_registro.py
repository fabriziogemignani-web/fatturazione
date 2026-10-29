# Iteration 7: PA clients (codice univoco 6, split payment), CIG/CUP/rif on invoices + FPA12 XML,
# correction of SDI-rejected (scartata) invoices, registro numerazione endpoint, storno copying PA data.
# Run with: pytest test_iteration7_pa_scartate_registro.py -n 0
import os
import subprocess
import xml.etree.ElementTree as ET
from datetime import date
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
API = f"{BASE_URL.rstrip('/')}/api"
TOK = "test_session_t7_admin"
UID = "test-user-t7-admin"
PIVA = "77777777771"
TODAY = date.today().isoformat()
YEAR = date.today().year
PREV = YEAR - 1


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


def party(name, codice="ABC1234", pa=False, split=False, **kw):
    return {"tipo": "cliente", "denominazione": name, "partita_iva": kw.pop("piva", "01234567890"), "codice_fiscale": kw.pop("cf", ""),
            "codice_destinatario": codice, "pubblica_amministrazione": pa, "split_payment": split,
            "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT", **kw}


def inv(pid, data=TODAY, numero=None, price=1000, **kw):
    d = {"tipo_documento": "TD01", "data": data, "party_id": pid, "modalita_pagamento": "MP05",
         "lines": [{"descrizione": "Servizio", "quantita": 1, "prezzo_unitario": price, "aliquota": 22}], **kw}
    if numero is not None:
        d["numero"] = numero
    return d


def strip_ns(xml):
    root = ET.fromstring(xml.encode())
    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


@pytest.fixture(scope="module")
def ctx():
    mongo(f'db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});'
          f'db.users.insertOne({{user_id:"{UID}", email:"test.user.t7.admin@example.com", name:"TEST_T7 Admin", picture:"", role:"admin", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
          f'db.user_sessions.insertOne({{user_id:"{UID}", session_token:"{TOK}", expires_at:new Date(Date.now()+7*864e5), created_at:new Date().toISOString()}});')
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {TOK}"
    old = mongo(f'const c=db.companies.findOne({{partita_iva:"{PIVA}"}}); print(c?c.id:"")')
    if old:
        mongo(f'db.invoices.deleteMany({{company_id:"{old}"}}); db.parties.deleteMany({{company_id:"{old}"}}); db.companies.deleteMany({{id:"{old}"}});')
    r = s.post(f"{API}/companies", json={"denominazione": "TEST_T7 PA Srl", "partita_iva": PIVA, "codice_fiscale": PIVA, "regime_fiscale": "RF01",
                                         "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    h = {"X-Company-Id": cid}
    yield {"s": s, "h": h, "cid": cid, "st": {}}
    mongo(f'db.invoices.deleteMany({{company_id:"{cid}"}}); db.parties.deleteMany({{company_id:"{cid}"}}); db.counters.deleteMany({{key:"progressivo_{cid}"}});'
          f'db.companies.deleteMany({{id:"{cid}"}}); db.users.deleteMany({{user_id:"{UID}"}}); db.user_sessions.deleteMany({{user_id:"{UID}"}});')


class TestPartyPA:
    def test_01_pa_codice_must_be_6(self, ctx):
        s, h = ctx["s"], ctx["h"]
        for c in ("ABC1234", "", "AB12", "0000000"):
            r = s.post(f"{API}/parties", json=party("TEST_T7 PA bad", codice=c, pa=True), headers=h)
            assert r.status_code == 422, (c, r.text)

    def test_02_pa_valid_with_split(self, ctx):
        s, h = ctx["s"], ctx["h"]
        r = s.post(f"{API}/parties", json=party("TEST_T7 Comune Split", codice="ufab12", pa=True, split=True, cf="80012345678", piva="80012345678"), headers=h)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["codice_destinatario"] == "UFAB12" and d["pubblica_amministrazione"] is True and d["split_payment"] is True
        ctx["st"]["pa_split"] = d["id"]
        r = s.post(f"{API}/parties", json=party("TEST_T7 Ente NoSplit", codice="UFZZ99", pa=True, split=False, piva="80012345679"), headers=h)
        assert r.status_code == 200 and r.json()["split_payment"] is False
        ctx["st"]["pa_nosplit"] = r.json()["id"]

    def test_03_non_pa_rules(self, ctx):
        s, h = ctx["s"], ctx["h"]
        assert s.post(f"{API}/parties", json=party("TEST_T7 B2B bad", codice="ABC123"), headers=h).status_code == 422
        r = s.post(f"{API}/parties", json=party("TEST_T7 B2B", codice="", split=True, piva="01234567891"), headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["codice_destinatario"] == "0000000" and r.json()["split_payment"] is False
        ctx["st"]["b2b_bad"] = r.json()["id"]  # 0000000 and no PEC -> will be rejected by SDI
        r = s.post(f"{API}/parties", json=party("TEST_T7 B2B ok", codice="ABC1234", piva="01234567892"), headers=h)
        assert r.status_code == 200
        ctx["st"]["b2b"] = r.json()["id"]

    def test_04_update_party_pa_toggle(self, ctx):
        s, h = ctx["s"], ctx["h"]
        pid = ctx["st"]["pa_nosplit"]
        r = s.put(f"{API}/parties/{pid}", json=party("TEST_T7 Ente NoSplit", codice="UFZZ99", pa=False, split=True, piva="80012345679"), headers=h)
        assert r.status_code == 422  # 6-char code no longer valid for B2B
        r = s.put(f"{API}/parties/{pid}", json=party("TEST_T7 Ente NoSplit", codice="UFZZ99", pa=True, piva="80012345679"), headers=h)
        assert r.status_code == 200
        lst = s.get(f"{API}/parties", params={"tipo": "cliente"}, headers=h).json()
        assert any(p["id"] == pid and p["pubblica_amministrazione"] for p in lst)


class TestPAInvoice:
    def test_05_cig_without_rif_422(self, ctx):
        r = ctx["s"].post(f"{API}/invoices", json=inv(ctx["st"]["pa_split"], cig="ABCDE12345"), headers=ctx["h"])
        assert r.status_code == 422 and "CIG/CUP" in r.text

    def test_06_cig_cup_format_422(self, ctx):
        s, h, pid = ctx["s"], ctx["h"], ctx["st"]["pa_split"]
        assert s.post(f"{API}/invoices", json=inv(pid, rif_documento="ORD1", cig="ABC123456"), headers=h).status_code == 422
        assert s.post(f"{API}/invoices", json=inv(pid, rif_documento="ORD1", cup="ABC"), headers=h).status_code == 422
        assert s.post(f"{API}/invoices", json=inv(pid, rif_documento="ORD1", rif_tipo="altro"), headers=h).status_code == 422
        assert s.post(f"{API}/invoices", json=inv(pid, rif_documento="ORD1", rif_data="2025-13-40"), headers=h).status_code == 422

    def test_07_create_pa_split(self, ctx):
        s, h = ctx["s"], ctx["h"]
        r = s.post(f"{API}/invoices", json=inv(ctx["st"]["pa_split"], rif_documento="ORD-2026/15", rif_data=f"{YEAR}-01-10",
                                               cig="abcde12345", cup="J12F34000560007"), headers=h)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["split_payment"] is True and d["iva"] == 220.0 and d["iva_split"] == 220.0
        assert d["totale"] == 1220.0 and d["netto"] == 1000.0
        assert d["cig"] == "ABCDE12345" and d["cup"] == "J12F34000560007" and d["rif_tipo"] == "ordine"
        ctx["st"]["inv_pa"] = d["id"]

    def test_08_xml_fpa12(self, ctx):
        r = ctx["s"].get(f"{API}/invoices/{ctx['st']['inv_pa']}/xml", headers=ctx["h"])
        assert r.status_code == 200
        root = strip_ns(r.text)
        assert root.get("versione") == "FPA12"
        assert root.find(".//FormatoTrasmissione").text == "FPA12"
        assert root.find(".//CodiceDestinatario").text == "UFAB12"
        doa = root.find(".//DatiGenerali/DatiOrdineAcquisto")
        assert doa is not None
        assert [c.tag for c in doa] == ["IdDocumento", "Data", "CodiceCUP", "CodiceCIG"]
        assert doa.find("IdDocumento").text == "ORD-2026/15" and doa.find("CodiceCIG").text == "ABCDE12345"
        assert root.find(".//EsigibilitaIVA").text == "S"
        assert root.find(".//ImportoPagamento").text == "1000.00"
        assert root.find(".//ImportoTotaleDocumento").text == "1220.00"

    def test_09_split_with_ritenuta_and_contratto(self, ctx):
        s, h = ctx["s"], ctx["h"]
        r = s.post(f"{API}/invoices", json=inv(ctx["st"]["pa_split"], rif_tipo="contratto", rif_documento="CTR9", cig="ZZZZZ99999",
                                               ritenuta={"tipo": "RT02", "aliquota": 20, "causale": "A"}), headers=h)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ritenuta_importo"] == 200.0 and d["netto"] == round(1220 - 200 - 220, 2)
        x = strip_ns(s.get(f"{API}/invoices/{d['id']}/xml", headers=h).text)
        dg = x.find(".//DatiGenerali")
        assert dg.find("DatiContratto") is not None and dg.find("DatiOrdineAcquisto") is None
        assert [c.tag for c in dg.find("DatiContratto")] == ["IdDocumento", "CodiceCIG"]
        assert x.find(".//ImportoPagamento").text == "800.00"
        ctx["st"]["inv_pa2"] = d["id"]

    def test_10_pa_no_split(self, ctx):
        r = ctx["s"].post(f"{API}/invoices", json=inv(ctx["st"]["pa_nosplit"]), headers=ctx["h"])
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["split_payment"] is False and d["netto"] == 1220.0 and d["iva_split"] == 0.0
        x = strip_ns(ctx["s"].get(f"{API}/invoices/{d['id']}/xml", headers=ctx["h"]).text)
        assert x.get("versione") == "FPA12" and x.find(".//EsigibilitaIVA").text == "I"
        assert x.find(".//DatiOrdineAcquisto") is None  # no rif given

    def test_11_non_pa_blanks_fields(self, ctx):
        s, h = ctx["s"], ctx["h"]
        r = s.post(f"{API}/invoices", json=inv(ctx["st"]["b2b"], rif_documento="X1", cig="ABCDE12345", cup="J12F34000560007"), headers=h)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["cig"] == "" and d["cup"] == "" and d["rif_documento"] == "" and d["split_payment"] is False
        x = strip_ns(s.get(f"{API}/invoices/{d['id']}/xml", headers=h).text)
        assert x.get("versione") == "FPR12" and x.find(".//CodiceDestinatario").text == "ABC1234"
        assert x.find(".//DatiOrdineAcquisto") is None and x.find(".//EsigibilitaIVA").text == "I"

    def test_12_storno_copies_pa_fields(self, ctx):
        s, h = ctx["s"], ctx["h"]
        iid = ctx["st"]["inv_pa"]
        assert s.post(f"{API}/invoices/{iid}/send", headers=h).status_code == 200
        assert s.post(f"{API}/invoices/{iid}/refresh", headers=h).json()["status"] == "consegnata"
        r = s.post(f"{API}/invoices/{iid}/storno-totale", json={"invia": False}, headers=h)
        assert r.status_code == 200, r.text
        nc = r.json()
        assert nc["tipo_documento"] == "TD04" and nc["numero_display"] == f"1/NC/{YEAR}"
        assert nc["cig"] == "ABCDE12345" and nc["cup"] == "J12F34000560007" and nc["rif_documento"] == "ORD-2026/15"
        assert nc["rif_data"] == f"{YEAR}-01-10" and nc["split_payment"] is True and nc["totale"] == 1220.0
        x = strip_ns(s.get(f"{API}/invoices/{nc['id']}/xml", headers=h).text)
        tags = [c.tag for c in x.find(".//DatiGenerali")]
        assert tags.index("DatiOrdineAcquisto") < tags.index("DatiFattureCollegate")


class TestScartata:
    def test_13_reject_flow(self, ctx):
        s, h = ctx["s"], ctx["h"]
        r = s.post(f"{API}/invoices", json=inv(ctx["st"]["b2b_bad"], price=500), headers=h)
        assert r.status_code == 200, r.text
        iid = r.json()["id"]
        ctx["st"]["scart"], ctx["st"]["scart_num"] = iid, r.json()["numero"]
        assert s.post(f"{API}/invoices/{iid}/send", headers=h).json()["status"] == "inviata"
        # PUT/DELETE on inviata -> 400
        assert s.put(f"{API}/invoices/{iid}", json=inv(ctx["st"]["b2b_bad"], price=500), headers=h).status_code == 400
        assert s.delete(f"{API}/invoices/{iid}", headers=h).status_code == 400
        r = s.post(f"{API}/invoices/{iid}/refresh", headers=h)
        assert r.json()["status"] == "scartata" and "00426" in r.json()["sdi_message"]

    def test_14_scartata_number_change_and_delete_blocked(self, ctx):
        s, h, iid = ctx["s"], ctx["h"], ctx["st"]["scart"]
        r = s.put(f"{API}/invoices/{iid}", json=inv(ctx["st"]["b2b_bad"], numero=ctx["st"]["scart_num"] + 1, price=500), headers=h)
        assert r.status_code == 400 and "stesso numero" in r.json()["detail"]
        r = s.delete(f"{API}/invoices/{iid}", headers=h)
        assert r.status_code == 400

    def test_15_correct_and_resend(self, ctx):
        s, h, iid, pid = ctx["s"], ctx["h"], ctx["st"]["scart"], ctx["st"]["b2b_bad"]
        # fix the client (add PEC), then save correction on invoice
        assert s.put(f"{API}/parties/{pid}", json=party("TEST_T7 B2B", codice="", piva="01234567891", pec="test@pec.example.com"), headers=h).status_code == 200
        r = s.put(f"{API}/invoices/{iid}", json=inv(pid, numero=ctx["st"]["scart_num"], price=600, causale="Corretta"), headers=h)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "scartata" and d["totale"] == 732.0 and d["numero"] == ctx["st"]["scart_num"]
        assert d["cliente"]["pec"] == "test@pec.example.com"
        assert any("Corretta dopo lo scarto" in (e.get("message") or "") for e in d["sdi_history"])
        # PUT without numero also allowed
        assert s.put(f"{API}/invoices/{iid}", json=inv(pid, price=600), headers=h).status_code == 200
        r = s.post(f"{API}/invoices/{iid}/send", headers=h)
        assert r.status_code == 200 and r.json()["status"] == "inviata" and r.json()["numero"] == ctx["st"]["scart_num"]
        r = s.post(f"{API}/invoices/{iid}/refresh", headers=h)
        assert r.json()["status"] == "consegnata", r.json()["sdi_message"]
        assert s.put(f"{API}/invoices/{iid}", json=inv(pid, price=600), headers=h).status_code == 400
        assert s.delete(f"{API}/invoices/{iid}", headers=h).status_code == 400


class TestRegistro:
    def test_16_registro_gap(self, ctx):
        s, h, pid = ctx["s"], ctx["h"], ctx["st"]["b2b"]
        ids = []
        for n, dd in ((1, "03-01"), (2, "03-05"), (3, "03-10")):
            r = s.post(f"{API}/invoices", json=inv(pid, data=f"{PREV}-{dd}"), headers=h)
            assert r.status_code == 200 and r.json()["numero"] == n, r.text
            ids.append(r.json()["id"])
        # number > max+1 rejected
        r = s.post(f"{API}/invoices", json=inv(pid, data=f"{PREV}-03-20", numero=6), headers=h)
        assert r.status_code == 400 and "progressiva" in r.json()["detail"]
        r = s.put(f"{API}/invoices/{ids[1]}", json=inv(pid, data=f"{PREV}-03-12", numero=4), headers=h)
        assert r.status_code == 200, r.text
        g = s.get(f"{API}/registro", params={"anno": PREV, "sezionale": ""}, headers=h).json()
        assert g["anno"] == PREV and PREV in g["anni"] and YEAR in g["anni"]
        assert g["documenti"] == 3 and g["liberi"] == 1 and g["primo"] == 1
        assert g["prossimo"]["numero"] == 5 and g["prossimo"]["numero_display"] == f"5/{PREV}" and g["prossimo"]["data_min"] == f"{PREV}-03-12"
        assert [r["numero"] for r in g["rows"]] == [1, 2, 3, 4]
        free = g["rows"][1]
        assert free["libero"] is True and free["data_min"] == f"{PREV}-03-01" and free["data_max"] == f"{PREV}-03-10"
        assert "_id" not in str(g)
        ctx["st"]["reg_ids"] = ids

    def test_17_fill_gap(self, ctx):
        s, h, pid = ctx["s"], ctx["h"], ctx["st"]["b2b"]
        r = s.post(f"{API}/invoices", json=inv(pid, data=f"{PREV}-03-05", numero=2), headers=h)
        assert r.status_code == 200, r.text
        g = s.get(f"{API}/registro", params={"anno": PREV}, headers=h).json()
        assert g["liberi"] == 0 and g["documenti"] == 4

    def test_18_registro_default_and_nc(self, ctx):
        s, h = ctx["s"], ctx["h"]
        g = s.get(f"{API}/registro", headers=h).json()
        assert g["anno"] == YEAR and g["sezionale"] == "" and g["documenti"] >= 5
        nc = s.get(f"{API}/registro", params={"anno": YEAR, "sezionale": "NC"}, headers=h).json()
        assert nc["documenti"] == 1 and nc["rows"][0]["numero_display"] == f"1/NC/{YEAR}" and nc["prossimo"]["numero"] == 2
        nc0 = s.get(f"{API}/registro", params={"anno": PREV, "sezionale": "NC"}, headers=h).json()
        assert nc0["documenti"] == 0 and nc0["primo"] is None and nc0["prossimo"]["numero"] == 1
        assert s.get(f"{API}/registro", params={"sezionale": "XX"}, headers=h).status_code == 422
        assert requests.get(f"{API}/registro").status_code == 401

# Iteration 21: Archivio fatture (imported importfatture project) - /api/archivio/*
# upload (xml/p7m/zip/nested/multibody/errors), classification, duplicates, list/search/sort/filters,
# export CSV, detail/xml/delete, anagrafiche, stats, tenancy, roles, isolation from Fatturazione.
# Run with: pytest test_iteration21_archivio.py -n 0
import base64
import io
import os
import subprocess
import tempfile
import zipfile
import pytest
import requests
from test_iteration7_pa_scartate_registro import API, mongo

TOK, UID = "test_session_t21_admin", "test-user-t21-admin"
TOK_OP, UID_OP = "test_session_t21_op", "test-user-t21-op"
TOK_CO, UID_CO = "test_session_t21_co", "test-user-t21-co"
PA, PB = "86999999001", "86999999002"
SUP1, SUP2, CLI1 = "01111111111", "02222222222", "03333333333"
STATE = {}


def fe(ced_piva, ces_piva, bodies, ced_name="TEST_Fornitore", ces_name="TEST_Cliente", ced_paese="IT"):
    bxml = ""
    for b in bodies:
        num, data, td, tot = b["numero"], b.get("data", "2024-03-15"), b.get("td", "TD01"), b.get("imponibile", 100.0)
        iva = round(tot * 0.22, 2)
        bxml += f"""<FatturaElettronicaBody><DatiGenerali><DatiGeneraliDocumento><TipoDocumento>{td}</TipoDocumento><Divisa>EUR</Divisa>
<Data>{data}</Data><Numero>{num}</Numero><ImportoTotaleDocumento>{tot + iva:.2f}</ImportoTotaleDocumento><Causale>{b.get('causale', 'Causale test')}</Causale>
</DatiGeneraliDocumento></DatiGenerali><DatiBeniServizi><DettaglioLinee><NumeroLinea>1</NumeroLinea><Descrizione>{b.get('desc', 'Consulenza')}</Descrizione>
<Quantita>1.00</Quantita><UnitaMisura>h</UnitaMisura><PrezzoUnitario>{tot:.2f}</PrezzoUnitario><PrezzoTotale>{tot:.2f}</PrezzoTotale><AliquotaIVA>22.00</AliquotaIVA></DettaglioLinee>
<DatiRiepilogo><AliquotaIVA>22.00</AliquotaIVA><ImponibileImporto>{tot:.2f}</ImponibileImporto><Imposta>{iva:.2f}</Imposta><EsigibilitaIVA>I</EsigibilitaIVA></DatiRiepilogo>
</DatiBeniServizi><DatiPagamento><CondizioniPagamento>TP02</CondizioniPagamento><DettaglioPagamento><ModalitaPagamento>MP05</ModalitaPagamento>
<DataScadenzaPagamento>2024-04-15</DataScadenzaPagamento><ImportoPagamento>{tot + iva:.2f}</ImportoPagamento><IBAN>IT60X0542811101000000123456</IBAN></DettaglioPagamento></DatiPagamento></FatturaElettronicaBody>"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica versione="FPR12" xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
<FatturaElettronicaHeader><DatiTrasmissione><IdTrasmittente><IdPaese>IT</IdPaese><IdCodice>{ced_piva}</IdCodice></IdTrasmittente>
<ProgressivoInvio>00001</ProgressivoInvio><FormatoTrasmissione>FPR12</FormatoTrasmissione><CodiceDestinatario>0000000</CodiceDestinatario></DatiTrasmissione>
<CedentePrestatore><DatiAnagrafici><IdFiscaleIVA><IdPaese>{ced_paese}</IdPaese><IdCodice>{ced_piva}</IdCodice></IdFiscaleIVA><Anagrafica><Denominazione>{ced_name}</Denominazione></Anagrafica><RegimeFiscale>RF01</RegimeFiscale></DatiAnagrafici>
<Sede><Indirizzo>Via Roma</Indirizzo><NumeroCivico>1</NumeroCivico><CAP>00100</CAP><Comune>Roma</Comune><Provincia>RM</Provincia><Nazione>IT</Nazione></Sede></CedentePrestatore>
<CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>{ces_piva}</IdCodice></IdFiscaleIVA><Anagrafica><Denominazione>{ces_name}</Denominazione></Anagrafica></DatiAnagrafici>
<Sede><Indirizzo>Via Milano 2</Indirizzo><CAP>20100</CAP><Comune>Milano</Comune><Provincia>MI</Provincia><Nazione>IT</Nazione></Sede></CessionarioCommittente>
</FatturaElettronicaHeader>{bxml}</p:FatturaElettronica>""".encode()


def p7m(xml: bytes, b64=False) -> bytes:
    d = tempfile.mkdtemp()
    key, crt, src, out = (os.path.join(d, x) for x in ("k.pem", "c.pem", "in.xml", "out.p7m"))
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key, "-out", crt, "-days", "1", "-subj", "/CN=TEST"], capture_output=True, check=True)
    open(src, "wb").write(xml)
    subprocess.run(["openssl", "cms", "-sign", "-binary", "-nodetach", "-in", src, "-signer", crt, "-inkey", key, "-outform", "DER", "-out", out], capture_output=True, check=True)
    data = open(out, "rb").read()
    return base64.b64encode(data) if b64 else data


def zipof(entries) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, c in entries:
            z.writestr(n, c)
    return buf.getvalue()


def sess(tok, cid=None):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    if cid:
        s.headers["X-Company-Id"] = cid
    return s


def clean():
    mongo(f'db.companies.find({{partita_iva:{{$in:["{PA}","{PB}"]}}}}).forEach(c=>{{db.arch_invoices.deleteMany({{company_id:c.id}}); db.arch_anagrafiche.deleteMany({{company_id:c.id}});'
          f'db.users.updateMany({{}}, {{$pull:{{company_ids:c.id}}}}); db.companies.deleteOne({{id:c.id}});}});'
          f'db.users.deleteMany({{user_id:{{$in:["{UID}","{UID_OP}","{UID_CO}"]}}}}); db.user_sessions.deleteMany({{user_id:{{$in:["{UID}","{UID_OP}","{UID_CO}"]}}}});')


@pytest.fixture(scope="module", autouse=True)
def setup():
    clean()
    for uid, tok, role in ((UID, TOK, "admin"), (UID_OP, TOK_OP, "operatore"), (UID_CO, TOK_CO, "contabile")):
        mongo(f'db.users.insertOne({{user_id:"{uid}", email:"test.user.{uid}@example.com", name:"TEST_{uid}", picture:"", role:"{role}", status:"approved", company_ids:[], created_at:new Date().toISOString()}});'
              f'db.user_sessions.insertOne({{user_id:"{uid}", session_token:"{tok}", expires_at:new Date(Date.now()+864e5), created_at:new Date().toISOString()}});')
    s = sess(TOK)
    for key, piva, name in (("A", PA, "TEST_T21 A Srl"), ("B", PB, "TEST_T21 B Srl")):
        r = s.post(f"{API}/companies", json={"denominazione": name, "partita_iva": piva, "codice_fiscale": piva, "regime_fiscale": "RF01",
                                             "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
        assert r.status_code == 200, r.text
        STATE[key] = r.json()["id"]
    mongo(f'db.users.updateMany({{user_id:{{$in:["{UID_OP}","{UID_CO}"]}}}}, {{$set:{{company_ids:["{STATE["A"]}"]}}}})')
    yield
    clean()


def up(files, tok=TOK, cid=None):
    return sess(tok, cid or STATE["A"]).post(f"{API}/archivio/upload", files=[("files", (n, c)) for n, c in files])


# --- upload & classification ---
def test_01_upload_xml_attiva_passiva_and_unrelated():
    r = up([("att1.xml", fe(PA, CLI1, [{"numero": "2", "data": "2024-01-10"}], ced_name="TEST_T21 A Srl", ces_name="TEST_Cliente Uno")),
            ("pas1.xml", fe(SUP1, PA, [{"numero": "FV/10", "data": "2024-02-05", "desc": "Carta igienica speciale"}], ced_name="TEST_Fornitore Uno")),
            ("none.xml", fe(SUP1, SUP2, [{"numero": "99"}]))])
    assert r.status_code == 200, r.text
    res = r.json()["results"]
    assert [x["status"] for x in res] == ["ok", "ok", "error"], res
    assert res[0]["tipo"] == "attiva" and res[1]["tipo"] == "passiva"
    assert "non compare né come cedente né come cessionario" in res[2]["message"]
    STATE["att1"], STATE["pas1"] = res[0]["id"], res[1]["id"]


def test_02_duplicate():
    r = up([("dup.xml", fe(PA, CLI1, [{"numero": "2", "data": "2024-01-10"}]))])
    assert r.json()["results"][0]["status"] == "duplicate"


def test_03_p7m_der_and_base64():
    r = up([("p1.xml.p7m", p7m(fe(SUP1, PA, [{"numero": "FV/2", "data": "2024-02-01"}], ced_name="TEST_Fornitore Uno"))),
            ("p2.xml.p7m", p7m(fe(SUP2, PA, [{"numero": "A-7", "data": "2023-11-20"}], ced_name="TEST_Fornitore Due"), b64=True))])
    res = r.json()["results"]
    assert [x["status"] for x in res] == ["ok", "ok"], res


def test_04_zip_nested_and_multibody():
    inner2 = zipof([("deep.xml", fe(PA, CLI1, [{"numero": "11", "data": "2024-05-01"}]))])
    inner = zipof([("multi.xml", fe(PA, CLI1, [{"numero": "10", "data": "2024-04-01"}, {"numero": "1", "data": "2024-01-02", "td": "TD04"}])),
                   ("z2.zip", inner2), ("__MACOSX/._x.xml", b"junk"), ("readme.txt", b"x")])
    r = up([("outer.zip", zipof([("dir/inner.zip", inner)]))])
    res = r.json()["results"]
    assert sorted(x["status"] for x in res) == ["ok", "ok", "ok"], res
    assert any("deep.xml" in x["filename"] for x in res)


def test_05_zip_too_deep():
    z = fe(PA, CLI1, [{"numero": "500"}])
    for i in range(4):
        z = zipof([(f"l{i}.zip" if i else "x.xml", z)])
    res = up([("deep.zip", z)]).json()["results"]
    assert any(x["status"] == "error" and "annidati" in x["message"] for x in res), res


def test_06_invalid_files_no_500():
    xxe = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><FatturaElettronica>&e;</FatturaElettronica>'
    r = up([("bad.xml", b"<not xml"), ("xxe.xml", xxe), ("bad.zip", b"PKnotzip"), ("x.pdf", b"%PDF"), ("other.xml", b"<root/>"),
            ("nonum.xml", fe(PA, CLI1, [{"numero": ""}]))])
    assert r.status_code == 200, r.text
    res = r.json()["results"]
    assert all(x["status"] == "error" for x in res), res
    assert "DTD" in res[1]["message"] or "non valido" in res[1]["message"]


def test_07_upload_roles_and_limits():
    assert up([("a.xml", fe(PA, CLI1, [{"numero": "777"}]))], tok=TOK_OP).status_code == 403
    r = up([("c.xml", fe(PA, CLI1, [{"numero": "3", "data": "2024-01-20"}]))], tok=TOK_CO)
    assert r.status_code == 200 and r.json()["results"][0]["status"] == "ok"
    assert up([(f"f{i}.xml", b"<x/>") for i in range(51)]).status_code == 400
    mongo(f'db.companies.updateOne({{id:"{STATE["B"]}"}}, {{$set:{{partita_iva:""}}}})')
    try:
        r = up([("a.xml", fe(PB, CLI1, [{"numero": "1"}]))], cid=STATE["B"])
        assert r.status_code == 400 and "Partita IVA" in r.json()["detail"]
    finally:
        mongo(f'db.companies.updateOne({{id:"{STATE["B"]}"}}, {{$set:{{partita_iva:"{PB}"}}}})')


def test_08_vat_with_it_prefix_matches():
    r = up([("pref.xml", fe(SUP2, "IT" + PA, [{"numero": "A-12", "data": "2023-12-01"}], ced_name="TEST_Fornitore Due"))])
    assert r.json()["results"][0]["status"] == "ok", r.json()


# --- list / search / sort / filters ---
def test_10_list_sort_natural():
    s = sess(TOK, STATE["A"])
    d = s.get(f"{API}/archivio/invoices", params={"tipo": "attiva", "anno": 2024}).json()
    nums = [x["numero"] for x in d["items"]]
    assert nums == ["1", "2", "3", "10", "11"], nums
    assert d["total"] == 5 and "xml" not in d["items"][0] and "_id" not in d["items"][0]
    desc = [x["numero"] for x in s.get(f"{API}/archivio/invoices", params={"tipo": "attiva", "anno": 2024, "order": "desc"}).json()["items"]]
    assert desc == nums[::-1]
    assert d["somma_totale"] == round(sum(x["totale"] for x in d["items"]), 2)


def test_11_search_filters_paging():
    s = sess(TOK, STATE["A"])
    g = lambda **p: s.get(f"{API}/archivio/invoices", params=p).json()
    assert [x["numero"] for x in g(q="igienica")["items"]] == ["FV/10"]
    assert g(q="Fornitore Due", tipo="passiva")["total"] == 2
    assert g(q=SUP1)["total"] == 2
    assert g(q="deep.xml")["total"] == 1
    assert g(q="(.*")["total"] == 0
    assert [x["numero"] for x in g(tipo_documento="td04")["items"]] == ["1"]
    p = g(tipo="attiva", limit=2, page=3)
    assert len(p["items"]) == 1 and p["total"] == 5
    assert s.get(f"{API}/archivio/years", params={"tipo": "passiva"}).json() == [2024, 2023]
    dt = s.get(f"{API}/archivio/doc-types", params={"tipo": "attiva"}).json()
    assert {"code": "TD04", "n": 1} in dt and {"code": "TD01", "n": 4} in dt


def test_12_export_csv():
    s = sess(TOK, STATE["A"])
    mongo(f'db.arch_invoices.updateOne({{id:"{STATE["pas1"]}"}}, {{$set:{{controparte_nome:"=HYPERLINK(1)"}}}})')
    r = s.get(f"{API}/archivio/export", params={"tipo": "passiva"})
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    txt = r.content.decode("utf-8-sig")
    lines = txt.strip().splitlines()
    assert lines[0].startswith("Tipo;Anno;Numero") and len(lines) == 5
    assert "'=HYPERLINK(1)" in txt and "122,00" in txt


# --- detail / xml / delete ---
def test_13_detail_and_xml():
    s = sess(TOK, STATE["A"])
    d = s.get(f"{API}/archivio/invoices/{STATE['pas1']}").json()
    assert d["numero"] == "FV/10" and d["righe"][0]["descrizione"] == "Carta igienica speciale"
    assert d["riepilogo"][0]["imposta"] == 22.0 and d["pagamenti"][0]["iban"].startswith("IT60") and "xml" not in d
    x = s.get(f"{API}/archivio/invoices/{STATE['pas1']}/xml")
    assert x.status_code == 200 and b"FatturaElettronica" in x.content and ".xml" in x.headers["content-disposition"]
    assert s.get(f"{API}/archivio/invoices/nonexistent").status_code == 404


def test_14_tenancy_isolation():
    sb = sess(TOK, STATE["B"])
    assert sb.get(f"{API}/archivio/invoices").json()["total"] == 0
    assert sb.get(f"{API}/archivio/invoices/{STATE['pas1']}").status_code == 404
    assert sb.get(f"{API}/archivio/invoices/{STATE['pas1']}/xml").status_code == 404
    assert sb.delete(f"{API}/archivio/invoices/{STATE['pas1']}").status_code == 404
    assert sb.get(f"{API}/archivio/anagrafiche").json() == []
    assert sb.get(f"{API}/archivio/stats").json()["per_tipo"] == {}
    # operatore not assigned to B
    assert sess(TOK_OP, STATE["B"]).get(f"{API}/archivio/invoices").status_code == 404
    # operatore can read A
    assert sess(TOK_OP, STATE["A"]).get(f"{API}/archivio/invoices").status_code == 200


def test_15_not_in_fatturazione():
    s = sess(TOK, STATE["A"])
    assert s.get(f"{API}/passive").json() in ([], {"items": []}) or len(s.get(f"{API}/passive").json()) == 0
    assert len(s.get(f"{API}/invoices").json()) == 0
    for ep in ("registro-iva-acquisti", "registro-iva-vendite"):
        r = s.get(f"{API}/{ep}", params={"anno": 2024})
        assert r.status_code == 200 and "FV/10" not in r.text and "TEST_Fornitore" not in r.text


# --- anagrafiche & stats ---
def test_16_anagrafiche():
    s = sess(TOK, STATE["A"])
    forn = s.get(f"{API}/archivio/anagrafiche", params={"ruolo": "fornitore"}).json()
    by = {a["chiave"]: a for a in forn}
    assert set(by) == {SUP1, SUP2}
    assert by[SUP1]["n_fatture"] == 2 and by[SUP2]["n_fatture"] == 2
    cli = s.get(f"{API}/archivio/anagrafiche", params={"ruolo": "cliente"}).json()
    assert [a["chiave"] for a in cli] == [CLI1] and cli[0]["n_fatture"] == 5
    y = s.get(f"{API}/archivio/anagrafiche", params={"ruolo": "fornitore", "anno": 2023}).json()
    assert [a["chiave"] for a in y] == [SUP2]
    assert [a["chiave"] for a in s.get(f"{API}/archivio/anagrafiche", params={"q": "Due"}).json()] == [SUP2]
    det = s.get(f"{API}/archivio/anagrafiche/{by[SUP2]['id']}").json()
    assert {p["anno"]: p["n"] for p in det["per_anno"]} == {2023: 2} and det["n_fatture"] == 2
    lst = s.get(f"{API}/archivio/invoices", params={"anagrafica_id": by[SUP2]["id"]}).json()
    assert lst["total"] == 2
    assert s.get(f"{API}/archivio/anagrafiche/nope").status_code == 404
    STATE["sup1_id"] = by[SUP1]["id"]


def test_17_stats():
    s = sess(TOK, STATE["A"])
    st = s.get(f"{API}/archivio/stats").json()
    assert st["per_tipo"]["attiva"]["n"] == 5 and st["per_tipo"]["passiva"]["n"] == 4
    assert len(st["mensile"]) == 12 and st["n_clienti"] == 1 and st["n_fornitori"] == 2
    assert len(st["recenti"]) == 6 and "xml" not in st["recenti"][0]
    st24 = s.get(f"{API}/archivio/stats", params={"anno": 2024}).json()
    assert st24["per_tipo"]["passiva"]["n"] == 2 and st24["mensile"][1]["passiva"] == 244.0


def test_18_delete_roles_and_orphan_anag():
    s = sess(TOK, STATE["A"])
    lst = s.get(f"{API}/archivio/invoices", params={"anagrafica_id": STATE["sup1_id"]}).json()["items"]
    assert sess(TOK_OP, STATE["A"]).delete(f"{API}/archivio/invoices/{lst[0]['id']}").status_code == 403
    assert sess(TOK_CO, STATE["A"]).delete(f"{API}/archivio/invoices/{lst[0]['id']}").status_code == 200
    assert s.get(f"{API}/archivio/invoices/{lst[0]['id']}").status_code == 404
    assert s.get(f"{API}/archivio/anagrafiche/{STATE['sup1_id']}").status_code == 200
    assert s.delete(f"{API}/archivio/invoices/{lst[1]['id']}").status_code == 200
    assert s.get(f"{API}/archivio/anagrafiche/{STATE['sup1_id']}").status_code == 404
    # re-upload after delete works (dedup freed)
    r = up([("pas1.xml", fe(SUP1, PA, [{"numero": "FV/10", "data": "2024-02-05"}]))])
    assert r.json()["results"][0]["status"] == "ok"


def test_19_unauthenticated_and_no_company():
    assert requests.get(f"{API}/archivio/invoices").status_code == 401
    assert sess(TOK).get(f"{API}/archivio/invoices").status_code == 400

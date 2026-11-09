# Iteration 36: per-company / per-user menu on/off (catalog, PUT endpoints, backend 403 blocking, scheda from anagrafica data)
import os
import uuid
from datetime import date

import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ADMIN = {"email": "fabrizio.gemignani@gmail.com", "password": "Fe-Admin-2aOBey8irzL8"}
PWD = "TestPass-123456"


def piva(base10):
    s = 0
    for i, ch in enumerate(base10):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            d = d - 9 if d > 9 else d
        s += d
    return base10 + str((10 - s % 10) % 10)


@pytest.fixture(scope="module")
def ctx():
    s = requests.Session()
    assert s.post(f"{BASE}/auth/login", json=ADMIN).status_code == 200
    co = piva("07" + uuid.uuid4().int.__str__()[:8])
    r = s.post(f"{BASE}/companies", json={"denominazione": "TEST_T36 Menu Srl", "partita_iva": co, "codice_fiscale": co, "regime_fiscale": "RF01",
                                         "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    s.headers["X-Company-Id"] = cid
    out = {"s": s, "cid": cid, "users": []}
    for k, tipo, name, b in [("cli", "cliente", "TEST_T36 Cliente Srl", "0123456781"), ("forn", "fornitore", "TEST_T36 Fornitore Srl", "0888999112")]:
        pv = piva(b)
        r = s.post(f"{BASE}/parties", json={"tipo": tipo, "denominazione": name, "partita_iva": pv, "codice_fiscale": pv, "codice_destinatario": "ABC1234",
                                            "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"})
        assert r.status_code == 200, r.text
        out[k] = r.json()["id"]
    r = s.post(f"{BASE}/invoices", json={"tipo_documento": "TD01", "data": date.today().isoformat(), "party_id": out["cli"], "modalita_pagamento": "MP05",
                                        "lines": [{"descrizione": "TEST riga", "quantita": 1, "prezzo_unitario": 100, "aliquota": 22}]})
    assert r.status_code == 200, r.text
    out["inv"] = r.json()["id"]
    assert s.post(f"{BASE}/invoices/{out['inv']}/send").status_code == 200
    out["inv_status"] = s.post(f"{BASE}/invoices/{out['inv']}/refresh").json().get("status")
    # non-admin user (contabile)
    email = f"test.user.t36{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(f"{BASE}/auth/register", json={"name": "TEST_T36 Contabile", "email": email, "password": PWD})
    assert r.status_code in (200, 201), r.text
    uid = s.get(f"{BASE}/users").json()
    uid = next(u["user_id"] for u in uid if u["email"] == email)
    out["users"].append(uid)
    r = s.patch(f"{BASE}/users/{uid}", json={"status": "approved", "role": "contabile", "company_ids": [cid]})
    assert r.status_code == 200, r.text
    u = requests.Session()
    assert u.post(f"{BASE}/auth/login", json={"email": email, "password": PWD}).status_code == 200
    u.headers["X-Company-Id"] = cid
    out["u"], out["uid"] = u, uid
    yield out
    s.put(f"{BASE}/companies/{cid}/menu", json={"off": []})
    for x in out["users"]:
        s.delete(f"{BASE}/users/{x}")
    r = s.delete(f"{BASE}/companies/{cid}")
    print("company delete", r.status_code, r.text[:200])


def set_co(ctx, off):
    r = ctx["s"].put(f"{BASE}/companies/{ctx['cid']}/menu", json={"off": off})
    assert r.status_code == 200, r.text
    return r.json()


# --- catalog & PUT endpoints
def test_catalog(ctx):
    d = ctx["s"].get(f"{BASE}/menu-voci").json()
    assert len(d) == 24 and all(set(x) == {"id", "gruppo", "label"} for x in d)
    assert ctx["u"].get(f"{BASE}/menu-voci").status_code == 403


def test_put_company_menu_validation(ctx):
    r = ctx["s"].put(f"{BASE}/companies/{ctx['cid']}/menu", json={"off": ["registro", "nonexistent"]})
    assert r.status_code == 422
    assert ctx["u"].put(f"{BASE}/companies/{ctx['cid']}/menu", json={"off": []}).status_code == 403
    assert ctx["s"].put(f"{BASE}/companies/nope/menu", json={"off": []}).status_code == 404
    assert set_co(ctx, ["registro", "registro", "scadenzario"]) == {"off": ["registro", "scadenzario"]}
    co = next(c for c in ctx["s"].get(f"{BASE}/companies").json() if c["id"] == ctx["cid"])
    assert co["menu_off"] == ["registro", "scadenzario"]
    set_co(ctx, [])


def test_user_menu_union_and_admin_ignore(ctx):
    s, u, uid = ctx["s"], ctx["u"], ctx["uid"]
    assert u.put(f"{BASE}/users/{uid}/menu", json={"off": ["fatture"]}).status_code == 403
    assert s.put(f"{BASE}/users/{uid}/menu", json={"off": ["bad"]}).status_code == 422
    assert s.put(f"{BASE}/users/{uid}/menu", json={"off": ["magazzino"]}).status_code == 200
    set_co(ctx, ["registro"])
    cu = next(c for c in u.get(f"{BASE}/companies").json() if c["id"] == ctx["cid"])
    assert cu["menu_off"] == ["magazzino", "registro"]
    ca = next(c for c in s.get(f"{BASE}/companies").json() if c["id"] == ctx["cid"])
    assert ca["menu_off"] == ["registro"]
    assert u.get(f"{BASE}/magazzino/articoli").status_code == 403
    assert s.get(f"{BASE}/magazzino/articoli").status_code == 200
    me = s.get(f"{BASE}/auth/me").json()
    assert s.put(f"{BASE}/users/{me['user_id']}/menu", json={"off": []}).status_code == 400
    lu = next(x for x in s.get(f"{BASE}/users").json() if x["user_id"] == uid)
    assert lu.get("menu_off") == ["magazzino"]
    s.put(f"{BASE}/users/{uid}/menu", json={"off": []})
    set_co(ctx, [])


# --- backend blocking
BLOCKS = [
    ("registro", "GET", "/registro", True), ("scadenzario", "GET", "/scadenzario", True),
    ("scadenzario-fornitori", "GET", "/scadenzario-passivo", True),
    ("liquidazione-iva", "GET", "/liquidazione-iva", True), ("liquidazione-iva", "GET", "/contabilita/liquidazioni", True),
    ("mastrini", "GET", "/contabilita/mastrino?conto=05.01.001", True), ("prima-nota", "GET", "/contabilita/registrazioni", True),
    ("bilancio", "GET", "/contabilita/bilancio", True),
    ("piano-conti", "GET", "/contabilita/conti", False), ("piano-conti", "POST", "/contabilita/conti", True),
    ("piano-conti", "PUT", "/contabilita/parametri", True), ("piano-conti", "POST", "/contabilita/causali", True),
    ("anagrafiche", "GET", "/parties", False), ("anagrafiche", "POST", "/parties", True),
    ("articoli", "GET", "/articles", False), ("articoli", "POST", "/articles", True),
    ("fatture", "GET", "/invoices", True), ("fatture", "GET", "/invoices/{inv}/pagamenti", False),
    ("passive", "GET", "/passive", True),
    ("riconciliazione", "GET", "/banca/conti", True), ("riconciliazione", "GET", "/banca/previsione", False),
    ("previsione-cassa", "GET", "/banca/previsione", True), ("previsione-cassa", "GET", "/banca/conti", False),
    ("magazzino", "GET", "/magazzino/riepilogo", True), ("corrispettivi", "GET", "/corrispettivi", True),
    ("registro-iva-vendite", "GET", "/registro-iva-vendite", True), ("registro-iva-acquisti", "GET", "/registro-iva-acquisti", True),
    ("esportazione", "GET", "/export/commercialista", True),
    ("arch-carica", "POST", "/archivio/upload", True), ("arch-anagrafiche", "GET", "/archivio/anagrafiche", True),
    ("arch-attive", "GET", "/archivio/invoices", False),
]


@pytest.mark.parametrize("mid,method,path,blocked", BLOCKS)
def test_block(ctx, mid, method, path, blocked):
    s = ctx["s"]
    set_co(ctx, [mid])
    try:
        r = s.request(method, BASE + path.replace("{inv}", ctx["inv"]), json={} if method in ("POST", "PUT") else None)
        is403 = r.status_code == 403 and "Voce di menu non attiva" in r.text
        assert is403 == blocked, (r.status_code, r.text[:200])
    finally:
        set_co(ctx, [])


def test_unblocked_after_reenable(ctx):
    set_co(ctx, ["registro"])
    assert ctx["s"].get(f"{BASE}/registro").status_code == 403
    set_co(ctx, [])
    assert ctx["s"].get(f"{BASE}/registro").status_code == 200


# --- scheda contabile data (mastrino filtered by party)
def test_mastrino_party(ctx):
    s = ctx["s"]
    yr = date.today().year
    r = s.get(f"{BASE}/contabilita/mastrino", params={"conto": "05.01.001", "dal": f"{yr}-01-01", "al": f"{yr}-12-31", "party_id": ctx["cli"]})
    assert r.status_code == 200, r.text
    d = r.json()
    print("inv status", ctx["inv_status"], "keys", list(d.keys()))
    movs = d.get("movimenti") or d.get("righe") or d.get("rows") or []
    assert len(movs) >= 1, d

# Iteration 37: Comunicazioni module (courtesy invoice email, payment reminders, 3-level dunning, log, menu/module gating)
# Run: pytest tests/test_iteration37_comunicazioni.py -v -n 0  (needs local debug SMTP on 127.0.0.1:1025 for the "ok" path)
import os
import subprocess
import time
import uuid
from datetime import date, timedelta

import pytest
import requests

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ADMIN = {"email": "fabrizio.gemignani@gmail.com", "password": "Fe-Admin-2aOBey8irzL8"}
TODAY = date.today()


def mongo(js):
    return subprocess.run(["mongosh", "--quiet", "--eval", f'use("test_database"); {js}'], capture_output=True, text=True).stdout.strip()


def piva(base10):
    s = 0
    for i, ch in enumerate(base10):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            d = d - 9 if d > 9 else d
        s += d
    return base10 + str((10 - s % 10) % 10)


def smtp_up():
    import socket
    try:
        socket.create_connection(("127.0.0.1", 1025), timeout=1).close()
        return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def ctx():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN)
    assert r.status_code == 200, r.text
    co = piva("0987123451")
    r = s.post(f"{API}/companies", json={"denominazione": "TEST_T37 Comunicazioni Srl", "partita_iva": co, "codice_fiscale": co, "regime_fiscale": "RF01",
                                         "indirizzo": "Via Roma 1", "cap": "00100", "comune": "Roma", "provincia": "RM", "nazione": "IT"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    s.headers["X-Company-Id"] = cid
    out = {"s": s, "cid": cid, "users": []}
    for key, name, pv, email in [("c1", "TEST_Alfa Srl", piva("0123456780"), "alfa@example.com"), ("c2", "TEST_Beta Spa", piva("0555666770"), "beta@example.com"),
                                 ("c3", "TEST_Gamma NoMail Srl", piva("0888999110"), "")]:
        r = s.post(f"{API}/parties", json={"tipo": "cliente", "denominazione": name, "partita_iva": pv, "codice_fiscale": pv, "codice_destinatario": "ABC1234",
                                           "email": email, "indirizzo": "Via X 1", "cap": "20100", "comune": "Milano", "provincia": "MI", "nazione": "IT"})
        assert r.status_code == 200, (key, r.text)
        out[key] = r.json()["id"]

    def mk(pid, days_ago, scad, price=100, send=True):
        r = s.post(f"{API}/invoices", json={"tipo_documento": "TD01", "data": (TODAY - timedelta(days=days_ago)).isoformat(), "party_id": pid, "modalita_pagamento": "MP05",
                                            "scadenza": (TODAY + timedelta(days=scad)).isoformat(),
                                            "lines": [{"descrizione": "TEST riga", "quantita": 1, "prezzo_unitario": price, "aliquota": 22}]})
        assert r.status_code == 200, r.text
        iid = r.json()["id"]
        if send:
            assert s.post(f"{API}/invoices/{iid}/send").status_code == 200
            rr = s.post(f"{API}/invoices/{iid}/refresh")
            assert rr.status_code == 200 and rr.json()["status"] == "consegnata", rr.text
        return iid
    out["mk"] = mk
    out["iA"] = mk(out["c1"], 60, -50, 100)   # c1 overdue 50gg -> lv3
    out["iB"] = mk(out["c1"], 20, -10, 200)   # c1 overdue 10gg -> lv1
    out["iC"] = mk(out["c2"], 3, 3, 300)      # c2 due in 3gg -> promemoria
    out["iD"] = mk(out["c3"], 2, 2, 50)       # c3 no email -> promemoria error
    yield out
    # cleanup only what we created
    mongo(f'["invoices","parties","payments","coa_entries","coa_accounts","coa_causali","coa_iva","sdi_events","audit","com_log"].forEach(k=>db[k].deleteMany({{company_id:"{cid}"}})); '
          f'db.counters.deleteMany({{key:{{$regex:"{cid}"}}}}); db.users.updateMany({{}},{{$pull:{{company_ids:"{cid}"}}}}); db.companies.deleteOne({{id:"{cid}"}});')
    for uid in out["users"]:
        mongo(f'db.users.deleteOne({{user_id:"{uid}"}}); db.user_sessions.deleteMany({{user_id:"{uid}"}});')


def logs(ctx, **p):
    r = ctx["s"].get(f"{API}/comunicazioni/log", params={"limit": 100, **p})
    assert r.status_code == 200, r.text
    return r.json()


def put_cfg(ctx, **kw):
    cfg = ctx["s"].get(f"{API}/comunicazioni/config").json()["config"]
    cfg.update(kw)
    return ctx["s"].put(f"{API}/comunicazioni/config", json=cfg)


# --- config defaults & validation
def test_config_defaults(ctx):
    r = ctx["s"].get(f"{API}/comunicazioni/config")
    assert r.status_code == 200
    d = r.json()
    c = d["config"]
    assert c["cortesia_auto"] is False and c["promemoria_auto"] is False and c["solleciti_auto"] is False
    assert c["promemoria_giorni"] == 5 and c["livelli"] == [7, 21, 45] and c["ora"] == 8
    assert set(c["testi"]) == {"cortesia", "promemoria", "sollecito1", "sollecito2", "sollecito3"}
    for t in c["testi"].values():
        assert t["oggetto"] and t["corpo"]
    assert set(d["segnaposto"]) == {"{cliente}", "{azienda}", "{numero}", "{data}", "{totale}", "{scadenza}", "{elenco}", "{iban}"}


@pytest.mark.parametrize("kw", [{"livelli": [7, 7, 45]}, {"livelli": [21, 7, 45]}, {"livelli": [7, 21]}, {"promemoria_giorni": 0},
                                {"promemoria_giorni": 31}, {"ora": 5}, {"ora": 21}])
def test_config_validation_422(ctx, kw):
    assert put_cfg(ctx, **kw).status_code == 422


def test_config_empty_text_422(ctx):
    cfg = ctx["s"].get(f"{API}/comunicazioni/config").json()["config"]
    cfg["testi"]["promemoria"]["oggetto"] = ""
    assert ctx["s"].put(f"{API}/comunicazioni/config", json=cfg).status_code == 422


def test_config_put_persists(ctx):
    cfg = ctx["s"].get(f"{API}/comunicazioni/config").json()["config"]
    cfg["testi"]["promemoria"]["oggetto"] = "TEST_Promemoria per {cliente} da {azienda}"
    cfg.update(promemoria_giorni=6, ora=9, livelli=[7, 21, 45])
    r = ctx["s"].put(f"{API}/comunicazioni/config", json=cfg)
    assert r.status_code == 200, r.text
    g = ctx["s"].get(f"{API}/comunicazioni/config").json()["config"]
    assert g["promemoria_giorni"] == 6 and g["ora"] == 9 and g["testi"]["promemoria"]["oggetto"].startswith("TEST_Promemoria")
    assert g["cortesia_auto"] is False


# --- courtesy invoice
def test_cortesia_off_no_log(ctx):
    assert [x for x in logs(ctx)["log"] if x["tipo"] == "cortesia"] == []


def test_cortesia_auto_on_without_smtp_logs_error(ctx):
    assert put_cfg(ctx, cortesia_auto=True).status_code == 200
    iid = ctx["mk"](ctx["c2"], 1, 30, 10)
    ctx["iE"] = iid
    time.sleep(3)
    rows = [x for x in logs(ctx, tipo="cortesia")["log"]]
    assert len(rows) == 1, rows
    assert rows[0]["esito"] == "errore" and "SMTP" in rows[0]["errore"] and rows[0]["to"] == "beta@example.com" and rows[0]["auto"] is True
    assert "keys" not in rows[0]


def test_cortesia_auto_client_without_email(ctx):
    ctx["mk"](ctx["c3"], 1, 30, 10)
    time.sleep(3)
    rows = [x for x in logs(ctx, tipo="cortesia")["log"] if x["cliente"] == "TEST_Gamma NoMail Srl"]
    assert len(rows) == 1 and rows[0]["errore"] == "Cliente senza email o PEC in anagrafica"


def test_cortesia_manual_bozza_400(ctx):
    iid = ctx["mk"](ctx["c1"], 0, 30, 10, send=False)
    ctx["bozza"] = iid
    r = ctx["s"].post(f"{API}/comunicazioni/cortesia/{iid}")
    assert r.status_code == 400
    assert ctx["s"].post(f"{API}/comunicazioni/cortesia/nonexistent").status_code == 404


def test_cortesia_manual_without_smtp_400_message(ctx):
    r = ctx["s"].post(f"{API}/comunicazioni/cortesia/{ctx['iE']}")
    assert r.status_code == 400 and "SMTP" in r.json()["detail"]


# --- reminders/dunning without SMTP: all errors, nothing deduped
def test_esegui_without_smtp_errors_and_retry(ctx):
    for _ in range(2):
        r = ctx["s"].post(f"{API}/comunicazioni/esegui")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["promemoria"] == 0 and d["solleciti"] == 0
        # c1 sollecito, c2 promemoria (iC + iE? iE due in 30gg -> no), c3 promemoria (iD)
        assert d["errori"] == 3, d


def test_configure_local_smtp(ctx):
    if not smtp_up():
        pytest.skip("local debug SMTP not running")
    r = ctx["s"].put(f"{API}/company/smtp", json={"host": "127.0.0.1", "port": 1025, "security": "none", "username": "", "password": "",
                                                   "from_email": "noreply@example.com", "from_name": "TEST_T37"})
    assert r.status_code == 200, r.text
    ctx["smtp"] = True


def test_cortesia_manual_ok(ctx):
    if not ctx.get("smtp"):
        pytest.skip("no smtp")
    r = ctx["s"].post(f"{API}/comunicazioni/cortesia/{ctx['iE']}")
    assert r.status_code == 200, r.text
    top = logs(ctx, tipo="cortesia")["log"][0]
    assert top["esito"] == "ok" and top["auto"] is False and top["documenti"]


def test_esegui_with_smtp_and_dedupe(ctx):
    if not ctx.get("smtp"):
        pytest.skip("no smtp")
    d = ctx["s"].post(f"{API}/comunicazioni/esegui").json()
    assert d == {"promemoria": 1, "solleciti": 1, "errori": 1}, d
    L = logs(ctx)["log"]
    sol = [x for x in L if x["tipo"] == "sollecito" and x["esito"] == "ok"]
    assert len(sol) == 1 and sol[0]["livello"] == 3 and sol[0]["cliente"] == "TEST_Alfa Srl"
    assert abs(sol[0]["importo"] - 366.0) < 0.01  # 122 + 244
    pro = [x for x in L if x["tipo"] == "promemoria" and x["esito"] == "ok"]
    assert len(pro) == 1 and pro[0]["cliente"] == "TEST_Beta Spa" and abs(pro[0]["importo"] - 366.0) < 0.01
    assert pro[0]["oggetto"] == "TEST_Promemoria per TEST_Beta Spa da TEST_T37 Comunicazioni Srl"
    # second run: deduped, only c3 error retried
    d2 = ctx["s"].post(f"{API}/comunicazioni/esegui").json()
    assert d2 == {"promemoria": 0, "solleciti": 0, "errori": 1}, d2


def test_sollecito_keys_cover_lower_rata(ctx):
    if not ctx.get("smtp"):
        pytest.skip("no smtp")
    # Design check: rata iB (10gg, lv1) was included in the lv3 email of iA -> keys S1..S3 marked for iB too
    keys = mongo(f'print(JSON.stringify(db.com_log.findOne({{company_id:"{ctx["cid"]}", tipo:"sollecito", esito:"ok"}}).keys))')
    print("SOLLECITO KEYS", keys)
    assert f"S1-{ctx['iB']}-1" in keys
    # escalate livelli so iB is now level 2 -> no new sollecito because S2-iB is already marked
    assert put_cfg(ctx, livelli=[5, 9, 45]).status_code == 200
    d = ctx["s"].post(f"{API}/comunicazioni/esegui").json()
    print("ESCALATION RUN", d)
    ctx["escalation"] = d
    assert put_cfg(ctx, livelli=[7, 21, 45]).status_code == 200


def test_log_shape_and_stats(ctx):
    d = logs(ctx)
    ts = [x["created_at"] for x in d["log"]]
    assert ts == sorted(ts, reverse=True)
    assert set(d["settimana"]) == {"cortesia", "promemoria", "sollecito"} and set(d["tipi"]) == {"cortesia", "promemoria", "sollecito"}
    assert d["errori"] >= 3
    assert d["ultimo"] and "at" in d["ultimo"]
    if ctx.get("smtp"):
        assert d["settimana"]["sollecito"] == 1 and d["settimana"]["promemoria"] == 1 and d["settimana"]["cortesia"] == 1
    assert all("_id" not in x and "keys" not in x for x in d["log"])


# --- automatic daily loop (Rome hour must be >= ora; backend loop runs every 60s)
def test_auto_loop_runs_once_per_day(ctx):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    h = datetime.now(ZoneInfo("Europe/Rome")).hour
    if h < 6:
        pytest.skip("too early in Rome")
    ctx["mk"](ctx["c2"], 0, 4, 10)  # new promemoria candidate for c2
    assert put_cfg(ctx, promemoria_auto=True, ora=min(h, 20)).status_code == 200
    before = len(logs(ctx, tipo="promemoria")["log"])
    for _ in range(14):
        time.sleep(5)
        if mongo(f'print(db.companies.findOne({{id:"{ctx["cid"]}"}}).com_last_day || "")'):
            break
    time.sleep(2)
    assert mongo(f'print(db.companies.findOne({{id:"{ctx["cid"]}"}}).com_last_day || "")') == datetime.now(ZoneInfo("Europe/Rome")).date().isoformat()
    after = [x for x in logs(ctx, tipo="promemoria")["log"]]
    new = after[: len(after) - before]
    assert any(x["auto"] is True for x in new), new
    assert put_cfg(ctx, promemoria_auto=False).status_code == 200


# --- gating: menu, module, role
def test_menu_off_403(ctx):
    s = ctx["s"]
    # admin bypasses user menu_off but not company menu_off
    assert s.put(f"{API}/companies/{ctx['cid']}/menu", json={"off": ["comunicazioni"]}).status_code == 200
    assert s.get(f"{API}/comunicazioni/config").status_code == 403
    assert s.get(f"{API}/comunicazioni/log").status_code == 403
    assert s.put(f"{API}/companies/{ctx['cid']}/menu", json={"off": []}).status_code == 200
    assert s.get(f"{API}/comunicazioni/config").status_code == 200


def test_module_fatture_attive_off_403(ctx):
    s = ctx["s"]
    m = {"fatturazione": True, "archivio": True, "fatture_attive": False, "fatture_passive": True, "corrispettivi": True, "contabilita": True}
    assert s.put(f"{API}/companies/{ctx['cid']}/moduli", json=m).status_code == 200
    assert s.get(f"{API}/comunicazioni/log").status_code == 403
    m["fatture_attive"] = True
    assert s.put(f"{API}/companies/{ctx['cid']}/moduli", json=m).status_code == 200
    assert s.get(f"{API}/comunicazioni/log").status_code == 200


def test_operatore_cannot_put_or_run(ctx):
    s = ctx["s"]
    email = f"test.user.t37{uuid.uuid4().hex[:6]}@example.com"
    requests.post(f"{API}/auth/register", json={"name": "TEST_T37 Operatore", "email": email, "password": "TestPass-123456"})
    uid = next(u["user_id"] for u in s.get(f"{API}/users").json() if u["email"] == email)
    ctx["users"].append(uid)
    assert s.patch(f"{API}/users/{uid}", json={"status": "approved", "role": "operatore", "company_ids": [ctx["cid"]]}).status_code == 200
    o = requests.Session()
    assert o.post(f"{API}/auth/login", json={"email": email, "password": "TestPass-123456"}).status_code == 200
    o.headers["X-Company-Id"] = ctx["cid"]
    assert o.get(f"{API}/comunicazioni/config").status_code == 200
    assert o.get(f"{API}/comunicazioni/log").status_code == 200
    cfg = o.get(f"{API}/comunicazioni/config").json()["config"]
    assert o.put(f"{API}/comunicazioni/config", json=cfg).status_code == 403
    assert o.post(f"{API}/comunicazioni/esegui").status_code == 403
    assert o.post(f"{API}/comunicazioni/cortesia/{ctx['iE']}").status_code == 403

# Iteration 18: _seed_admin concurrency (multi-worker uvicorn) + password preservation + live regression
import os
import re
import subprocess
import time
import signal
import uuid

import bcrypt
import pytest
import requests
from pymongo import MongoClient

BACKEND_DIR = "/app/backend"


def _env_file():
    vals = {}
    for line in open(os.path.join(BACKEND_DIR, ".env")):
        m = re.match(r'^([A-Z_]+)="?(.*?)"?$', line.strip())
        if m:
            vals[m.group(1)] = m.group(2)
    return vals


ENV = _env_file()
MONGO_URL = ENV["MONGO_URL"]
ADMIN_EMAIL = ENV["ADMIN_EMAIL"]
ADMIN_PASSWORD = ENV["ADMIN_PASSWORD"]


def _frontend_url():
    for line in open("/app/frontend/.env"):
        if line.startswith("REACT_APP_BACKEND_URL"):
            return line.split("=", 1)[1].strip().strip('"').rstrip("/")


BASE_URL = _frontend_url()
mc = MongoClient(MONGO_URL)


def _run_uvicorn(db_name, port, workers=3, wait=25):
    env = dict(os.environ, DB_NAME=db_name)
    log = f"/tmp/seed_race_{db_name}.log"
    f = open(log, "w")
    p = subprocess.Popen(["python3", "-m", "uvicorn", "server:app", "--port", str(port), "--workers", str(workers)],
                         cwd=BACKEND_DIR, env=env, stdout=f, stderr=subprocess.STDOUT, preexec_fn=os.setsid)
    deadline = time.time() + wait
    out = ""
    while time.time() < deadline:
        time.sleep(1)
        out = open(log).read()
        if out.count("Application startup complete") >= workers or "startup failed" in out:
            break
    time.sleep(1)
    os.killpg(os.getpgid(p.pid), signal.SIGTERM)
    try:
        p.wait(10)
    except Exception:
        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
    return open(log).read()


@pytest.mark.parametrize("run", range(5))
def test_multi_worker_empty_db_no_race(run):
    db_name = f"tmp_seed_race_{uuid.uuid4().hex[:6]}"
    try:
        out = _run_uvicorn(db_name, 8124 + run, workers=3)
        assert "DuplicateKeyError" not in out, out[-3000:]
        assert "startup failed" not in out, out[-3000:]
        assert out.count("Application startup complete") == 3, out[-3000:]
        users = list(mc[db_name].users.find({"email": ADMIN_EMAIL}))
        assert len(users) == 1
        u = users[0]
        assert u["password_hash"].startswith("$2b$")
        assert bcrypt.checkpw(ADMIN_PASSWORD.encode(), u["password_hash"].encode())
        assert u["role"] == "admin" and u["status"] == "approved"
    finally:
        mc.drop_database(db_name)


def test_existing_password_not_overwritten_and_missing_password_set():
    db_name = f"tmp_seed_race_{uuid.uuid4().hex[:6]}"
    try:
        other_hash = bcrypt.hashpw(b"SomeOtherPass123", bcrypt.gensalt()).decode()
        mc[db_name].users.insert_one({"user_id": "user_x1", "email": ADMIN_EMAIL, "password_hash": other_hash,
                                      "role": "admin", "status": "approved"})
        out = _run_uvicorn(db_name, 8131, workers=2)
        assert out.count("Application startup complete") == 2, out[-3000:]
        u = mc[db_name].users.find_one({"email": ADMIN_EMAIL})
        assert u["password_hash"] == other_hash
        assert mc[db_name].users.count_documents({"email": ADMIN_EMAIL}) == 1
    finally:
        mc.drop_database(db_name)

    for variant in ({"password_hash": None}, {"password_hash": ""}, {}):
        db_name = f"tmp_seed_race_{uuid.uuid4().hex[:6]}"
        try:
            mc[db_name].users.insert_one({"user_id": "user_x2", "email": ADMIN_EMAIL, "role": "operatore",
                                          "status": "pending", **variant})
            out = _run_uvicorn(db_name, 8132, workers=2)
            assert out.count("Application startup complete") == 2, out[-3000:]
            u = mc[db_name].users.find_one({"email": ADMIN_EMAIL})
            assert u["password_hash"] and bcrypt.checkpw(ADMIN_PASSWORD.encode(), u["password_hash"].encode()), variant
            assert u["role"] == "admin" and u["status"] == "approved"
            assert u["user_id"] == "user_x2"
        finally:
            mc.drop_database(db_name)


def test_deploy_files_single_worker():
    bat = open("/app/deploy/windows/avvia-backend.bat").read()
    dock = open("/app/deploy/backend.Dockerfile").read()
    assert "--workers 1" in bat and "--workers 2" not in bat
    assert '"--workers", "1"' in dock


def test_live_login_and_me():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    assert "session_token" in r.headers.get("set-cookie", "")
    assert "httponly" in r.headers.get("set-cookie", "").lower()
    me = s.get(f"{BASE_URL}/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == ADMIN_EMAIL
    assert me.json()["role"] == "admin"


def test_no_tmp_dbs_left():
    assert not [d for d in mc.list_database_names() if d.startswith("tmp_seed_race_")]

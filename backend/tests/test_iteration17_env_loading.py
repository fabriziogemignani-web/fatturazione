# Iteration 17: backend/server.py _load_env() robustness (.env missing, .env.txt, UTF-16, BOM, env-provided) + live regression
import os
import shutil
import subprocess
import tempfile
import glob
import pytest
import requests
from cryptography.fernet import Fernet

BACKEND_DIR = "/app/backend"
BASE_URL = None
with open("/app/frontend/.env") as f:
    for line in f:
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")

KEY = Fernet.generate_key().decode()
ENV_TEXT = (
    'MONGO_URL="mongodb://127.0.0.1:27017"\r\n'
    'DB_NAME="t17_envtest"\r\n'
    'APP_URL="http://fatture.intranet.local"\r\n'
    'CORS_ORIGINS="http://fatture.intranet.local"\r\n'
    'COOKIE_SECURE="false"\r\n'
    'ADMIN_EMAIL="Admin@VostraAzienda.it"\r\n'
    'ADMIN_PASSWORD="cambia-questa-password"\r\n'
    'EMAIL_FROM_NAME="Fatturazione Elettronica"\r\n'
    f'SMTP_ENCRYPTION_KEY="{KEY}"\r\n'
)
PROBE = (
    "import os, server; "
    "print('OK', os.environ['MONGO_URL'], os.environ['DB_NAME'], server.ADMIN_EMAIL, server.APP_URL, server.COOKIE_SECURE)"
)


@pytest.fixture
def tmpdir_copy():
    d = tempfile.mkdtemp(prefix="t17_env_")
    for p in glob.glob(os.path.join(BACKEND_DIR, "*.py")):
        shutil.copy(p, d)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def run(d, extra_env=None):
    env = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/root")}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(["python", "-c", PROBE], cwd=d, env=env, capture_output=True, text=True, timeout=60)


def write(d, name, data: bytes):
    with open(os.path.join(d, name), "wb") as f:
        f.write(data)


class TestLoadEnv:
    def test_missing_env_clear_message(self, tmpdir_copy):
        r = run(tmpdir_copy)
        assert r.returncode != 0
        assert "KeyError" not in r.stderr
        assert "File di configurazione non trovato" in r.stderr
        assert os.path.join(tmpdir_copy, ".env") in r.stderr
        assert "backend.env.example" in r.stderr

    def test_utf8_env(self, tmpdir_copy):
        write(tmpdir_copy, ".env", ENV_TEXT.encode("utf-8"))
        r = run(tmpdir_copy)
        assert r.returncode == 0, r.stderr
        assert "OK mongodb://127.0.0.1:27017 t17_envtest admin@vostraazienda.it http://fatture.intranet.local False" in r.stdout

    def test_utf8_bom_env(self, tmpdir_copy):
        write(tmpdir_copy, ".env", ENV_TEXT.encode("utf-8-sig"))
        r = run(tmpdir_copy)
        assert r.returncode == 0, r.stderr
        assert "OK mongodb://127.0.0.1:27017 t17_envtest" in r.stdout

    def test_utf16_le_env(self, tmpdir_copy):
        write(tmpdir_copy, ".env", ENV_TEXT.encode("utf-16"))  # BOM + LE, like Notepad "Unicode"
        r = run(tmpdir_copy)
        assert r.returncode == 0, r.stderr
        assert "OK mongodb://127.0.0.1:27017 t17_envtest" in r.stdout

    def test_utf16_be_env(self, tmpdir_copy):
        write(tmpdir_copy, ".env", b"\xfe\xff" + ENV_TEXT.encode("utf-16-be"))
        r = run(tmpdir_copy)
        assert r.returncode == 0, r.stderr
        assert "OK mongodb://127.0.0.1:27017 t17_envtest" in r.stdout

    def test_env_txt_fallback(self, tmpdir_copy):
        write(tmpdir_copy, ".env.txt", ENV_TEXT.encode("utf-8"))
        r = run(tmpdir_copy)
        assert r.returncode == 0, r.stderr
        assert "OK mongodb://127.0.0.1:27017 t17_envtest" in r.stdout

    def test_env_txt_utf16_fallback(self, tmpdir_copy):
        write(tmpdir_copy, ".env.txt", ENV_TEXT.encode("utf-16"))
        r = run(tmpdir_copy)
        assert r.returncode == 0, r.stderr
        assert "t17_envtest" in r.stdout

    def test_env_preferred_over_env_txt(self, tmpdir_copy):
        write(tmpdir_copy, ".env", ENV_TEXT.encode("utf-8"))
        write(tmpdir_copy, ".env.txt", ENV_TEXT.replace("t17_envtest", "WRONG_txt").encode("utf-8"))
        r = run(tmpdir_copy)
        assert r.returncode == 0, r.stderr
        assert "t17_envtest" in r.stdout and "WRONG_txt" not in r.stdout

    def test_env_provided_by_environment_no_file(self, tmpdir_copy):
        extra = {}
        for line in ENV_TEXT.strip().split("\r\n"):
            k, v = line.split("=", 1)
            extra[k] = v.strip('"')
        r = run(tmpdir_copy, extra)
        assert r.returncode == 0, r.stderr
        assert "OK mongodb://127.0.0.1:27017 t17_envtest" in r.stdout

    def test_environment_overrides_file(self, tmpdir_copy):
        write(tmpdir_copy, ".env", ENV_TEXT.encode("utf-8"))
        r = run(tmpdir_copy, {"DB_NAME": "from_env"})
        assert r.returncode == 0, r.stderr
        assert "from_env" in r.stdout

    def test_uvicorn_import_missing_env(self, tmpdir_copy):
        env = {"PATH": os.environ["PATH"], "HOME": "/root"}
        r = subprocess.run(["python", "-c", "import uvicorn.importer as i; i.import_from_string('server:app')"],
                           cwd=tmpdir_copy, env=env, capture_output=True, text=True, timeout=60)
        assert r.returncode != 0
        assert "File di configurazione non trovato" in r.stderr
        assert "KeyError" not in r.stderr


class TestLiveRegression:
    def test_login_and_me(self):
        creds = open("/app/memory/test_credentials.md").read()
        assert "fabrizio.gemignani@gmail.com" in creds
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login", json={"email": "fabrizio.gemignani@gmail.com", "password": "Fe-Admin-2aOBey8irzL8"})
        assert r.status_code == 200, r.text
        assert "session_token" in s.cookies.get_dict()
        me = s.get(f"{BASE_URL}/api/auth/me")
        assert me.status_code == 200
        assert me.json()["email"] == "fabrizio.gemignani@gmail.com"
        assert me.json()["role"] == "admin"
        assert "password_hash" not in me.json()

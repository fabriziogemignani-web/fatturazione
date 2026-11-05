import os
import asyncio
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta

import httpx
from fastapi import APIRouter, HTTPException, Depends

APP_DIR = Path(__file__).resolve().parent.parent
STATE_FILE = APP_DIR / "logs" / "aggiornamento.stato"
SCRIPT = APP_DIR / "deploy" / "windows" / "aggiorna-auto.bat"
TASK = "FatturazioneAggiornamento"
CHECK_EVERY = timedelta(hours=24)
_cache = {"at": None, "remote": None, "error": None}


def _cfg():
    return os.environ.get("UPDATE_REPO"), os.environ.get("UPDATE_BRANCH") or "main", os.environ.get("GITHUB_TOKEN")


async def _local_sha():
    p = await asyncio.create_subprocess_exec("git", "-c", "safe.directory=*", "-C", str(APP_DIR), "rev-parse", "HEAD",
                                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    out, _ = await p.communicate()
    return out.decode().strip() or None


async def _remote(repo, branch, token):
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"https://api.github.com/repos/{repo}/commits/{branch}", headers=headers)
    if r.status_code != 200:
        raise RuntimeError(f"GitHub ha risposto {r.status_code}: controlla UPDATE_REPO, UPDATE_BRANCH e GITHUB_TOKEN")
    d = r.json()
    return {"sha": d["sha"], "message": (d["commit"]["message"] or "").split("\n")[0][:200], "date": d["commit"]["committer"]["date"]}


def _state():
    try:
        return STATE_FILE.read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return ""


def build_router(user_dep) -> APIRouter:
    r = APIRouter()

    async def status(force: bool = False):
        repo, branch, token = _cfg()
        if not repo:
            return {"enabled": False}
        now = datetime.now(timezone.utc)
        if force or not _cache["at"] or now - _cache["at"] > CHECK_EVERY:
            try:
                _cache.update(remote=await _remote(repo, branch, token), error=None)
            except Exception as e:
                _cache["error"] = str(e)
            _cache["at"] = now
        local = await _local_sha()
        remote = _cache["remote"]
        state = _state()
        return {
            "enabled": True, "local": local, "remote": remote, "checked_at": _cache["at"].isoformat(),
            "error": _cache["error"], "state": state,
            "available": bool(remote and local and remote["sha"] != local),
            "can_run": os.name == "nt" and SCRIPT.exists(),
        }

    @r.get("/system/update-status")
    async def update_status(_: dict = Depends(user_dep)):
        return await status()

    @r.post("/system/update")
    async def run_update(user: dict = Depends(user_dep)):
        st = await status(force=True)
        if not st["enabled"]:
            raise HTTPException(400, "Aggiornamento automatico non configurato su questo server")
        if not st["available"]:
            raise HTTPException(400, "Il programma è già aggiornato all'ultima versione")
        if not st["can_run"]:
            raise HTTPException(400, "L'aggiornamento automatico è disponibile solo sul server Windows")
        if st["state"].startswith("in corso"):
            raise HTTPException(409, "Un aggiornamento è già in corso")
        STATE_FILE.parent.mkdir(exist_ok=True)
        STATE_FILE.write_text(f"in corso: avviato da {user.get('email')}", encoding="utf-8")
        cmd = ["schtasks", "/create", "/f", "/tn", TASK, "/sc", "once", "/st", "00:00", "/ru", "SYSTEM", "/rl", "HIGHEST",
               "/tr", f'cmd /c "{SCRIPT}"']
        for c in (cmd, ["schtasks", "/run", "/tn", TASK]):
            res = subprocess.run(c, capture_output=True, text=True)
            if res.returncode != 0:
                STATE_FILE.write_text("errore: impossibile avviare l'aggiornamento", encoding="utf-8")
                raise HTTPException(500, f"Impossibile avviare l'aggiornamento: {(res.stderr or res.stdout).strip()[:300]}")
        return {"ok": True, "from": st["local"], "to": st["remote"]["sha"]}

    return r

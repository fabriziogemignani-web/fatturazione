@echo off
cd /d C:\fatturazione\backend
C:\fatturazione\venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8001 --workers 2

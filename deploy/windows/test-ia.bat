@echo off
rem Verifica che la chiave IA del server funzioni
cd /d C:\fatturazione
C:\fatturazione\venv\Scripts\python.exe deploy\windows\test-ia.py
pause

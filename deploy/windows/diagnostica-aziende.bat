@echo off
rem Mostra quali aziende e utenti ci sono nel database e quale database usa Invoix
rem Uso: diagnostica-aziende.bat            (solo controllo)
rem      diagnostica-aziende.bat ripara     (rimette il ruolo amministratore a ADMIN_EMAIL)
cd /d C:\fatturazione
if /i "%1"=="ripara" (
  C:\fatturazione\venv\Scripts\python.exe deploy\windows\diagnostica-aziende.py --ripara-admin
) else (
  C:\fatturazione\venv\Scripts\python.exe deploy\windows\diagnostica-aziende.py
)
pause

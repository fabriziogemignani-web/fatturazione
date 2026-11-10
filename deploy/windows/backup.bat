@echo off
rem Backup del database con copia su FTP privato. Programmatelo ogni notte con "Utilità di pianificazione"
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\fatturazione\deploy\windows\backup.ps1"
exit /b %errorlevel%

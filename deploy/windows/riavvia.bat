@echo off
rem Riavvia l'applicazione nell'ordine corretto (prima si ferma il web, poi il backend)
nssm stop FatturazioneWeb
nssm stop FatturazioneBackend
nssm start FatturazioneBackend
timeout /t 5 /nobreak >nul
nssm start FatturazioneWeb
sc query FatturazioneBackend | findstr STATO
sc query FatturazioneWeb | findstr STATO
pause

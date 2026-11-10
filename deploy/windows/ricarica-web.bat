@echo off
rem Ricarica il web dopo il rinnovo del certificato (lanciato da win-acme)
nssm stop FatturazioneWeb >nul 2>&1
taskkill /f /im nginx.exe >nul 2>&1
nssm start FatturazioneWeb

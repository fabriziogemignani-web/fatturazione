@echo off
rem Ricarica il web dopo il rinnovo del certificato (lanciato da win-acme)
nssm restart FatturazioneWeb

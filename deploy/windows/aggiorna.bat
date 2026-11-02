@echo off
rem Aggiorna l'applicazione dopo un "git pull" o dopo aver copiato i nuovi file
echo Arresto servizi...
nssm stop FatturazioneWeb
nssm stop FatturazioneBackend
cd /d C:\fatturazione
git pull
echo Aggiornamento librerie Python...
C:\fatturazione\venv\Scripts\pip.exe install -r deploy\requirements.txt
echo Ricostruzione interfaccia web...
cd /d C:\fatturazione\frontend
call yarn install --frozen-lockfile
call yarn build
echo Avvio servizi...
nssm start FatturazioneBackend
nssm start FatturazioneWeb
echo Aggiornamento completato.
pause

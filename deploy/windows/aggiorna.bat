@echo off
rem Aggiorna l'applicazione dopo un "git pull" o dopo aver copiato i nuovi file
echo Avviso agli utenti collegati...
C:\fatturazione\venv\Scripts\python.exe C:\fatturazione\deploy\windows\avviso-aggiornamento.py inizio 30
echo Attendo 30 secondi prima di arrestare il sistema...
timeout /t 30 /nobreak
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
echo Rimozione avviso...
C:\fatturazione\venv\Scripts\python.exe C:\fatturazione\deploy\windows\avviso-aggiornamento.py fine
echo Avvio servizi...
nssm start FatturazioneBackend
nssm start FatturazioneWeb
echo Aggiornamento completato.
pause

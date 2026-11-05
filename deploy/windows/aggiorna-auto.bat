@echo off
rem Aggiornamento automatico avviato dal bottone rosso nel programma: backup, aggiornamento, riavvio
setlocal
set APP=C:\fatturazione
set LOGDIR=%APP%\logs
set LOG=%LOGDIR%\aggiornamento.log
set STATO=%LOGDIR%\aggiornamento.stato
if not exist %LOGDIR% mkdir %LOGDIR%
for /f "usebackq tokens=1,* delims==" %%a in ("%APP%\backend\.env") do (
  if "%%a"=="GITHUB_TOKEN" set TOK=%%~b
  if "%%a"=="UPDATE_REPO" set REPO=%%~b
  if "%%a"=="UPDATE_BRANCH" set BRANCH=%%~b
)
if "%BRANCH%"=="" set BRANCH=main
echo ===== %date% %time% inizio aggiornamento >> %LOG%

echo in corso: backup del database> %STATO%
call %APP%\deploy\windows\backup.bat >> %LOG% 2>&1
if errorlevel 1 (
  echo errore: backup non riuscito, aggiornamento annullato> %STATO%
  echo Backup non riuscito: aggiornamento annullato >> %LOG%
  exit /b 1
)

echo in corso: arresto servizi> %STATO%
nssm stop FatturazioneWeb >> %LOG% 2>&1
nssm stop FatturazioneBackend >> %LOG% 2>&1
cd /d %APP%

echo in corso: download nuova versione> %STATO%
git -c safe.directory=* checkout -- frontend/.env >> %LOG% 2>&1
if "%TOK%"=="" (
  git -c safe.directory=* pull --ff-only origin %BRANCH% >> %LOG% 2>&1
) else (
  git -c safe.directory=* pull --ff-only https://x-access-token:%TOK%@github.com/%REPO%.git %BRANCH% >> %LOG% 2>&1
)
if errorlevel 1 goto errore
> frontend\.env echo REACT_APP_BACKEND_URL=

echo in corso: aggiornamento librerie> %STATO%
%APP%\venv\Scripts\pip.exe install -r deploy\requirements.txt >> %LOG% 2>&1
if errorlevel 1 goto errore

echo in corso: ricostruzione pagine web> %STATO%
cd /d %APP%\frontend
call npx --yes yarn@1.22.22 install --frozen-lockfile >> %LOG% 2>&1
if errorlevel 1 goto errore
call npx --yes yarn@1.22.22 build >> %LOG% 2>&1
if errorlevel 1 goto errore

echo ok: aggiornamento completato il %date% %time%> %STATO%
echo Aggiornamento completato >> %LOG%
goto avvio

:errore
echo errore: aggiornamento non riuscito, vedi logs\aggiornamento.log> %STATO%
echo ERRORE durante l'aggiornamento >> %LOG%

:avvio
nssm start FatturazioneBackend >> %LOG% 2>&1
nssm start FatturazioneWeb >> %LOG% 2>&1
endlocal

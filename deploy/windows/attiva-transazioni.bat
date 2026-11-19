@echo off
rem Attiva le transazioni "tutto o niente" di MongoDB (replica set a un solo nodo) e riavvia Invoix.
rem Esegui come amministratore. Prima fa un backup del database.
setlocal
set CFG=
for /d %%D in ("C:\Program Files\MongoDB\Server\*") do if exist "%%D\bin\mongod.cfg" set "CFG=%%D\bin\mongod.cfg"
if "%CFG%"=="" (
  echo File mongod.cfg non trovato in C:\Program Files\MongoDB\Server\*\bin
  pause
  exit /b 1
)
echo Configurazione MongoDB: %CFG%

if exist "%~dp0backup.bat" (
  echo Backup del database in corso...
  call "%~dp0backup.bat" < nul
)

findstr /c:"replSetName" "%CFG%" >nul
if errorlevel 1 (
  copy /y "%CFG%" "%CFG%.prima-transazioni" >nul
  >>"%CFG%" echo.
  >>"%CFG%" echo replication:
  >>"%CFG%" echo   replSetName: rs0
  echo Replica set aggiunto alla configurazione.
) else (
  echo Replica set gia' presente nella configurazione.
)

nssm stop FatturazioneWeb
nssm stop FatturazioneBackend
net stop MongoDB
net start MongoDB
if errorlevel 1 (
  echo MongoDB non riparte: ripristino la configurazione precedente.
  if exist "%CFG%.prima-transazioni" copy /y "%CFG%.prima-transazioni" "%CFG%" >nul
  net start MongoDB
  nssm start FatturazioneBackend
  nssm start FatturazioneWeb
  pause
  exit /b 1
)
timeout /t 5 /nobreak >nul

C:\fatturazione\venv\Scripts\python.exe -c "from pymongo import MongoClient; c=MongoClient('mongodb://127.0.0.1:27017/?directConnection=true', serverSelectionTimeoutMS=10000); s=c.admin.command('hello'); print('Replica set gia attivo') if s.get('setName') else (c.admin.command('replSetInitiate', {'_id': 'rs0', 'members': [{'_id': 0, 'host': '127.0.0.1:27017'}]}), print('Replica set inizializzato'))"
timeout /t 10 /nobreak >nul

nssm start FatturazioneBackend
timeout /t 5 /nobreak >nul
nssm start FatturazioneWeb
echo.
echo Fatto. Nel log del backend deve comparire: "Transazioni MongoDB attive".
pause

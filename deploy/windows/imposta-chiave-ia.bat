@echo off
rem Imposta la chiave IA (EMERGENT_LLM_KEY) in C:\fatturazione\backend\.env e riavvia i servizi
set ENVFILE=C:\fatturazione\backend\.env
if not exist "%ENVFILE%" (
  echo File %ENVFILE% non trovato. Controllare l'installazione.
  pause
  exit /b 1
)
echo Incollare la chiave IA (Emergent: Profilo - Universal Key) e premere Invio:
set /p KEY=Chiave: 
if "%KEY%"=="" (
  echo Nessuna chiave inserita, operazione annullata.
  pause
  exit /b 1
)
echo %KEY%| findstr /b /c:"sk-emergent-" >nul
if errorlevel 1 (
  echo La chiave deve iniziare con sk-emergent- : copiare la Universal Key completa da Emergent, Profilo - Universal Key.
  pause
  exit /b 1
)
copy /y "%ENVFILE%" "%ENVFILE%.prima-chiave-ia" >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0imposta-chiave-ia.ps1" -EnvFile "%ENVFILE%"
if errorlevel 1 (
  echo Scrittura non riuscita: copia originale in %ENVFILE%.prima-chiave-ia
  pause
  exit /b 1
)
set KEY=
echo Chiave salvata. Riavvio dei servizi...
nssm stop FatturazioneWeb
nssm stop FatturazioneBackend
nssm start FatturazioneBackend
timeout /t 5 /nobreak >nul
nssm start FatturazioneWeb
sc query FatturazioneBackend | findstr STATO
echo Fatto. Riprovare il Consulente IA.
pause

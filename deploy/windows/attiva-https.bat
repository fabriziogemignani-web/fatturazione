@echo off
setlocal
rem ============================================================
rem  Attiva HTTPS (porta 443) con certificato gratuito Let's Encrypt
rem  Eseguire come Amministratore. Richiede C:\win-acme\wacs.exe
rem ============================================================
set DOMINIO=invoix.digitalmape.it
set APP=C:\fatturazione
set NGXDIR=C:\nginx
set WACS=C:\win-acme\wacs.exe

net session >nul 2>&1 || (echo ERRORE: aprite il prompt come Amministratore & pause & exit /b 1)
if not exist "%WACS%" (echo ERRORE: manca %WACS% - vedi guida, punto 8.1 & pause & exit /b 1)

set /p EMAIL=Email per gli avvisi di Let's Encrypt (scadenze certificato): 
if "%EMAIL%"=="" (echo ERRORE: email obbligatoria & pause & exit /b 1)

echo.
echo [1/6] Apro le porte 80 e 443 nel firewall di Windows...
netsh advfirewall firewall delete rule name="Fatturazione HTTP" >nul 2>&1
netsh advfirewall firewall delete rule name="Fatturazione HTTPS" >nul 2>&1
netsh advfirewall firewall add rule name="Fatturazione HTTP" dir=in action=allow protocol=TCP localport=80 >nul
netsh advfirewall firewall add rule name="Fatturazione HTTPS" dir=in action=allow protocol=TCP localport=443 >nul

echo [2/6] Preparo il web sulla porta 80 per la verifica del dominio...
if not exist "%NGXDIR%\ssl" mkdir "%NGXDIR%\ssl"
if not exist "%NGXDIR%\html\.well-known\acme-challenge" mkdir "%NGXDIR%\html\.well-known\acme-challenge"
copy /y "%NGXDIR%\conf\nginx.conf" "%NGXDIR%\conf\nginx.conf.prima-https" >nul
copy /y "%APP%\deploy\windows\nginx.conf" "%NGXDIR%\conf\nginx.conf" >nul || (echo ERRORE: non riesco a copiare la configurazione in %NGXDIR%\conf & pause & exit /b 1)
nssm stop FatturazioneWeb >nul 2>&1
taskkill /f /im nginx.exe >nul 2>&1
timeout /t 2 /nobreak >nul
nssm start FatturazioneWeb >nul
timeout /t 3 /nobreak >nul

echo [2b] Verifico che la porta 80 risponda con Nginx...
echo ok-fatturazione> "%NGXDIR%\html\.well-known\acme-challenge\prova-fatturazione"
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 'http://127.0.0.1/.well-known/acme-challenge/prova-fatturazione'; if (([string]$r.Content).Contains('ok-fatturazione') -or ([Text.Encoding]::ASCII.GetString([byte[]]$r.RawContentStream.ToArray())).Contains('ok-fatturazione')) { exit 0 } else { Write-Host ('Risposta inattesa: ' + $r.StatusCode); exit 1 } } catch { Write-Host ('Errore: ' + $_.Exception.Message); exit 1 }"
if errorlevel 1 (
  echo.
  echo ERRORE: sulla porta 80 di questo server non risponde Nginx con la cartella %NGXDIR%\html.
  echo --- Programma in ascolto sulla porta 80:
  powershell -NoProfile -Command "$c = Get-NetTCPConnection -LocalPort 80 -State Listen -ErrorAction SilentlyContinue; if (-not $c) { 'NESSUNO: Nginx non e partito o ascolta su un altra porta' } else { $c | ForEach-Object { $p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue; '{0}  PID {1}  {2}' -f $_.LocalAddress, $_.OwningProcess, $p.ProcessName } }"
  echo --- Stato del servizio web:
  sc query FatturazioneWeb | findstr STAT
  echo --- Controllo configurazione Nginx:
  pushd "%NGXDIR%" & nginx.exe -t & popd
  echo --- Ultimi errori di Nginx:
  powershell -NoProfile -Command "if (Test-Path '%NGXDIR%\logs\error.log') { Get-Content '%NGXDIR%\logs\error.log' -Tail 8 }"
  echo.
  echo Se il PID e' 4 / System la porta e' di IIS: iisreset /stop  e  sc config W3SVC start= disabled
  echo Mandate questa schermata all'assistenza. Vedi guida punto 8.1.
  copy /y "%NGXDIR%\conf\nginx.conf.prima-https" "%NGXDIR%\conf\nginx.conf" >nul
  nssm restart FatturazioneWeb >nul
  pause & exit /b 1
)
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 15 'http://%DOMINIO%/.well-known/acme-challenge/prova-fatturazione'; if (([Text.Encoding]::ASCII.GetString([byte[]]$r.RawContentStream.ToArray())).Contains('ok-fatturazione')) { exit 0 } else { exit 1 } } catch { exit 1 }"
if errorlevel 1 (
  echo ATTENZIONE: da questo server http://%DOMINIO% non arriva a Nginx. Se il router non supporta il "loopback" e' normale:
  echo provo comunque. Se fallisce, controllate che il router inoltri la porta 80 a QUESTO server.
)
del "%NGXDIR%\html\.well-known\acme-challenge\prova-fatturazione" >nul 2>&1

echo [3/6] Richiedo il certificato per %DOMINIO% (rinnovo automatico ogni 60 giorni)...
"%WACS%" --source manual --host %DOMINIO% --validation filesystem --webroot "%NGXDIR%\html" --store pemfiles --pemfilespath "%NGXDIR%\ssl" --installation script --script "%APP%\deploy\windows\ricarica-web.bat" --accepttos --emailaddress %EMAIL%
if not exist "%NGXDIR%\ssl\%DOMINIO%-chain.pem" (
  echo.
  echo ERRORE: certificato non ottenuto. Controllate che %DOMINIO% punti all'IP pubblico di questo server
  echo e che la porta 80 sia inoltrata dal router/firewall a questo server. Nulla e' stato cambiato.
  pause & exit /b 1
)

echo [4/6] Attivo la configurazione HTTPS di Nginx...
copy /y "%APP%\deploy\windows\nginx-https.conf" "%NGXDIR%\conf\nginx.conf" >nul
pushd "%NGXDIR%"
nginx.exe -t || (popd & copy /y "%NGXDIR%\conf\nginx.conf.prima-https" "%NGXDIR%\conf\nginx.conf" >nul & echo ERRORE nella configurazione: ripristinata quella precedente & pause & exit /b 1)
popd

echo [5/6] Aggiorno backend\.env (APP_URL, CORS_ORIGINS, COOKIE_SECURE)...
copy /y "%APP%\backend\.env" "%APP%\backend\.env.prima-https" >nul
powershell -NoProfile -Command "$f='%APP%\backend\.env'; $t=Get-Content $f; $t=$t -replace '^APP_URL=.*','APP_URL=\"https://%DOMINIO%\"' -replace '^CORS_ORIGINS=.*','CORS_ORIGINS=\"https://%DOMINIO%\"' -replace '^COOKIE_SECURE=.*','COOKIE_SECURE=\"true\"'; Set-Content -Path $f -Value $t -Encoding UTF8"

echo [6/6] Riavvio i servizi...
nssm stop FatturazioneWeb >nul
taskkill /f /im nginx.exe >nul 2>&1
nssm restart FatturazioneBackend >nul
timeout /t 5 /nobreak >nul
nssm start FatturazioneWeb >nul
sc query FatturazioneBackend | findstr STAT
sc query FatturazioneWeb | findstr STAT

echo.
echo Fatto. Aprite https://%DOMINIO% dal browser.
echo Copie di sicurezza: %NGXDIR%\conf\nginx.conf.prima-https e %APP%\backend\.env.prima-https
pause

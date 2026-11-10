@echo off
setlocal
rem ============================================================
rem  Attiva HTTPS (porta 443) con certificato gratuito Let's Encrypt
rem  Eseguire come Amministratore. Richiede C:\win-acme\wacs.exe
rem ============================================================
set DOMINIO=invoix.digitalmape.it
set APP=C:\fatturazione
set NGINX=C:\nginx
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
if not exist "%NGINX%\ssl" mkdir "%NGINX%\ssl"
if not exist "%NGINX%\html\.well-known\acme-challenge" mkdir "%NGINX%\html\.well-known\acme-challenge"
copy /y "%NGINX%\conf\nginx.conf" "%NGINX%\conf\nginx.conf.prima-https" >nul
copy /y "%APP%\deploy\windows\nginx.conf" "%NGINX%\conf\nginx.conf" >nul
nssm restart FatturazioneWeb >nul
timeout /t 3 /nobreak >nul

echo [3/6] Richiedo il certificato per %DOMINIO% (rinnovo automatico ogni 60 giorni)...
"%WACS%" --source manual --host %DOMINIO% --validation filesystem --webroot "%NGINX%\html" --store pemfiles --pemfilespath "%NGINX%\ssl" --installation script --script "%APP%\deploy\windows\ricarica-web.bat" --accepttos --emailaddress %EMAIL%
if not exist "%NGINX%\ssl\%DOMINIO%-chain.pem" (
  echo.
  echo ERRORE: certificato non ottenuto. Controllate che %DOMINIO% punti all'IP pubblico di questo server
  echo e che la porta 80 sia inoltrata dal router/firewall a questo server. Nulla e' stato cambiato.
  pause & exit /b 1
)

echo [4/6] Attivo la configurazione HTTPS di Nginx...
copy /y "%APP%\deploy\windows\nginx-https.conf" "%NGINX%\conf\nginx.conf" >nul
pushd "%NGINX%"
nginx.exe -t || (popd & copy /y "%NGINX%\conf\nginx.conf.prima-https" "%NGINX%\conf\nginx.conf" >nul & echo ERRORE nella configurazione: ripristinata quella precedente & pause & exit /b 1)
popd

echo [5/6] Aggiorno backend\.env (APP_URL, CORS_ORIGINS, COOKIE_SECURE)...
copy /y "%APP%\backend\.env" "%APP%\backend\.env.prima-https" >nul
powershell -NoProfile -Command "$f='%APP%\backend\.env'; $t=Get-Content $f; $t=$t -replace '^APP_URL=.*','APP_URL=\"https://%DOMINIO%\"' -replace '^CORS_ORIGINS=.*','CORS_ORIGINS=\"https://%DOMINIO%\"' -replace '^COOKIE_SECURE=.*','COOKIE_SECURE=\"true\"'; Set-Content -Path $f -Value $t -Encoding UTF8"

echo [6/6] Riavvio i servizi...
nssm stop FatturazioneWeb >nul
nssm restart FatturazioneBackend >nul
timeout /t 5 /nobreak >nul
nssm start FatturazioneWeb >nul
sc query FatturazioneBackend | findstr STAT
sc query FatturazioneWeb | findstr STAT

echo.
echo Fatto. Aprite https://%DOMINIO% dal browser.
echo Copie di sicurezza: %NGINX%\conf\nginx.conf.prima-https e %APP%\backend\.env.prima-https
pause

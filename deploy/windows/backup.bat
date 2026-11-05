@echo off
rem Backup del database. Programmatelo ogni notte con "Utilità di pianificazione"
set DEST=C:\backup-fatture
if not exist %DEST% mkdir %DEST%
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set OGGI=%%i
"C:\Program Files\MongoDB\Tools\100\bin\mongodump.exe" --db fatturazione --gzip --archive=%DEST%\fatture-%OGGI%.gz
if errorlevel 1 exit /b 1
copy /y C:\fatturazione\backend\.env %DEST%\backend-env-%OGGI%.txt >nul
forfiles /p %DEST% /m *.* /d -30 /c "cmd /c del @path" 2>nul

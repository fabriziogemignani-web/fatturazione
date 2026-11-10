# Backup notturno: database + configurazione, copia su FTP privato, stato per la dashboard
$ErrorActionPreference = "Stop"
$App = "C:\fatturazione"
$Dest = "C:\backup-fatture"
$MongoDump = "C:\Program Files\MongoDB\Tools\100\bin\mongodump.exe"
$StatoFile = Join-Path $Dest "stato-backup.json"
$Oggi = Get-Date -Format "yyyy-MM-dd"

function Leggi-Env($path) {
    $h = @{}
    foreach ($l in Get-Content $path) {
        if ($l -match '^\s*([A-Z0-9_]+)\s*=\s*(.*)$') { $h[$Matches[1]] = $Matches[2].Trim().Trim('"') }
    }
    return $h
}

function Scrivi-Stato($s) {
    $s.data = (Get-Date).ToUniversalTime().ToString("o")
    $s | ConvertTo-Json | Set-Content -Path $StatoFile -Encoding UTF8
}

$stato = [ordered]@{ data = $null; backup_ok = $false; errore = $null; file = $null; ftp_ok = $null; ftp_errore = $null }
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
$envVars = Leggi-Env "$App\backend\.env"

try {
    $db = $envVars["DB_NAME"]
    $arch = Join-Path $Dest "fatture-$Oggi.gz"
    & $MongoDump --db $db --gzip "--archive=$arch"
    if ($LASTEXITCODE -ne 0) { throw "mongodump terminato con codice $LASTEXITCODE" }
    $cfg = Join-Path $Dest "backend-env-$Oggi.txt"
    Copy-Item "$App\backend\.env" $cfg -Force
    Get-ChildItem $Dest -File | Where-Object { $_.Name -ne "stato-backup.json" -and $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item -Force
    $stato.backup_ok = $true
    $stato.file = Split-Path $arch -Leaf
} catch {
    $stato.errore = "Backup locale non riuscito: $($_.Exception.Message)"
    Scrivi-Stato $stato
    exit 1
}

$ftpHost = $envVars["BACKUP_FTP_HOST"]
if ($ftpHost) {
    $netrc = Join-Path $env:TEMP ("ftp-" + [guid]::NewGuid().ToString() + ".netrc")
    try {
        $dir = ($envVars["BACKUP_FTP_DIR"]).Trim("/")
        $port = if ($envVars["BACKUP_FTP_PORT"]) { $envVars["BACKUP_FTP_PORT"] } else { "21" }
        $base = "ftp://${ftpHost}:$port/" + $(if ($dir) { "$dir/" } else { "" })
        "machine $ftpHost login $($envVars['BACKUP_FTP_USER']) password $($envVars['BACKUP_FTP_PASSWORD'])" | Set-Content -Path $netrc -Encoding ASCII
        $tls = @()
        if ($envVars["BACKUP_FTP_TLS"] -ne "false") { $tls = @("--ssl-reqd") }
        foreach ($f in @($arch, $cfg)) {
            $out = & curl.exe --silent --show-error --fail --ftp-create-dirs --retry 2 --connect-timeout 30 --netrc-file $netrc @tls -T $f $base 2>&1
            if ($LASTEXITCODE -ne 0) { throw "curl codice ${LASTEXITCODE}: $out" }
        }
        $stato.ftp_ok = $true
    } catch {
        $stato.ftp_ok = $false
        $stato.ftp_errore = "$($_.Exception.Message)"
    } finally {
        Remove-Item $netrc -Force -ErrorAction SilentlyContinue
    }
}

Scrivi-Stato $stato
if ($stato.ftp_ok -eq $false) { exit 2 }

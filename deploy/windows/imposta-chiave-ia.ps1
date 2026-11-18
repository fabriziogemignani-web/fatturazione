param([Parameter(Mandatory = $true)][string]$EnvFile)
$ErrorActionPreference = "Stop"
$k = "$env:KEY".Trim().Trim('"').Trim("'")
if (-not $k.StartsWith("sk-emergent-")) { Write-Host "La chiave deve iniziare con sk-emergent-"; exit 1 }
$righe = @([IO.File]::ReadAllLines($EnvFile) | Where-Object { $_ -notmatch '^\s*EMERGENT_LLM_KEY\s*=' })
$righe += 'EMERGENT_LLM_KEY="' + $k + '"'
[IO.File]::WriteAllLines($EnvFile, $righe, (New-Object Text.UTF8Encoding $false))
Write-Host "Chiave salvata in $EnvFile"

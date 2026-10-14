# MERLIN MEMORY KIT - qdrant-boot.ps1 (Windows)
# Guarded, logged, idempotent vector-store launcher.
#
# WHY THIS EXISTS (LESSON 1): a reboot left the vector store not running. Nothing
# complained. Semantic recall was silently offline until a manual search failed.
# The fix is not "remember to start it" - it is a launcher that runs at logon,
# checks whether the store is already listening, starts it only if needed, and
# LOGS the result so a reboot can be verified from the file.
#
# Install (Task Scheduler or Startup folder):
#   powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File qdrant-boot.ps1
# Configure: edit the three paths below (or set MMK_QDRANT_DIR / MMK_QDRANT_EXE).

$ErrorActionPreference = 'SilentlyContinue'

$dir  = if ($env:MMK_QDRANT_DIR) { $env:MMK_QDRANT_DIR } else { "$PSScriptRoot\qdrant" }
$exe  = if ($env:MMK_QDRANT_EXE) { $env:MMK_QDRANT_EXE } else { "$dir\qdrant.exe" }
$cfg  = "$dir\config.yaml"
$port = if ($env:MMK_QDRANT_PORT) { [int]$env:MMK_QDRANT_PORT } else { 6333 }
$log  = if ($env:MMK_BOOT_LOG)    { $env:MMK_BOOT_LOG }    else { "$dir\qdrant-boot.log" }

function L($m) { (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '  ' + $m | Add-Content -LiteralPath $log }

function Listening {
  try { (New-Object System.Net.Sockets.TcpClient).Connect('127.0.0.1', $port); $true } catch { $false }
}

L '--- boot pass ---'
if (Listening) { L "already listening on $port - nothing to do"; exit 0 }
if (-not (Test-Path $exe)) { L "MISSING $exe - cannot start (set MMK_QDRANT_EXE)"; exit 1 }

L "starting vector store on $port"
$qargs = if (Test-Path $cfg) { @('--config-path', $cfg) } else { @('--storage-path', "$dir\storage") }
Start-Process -FilePath $exe -ArgumentList $qargs -WorkingDirectory $dir -WindowStyle Minimized

# confirm it actually bound - record success or failure, never assume
for ($i = 0; $i -lt 30; $i++) {
  Start-Sleep -Seconds 2
  if (Listening) { L "UP on $port after ~$($i * 2)s"; exit 0 }
}
L "FAILED to bind $port within 60s - recall is DOWN, investigate now"
exit 1

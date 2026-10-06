$log = "C:\Users\ADSS\AI-XAU-BOT\logs\midnight_shutdown.log"
function Log($m) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m" | Add-Content -Path $log }

Log "=== Shutdown sequence dimulai ==="

try {
    $r = Invoke-RestMethod -Uri "http://localhost:8000/api/auto-trade/do-disable" -Method Get -TimeoutSec 10
    Log "Autotrade disabled: $($r | ConvertTo-Json -Compress)"
} catch {
    Log "Disable autotrade gagal: $($_.Exception.Message)"
}

do {
    Start-Sleep -Seconds 15
} while ((Get-Date).Hour -ne 0)

Log "Tengah malam - mematikan semua bot..."

taskkill /F /IM python.exe /T 2>$null | Out-Null
Log "Python (DLineBot dashboard/engine) dimatikan"

Start-Sleep -Seconds 3

taskkill /F /IM terminal64.exe /T 2>$null | Out-Null
Log "MetaTrader 5 (Dark Venus EA) dimatikan"

Log "=== SEMUA BOT OFF ==="

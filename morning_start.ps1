$log = "D:\Project\Wedd\DLineBot\logs\morning_start.log"
function Log($m) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m" | Add-Content -Path $log }

Log "=== Morning start dimulai ==="

$up = $false
try {
    Invoke-WebRequest -Uri "http://localhost:8000/api/account/status" -TimeoutSec 5 -UseBasicParsing | Out-Null
    $up = $true
    Log "Dashboard sudah jalan"
} catch {
    Log "Dashboard belum jalan - start"
    Start-Process -FilePath "python" -ArgumentList "D:\Project\Wedd\DLineBot\dashboard.py" -WorkingDirectory "D:\Project\Wedd\DLineBot" -WindowStyle Minimized
}

$deadline = (Get-Date).AddSeconds(90)
do {
    Start-Sleep -Seconds 5
    try {
        Invoke-WebRequest -Uri "http://localhost:8000/api/account/status" -TimeoutSec 5 -UseBasicParsing | Out-Null
        $up = $true
    } catch { $up = $false }
} while (-not $up -and (Get-Date) -lt $deadline)

if (-not $up) {
    Log "ERROR: Dashboard tidak merespon setelah 90 detik"
    exit 1
}

try {
    $r = Invoke-RestMethod -Uri "http://localhost:8000/api/auto-trade/do-enable" -Method Get -TimeoutSec 10
    Log "Autotrade enabled: $($r | ConvertTo-Json -Compress)"
} catch {
    Log "ERROR enable autotrade: $($_.Exception.Message)"
}

$watchAlive = Get-Process python -ErrorAction SilentlyContinue | Where-Object {
    try { $_.Path -and (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine -like "*watch_entries*" } catch { $false }
}
if (-not $watchAlive) {
    Start-Process -FilePath "python" -ArgumentList "C:\Users\Administrator\AppData\Local\Temp\opencode\watch_entries.py" -WorkingDirectory "D:\Project\Wedd\DLineBot" -WindowStyle Minimized
    Log "Watcher di-start"
} else {
    Log "Watcher sudah jalan"
}

Log "=== Morning start selesai ==="

@echo off
cd /d "%~dp0"
for /f %%D in ('powershell -NoProfile -Command "(Get-Date).DayOfWeek"') do set "DOW=%%D"
if /I "%DOW%"=="Saturday" goto weekend
if /I "%DOW%"=="Sunday" goto weekend
"%~dp0venv\Scripts\python.exe" enable_autotrade.py
powershell -NoProfile -ExecutionPolicy Bypass -Command "if (-not (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)) { Start-Process -FilePath '%~dp0venv\Scripts\python.exe' -ArgumentList 'dashboard.py' -WorkingDirectory '%~dp0' -WindowStyle Hidden -RedirectStandardOutput '%~dp0logs\dashboard.log' -RedirectStandardError '%~dp0logs\dashboard_err.log' } else { Write-Output 'dashboard sudah jalan' }"
goto :eof

:weekend
echo [scheduler] %DOW% - market tutup, bot TIDAK diaktifkan.
exit /b 0

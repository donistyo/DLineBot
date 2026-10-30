@echo off
cd /d "%~dp0"
if exist "%~dp0runtime\local_bot_off.flag" (
    echo [start_service] local_bot_off.flag ditemukan - bot TIDAK dijalankan di PC ini.
    exit /b 0
)
"%~dp0venv\Scripts\python.exe" dashboard.py

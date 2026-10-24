@echo off
cd /d "%~dp0"
"%~dp0venv\Scripts\python.exe" -u news_auto_off.py >> "%~dp0logs\news_watch.log" 2>&1


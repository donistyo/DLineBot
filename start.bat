@echo off
title DLine Dashboard
cd /d "%~dp0"
echo Starting DLineBot Dashboard...
echo.
"%~dp0venv\Scripts\python.exe" dashboard.py
pause

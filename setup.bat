@echo off
title DLineBot Setup
cd /d "%~dp0"

echo ====================================
echo   DLineBot Portable Setup
echo ====================================
echo.

:: Cek Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python tidak terinstall!
    echo Download: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Cek MT5
echo [CHECK] MetaTrader5...
if not exist "%ProgramFiles%\MetaTrader 5\terminal64.exe" (
    if not exist "%ProgramFiles(x86)%\MetaTrader 5\terminal64.exe" (
        echo [WARN] MT5 tidak ditemukan di Program Files.
        echo       Install MT5 dulu dari broker Exness.
        echo.
    )
)

:: Cek .env
echo [CHECK] .env file...
if not exist ".env" (
    echo [WARN] File .env tidak ditemukan!
    echo       Copy .env dari PC asal atau buat manual.
    echo.
)

:: Buat venv
echo [STEP 1/3] Membuat virtual environment...
if not exist "venv\" (
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Gagal buat venv
        pause
        exit /b 1
    )
    echo   OK
) else (
    echo   Sudah ada, skip.
)

:: Install dependencies
echo [STEP 2/3] Install dependencies...
call venv\Scripts\python.exe -m pip install --upgrade pip -q
call venv\Scripts\python.exe -m pip install -r requirements.txt -q
echo   OK

:: Setup desktop shortcut
echo [STEP 3/3] Membuat shortcut desktop...
call venv\Scripts\python.exe -c "
import os, sys
from pathlib import Path
desktop = Path(os.environ['USERPROFILE']) / 'Desktop'
link = desktop / 'DLine Dashboard.lnk'
target = Path(os.getcwd()) / 'start.bat'
icon = Path(os.getcwd()) / 'dline.ico'
if not link.exists():
    import pythoncom, win32com.client
    pythoncom.CoInitialize()
    shell = win32com.client.Dispatch('WScript.Shell')
    shortcut = shell.CreateShortCut(str(link))
    shortcut.TargetPath = str(target)
    shortcut.WorkingDirectory = str(target.parent)
    shortcut.Description = 'DLineBot Dashboard + Live Engine'
    if icon.exists():
        shortcut.IconLocation = str(icon)
    shortcut.Save()
    print('  Shortcut dibuat')
else:
    print('  Sudah ada, skip')
"
echo.
echo ====================================
echo   SETUP SELESAI!
echo ====================================
echo.
echo Jalankan: klik 2x "DLine Dashboard.lnk" di Desktop
echo    atau:  python dashboard.py
echo.
pause

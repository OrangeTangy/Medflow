@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3 scripts\run_local.py --receive-devices --insecure-lan %*
) else (
    python scripts\run_local.py --receive-devices --insecure-lan %*
)
if errorlevel 1 pause

@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3 scripts\run_local.py
) else (
    python scripts\run_local.py
)
if errorlevel 1 pause

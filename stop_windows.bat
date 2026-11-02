@echo off
title AI IT Operations - Stop Services
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_windows.ps1"
pause

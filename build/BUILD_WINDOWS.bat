@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Build-SelfContained-Windows.ps1"
pause

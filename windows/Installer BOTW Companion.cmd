@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Installer BOTW Companion.ps1"
if errorlevel 1 pause
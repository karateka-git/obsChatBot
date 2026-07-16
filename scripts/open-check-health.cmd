@echo off
start "obsChatBot healthcheck" powershell.exe -NoExit -ExecutionPolicy Bypass -File "%~dp0check-health.ps1"

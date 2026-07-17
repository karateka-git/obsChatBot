@echo off
start "obsChatBot dev-start" powershell.exe -NoExit -ExecutionPolicy Bypass -File "%~dp0dev-start.ps1" %*

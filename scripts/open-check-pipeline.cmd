@echo off
start "obsChatBot pipeline-smoke" powershell.exe -NoExit -ExecutionPolicy Bypass -File "%~dp0check-pipeline.ps1"

@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0swarm.ps1" %*
pause
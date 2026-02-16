@echo off
REM Wrapper script for swarm-msg.ps1
REM Allows agents to call: swarm-msg send --to Claude-2 --body "message"

powershell -ExecutionPolicy Bypass -File "%~dp0swarm-msg.ps1" %*

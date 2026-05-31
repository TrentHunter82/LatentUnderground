@echo off
title Latent Underground
echo ========================================
echo   Latent Underground - Starting...
echo ========================================
echo.

:: Repo root is this script's folder, so the launcher is location-independent.
set "ROOT=%~dp0"

:: Resolve uv (user install). Fall back to PATH if not in the default location.
set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not exist "%UV%" set "UV=uv"

:: Ensure Node/npm is reachable even in shells opened before the PATH refresh.
set "NODEDIR=%ProgramFiles%\nodejs"

:: Start backend in a new window (suppress its auto-open since we open :5173)
echo Starting backend (port 8000)...
start "LU Backend" cmd /k "cd /d "%ROOT%backend" && set LU_NO_BROWSER=1 && set LU_NO_RELOAD=1 && "%UV%" run python run.py"

:: Give backend a moment to start
timeout /t 2 /nobreak >nul

:: Start frontend dev server in a new window
echo Starting frontend (port 5173)...
start "LU Frontend" cmd /k "cd /d "%ROOT%frontend" && set "PATH=%NODEDIR%;%PATH%" && npm run dev"

:: Wait and open browser
timeout /t 3 /nobreak >nul
echo.
echo Opening browser...
start http://localhost:5173

echo.
echo ========================================
echo   Both servers running!
echo   Frontend: http://localhost:5173
echo   Backend:  http://localhost:8000
echo ========================================
echo.
echo Close the server windows to stop.
pause

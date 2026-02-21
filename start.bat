@echo off
title Latent Underground
echo ========================================
echo   Latent Underground - Starting...
echo ========================================
echo.

:: Start backend in a new window (suppress its auto-open since we open :5173)
echo Starting backend (port 8000)...
start "LU Backend" cmd /k "cd /d F:\LatentUnderground\backend && set LU_NO_BROWSER=1 && set LU_NO_RELOAD=1 && C:\Users\flipp\.local\bin\uv.exe run python run.py"

:: Give backend a moment to start
timeout /t 2 /nobreak >nul

:: Start frontend dev server in a new window
echo Starting frontend (port 5173)...
start "LU Frontend" cmd /k "cd /d F:\LatentUnderground\frontend && npm run dev"

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

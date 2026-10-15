@echo off
title FreightIQ Local Server
echo ========================================================
echo   Starting FreightIQ Frontend Server
echo   Opening: http://localhost:8000
echo ========================================================
echo.
timeout /t 1 /nobreak >nul
start http://localhost:8000
python -m http.server 8000
pause

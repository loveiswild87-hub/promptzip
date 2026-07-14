@echo off
setlocal
cd /d "%~dp0"
title PromptZip V44 Launcher
cls
echo ====================================================
echo PromptZip V44 + PromptCraft
echo ====================================================
echo.
echo This launcher will open the server window and then open your browser automatically.
echo.
echo Local URL: http://127.0.0.1:8816
echo Health URL: http://127.0.0.1:8816/healthz
echo.
echo Starting server in a separate window...
start "PromptZip V44 Server - KEEP THIS WINDOW OPEN" cmd /k "cd /d ""%~dp0"" && set PORT=8816 && python app.py"

echo Waiting for the server to start...
timeout /t 4 /nobreak >nul

echo Opening browser...
start "" "http://127.0.0.1:8816"

echo.
echo If the browser still says connection refused, wait 3 seconds and refresh.
echo Do not close the black server window named PromptZip V44 Server.
echo.
pause

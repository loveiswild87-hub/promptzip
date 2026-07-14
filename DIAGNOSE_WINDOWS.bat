@echo off
cd /d "%~dp0"
title PromptZip V44 Diagnose
cls
echo PromptZip V44 Diagnose
echo.
echo Current folder:
cd
echo.
echo Checking Python...
python --version
echo.
echo If Python version is shown above, Python is installed.
echo If not, install Python and check Add Python to PATH.
echo.
echo Checking files...
dir app.py
pause

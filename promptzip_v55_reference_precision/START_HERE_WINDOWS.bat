@echo off
title PromptCraft V48 - Motion Hero Edition
cd /d %~dp0
python -m pip install -r requirements.txt
start http://127.0.0.1:8818
python app.py
pause

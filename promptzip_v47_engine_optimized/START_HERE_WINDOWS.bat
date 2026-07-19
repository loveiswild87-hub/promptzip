@echo off
title PromptZip V46 - Genspark AI Edition
cd /d %~dp0
python -m pip install -r requirements.txt
start http://127.0.0.1:8817
python app.py
pause

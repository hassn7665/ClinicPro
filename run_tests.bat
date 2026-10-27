@echo off
chcp 65001 >nul
cd /d "%~dp0"
python tests\run_all.py
pause

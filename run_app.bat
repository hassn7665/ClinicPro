@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ===== تشغيل تطبيق Clinic Pro =====
python -m pip install -q flet==0.28.3
python make_icons.py
python main.py
pause

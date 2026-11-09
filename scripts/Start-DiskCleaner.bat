@echo off
chcp 65001 >nul
title Antigravity Disk Cleaner — Live Dashboard

echo =====================================================================
echo                Antigravity Disk Cleaner (Windows)
echo =====================================================================
echo.
echo [1/2] Запуск сканирования дисков и мусора...
python "%~dp0..\skills\disk-cleaner\scripts\disk_cleaner_core.py" --scan --html-out "%~dp0..\ui\disk_cleaner_dashboard.html" --compact-out "%~dp0..\ui\disk_cleaner_compact.html"

echo.
echo [2/2] Запуск интерактивного локального дашборда на http://localhost:8765...
start http://localhost:8765
python "%~dp0..\skills\disk-cleaner\scripts\disk_cleaner_core.py" --serve --port 8765
pause

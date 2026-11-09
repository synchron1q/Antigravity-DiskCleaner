@echo off
chcp 65001 >nul
title Antigravity Disk Cleaner - Удаление выбранных программ

:: Проверка прав администратора
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [i] Требуются права Администратора для удаления программ из Program Files.
    echo [i] Запрашиваем UAC повышение привилегий...
    powershell -NoProfile -Command "Start-Process cmd -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

echo =====================================================================
echo       Antigravity Disk Cleaner - Удаление одобренных программ
echo =====================================================================
echo.
echo Будут удалены только программы, разрешённые пользователем:
echo   - AutoCAD 2026 (~3.65 ГБ)
echo   - Android SDK (~0.83 ГБ)
echo   - 1C:Предприятие Тонкий клиент (~1.0 ГБ)
echo   - Paint.NET (~0.61 ГБ)
echo   - OBS Studio (~0.46 ГБ)
echo   - Microsoft SQL Server LocalDB (~0.31 ГБ)
echo.
echo Внимание: Visual Studio, .NET SDK, VS Code, Antigravity, Office,
echo скриншоты и курсовая работа НЕ ЗАТРАГИВАЮТСЯ!
echo.
echo Нажмите любую клавишу для запуска удаления (или закройте окно для отмены)...
pause >nul

echo.
echo [1/6] Удаление OBS Studio...
if exist "C:\Program Files\obs-studio\uninstall.exe" (
    "C:\Program Files\obs-studio\uninstall.exe" /S
    timeout /t 3 >nul
    if exist "C:\Program Files\obs-studio" rmdir /s /q "C:\Program Files\obs-studio" 2>nul
    echo   -> Готово!
) else (
    echo   -> Не найдено, пропуск.
)

echo.
echo [2/6] Удаление Paint.NET...
MsiExec.exe /X{B33D3774-736A-43FD-BE83-76733BE4CB10} /qn /norestart
timeout /t 3 >nul
if exist "C:\Program Files\paint.net" rmdir /s /q "C:\Program Files\paint.net" 2>nul
echo   -> Готово!

echo.
echo [3/6] Удаление 1C:Предприятие Тонкий клиент...
MsiExec.exe /X{7C5BD957-D3F4-1B01-E640-803C8DB30FAB} /qn /norestart
MsiExec.exe /X{1ED2949E-8F53-F893-9B62-A2C70252C968} /qn /norestart
timeout /t 3 >nul
if exist "C:\Program Files\1cv8" rmdir /s /q "C:\Program Files\1cv8" 2>nul
if exist "C:\Program Files (x86)\1cv8" rmdir /s /q "C:\Program Files (x86)\1cv8" 2>nul
echo   -> Готово!

echo.
echo [4/6] Удаление AutoCAD 2026...
if exist "C:\Program Files\Autodesk\AdODIS\V1\Installer.exe" (
    "C:\Program Files\Autodesk\AdODIS\V1\Installer.exe" -i uninstall --trigger_point system -m "C:\ProgramData\Autodesk\ODIS\metadata\{E017312B-20E7-38A1-9F80-9B662193E90F}\bundleManifest.xml" -x "C:\ProgramData\Autodesk\ODIS\metadata\{E017312B-20E7-38A1-9F80-9B662193E90F}\SetupRes\manifest.xsd" -q
    timeout /t 5 >nul
)
if exist "C:\Program Files\Autodesk\AutoCAD 2026" rmdir /s /q "C:\Program Files\Autodesk\AutoCAD 2026" 2>nul
if exist "C:\ProgramData\Autodesk" rmdir /s /q "C:\ProgramData\Autodesk" 2>nul
echo   -> Готово!

echo.
echo [5/6] Удаление Android SDK...
if exist "C:\Program Files (x86)\Android" (
    rmdir /s /q "C:\Program Files (x86)\Android" 2>nul
    echo   -> Готово!
) else (
    echo   -> Не найдено, пропуск.
)

echo.
echo [6/6] Удаление SQL Server LocalDB...
MsiExec.exe /X{568A72D3-8666-4F65-ABB5-D55BD975ADA7} /qn /norestart
timeout /t 3 >nul
echo   -> Готово!

echo.
echo =====================================================================
echo Очистка завершена! Освобождено ещё до ~6.9 ГБ места.
echo =====================================================================
echo.
pause
